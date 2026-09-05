"""Enhanced RAG — 평가 지표.

검색 정확도 (라벨 필요, 순수 계산):
- Hit@k, Precision@k, Recall@k, MRR, nDCG@k

응답 품질 (LLM-as-judge, 선택적):
- faithfulness / answer_relevancy / context_precision / context_recall (0~1)
- lexical_overlap: 참조 답변 대비 토큰 F1 (제공 시)
"""
from __future__ import annotations

import json
import logging
import math

from ..llm.base import Message
from ..llm.fallback import chat_with_fallback

from .bm25 import tokenize
from .types import GenerationMetrics, RetrievalMetrics

logger = logging.getLogger(__name__)


class RAGEvaluator:
    # ──────────────────────────────────────────────────────────────
    # 검색 지표 (순수 계산)
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def eval_retrieval(
        cases: list[dict],
        k: int,
    ) -> RetrievalMetrics:
        """cases: [{"retrieved": [RetrievedChunk], "relevant": set[str],
                    "relevant_is_doc": bool}, ...]"""
        n = len(cases)
        if n == 0:
            return RetrievalMetrics(
                queries=0, k=k, hit_rate=0.0, precision_at_k=0.0,
                recall_at_k=0.0, mrr=0.0, ndcg_at_k=0.0,
            )

        hit = prec = rec = mrr = ndcg = 0.0
        for case in cases:
            retrieved = case.get("retrieved", []) or []
            rel = case.get("relevant") or set()
            is_doc = case.get("relevant_is_doc", False)

            rids = [c.doc_id if is_doc else c.chunk_id for c in retrieved]
            topk = rids[:k]
            hits = [x for x in topk if x in rel]

            hit += 1.0 if hits else 0.0
            prec += (len(hits) / k) if k else 0.0
            # 관련 문서가 정의되지 않은 케이스는 recall 을 0 으로 처리(과대평가 방지).
            rec += (len(hits) / len(rel)) if rel else 0.0

            rank = next((i + 1 for i, x in enumerate(rids) if x in rel), None)
            mrr += (1.0 / rank) if rank else 0.0

            rel_bin = [1.0 if x in rel else 0.0 for x in rids[:k]]
            dcg = sum(rv / math.log2(i + 2) for i, rv in enumerate(rel_bin))
            ideal = sorted(rel_bin, reverse=True)
            idcg = sum(rv / math.log2(i + 2) for i, rv in enumerate(ideal))
            # 관련 문서를 전혀 검색하지 못한 경우(또는 라벨 없음) nDCG=0.
            # idcg>0 일 때만(상위 k 에 관련 문서가 존재할 때만) 비율 산정.
            ndcg += (dcg / idcg) if idcg > 0 else 0.0

        return RetrievalMetrics(
            queries=n,
            k=k,
            hit_rate=hit / n,
            precision_at_k=prec / n,
            recall_at_k=rec / n,
            mrr=mrr / n,
            ndcg_at_k=ndcg / n,
        )

    # ──────────────────────────────────────────────────────────────
    # 응답 품질 지표 (LLM-as-judge)
    # ──────────────────────────────────────────────────────────────
    def eval_generation(
        self,
        pairs: list[dict],
        config=None,
    ) -> GenerationMetrics:
        """pairs: [{"query": str, "answer": str, "contexts": list[str],
                    "reference": str|None}, ...]"""
        n = len(pairs)
        if n == 0:
            return GenerationMetrics(
                samples=0, faithfulness=0.0, answer_relevancy=0.0,
                context_precision=0.0, context_recall=0.0,
                lexical_overlap=0.0, avg_generation_time_ms=0.0,
            )

        f_sum = a_sum = cp_sum = cr_sum = lex_sum = 0.0
        has_ref = any(p.get("reference") for p in pairs)

        for p in pairs:
            m = self._judge(p.get("query", ""), p.get("answer", ""), p.get("contexts", []))
            f_sum += m["faithfulness"]
            a_sum += m["answer_relevancy"]
            cp_sum += m["context_precision"]
            cr_sum += m["context_recall"]
            ref = p.get("reference")
            if ref:
                lex_sum += self._lexical_f1(p.get("answer", ""), ref)

        return GenerationMetrics(
            samples=n,
            faithfulness=f_sum / n,
            answer_relevancy=a_sum / n,
            context_precision=cp_sum / n,
            context_recall=cr_sum / n,
            lexical_overlap=(lex_sum / n) if has_ref else 0.0,
            avg_generation_time_ms=0.0,
        )

    def _judge(self, query: str, answer: str, contexts: list[str]) -> dict:
        ctx = "\n\n".join(f"[{i+1}] {c[:600]}" for i, c in enumerate(contexts))
        system = (
            "You are an evaluation judge. Given a question, an answer, and retrieved context, "
            "score the answer on four 0.0-1.0 dimensions. Respond ONLY with JSON: "
            '{"faithfulness": <0-1>, "answer_relevancy": <0-1>, '
            '"context_precision": <0-1>, "context_recall": <0-1>}. No prose.'
        )
        user = (
            f"QUESTION: {query}\n\nANSWER: {answer}\n\nCONTEXT:\n{ctx}"
        )
        try:
            resp, _, _ = chat_with_fallback(
                [Message(role="user", content=user)],
                temperature=0.0,
                max_tokens=300,
                system=system,
            )
            data = json.loads(resp.text.strip())
            return {
                "faithfulness": float(data.get("faithfulness", 0.0)),
                "answer_relevancy": float(data.get("answer_relevancy", 0.0)),
                "context_precision": float(data.get("context_precision", 0.0)),
                "context_recall": float(data.get("context_recall", 0.0)),
            }
        except Exception as e:
            logger.warning("[rag-eval] LLM judge 실패: %s", e)
            return {
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": 0.0,
                "context_recall": 0.0,
            }

    @staticmethod
    def _lexical_f1(a: str, b: str) -> float:
        ta, tb = set(tokenize(a)), set(tokenize(b))
        if not ta or not tb:
            return 0.0
        inter = ta & tb
        if not inter:
            return 0.0
        prec = len(inter) / len(ta)
        rec = len(inter) / len(tb)
        return 2 * prec * rec / (prec + rec)
