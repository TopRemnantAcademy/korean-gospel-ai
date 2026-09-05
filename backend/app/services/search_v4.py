"""검색 엔진.

주요 기능:
1. MMR 기반 결과 다양성 조정
2. 컨텍스트 압축
3. 신뢰도 점수 계산
4. 검색 explain 메타데이터 생성
5. dense/sparse/rerank 점수 기반 결과 보강
"""
from __future__ import annotations
import asyncio
import logging
import re
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# rerank 점수가 이 값을 넘으면 "질문-답변 관계가 밀접"으로 판단
RERANK_CONFIDENCE_THRESHOLD = 0.6

# ── 성능(OPT-C): 정규식 사전 컴파일 + 불용어 set 모듈레벨 hoist ──────────────
# _extract_keywords / _split_sentences 는 compress() 에서 쿼리 1회 + 문장마다 호출된다.
# 매 호출 stopwords set 리터럴 재생성 및 정규식 인라인 컴파일을 제거한다 (동작 동일).
_WORD_RE = re.compile(r'[가-힣a-zA-Z]{2,}')
# 한국어 문장 분리는 chunker 의 분리기를 단일 소스로 사용 (영문 `[.?!]\s+` 규칙은
# 한국어 종결어미를 분리하지 못해 압축 품질을 떨어뜨림).
from .chunker import split_korean_sentences as _split_korean_sentences  # noqa: E402
_STOPWORDS = frozenset({
    "합니다", "있습니다", "입니다", "하는", "그리고", "하지만", "그러나",
    "또한", "매우", "정말", "우리", "여러", "여러분", "당신", "이것", "저것",
})



@dataclass
class ContextChunk:
    """압축된 컨텍스트 청크"""
    original_text: str
    compressed_text: str
    relevant_sentences: list[str]
    confidence: float  # 0~1: 이 청크가 얼마나 질문과 관련있는가


@dataclass
class SearchExplanation:
    """검색 결과 설명"""
    query_match_score: float  # 쿼리 용어 일치 점수
    semantic_similarity: float  # 의미적 유사도
    relevance_keywords: list[str]  # 일치한 핵심 키워드
    diversity_contribution: float  # 다양성 기여도 (다른 결과와 얼마나 다른지)
    overall_reason: str  # 종합 설명 문자열


@dataclass
class EnrichedSearchResult:
    """고급 검색 결과 - 모든 메타데이터와 압축 컨텍스트 포함"""
    id: str
    text: str  # 원문 (옵션: 너무 길면 생략)
    compressed_context: Optional[ContextChunk]  # 압축된 컨텍스트
    final_score: float  # 최종 점수 (0~1)
    raw_dense_score: float  # dense 검색 점수
    raw_sparse_score: Optional[float]  # sparse 검색 점수 (RRF fusion 후 None 가능)
    rerank_score: float  # rerank 점수
    source_title: str  # 출처 문서 제목
    source_type: str  # 문서 타입 (성경/설교/교리/간증 등)
    reliability_score: float  # 출처 신뢰도 (0~1)
    explanation: Optional[SearchExplanation]  # 검색 설명
    metadata: dict  # 원본 메타데이터


class MMRRanking:
    """Maximal Marginal Relevance 랭킹.

    관련도와 다양성의 균형을 맞춰서:
    - 1등과 2등이 거의 같은 내용이면, 3등의 다른 내용을 올려줌
    - 다양한 관점의 결과를 보여주는 효과
    """

    def __init__(self, lambda_param: float = 0.7):
        """
        Args:
            lambda_param: 1.0에 가까울수록 관련도 우선, 0.0에 가까울수록 다양성 우선
        """
        self.lambda_param = lambda_param

    @staticmethod
    def _text_overlap_score(text1: str, text2: str) -> float:
        """두 텍스트의 키워드 중복도 (0~1)"""
        # 간단한 bigram 기반 유사도
        words1 = set(re.findall(r'[가-힣a-zA-Z]{2,}', text1))
        words2 = set(re.findall(r'[가-힣a-zA-Z]{2,}', text2))

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0

    def rerank_for_diversity(
        self,
        items: list[dict],  # {"id": str, "text": str, "score": float}
        top_k: int = 10,
    ) -> list[dict]:
        """MMR 기반 다양성 증강 리랭킹. word set precompute로 O(k²) 중복 계산 제거."""
        if len(items) <= 1:
            return items

        # ✅ 최적화: 모든 텍스트의 word set을 미리 계산 — 반복 regex 제거
        precomputed_sets = [
            set(re.findall(r'[가-힣a-zA-Z]{2,}', item["text"]))
            for item in items
        ]

        selected = []
        selected_sets = []
        # (원본 인덱스, item) — O(n²) items.index() 호출 제거
        remaining = [(i, items[i]) for i in range(len(items))]
        scores = [float(item.get("score", 0.0)) for item in items]
        min_score = min(scores)
        max_score = max(scores)
        score_span = max_score - min_score

        while len(selected) < min(top_k, len(items)):
            best_score = -1.0
            best_idx = 0
            best_orig_idx = 0

            for i, (orig_idx, candidate) in enumerate(remaining):
                raw_relevance = float(candidate.get("score", 0.0))
                relevance = (
                    (raw_relevance - min_score) / score_span
                    if score_span > 1e-9
                    else 1.0
                )

                # 이미 선택된 것들과의 중복도 — 미리 계산된 word set 사용
                diversity_penalty = 0.0
                if selected_sets:
                    cand_set = precomputed_sets[orig_idx]
                    overlaps = [
                        len(cand_set & sel_set) / max(len(cand_set | sel_set), 1)
                        for sel_set in selected_sets
                    ]
                    diversity_penalty = max(overlaps)

                # MMR 점수 계산
                mmr_score = (
                    self.lambda_param * relevance -
                    (1.0 - self.lambda_param) * diversity_penalty
                )

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i
                    best_orig_idx = orig_idx

            _, chosen = remaining.pop(best_idx)
            selected.append(chosen)
            selected_sets.append(precomputed_sets[best_orig_idx])

        return selected


class ContextCompressor:
    """LLM 없이 고속 컨텍스트 압축 - 쿼리 관련 구문만 추출.

    키워드 기반으로 질문과 직접 관련 있는 문장만 골라냅니다.
    컨텍스트 길이를 50~70% 줄이면서 핵심 정보는 유지.
    """

    def __init__(self, min_sentences: int = 2, max_sentences: int = 5):
        self.min_sentences = min_sentences
        self.max_sentences = max_sentences

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """문장 분리 (한국어 특화 — chunker 분리기 재사용)"""
        sentences = _split_korean_sentences(text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        return sentences

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """텍스트에서 중요 키워드 추출"""
        # 2글자 이상의 한글/영어 단어
        words = _WORD_RE.findall(text)
        # 고빈도 불용어 필터링 (모듈레벨 _STOPWORDS 재사용)
        return {w for w in words if w not in _STOPWORDS and len(w) <= 15}

    def compress(
        self,
        query: str,
        passage_text: str,
        min_confidence: float = 0.1,
    ) -> ContextChunk:
        """쿼리와 관련된 구문만 추출하여 압축"""
        query_keywords = self._extract_keywords(query)
        sentences = self._split_sentences(passage_text)

        if not sentences:
            return ContextChunk(
                original_text=passage_text,
                compressed_text=passage_text[:200],
                relevant_sentences=[passage_text[:200]],
                confidence=0.5,
            )

        # 각 문장의 관련도 점수
        scored_sentences = []
        for sent in sentences:
            sent_keywords = self._extract_keywords(sent)
            overlap = len(query_keywords & sent_keywords)
            # 긴 문장 보정 (짧은 문장은 유리하므로)
            score = overlap / (len(sent_keywords) + 5)
            scored_sentences.append((score, sent))

        # 관련도 순으로 정렬
        scored_sentences.sort(key=lambda x: -x[0])

        # 관련 있는 문장 선택
        selected = []
        total_confidence = 0.0
        for score, sent in scored_sentences:
            if score > 0 or len(selected) < self.min_sentences:
                selected.append(sent)
                total_confidence += score
            if len(selected) >= self.max_sentences:
                break

        avg_confidence = total_confidence / len(selected) if selected else 0.0

        # 순서 원래대로 복원
        original_order_sentences = []
        for sent in sentences:
            if sent in selected:
                original_order_sentences.append(sent)

        compressed = ". ".join(original_order_sentences) + "."

        return ContextChunk(
            original_text=passage_text,
            compressed_text=compressed,
            relevant_sentences=original_order_sentences,
            confidence=min(1.0, avg_confidence * 2),
        )


class ReliabilityScorer:
    """출처 신뢰도 점수 계산기"""

    # 타입별 기본 신뢰도
    TYPE_BASE_SCORES = {
        "bible": 1.00,  # 성경은 최고 신뢰도
        "doctrine": 0.95,  # 교리 문서
        "creed": 0.98,  # 신조
        "sermon": 0.85,  # 설교
        "testimony": 0.80,  # 간증
        "book": 0.90,  # 출판된 책
        "article": 0.85,  # 글/기사
        "unknown": 0.70,  # 미분류
    }

    @classmethod
    def score(cls, doc_type: str, metadata: dict) -> float:
        base_score = cls.TYPE_BASE_SCORES.get(doc_type, 0.70)

        # 저자 신뢰도 가산 (알려진 목사/신학자)
        author = metadata.get("author", "")
        known_authors = {"박형준", "마틴 로이드 존스", "칼빈", "루터", "벌직거", "스펄전"}
        if any(known in author for known in known_authors):
            base_score += 0.05

        # 출판일 가산: 최근 문서
        year = metadata.get("year")
        if year and isinstance(year, int) and year > 2000:
            base_score += 0.02

        return min(1.0, base_score)


class SearchExplainer:
    """검색 결과 설명 생성기"""

    @classmethod
    def explain(
        cls,
        query: str,
        result: dict,
        dense_score: float,
        sparse_score: float,
        rerank_score: float,
    ) -> SearchExplanation:
        """왜 이 결과가 나왔는지 설명 생성"""
        query_words = set(re.findall(r'[가-힣a-zA-Z]{2,}', query))
        result_words = set(re.findall(r'[가-힣a-zA-Z]{2,}', result["text"]))
        matched = list(query_words & result_words)

        # 키워드 일치 점수
        keyword_match = len(matched) / len(query_words) if query_words else 0.0

        # 의미 유사도 (dense 점수 활용)
        semantic_sim = dense_score

        # 다양성 기여도 (첫 문서는 1.0, 나머지는 상대적)
        diversity = 1.0 / (result.get("rank", 1) + 1)

        # 종합 이유 문장
        reasons = []
        if matched:
            reasons.append(f"'{', '.join(matched[:3])}' 등 키워드 일치")
        if semantic_sim > 0.7:
            reasons.append("의미적 내용이 유사")
        if rerank_score > RERANK_CONFIDENCE_THRESHOLD:
            reasons.append("질문-답변 관계가 밀접")

        overall = ", ".join(reasons) if reasons else "의미적 유사성 기반 검색"

        return SearchExplanation(
            query_match_score=keyword_match,
            semantic_similarity=semantic_sim,
            relevance_keywords=matched[:5],
            diversity_contribution=diversity,
            overall_reason=overall,
        )


class AdvancedSearchEngine:
    """검색 엔진 통합.

    파이프라인:
    1. 다중 쿼리 확장 (원본 + HyDE + 관점 변형)
    2. 병렬 검색 (dense + sparse)
    3. RRF 퓨전
    4. Cross-Encoder rerank
    5. MMR 다양성 조정
    6. 컨텍스트 압축
    7. 신뢰도 점수 + Explain 추가
    """

    def __init__(self, retriever):
        self.retriever = retriever
        self.embedder_name = getattr(retriever, "embedder_name", "unknown")
        self.mmr = MMRRanking(lambda_param=0.7)
        self.compressor = ContextCompressor()

    async def search(
        self,
        query: str,
        top_k: int = 10,
        enable_mmr: bool = True,
        enable_compression: bool = True,
        enable_explain: bool = True,
        profile: Optional[dict] = None,
    ) -> list[EnrichedSearchResult]:
        """검색 결과를 보강해서 반환"""
        # 1. 기본 검색 실행
        # 최적화: retriever 가 내부적으로 recall_k 를 top_k 비례로 축소하므로,
        # 여기서 요청하는 top_k 도 과도하게 키우지 않는다.
        # 채팅(top_k=5) → retriever 에는 rerank_top_n=5 만 요청해
        # 내부 recall/rerank 비용을 줄인다. (기존 top_k*4=20 → top_k+여유)
        try:
            base_results = await self.retriever.retrieve(
                query, top_k=top_k, rerank_top_n=max(top_k, 5), profile=profile
            )
        except Exception:
            logger.exception("[search_v4] retriever.retrieve 실패")
            return []

        # 2. MMR 다양성 랭킹 (옵션)
        if enable_mmr and len(base_results) >= 3:
            mmr_items = [
                {"id": r.id, "text": r.text, "score": r.score}
                for r in base_results
            ]
            mmr_reranked = self.mmr.rerank_for_diversity(mmr_items, top_k=top_k)
            # 원본 정보 다시 붙이기
            id_to_result = {r.id: r for r in base_results}
            final_results = [id_to_result[r["id"]] for r in mmr_reranked]
        else:
            final_results = base_results[:top_k]

        # 3. 컨텍스트 압축 + 메타데이터 풍부화 (병렬 — asyncio.gather)
        async def _enrich_one(rank, r):
            compressed = (
                await asyncio.to_thread(self.compressor.compress, query, r.text)
                if enable_compression
                else None
            )
            source_type = r.metadata.get("doc_type", "unknown")
            reliability = ReliabilityScorer.score(source_type, r.metadata)
            explanation = None
            if enable_explain:
                explanation = SearchExplainer.explain(
                    query=query,
                    result={"text": r.text, "rank": rank},
                    dense_score=r.rrf_score,
                    sparse_score=None,
                    rerank_score=r.score,
                )
            return EnrichedSearchResult(
                id=r.id, text=r.text,
                compressed_context=compressed,
                final_score=r.score,
                raw_dense_score=r.rrf_score,
                raw_sparse_score=None,
                rerank_score=r.score,
                source_title=r.metadata.get("title", "제목 없음"),
                source_type=source_type,
                reliability_score=reliability,
                explanation=explanation,
                metadata=r.metadata,
            )

        enriched = await asyncio.gather(*[
            _enrich_one(rank, r) for rank, r in enumerate(final_results)
        ])

        return enriched


_search_engine_cache: dict[tuple[str, str] | tuple[str, int], AdvancedSearchEngine] = {}
_search_engine_lock = threading.RLock()


def get_search_engine(retriever) -> AdvancedSearchEngine:
    """고급 검색 엔진 반환"""
    embedder_name = getattr(retriever, "embedder_name", None) or ""
    collection = getattr(getattr(retriever, "store", None), "collection", None) or getattr(retriever, "collection", None) or ""
    key = (embedder_name, collection) if embedder_name or collection else ("id", id(retriever))
    if key in _search_engine_cache:
        return _search_engine_cache[key]
    with _search_engine_lock:
        if key not in _search_engine_cache:
            _search_engine_cache[key] = AdvancedSearchEngine(retriever)
        return _search_engine_cache[key]


