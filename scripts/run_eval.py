"""평가 하네스 러너 (Wave 2단계).

EvalQuestion(active) 를 실행해 EvalRun 을 기록하고 요약을 출력한다.

분류:
- crisis / safety_negative : 결정적 위기 체크 (오프라인, CI 게이트 100%)
- factual                  : 검색 지표 Hit@k/MRR/nDCG (vector store 필요)
- salvation / style        : --live 플래그 시 Live 파이프라인 + LLM-judge (미지정 시 skip)

게이트 정책:
- crisis/safety_negative 중 passed != True 인 문항이 하나라도 있으면 exit 1 (CI 실패)
- 그 외 카테고리는 게이트에 영향을 주지 않음(정보 제공)

실행:
    cd <repo> && python scripts/run_eval.py
    python scripts/run_eval.py --category crisis          # 특정 카테고리만
    python scripts/run_eval.py --live                      # salvation/style 도 실행
    python scripts/run_eval.py --k 5 --gate-threshold 0.5
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import uuid

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backend")
# 주의: REPO 루트의 app.py 가 backend/app 패키지를 가리지 않도록 BACKEND 만 경로에 추가
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("run_eval")

from app.db import init_db, get_session_immediate  # noqa: E402
from app.models.orm import EvalQuestion, EvalRun  # noqa: E402
from app.services.eval_service import (  # noqa: E402
    crisis_bypass_check,
    retrieval_metrics,
    profile_boost_self_test,
)

# 위기 게이트로 취급할 카테고리
CRISIS_GATE_CATEGORIES = ("crisis", "safety_negative")


def _run_crisis_question(q: EvalQuestion, run_id: str, session) -> EvalRun:
    t0 = time.time()
    expected = bool(q.expected_crisis_bypass)
    res = crisis_bypass_check(q.question, target_lang=q.lang or "ko", expected_bypass=expected)
    elapsed = int((time.time() - t0) * 1000)
    log.info(
        "  [%s] triggered=%s hotline=%s passed=%s",
        q.category, res.triggered, res.hotline_present, res.passed,
    )
    return EvalRun(
        run_id=run_id,
        question_id=q.id,
        category=q.category,
        answer=res.response,
        retrieved_ids=[],
        crisis_bypass_triggered=res.triggered,
        detected_risk_level=res.crisis_level,
        passed=res.passed,
        model="deterministic",
        elapsed_ms=elapsed,
    )


def _run_factual_question(q: EvalQuestion, run_id: str, session, retriever, k: int) -> EvalRun:
    t0 = time.time()
    try:
        items = retriever.retrieve(q.question, top_k=k)
        metrics = retrieval_metrics(items, q.expected_doc_ids or [], k=k)
        hit = metrics.get("hit_at_k")
        passed = (hit or 0.0) >= GATE_THRESHOLD
        note = metrics.get("note")
        log.info(
            "  [factual] hit@%d=%.2f mrr=%.2f ndcg=%.2f passed=%s%s",
            k, hit or 0, metrics.get("mrr") or 0, metrics.get("ndcg_at_k") or 0,
            passed, f" ({note})" if note else "",
        )
        return EvalRun(
            run_id=run_id,
            question_id=q.id,
            category=q.category,
            retrieved_ids=[str(x) for x in (q.expected_doc_ids or [])],
            hit_at_k=hit,
            mrr=metrics.get("mrr"),
            ndcg_at_k=metrics.get("ndcg_at_k"),
            passed=passed,
            model="retriever",
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    except Exception as e:
        log.warning("  [factual] 검색 실패 — skip: %s", e)
        return EvalRun(
            run_id=run_id,
            question_id=q.id,
            category=q.category,
            passed=None,
            model="retriever",
            elapsed_ms=int((time.time() - t0) * 1000),
            judge_verdict=f"skipped: {e}",
        )


def _run_live_question(q: EvalQuestion, run_id: str, k: int) -> EvalRun:
    """--live: Live 채팅 파이프라인 호출 + LLM-judge (무거움, 선택적)."""
    t0 = time.time()
    from app.api.chat_pipeline import detect_crisis_bypass, build_crisis_response  # noqa: E402
    try:
        from app.services.retriever import get_retriever  # noqa: E402
        items = get_retriever().retrieve(q.question, top_k=k)
        retrieved_ids = [str(x) for x in (q.expected_doc_ids or [])]
        metrics = retrieval_metrics(items, q.expected_doc_ids or [], k=k)
    except Exception as e:
        log.warning("  [%s] live 검색 실패: %s", q.category, e)
        return EvalRun(run_id=run_id, question_id=q.id, category=q.category,
                       passed=None, model="live", judge_verdict=f"retrieve-skip: {e}",
                       elapsed_ms=int((time.time() - t0) * 1000))
    # LLM-judge (응답 생성은 별도 구현 필요 — 여기선 검색 지표 + 결정적 위기만 기록)
    bypass, assess = detect_crisis_bypass(q.question, _dummy_classification(q.expected_risk_level))
    answer = build_crisis_response(assess, target_lang=q.lang or "ko") if bypass else ""
    passed = None
    log.info("  [%s] live hit@%d=%.2f crisis_bypass=%s", q.category, k,
             metrics.get("hit_at_k") or 0, bypass)
    return EvalRun(
        run_id=run_id,
        question_id=q.id,
        category=q.category,
        answer=answer,
        retrieved_ids=retrieved_ids,
        hit_at_k=metrics.get("hit_at_k"),
        mrr=metrics.get("mrr"),
        ndcg_at_k=metrics.get("ndcg_at_k"),
        crisis_bypass_triggered=bypass,
        passed=passed,
        model="live",
        elapsed_ms=int((time.time() - t0) * 1000),
    )


def _dummy_classification(risk_level_value: str | None):
    """Live 모드에서 위기 판정용 최소 분류 객체 (risk_level 만 보유)."""
    from app.models.schemas import RiskLevel

    class _C:
        pass

    c = _C()
    try:
        c.risk_level = RiskLevel(risk_level_value) if risk_level_value else RiskLevel.low
    except Exception:
        c.risk_level = RiskLevel.low
    return c


def _run_profile_boost_self_test() -> int:
    """Wave C: 프로필 부스트 이식 검증 (오프라인 결정적). 실패 건수 반환.

    RAG/DB 불필요 — 매트릭스 값과 다단계 누적 로직을 결정적으로 검증한다.
    """
    results = profile_boost_self_test()
    fails = 0
    log.info("── profile_boost self-test ──")
    for r in results:
        ok = r.passed
        fails += 0 if ok else 1
        log.info(
            "  %s boost=%.3f expected=%.3f | %s",
            "OK  " if ok else "FAIL", r.boost, r.expected, r.note,
        )
    log.info("profile_boost self-test 실패: %d / %d", fails, len(results))
    return fails


def main() -> int:
    global GATE_THRESHOLD
    ap = argparse.ArgumentParser(description="Gospel AI 평가 하네스 러너")
    ap.add_argument("--category", default=None, help="특정 카테고리만 실행")
    ap.add_argument("--k", type=int, default=5, help="검색 지표 상위 k")
    ap.add_argument("--gate-threshold", type=float, default=0.5,
                    help="factual 통과 Hit@k 임계값")
    ap.add_argument("--live", action="store_true",
                    help="salvation/style 도 Live 파이프라인+judge 로 실행")
    args = ap.parse_args()
    GATE_THRESHOLD = args.gate_threshold

    # Wave C 오프라인 결정적 게이트 (DB/vector store 불필요)
    pb_fails = _run_profile_boost_self_test()
    if pb_fails > 0:
        log.error("❌ profile_boost self-test 실패 — CI 실패 (exit 1)")
        return 1

    init_db()
    run_id = uuid.uuid4().hex[:12]
    log.info("run_id=%s 시작", run_id)

    retriever = None
    if not args.category or args.category == "factual" or args.live:
        try:
            from app.services.retriever import get_retriever
            retriever = get_retriever()
            log.info("retriever 준비 완료")
        except Exception as e:
            log.warning("retriever 초기화 실패(factual/live 건너뜀): %s", e)

    with get_session_immediate() as s:
        q = s.query(EvalQuestion).filter(EvalQuestion.active.is_(True))
        if args.category:
            q = q.filter(EvalQuestion.category == args.category)
        questions = q.order_by(EvalQuestion.category, EvalQuestion.id).all()

        runs: list[EvalRun] = []
        crisis_fail = 0
        for qn in questions:
            log.info("[%s] %s", qn.category, qn.question[:40])
            if qn.category in CRISIS_GATE_CATEGORIES:
                r = _run_crisis_question(qn, run_id, s)
                if not r.passed:
                    crisis_fail += 1
            elif qn.category == "factual":
                r = _run_factual_question(qn, run_id, s, retriever, args.k) if retriever \
                    else EvalRun(run_id=run_id, question_id=qn.id, category=qn.category,
                                 passed=None, model="retriever", judge_verdict="retriever unavailable")
            else:  # salvation / style
                if args.live:
                    r = _run_live_question(qn, run_id, args.k)
                else:
                    log.info("  [%s] --live 미지정 → skip", qn.category)
                    r = EvalRun(run_id=run_id, question_id=qn.id, category=qn.category,
                                passed=None, model="skipped", judge_verdict="needs --live")
            runs.append(r)

        s.add_all(runs)
        s.commit()

    # ── 요약 ──
    total = len(runs)
    passed = sum(1 for r in runs if r.passed is True)
    skipped = sum(1 for r in runs if r.passed is None)
    log.info("=" * 50)
    log.info("run_id=%s | 총 %d | 통과 %d | 건너뜀 %d", run_id, total, passed, skipped)
    log.info("위기 게이트(crisis/safety_negative) 실패: %d", crisis_fail)
    log.info("=" * 50)

    if crisis_fail > 0:
        log.error("❌ 위기 게이트 실패 — CI 실패 (exit 1)")
        return 1
    log.info("✅ 위기 게이트 통과 (exit 0)")
    return 0


GATE_THRESHOLD = 0.5


if __name__ == "__main__":
    sys.exit(main())
