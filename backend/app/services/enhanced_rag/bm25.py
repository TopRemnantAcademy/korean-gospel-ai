"""Enhanced RAG — 경량 in-memory BM25 (키워드/희소 검색).

목적:
- 하이브리드 검색의 'keyword' 축 담당 (Qdrant sparse BM42 에 의존하지 않음)
- 증분 문서 갱신 지원: add(doc_id, tokens) / remove(doc_id)
- 의존성 최소 (numpy 불필요), 순수 파이썬

토크나이저:
- 라틴어/숫자: 공백+구두점 분리 후 소문자
- CJK(한/중/일): 문자 unigram + bigram (형태소 분석기 없이 견고하게 동작)
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

_CJK = re.compile(r"[一-鿿가-힣぀-ヿ]")
_LATIN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    tokens: list[str] = []

    # 라틴/숫자 토큰
    tokens.extend(_LATIN.findall(lowered))

    # CJK: 연속 CJK 구간을 unigram+bigram 으로 확장
    for seg in re.findall(r"[一-鿿가-힣぀-ヿ]+", lowered):
        for i in range(len(seg)):
            tokens.append(seg[i])                      # unigram
            if i + 1 < len(seg):
                tokens.append(seg[i : i + 2])          # bigram
    return tokens


class SimpleBM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: dict[str, list[str]] = {}          # doc_id -> tokens
        self._tf: dict[str, Counter] = {}              # doc_id -> Term Frequency (Counter)
        self._df: dict[str, int] = defaultdict(int)    # term -> 문서빈도
        self._doc_count = 0
        self._avgdl = 0.0
        self._total_len = 0

    # ── 증분 갱신 ──
    def add(self, doc_id: str, tokens: list[str]) -> None:
        if doc_id in self._docs:
            self.remove(doc_id)
        toks = list(tokens)
        self._docs[doc_id] = toks
        self._tf[doc_id] = Counter(toks)               # TF dict 사전 계산
        seen = set()
        for t in toks:
            if t not in seen:
                self._df[t] += 1
                seen.add(t)
        self._doc_count += 1
        self._total_len += len(toks)
        self._avgdl = (self._total_len / self._doc_count) if self._doc_count else 0.0

    def remove(self, doc_id: str) -> None:
        toks = self._docs.pop(doc_id, None)
        self._tf.pop(doc_id, None)  # TF dict도 함께 제거
        if toks is None:
            return
        seen = set()
        for t in toks:
            if t not in seen:
                self._df[t] = max(0, self._df[t] - 1)
                if self._df[t] == 0:
                    self._df.pop(t, None)
                seen.add(t)
        self._doc_count -= 1
        self._total_len -= len(toks)
        self._avgdl = (self._total_len / self._doc_count) if self._doc_count else 0.0

    def __contains__(self, doc_id: str) -> bool:
        return doc_id in self._docs

    def __len__(self) -> int:
        return len(self._docs)

    # ── 검색 ──
    def search(self, query_tokens: list[str], top_k: int = 20) -> list[tuple[str, float]]:
        if not self._docs or not query_tokens:
            return []
        N = self._doc_count
        avgdl = self._avgdl or 1.0

        # 쿼리 term 별 (idf, tf per doc)
        scores: dict[str, float] = defaultdict(float)
        for q in query_tokens:
            df = self._df.get(q, 0)
            if df == 0:
                continue
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            for doc_id, toks in self._docs.items():
                tf = self._tf[doc_id].get(q, 0)  # O(1) lookup instead of O(n) count
                if tf == 0:
                    continue
                dl = len(toks)
                denom = tf + self.k1 * (1 - self.b + self.b * dl / avgdl)
                scores[doc_id] += idf * (tf * (self.k1 + 1)) / denom

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return ranked[:top_k]
