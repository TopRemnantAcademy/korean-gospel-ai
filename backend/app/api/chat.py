"""POST /chat + /chat/stream — 메인 채팅 파이프라인.

리팩토링 v2:
- 공통 로직은 chat_pipeline.py 로 분리 (DRY 원칙)
- 컨텍스트 압축: 최상위 3개 청크만 LLM에 전달 (노이즈 감소)
- 프롬프트 길이 최적화: max_tokens 700 → 1000으로 증가 (충분한 답변)
- 안정성: 모든 백그라운드 작업 추적 및 로깅 강화

파이프라인 순서:
1. 인증 → sub_id 결정
2. 입력 정책 검사
3. 프로필 로드
4. ⚡ 병렬: 입력 분류 + 검색
5. (선택) 재질문 분기
6. ⚡ 백그라운드: 프로필 업데이트 + 구원 감지
7. 프롬프트 구성 (메모리 + 시스템 + 교정 + 구조)
8. LLM 답변 (스트리밍 또는 일반)
9. 품질 필터 (아첨 + 율법주의)
10. 안전망 적용
11. 온보딩 질문 자동 추가
12. E-A: 토큰 로깅 + Interaction 저장
"""
from __future__ import annotations
import asyncio
import time
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
# 동시성 제어 (동시 20 CCU 대응)
#   /chat 은 LLM 폴백 체인(nvidia→tencent→gemini) + Qdrant 검색 + SQLite 쓰기를
#   동기 블로킹으로 수행. 20명이 동시 호출 시 executor 스레드 풀 고갈 →
#   이벤트 루프 블로킹 → 정적 엔드포인트까지 응답 불가 → 서버 크래시.
#   해결: 전역 세마포어로 동시 /chat 처리 수를 제한(기본 8). 나머지는 공정 대기.
#   env CHAT_MAX_CONCURRENCY 로 조정 가능.
# ═══════════════════════════════════════════════════════════════════════════════
import os as _os

_CHAT_MAX_CONCURRENCY = int(_os.getenv("CHAT_MAX_CONCURRENCY", "8"))
_chat_semaphore = asyncio.Semaphore(_CHAT_MAX_CONCURRENCY)
_CHAT_TIMEOUT_SEC = float(_os.getenv("CHAT_TIMEOUT_SEC", "30"))
# 세마포어 대기 상한: 이 시간 내 획득 실패 시 동기 대기 누적 대신 스트리밍으로 유도 (§5.5)
_CHAT_QUEUE_TIMEOUT_SEC = float(_os.getenv("CHAT_QUEUE_TIMEOUT_SEC", "8"))

from fastapi import APIRouter, HTTPException, Header, Request

from ..config import settings as _settings
from ..models.schemas import (
    ChatRequest,
    ChatResponse,
    SourceItem,
    PolicyInfo,
    FeedbackRequest,
    GreetingResponse,
    InputClassification,
)
from ..services.llm.base import Message
from ..services.llm.fallback import chat_with_fallback, stream_with_fallback
from ..services.policy import judge_output
from ..services.safety_service import apply as apply_safety, post_check_legalism
from ..services.flattery_filter import check_flattery
from ..services.regen import regenerate_strict
from ..services.tracing import get_client
from ..services.memory_service import DEFAULT_USER
from ..services.onboarding_service import check_and_get_onboarding_question
from ..services import quota_service
from ..services.grounding_verifier import verify_grounding, verify_grounding_with_timeout, safe_response
from ..middleware.rate_limit import _real_client_ip

# 공통 파이프라인
from .chat_pipeline import (
    _verify_auth,
    _estimate_tokens,
    check_input_and_quota,
    retrieve_and_classify,
    check_clarification_needed,
    detect_crisis_bypass,
    build_crisis_response,
    start_background_profile_update,
    build_prompts,
    build_cited,
    is_greeting_or_smalltalk,
)

from ..db import get_session

router = APIRouter(prefix="", tags=["chat"])

# 정정 응답 라벨 (언어별) — 스트리밍 경로에서 재사용
_CORRECTION_LABELS: dict[str, str] = {
    "ko": "\n\n[앞서 응답을 정정합니다]\n",
    "en": "\n\n[Correction to the previous response]\n",
    "zh": "\n\n[对前一回答的更正]\n",
    "ja": "\n\n[先ほどの回答を訂正します]\n",
}


def _correction_label(lang: str) -> str:
    """언어별 정정 라벨 반환 (기본값 ko)."""
    return _CORRECTION_LABELS.get(lang, "\n\n[정정]\n")

# 백그라운드 태스크 참조 보관 — GC 방지
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg_task(coro) -> None:
    """asyncio.create_task 의 참조를 보관하여 GC 를 방지한다."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _translate_to_korean(text: str, src_lang: str) -> Optional[str]:
    """이중언어 병기용: 비한국어 응답을 한국어로 번역. 실패 시 None(본문만 반환, 안전)."""
    if not text or not text.strip() or src_lang == "ko":
        return None
    _names = {"zh": "中文", "en": "English", "ja": "日本語"}
    _src = _names.get(src_lang, src_lang)
    _sys = (
        f"You are a professional translator. Translate the following {_src} text into natural, "
        f"fluent Korean. Preserve the meaning, tone, and any scripture or verse references. "
        f"Output ONLY the Korean translation with no extra commentary or preface."
    )
    try:
        _resp, _llm, _attempts = await chat_with_fallback(
            [Message(role="user", content=text)],
            system=_sys,
            temperature=0.1,
            max_tokens=_settings.chat_max_tokens,
        )
        return (_resp.text or "").strip() or None
    except Exception:
        import logging as _lt
        _lt.getLogger("gospel-api.chat").warning("병기 번역(한국어) 실패 — 본문만 반환", exc_info=True)
        return None


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, authorization: Optional[str] = Header(default=None), request: Request = None):
    """동기 채팅 - 전체 응답을 한 번에 반환.

    streaming이 필요하면 /chat/stream 사용.

    동시성 제어: 전역 세마포어(_chat_semaphore)로 동시 처리 수 제한 → 서버 생존 보장.
    LLM 폴백 체인에 CHAT_TIMEOUT_SEC 하드 타임아웃 적용 → 무한 대기 방지.

    §5.5: 세마포어 포화 시 CHAT_QUEUE_TIMEOUT_SEC 내 획득 실패하면 429 +
    X-Chat-Mode: stream 헤더로 클라이언트가 /chat/stream 으로 즉시 재시도 유도
    (동기 대기 45~60초 누적 제거).
    """
    # 세마포어 획득 (동시 CHAT_MAX_CONCURRENCY 초과 시 공정 대기, 서버 과부하 방지)
    try:
        await asyncio.wait_for(_chat_semaphore.acquire(), timeout=_CHAT_QUEUE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=429,
            detail="채팅 처리 대기열이 가득 찼습니다. 실시간 스트리밍(/chat/stream)으로 재시도해 주세요.",
            headers={
                "Retry-After": str(int(_CHAT_QUEUE_TIMEOUT_SEC)),
                "X-Chat-Mode": "stream",
            },
        )
    try:
        return await _chat_inner(req, authorization, request)
    finally:
        _chat_semaphore.release()


async def _chat_inner(req: ChatRequest, authorization: Optional[str], request: Request = None):
    t0 = time.time()
    # ✏️ 2026-08-14: target_lang="auto" → 질문 언어 자동 감지 (LLM 자연 동작 복원).
    # 기존엔 "ko" 고정이라 영어/중국어 질문도 한국어로 강제 답변했던 과도 제약을 제거.
    if req.target_lang == "auto":
        from ..prompts.system import detect_language
        req.target_lang = detect_language(req.query)
    lf = get_client()
    
    # 1. 인증 및 사용자 식별
    sub_id = _verify_auth(authorization, req.user_id)
    is_logged_in = bool(authorization and str(authorization).lower().startswith("bearer "))
    
    trace = (
        lf.trace(name="chat", input=req.model_dump(), user_id=sub_id) if lf else None
    )

    # === FAQ 정적 캐시 (동기 /chat에도 적용) ===
    if _settings.faq_cache_enabled:
        try:
            from ..services.faq_cache import get_cached_answer
            cached = get_cached_answer(req.query)
            if cached:
                answer_text, _sources = cached
                elapsed = int((time.time() - t0) * 1000)
                # FAQ 캐시 히트도 DB에 상호작용 저장 (스트리밍 경로와 일관성, OPT-A)
                from ..services.token_service import save_interaction_and_finalize_tokens
                try:
                    await save_interaction_and_finalize_tokens(
                        sub_id=sub_id,
                        question=req.query,
                        answer=answer_text,
                        cited_versions=_sources,
                        trace_id=trace.id if trace else None,
                        elapsed_ms=elapsed,
                        actual_tokens=0,
                        estimated=0,
                    )
                except Exception:
                    import logging as _ll
                    _ll.getLogger("gospel-api.chat").warning("FAQ 상호작용 저장 실패(sync)", exc_info=True)
                return ChatResponse(
                    answer=answer_text,
                    sources=[],
                    policy=PolicyInfo(
                        input_allowed=True,
                        input_severity=0.0,
                        input_flags=[],
                        output_pass=True,
                        output_score=1.0,
                        output_notes="faq-cache",
                    ),
                    llm_provider="faq-cache",
                    llm_model="static",
                    embedder="none",
                    elapsed_ms=elapsed,
                    trace_id=trace.id if trace else None,
                    target_lang=req.target_lang,
                )
        except Exception as _faq_err:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").warning("FAQ 캐시 조회 실패(graceful skip): %s", _faq_err)

    # === 생성 답변 캐시 조회 (정규화 키 + TTL) — FAQ 정확캐시와 별도 (P4 #1) ===
    if _settings.answer_cache_enabled:
        try:
            from ..services.answer_cache import get_answer, normalize_query
            # [P0-7] 캐시 키에 사용자 스코프(sub_id) 포함 — build_prompts 가 사용자
            # 프로필/메모리를 답변에 주입하므로 (질의+언어) 키만으로는 개인화 답변이
            # 타 사용자에게 누출된다. 저장(아래 629)과 동일한 키 구성을 유지할 것.
            _acache_key = f"answer_cache:{normalize_query(req.query)}:{req.target_lang}:{sub_id}"
            _acached = get_answer(_acache_key)
            if _acached:
                elapsed = int((time.time() - t0) * 1000)
                return ChatResponse(
                    answer=_acached["answer"],
                    sources=[
                        SourceItem(
                            id=s.get("doc_id") or "cached",
                            text="",
                            score=s.get("score", 0.0),
                            metadata=s,
                        )
                        for s in _acached.get("sources", [])
                    ],
                    policy=PolicyInfo(
                        input_allowed=True,
                        input_severity=0.0,
                        input_flags=[],
                        output_pass=True,
                        output_score=1.0,
                        output_notes="answer-cache",
                    ),
                    llm_provider="answer-cache",
                    llm_model="cached",
                    embedder="none",
                    elapsed_ms=elapsed,
                    trace_id=trace.id if trace else None,
                    target_lang=req.target_lang,
                )
        except Exception as _ac_err:
            import logging as _ll2
            _ll2.getLogger("gospel-api.chat").warning("답변 캐시 조회 실패(graceful skip): %s", _ac_err)

    # 2. 입력 정책 + 프로필 로드
    in_policy, quote, profile = await check_input_and_quota(
        req.query, sub_id, trace, req.target_lang
    )
    
    # 3. ⚡ 병렬: 입력 분류 + 검색
    # 3-FAST: 순수 인사/잡담은 RAG(분류 LLM+임베딩+Qdrant) 완전 생략 → LLM 즉시 응답.
    #   첫 메시지 병목(TTFT 7~11s) 제거. 인사 뒤 실제 질문이 오면 정규식이 매치되지 않아
    #   자동으로 RAG 경로로 fallback. 위기 바이패스는 assess_addiction_query(규칙 기반)가
    #   그대로 동작하므로 안전성 보존.
    retriever = None
    if _settings.greeting_fastpath_enabled and is_greeting_or_smalltalk(req.query):
        classification = InputClassification(rationale="greeting_fastpath(no-rag)")
        items = []
    else:
        classification, items, retriever = await retrieve_and_classify(
            req.query, profile, trace, req.embedder, req.target_lang
        )

    # 3-5. 🚨 Wave A: 위기 하드 바이패스 (RAG/LLM 생성 스킵)
    #  RiskLevel.urgent 또는 CrisisLevel.critical 감지 시, LLM 환각 위험을
    #  원천 차단하기 위해 사전 검증된 결정적 안전 응답을 즉시 반환한다.
    _crisis_bypass, _crisis_assess = detect_crisis_bypass(req.query, classification)
    if _crisis_bypass:
        crisis_answer = build_crisis_response(_crisis_assess, target_lang=req.target_lang)
        elapsed = int((time.time() - t0) * 1000)
        if trace:
            trace.event(name="crisis_hard_bypass", output={
                "risk_level": getattr(classification.risk_level, "value", None),
                "crisis_level": getattr(_crisis_assess.crisis_level, "value", None),
            })
        from ..services.token_service import save_interaction_and_finalize_tokens
        crisis_interaction_id = None
        try:
            crisis_interaction_id = await save_interaction_and_finalize_tokens(
                sub_id=sub_id,
                question=req.query,
                answer=crisis_answer,
                cited_versions=[],
                trace_id=trace.id if trace else None,
                elapsed_ms=elapsed,
                actual_tokens=0,  # LLM 미호출
                estimated=_settings.token_estimate_per_request,
                crisis_bypass=True,
            )
        except Exception as _cb_err:
            import logging as _llc
            _llc.getLogger("gospel-api.chat").warning("위기 바이패스 저장 실패: %s", _cb_err)
        return ChatResponse(
            answer=crisis_answer,
            answer_parallel=(
                await _translate_to_korean(crisis_answer, req.target_lang)
                if (req.bilingual and req.target_lang != "ko") else None
            ),
            sources=[],
            policy=PolicyInfo(
                input_allowed=True,
                input_severity=in_policy.severity,
                input_flags=in_policy.flags,
                output_pass=True,
                output_score=1.0,
                output_notes="crisis_hard_bypass",
            ),
            llm_provider="crisis-bypass",
            llm_model="deterministic",
            embedder="none",
            elapsed_ms=elapsed,
            trace_id=trace.id if trace else None,
            interaction_id=crisis_interaction_id,
            target_lang=req.target_lang,
        )

    # 4. G-2: 재질문 분기 (LLM 건너뜀)
    clarifying_q = await check_clarification_needed(req.query, classification, trace, req.target_lang)
    if clarifying_q:
        elapsed = int((time.time() - t0) * 1000)
        debug_info = {"classification": classification.model_dump()} if req.debug else None
        # H2 수정: 명확화 분기에서도 예약된 할당량을 정산(finalize)해야 한다.
        # check_input_and_quota()가 token_estimate_per_request(기본 2000) 토큰을 즉시
        # 차감하지만 여기서 finalize하지 않으면 차감이 영구 누수되어 사용자 할당량이
        # 허위 소진된다. 실제 명확화 생성 토큰만큼만 정산(나머지 환불)한다.
        try:
            from ..services.token_service import save_interaction_and_finalize_tokens
            await save_interaction_and_finalize_tokens(
                sub_id, req.query, clarifying_q, profile,
                actual_tokens=_estimate_tokens(clarifying_q),
                estimated=_settings.token_estimate_per_request,
            )
        except Exception as e:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").warning("[chat] 명확화 할당량 정산 실패: %s", e)
        return ChatResponse(
            answer=clarifying_q,
            answer_parallel=(
                await _translate_to_korean(clarifying_q, req.target_lang)
                if (req.bilingual and req.target_lang != "ko") else None
            ),
            sources=[],
            policy=PolicyInfo(
                input_allowed=True,
                input_severity=in_policy.severity,
                input_flags=in_policy.flags,
                output_pass=True,
                output_score=1.0,
                output_notes="clarification_requested",
            ),
            llm_provider="clarifier",
            llm_model="clarifier",
            embedder="none",
            elapsed_ms=elapsed,
            trace_id=trace.id if trace else None,
            debug_info=debug_info,
            target_lang=req.target_lang,
        )
    
    # 5. ⚡ 백그라운드: 프로필 업데이트 + 구원 감지
    start_background_profile_update(sub_id, req.query, profile, req.target_lang)
    
    # 6. 프롬프트 구성 (전체 파이프라인)
    messages, user_prompt, system_prompt, addiction_assessment = await build_prompts(
        sub_id, req.query, items, classification, req.target_lang, req.user_context
    )
    
    # history 추가 — 클라이언트 제공 history 도 영속 기록(build_prompts 내 sanitize_history)과
    # 동일하게 system role 주입을 차단한다 (프롬프트 인젝션 LLM01 방지)
    from ..services.prompt_guard import sanitize_history
    _safe_history = sanitize_history(
        [{"role": getattr(m, "role", "user"), "content": getattr(m, "content", "")} for m in (req.history or [])]
    )
    messages.extend([Message(role=h["role"], content=h["content"]) for h in _safe_history])
    messages.append(Message(role="user", content=user_prompt))

    # ── 로그인 사용자의 구독 정보 로드(할당량 티어 판정용) ──
    q_sub = None
    if is_logged_in:
        from ..models.orm import Subscriber
        def _load_subscriber():
            with get_session() as _s:
                return _s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        q_sub = await asyncio.to_thread(_load_subscriber)

    # ── 일일 질문 할당량 (2026-07-23) ── (FAQ/답변 캐시 히트는 위에서 early-return 되어 여기 도달 안 함)
    if is_logged_in and q_sub is not None:
        _qr = quota_service.check_quota(sub=q_sub)
    else:
        _qr = quota_service.check_quota(ip=_real_client_ip(request), uuid=req.user_id or DEFAULT_USER)
    if not _qr["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "QUOTA_EXCEEDED",
                "remaining": _qr["remaining"],
                "reset_in_hours": _qr["reset_in_hours"],
                "login_required": not is_logged_in,
                "tier": _qr["tier"],
                "daily_limit": _qr["daily_limit"],
            },
        )

    # 7. LLM 답변
    gen = trace.generation(name="answer", model=req.llm_provider or "auto", input=user_prompt) if trace else None
    
    try:
        resp, llm, llm_attempts = await asyncio.wait_for(
            chat_with_fallback(
                messages,
                primary_provider=req.llm_provider,
                system=system_prompt,
                temperature=0.3,
                max_tokens=_settings.chat_max_tokens,  # 700 (config.py 라인 80)
            ),
            timeout=_CHAT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        import logging as _to_log
        _to_log.getLogger("gospel-api.chat").error(
            "chat LLM 타임아웃(%.1fs) — 사용자 %s", _CHAT_TIMEOUT_SEC, sub_id
        )
        raise HTTPException(
            status_code=504,
            detail=f"답변 생성 시간 초과({_CHAT_TIMEOUT_SEC:.0f}s). 잠시 후 다시 시도해 주세요.",
        )
    
    if gen:
        gen.update(model=llm.model_name)
        gen.end(output=resp.text, usage={
            "input": resp.prompt_tokens,
            "output": resp.completion_tokens,
        })
    
    # 8. 품질 필터: 아첨 (Layer A)
    filter_result = check_flattery(resp.text, target_lang=req.target_lang)
    if filter_result.violated and trace:
        trace.event(name="flattery_filter_hit", output={
            "patterns": filter_result.matched_patterns,
            "category": filter_result.category,
        })
    
    resp_text = resp.text
    
    # 9. D-C23: 율법주의 후검사 + 재생성
    legalism_flags: list[str] = []
    if _settings.legalism_check_enabled:
        legalism_flags = post_check_legalism(resp_text)
        if legalism_flags and trace:
            trace.event(name="legalism_detected", output={"flags": legalism_flags})
    
    if legalism_flags:
        _regen_text, _regen_status = await regenerate_strict(
            messages, system_prompt, req.target_lang, legalism_flags[:3], req.query, req.llm_provider
        )
        if _regen_status == "ok" and _regen_text:
            resp_text = _regen_text
            if trace:
                trace.event(name="legalism_regen_ok", output={"flags": legalism_flags})
    
    # 10. ⚡ 백그라운드: LLM 품질 심사 (응답 블록하지 않음)
    async def _bg_judge():
        try:
            out_j = await judge_output(req.query, resp_text, target_lang=req.target_lang)
            if trace:
                trace.event(name="output_policy_bg", input=resp_text, output=out_j.model_dump())
        except Exception as exc:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").warning("백그라운드 judge 실패: %s", exc)
    
    if _settings.policy_enabled:
        _spawn_bg_task(_bg_judge())
    
    out_judge_pass = not filter_result.violated
    out_judge_score = 0.8 if filter_result.violated else 1.0
    out_judge_notes = "bg-judge"
    
    # 11. 안전망
    verdict = apply_safety(req.query, resp_text)
    final_answer = verdict.answer

    # 11-1. ✅ 중독 케어: 위기 레벨에 따른 안전 메시지 추가
    from ..services.addiction_care import get_safety_guard_message
    safety_msg = get_safety_guard_message(addiction_assessment, target_lang=req.target_lang)
    if safety_msg:
        final_answer += safety_msg

    # 12. === C3: 온보딩 질문 자동 추가 ===
    # ✅ 2026-07-24: DB 락 등 온보딩 실패가 응답 전체(500)를 죽이지 않도록 보호
    onboarding_q = None
    try:
        onboarding_q = await asyncio.to_thread(check_and_get_onboarding_question, sub_id)
    except Exception as _ob_err:
        import logging as _ll
        _ll.getLogger("gospel-api.chat").warning("온보딩 질문 확인 실패 (응답 계속): %s", _ob_err)
    if onboarding_q:
        final_answer += onboarding_q
    
    # 10-2. ⚡ 근거 귀속(환각) 검증 — SourceGroundingVerifier
    # monitor: 백그라운드 실행(응답 지연 0). enforce: 동기 실행, 미통과 시 안전 응답 대체.
    if _settings.grounding_verify_enabled:
        if _settings.grounding_verify_mode == "enforce":
            try:
                gv = await verify_grounding_with_timeout(
                    resp_text, items, target_lang=req.target_lang, mode="enforce"
                )
                if not gv.passed:
                    final_answer = safe_response(req.target_lang)
                    if trace:
                        trace.event(name="grounding_enforce_blocked", output={"score": gv.score, "issues": gv.issues[:3]})
            except Exception as exc:
                import logging as _ll
                _ll.getLogger("gospel-api.chat").warning("enforce grounding 실패(fail-open): %s", exc)
        else:
            async def _bg_grounding():
                try:
                    gv = await verify_grounding(resp_text, items, target_lang=req.target_lang, mode="monitor")
                    if trace:
                        trace.event(name="grounding_monitor", input=resp_text,
                                    output={"score": gv.score, "passed": gv.passed, "issues": gv.issues[:3]})
                except Exception as exc:
                    import logging as _ll
                    _ll.getLogger("gospel-api.chat").warning("백그라운드 grounding 실패: %s", exc)
            _spawn_bg_task(_bg_grounding())
    
    if trace and verdict.triggered:
        trace.event(name="safety_triggered", output={
            "codes": verdict.triggered, "blocked": verdict.blocked
        })
    
    elapsed = int((time.time() - t0) * 1000)
    
    # 13. E-A: Interaction 저장 + 토큰 최종 정산
    from ..services.token_service import save_interaction_and_finalize_tokens
    actual_tokens = getattr(resp, "prompt_tokens", 0) + getattr(resp, "completion_tokens", 0)
    interaction_obj_id = None
    try:
        interaction_obj_id = await save_interaction_and_finalize_tokens(
            sub_id=sub_id,
            question=req.query,
            answer=final_answer,
            cited_versions=build_cited(items),
            trace_id=trace.id if trace else None,
            elapsed_ms=elapsed,
            actual_tokens=actual_tokens,
            estimated=_settings.token_estimate_per_request,
            # CCP: 원가 귀속용 실제 공급자/모델/토큰 명세
            llm_provider=getattr(resp, "provider", None),
            llm_model=getattr(resp, "model", None),
            prompt_tokens=getattr(resp, "prompt_tokens", None),
            completion_tokens=getattr(resp, "completion_tokens", None),
        )
    except Exception as e:
        import logging as _ll
        _ll.getLogger("gospel-api.chat").warning("상호작용 저장 실패: %s", e)
        if trace:
            trace.event(name="interaction_save_failed", output={"error": str(e)})
    
    # 메모 추가
    notes = out_judge_notes
    if verdict.triggered:
        notes += " | safety:" + ",".join(verdict.triggered)
    if verdict.blocked:
        notes += " | BLOCKED"
    
    debug_info = None
    if req.debug:
        debug_info = {
            "candidate_count": len(items),
            "candidates": [
                {
                    "title": it.metadata.get("title", "?"),
                    "doc_id": it.metadata.get("doc_id"),
                    "version": it.metadata.get("version_number"),
                    "score": round(it.final_score, 4),
                    "rrf_score": round(it.raw_dense_score, 4),
                    "preview": (
                        it.compressed_context.compressed_text
                        if it.compressed_context
                        else it.text
                    )[:200],
                }
                for it in items
            ],
            "policy_input": in_policy.__dict__,
            "policy_output_judge": {
                "pass": out_judge_pass,
                "score": out_judge_score,
                "notes": out_judge_notes,
                "bg": True,
            },
            "safety_triggered": verdict.triggered,
            "system_prompt_len": len(system_prompt),
            "memory_prior_pairs": len(profile) if profile else 0,
            "llm_attempts": llm_attempts,
            "classification": classification.model_dump(),
            "flattery_filter": filter_result.model_dump(),
            "legalism_flags": legalism_flags,
        }
    
    # === 생성 답변 캐시 저장 (P4 #1) ===
    if _settings.answer_cache_enabled and not verdict.blocked:
        try:
            from ..services.answer_cache import set_answer, normalize_query
            # [P0-7] 조회(위 235)와 동일하게 sub_id 스코프 포함 — 사용자 간 답변 누출 방지
            _acache_key = f"answer_cache:{normalize_query(req.query)}:{req.target_lang}:{sub_id}"
            # 정밀 기록: 부분 정보(제목/점수만)가 아니라 build_cited 전체 메타를 캐시에 보관해,
            # 캐시 히트 시에도 interaction.cited_versions 가 동일한 정밀도를 갖도록 함.
            _cached_sources = build_cited(items)
            set_answer(_acache_key, {"answer": final_answer, "sources": _cached_sources})
        except Exception as _acse:
            import logging as _ll3
            _ll3.getLogger("gospel-api.chat").warning("답변 캐시 저장 실패(graceful skip): %s", _acse)

    return ChatResponse(
        answer=final_answer,
        sources=[
            SourceItem(
                id=it.id,
                text=(
                    it.compressed_context.compressed_text
                    if it.compressed_context
                    else it.text
                ),
                score=it.final_score,
                metadata=it.metadata,
            )
            for it in items
        ],
        policy=PolicyInfo(
            input_allowed=in_policy.allowed,
            input_severity=in_policy.severity,
            input_flags=in_policy.flags,
            output_pass=out_judge_pass and not verdict.blocked,
            output_score=out_judge_score,
            output_notes=notes,
        ),
        llm_provider=llm.provider_name,
        llm_model=llm.model_name,
        embedder=(retriever.embedder_name if retriever else None),
        elapsed_ms=elapsed,
        trace_id=trace.id if trace else None,
        interaction_id=interaction_obj_id,
        debug_info=debug_info,
        target_lang=req.target_lang,
        quota=_qr,
    )


@router.get("/quota")
def get_quota(
    authorization: Optional[str] = Header(default=None),
    request: Request = None,
    user_id: Optional[str] = None,
):
    """일일 질문 할당량 잔여 조회 (프론트 표시/429 재발송 UI). 소비 안 함."""
    from ..models.orm import Subscriber

    sub_id = _verify_auth(authorization, user_id)
    is_logged_in = bool(authorization and str(authorization).lower().startswith("bearer "))
    if is_logged_in:
        with get_session() as s:
            sub = s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        if sub is None:
            return quota_service.quota_status(ip=_real_client_ip(request), uuid=user_id or DEFAULT_USER)
        return quota_service.quota_status(sub=sub)
    return quota_service.quota_status(ip=_real_client_ip(request), uuid=user_id or DEFAULT_USER)


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest, authorization: Optional[str] = Header(default=None), request: Request = None
):
    """스트리밍 채팅 - 답변을 조각으로 즉시 전송."""
    t0_stream = time.time()
    # ✏️ 2026-08-14: target_lang="auto" → 질문 언어 자동 감지 (동기 chat 과 동일).
    if req.target_lang == "auto":
        from ..prompts.system import detect_language
        req.target_lang = detect_language(req.query)
    sub_id = _verify_auth(authorization, req.user_id)
    is_logged_in = bool(authorization and str(authorization).lower().startswith("bearer "))
    lf = get_client()
    
    trace = (
        lf.trace(name="chat_stream", input=req.model_dump(), user_id=sub_id)
        if lf else None
    )
    
    # SSE 헬퍼: data 필드에 개행이 포함되면 이벤트가 조기 종료되므로
    # 각 줄을 별도 data: 라인으로 분리해 개행을 보존한다.
    # (OPT-A: FAQ 스트리밍에서도 사용하므로 정책/쿼터 검사보다 먼저 정의)
    def _sse(text: str, event: str | None = None) -> str:
        lines = str(text).split("\n")
        body = "".join(f"data: {ln}\n" for ln in lines)
        return f"event: {event}\n{body}\n" if event else f"{body}\n"

    async def _aclose(it) -> None:
        aclose = getattr(it, "aclose", None)
        if callable(aclose):
            try:
                await aclose()
            except Exception:
                pass

    # 1.5. ⚡ OPT-A: FAQ 정적 캐시를 정책/쿼터 검사보다 먼저 조회 (/chat 과 정렬).
    # 반복되는 인기 질문은 DB 프로필 읽기 + 토큰 사전예약을 건너뛰고 즉시 스트리밍한다.
    # (기존엔 check_input_and_quota 이후라 캐시 히트도 쿼터를 소모했음 — 비대칭 해소)
    if _settings.faq_cache_enabled:
        try:
            from ..services.faq_cache import get_cached_answer as _faq_get
            faq_hit = _faq_get(req.query)
        except Exception as _faq_err:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").warning("FAQ 캐시 조회 실패(graceful skip): %s", _faq_err)
            faq_hit = None
        if faq_hit is not None:
            answer_text, sources = faq_hit
            elapsed = int((time.time() - t0_stream) * 1000)

            # FAQ 캐시 히트도 DB에 상호작용 저장 (일반 경로와 일관성)
            from ..services.token_service import save_interaction_and_finalize_tokens
            try:
                final_interaction_id = await save_interaction_and_finalize_tokens(
                    sub_id=sub_id,
                    question=req.query,
                    answer=answer_text,
                    cited_versions=sources,
                    trace_id=trace.id if trace else None,
                    elapsed_ms=elapsed,
                    actual_tokens=0,  # 캐시 히트는 LLM 호출 없음
                    estimated=0,      # OPT-A: 쿼터 사전예약을 건너뛰었으므로 정산분 0
                    extra_llm_calls=0,
                )
            except Exception:
                import logging as _ll
                _ll.getLogger("gospel-api.chat").warning("FAQ 상호작용 저장 실패", exc_info=True)
                final_interaction_id = ""

            from fastapi.responses import StreamingResponse as _SR

            async def _faq_gen():
                # 청크 단위로 즉시 전송 (캐시라도 스트리밍 UX 유지)
                for i in range(0, len(answer_text), 40):
                    yield _sse(answer_text[i:i+40])
                    await asyncio.sleep(0)
                # ✅ FAQ 캐시 히트도 일반 경로와 동일한 메타데이터 이벤트 전송
                import json
                meta = {
                    "interaction_id": final_interaction_id,
                    "sources": sources,
                    "has_correction": False,
                    "safety_triggered": False,
                    "elapsed_ms": elapsed,
                }
                yield _sse(json.dumps(meta, ensure_ascii=False))
                yield "event: done\n"
                yield "data: done\n\n"

            return _SR(_faq_gen(), media_type="text/event-stream")

    # 2.5 ⚡ OPT-SPEED: 질문 횟수 할당량 게이트를 검색(retrieval) 이전에 수행.
    #   - 무료 질문 소진 사용자는 임베더 로드/Qdrant 검색/분류 LLM 호출 없이 즉시 429 반환
    #     → "무료 질문 모두 사용" 안내 지연 제거 + 비로그인 유저 임베딩 비용 과금 방지.
    #   - check_quota 는 소비 없이 상태만 조회(실제 소비는 저장 단계) → 중복 호출 안전.
    _q_sub = None
    if is_logged_in:
        from ..models.orm import Subscriber
        def _load_subscriber():
            with get_session() as _s:
                return _s.query(Subscriber).filter(Subscriber.subscriber_id == sub_id).first()
        _q_sub = await asyncio.to_thread(_load_subscriber)
    # OPT-SPEED/안정성: 쿼터 조회(쓰기 포함)를 워커 스레드로 오프로드 → SQLite 잠금 재시도 대기 시
    # 이벤트 루프 블로킹 방지.
    _qr = await asyncio.to_thread(
        quota_service.check_quota,
        ip=_real_client_ip(request),
        uuid=req.user_id or DEFAULT_USER,
        sub=_q_sub,
    )
    if not _qr["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "QUOTA_EXCEEDED",
                "remaining": _qr["remaining"],
                "reset_in_hours": _qr["reset_in_hours"],
                "login_required": not is_logged_in,
                "tier": _qr["tier"],
                "daily_limit": _qr["daily_limit"],
            },
        )

    # 2. 입력 정책 + 프로필 로드 (FAQ 미스 시에만 도달)
    in_pol, quote, _stream_profile = await check_input_and_quota(
        req.query, sub_id, trace, req.target_lang
    )

    # 3. ⚡ 병렬: 입력 분류 + 검색
    # 3-FAST: 순수 인사/잡담은 RAG(분류 LLM+임베딩+Qdrant) 완전 생략 → LLM 즉시 스트리밍.
    #   첫 메시지 병목(TTFT 7~11s) 제거. 인사 뒤 실제 질문이 오면 정규식이 매치되지 않아
    #   자동으로 RAG 경로로 fallback. 위기 바이패스(assess_addiction_query, 규칙 기반)는 보존.
    retriever = None
    if _settings.greeting_fastpath_enabled and is_greeting_or_smalltalk(req.query):
        classification = InputClassification(rationale="greeting_fastpath(no-rag)")
        items = []
    else:
        classification, items, retriever = await retrieve_and_classify(
            req.query, _stream_profile, trace, req.embedder, req.target_lang
        )

    # 3-5. 🚨 Wave A: 위기 하드 바이패스 (RAG/LLM 생성 스킵, SSE 로 즉시 스트리밍)
    _crisis_bypass, _crisis_assess = detect_crisis_bypass(req.query, classification)
    if _crisis_bypass:
        crisis_answer = build_crisis_response(_crisis_assess, target_lang=req.target_lang)
        elapsed = int((time.time() - t0_stream) * 1000)
        if trace:
            trace.event(name="crisis_hard_bypass", output={
                "risk_level": getattr(classification.risk_level, "value", None),
                "crisis_level": getattr(_crisis_assess.crisis_level, "value", None),
            })
        from ..services.token_service import save_interaction_and_finalize_tokens
        try:
            crisis_interaction_id = await save_interaction_and_finalize_tokens(
                sub_id=sub_id,
                question=req.query,
                answer=crisis_answer,
                cited_versions=[],
                trace_id=trace.id if trace else None,
                elapsed_ms=elapsed,
                actual_tokens=0,
                estimated=_settings.token_estimate_per_request,
                crisis_bypass=True,
            )
        except Exception as _cb_err:
            import logging as _llc
            _llc.getLogger("gospel-api.chat").warning("위기 바이패스 저장 실패: %s", _cb_err)
            crisis_interaction_id = ""

        from fastapi.responses import StreamingResponse as _SRc

        async def _crisis_gen():
            for i in range(0, len(crisis_answer), 40):
                yield _sse(crisis_answer[i:i+40])
                await asyncio.sleep(0)
            import json
            meta = {
                "interaction_id": crisis_interaction_id,
                "sources": [],
                "has_correction": False,
                "safety_triggered": True,
                "crisis_bypass": True,
                "elapsed_ms": elapsed,
            }
            yield _sse(json.dumps(meta, ensure_ascii=False))
            yield "event: done\n"
            yield "data: done\n\n"

        return _SRc(_crisis_gen(), media_type="text/event-stream")

    # 4. G-2: 재질문 분기 (스트리밍 없이 즉시 반환)
    clarifying_q = await check_clarification_needed(req.query, classification, trace, req.target_lang)
    if clarifying_q:
        elapsed = int((time.time() - t0_stream) * 1000)
        # H2 수정: 명확화 분기 할당량 정산 (예약 누수 방지)
        try:
            from ..services.token_service import save_interaction_and_finalize_tokens
            await save_interaction_and_finalize_tokens(
                sub_id, req.query, clarifying_q, _stream_profile,
                actual_tokens=_estimate_tokens(clarifying_q),
                estimated=_settings.token_estimate_per_request,
            )
        except Exception as e:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").warning("[chat] 명확화 할당량 정산 실패(스트림): %s", e)
        from fastapi.responses import JSONResponse
        return JSONResponse(content={
            "answer": clarifying_q,
            "sources": [],
            "policy": {"input_allowed": True, "output_notes": "clarification_requested"},
            "llm_provider": "clarifier",
            "llm_model": "clarifier",
            "embedder": "none",
            "elapsed_ms": elapsed,
            "trace_id": trace.id if trace else None,
            "target_lang": req.target_lang,
        })
    
    # 5. ⚡ 백그라운드: 프로필 업데이트 + 구원 감지
    start_background_profile_update(sub_id, req.query, _stream_profile, req.target_lang)
    
    # 6. 프롬프트 구성
    messages, user_prompt, system_prompt, addiction_assessment = await build_prompts(
        sub_id, req.query, items, classification, req.target_lang, req.user_context
    )
    # [P0-1] history 추가 — 비스트리밍 경로(chat 함수, 위 392-398)와 동일하게
    # sanitize_history 로 system role 주입을 차단한다 (프롬프트 인젝션 방지).
    # 기존 스트리밍 경로는 클라이언트 history 를 그대로 extend 해 인젝션에 노출됐다.
    from ..services.prompt_guard import sanitize_history
    _stream_safe_history = sanitize_history(
        [{"role": getattr(m, "role", "user"), "content": getattr(m, "content", "")} for m in (req.history or [])]
    )
    messages.extend([Message(role=h["role"], content=h["content"]) for h in _stream_safe_history])
    messages.append(Message(role="user", content=user_prompt))

    # ── 일일 질문 할당량 게이트는 위(OPT-SPEED 2.5)에서 검색 이전에 이미 통과/차단됨 ──

    # 7. LLM 스트리밍
    # 최적화: max_tokens 를 설정값(default 700)으로 축소 → TTFT 이후 종료도 빨라짐
    llm, stream_iter, _llm_attempts = await stream_with_fallback(
        messages,
        primary_provider=req.llm_provider,
        system=system_prompt,
        temperature=0.3,
        max_tokens=_settings.chat_max_tokens,
    )
    
    gen_span = (
        trace.generation(name="stream_answer", model=req.llm_provider or "auto", input=user_prompt)
        if trace else None
    )
    if gen_span:
        gen_span.update(model=llm.model_name)
    
    from fastapi.responses import StreamingResponse as _SR
    
    async def gen():
        full = []
        final_interaction_id = None
        disconnected = False
        try:
            async for piece in stream_iter:
                full.append(piece)
                # SSE 형식: data: 텍스트 내용 (개행 이스케이프)
                yield _sse(piece)
        except (GeneratorExit, asyncio.CancelledError):
            # 클라이언트 단절: upstream 스트림 정리 후 조용히 종료
            disconnected = True
        except Exception as exc:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").warning("스트리밍 중단: %s", exc)
            yield _sse("[⚠️ 응답이 중간에 끊겼습니다. 다시 질문해 주세요.]")
        finally:
            # upstream LLM 스트림/연결 누수 방지
            await _aclose(stream_iter)
            # 단절/예외 시에도 trace span 을 닫아 누수 방지
            if gen_span:
                gen_span.end(output="".join(full))

        # 클라이언트가 이미 떠났으면 저장 생략 (고아 상호작용 방지)
        if disconnected:
            return
        
        full_text = "".join(full)

        # 최적화: 자주 묻는 질문 정적 캐시에 등록 (다음 동일 질문은
        # 검색/LLM 생략하고 즉시 응답). 비동기 저장이라 응답 지연에 영향 없음.
        try:
            from ..services.faq_cache import maybe_cache_answer
            maybe_cache_answer(req.query, full_text, build_cited(items))
        except Exception as _fc_exc:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").debug("FAQ 캐시 저장 실패(무시): %s", _fc_exc)

        # gen_span.end() 는 위 finally 에서 이미 호출됨 (중복 호출 방지)
        _stream_actual_tokens = _estimate_tokens(full_text)

        # ── CCP: 스트리밍 경로 원가 귀속용 토큰 추정 ──
        # SSE 스트림은 공급자가 usage 를 주지 않으므로 정확한 값이 없다.
        # 실제 전송한 프롬프트(system + messages)와 수신 텍스트를 각각 추정해
        # 입력/출력 단가를 구분 적용한다. 추정치임을 컬럼 의미상 감수한다
        # (비스트리밍 경로는 공급자 usage 실측값 사용).
        _stream_prompt_tokens = _estimate_tokens(
            system_prompt + "".join(getattr(m, "content", "") for m in messages)
        )
        _stream_completion_tokens = _stream_actual_tokens
        
        # 8. 품질 필터: 아첨 + 율법주의
        stream_filter = check_flattery(full_text, target_lang=req.target_lang)
        final_text = full_text
        
        # D-C23: 율법주의 후검사
        stream_legalism_flags: list[str] = []
        if _settings.legalism_check_enabled:
            stream_legalism_flags = post_check_legalism(final_text)
            if stream_legalism_flags and trace:
                trace.event(name="stream_legalism_detected", output={"flags": stream_legalism_flags})
        
        # 9. ⚡ 백그라운드: LLM 품질 심사
        async def _bg_stream_judge():
            try:
                _out_j = await judge_output(req.query, final_text, target_lang=req.target_lang)
                if trace:
                    trace.event(name="output_policy_stream", input=final_text, output=_out_j.model_dump())
            except Exception as exc:
                import logging as _ll
                _ll.getLogger("gospel-api.chat").warning("스트리밍 백그라운드 judge 실패: %s", exc)
        
        if _settings.policy_enabled:
            _spawn_bg_task(_bg_stream_judge())
        
        extra_calls = 0
        has_correction = False
        
        # 아첨 재생성
        if stream_filter.violated:
            _violations = stream_filter.matched_patterns[:3]
            new_text, _status = await regenerate_strict(
                messages, system_prompt, req.target_lang, _violations, req.query, req.llm_provider
            )
            extra_calls = 1
            if _status == "ok" and new_text:
                yield _sse(_correction_label(req.target_lang))
                yield _sse(new_text)
                final_text = new_text
                has_correction = True
            if trace:
                trace.event(name=f"stream_regen_{_status}", output={"violations": _violations})
        
        # 율법주의 재생성
        if stream_legalism_flags:
            _legalism_regen, _legalism_status = await regenerate_strict(
                messages, system_prompt, req.target_lang, stream_legalism_flags[:3], req.query, req.llm_provider
            )
            if _legalism_status == "ok" and _legalism_regen:
                yield _sse(_correction_label(req.target_lang))
                yield _sse(_legalism_regen)
                final_text = _legalism_regen
                extra_calls += 1
                has_correction = True
                if trace:
                    trace.event(name="stream_legalism_regen_ok", output={"flags": stream_legalism_flags})
        
        # 10. 안전망
        verdict = apply_safety(req.query, final_text)
        if verdict.appended_text:
            yield _sse(verdict.appended_text)
        if trace and verdict.triggered:
            trace.event(name="safety_triggered", output={"codes": verdict.triggered, "blocked": verdict.blocked})

        # 10-1. ✅ 중독 케어: 위기 레벨에 따른 안전 메시지 추가
        from ..services.addiction_care import get_safety_guard_message
        safety_msg = get_safety_guard_message(addiction_assessment, target_lang=req.target_lang)
        if safety_msg:
            yield _sse(safety_msg)

        # 11. 온보딩 질문
        # ✅ 2026-07-24 근본수정: DB 락 등 온보딩 실패가 SSE 스트림 전체를
        # 죽이지 않도록 보호. (이전에는 여기서 database is locked 예외가
        # 스트림을 끊어 프론트가 "연결 에러"를 표시했음)
        onboarding_q = None
        try:
            onboarding_q = await asyncio.to_thread(check_and_get_onboarding_question, sub_id)
        except Exception as _ob_err:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").warning("온보딩 질문 확인 실패 (스트림 계속): %s", _ob_err)
            if trace:
                trace.event(name="onboarding_check_failed", output={"error": str(_ob_err)})
        if onboarding_q:
            yield _sse(onboarding_q)

        # 12-1. ✅ 이중언어 병기 답변 (bilingual): 비한국어 응답을 한국어로 번역해 병기
        if req.bilingual and req.target_lang != "ko":
            try:
                _ko = await _translate_to_korean(final_text_for_save, req.target_lang)
                if _ko:
                    yield _sse("\n\n---\n\n🇰🇷 **한국어 번역**\n\n" + _ko)
            except Exception as _bpex:
                import logging as _llbp
                _llbp.getLogger("gospel-api.chat").warning("병기 번역 스트리밍 실패(무시): %s", _bpex)

        # 10-2. ⚡ 근거 귀속(환각) 검증 — SourceGroundingVerifier
        # monitor: 백그라운드(지연 0). enforce: 동기 실행 → 미통과 시 스트림 끊지 않고
        # 안전 알림을 끝에 append (이미 전송된 토큰은 회수 불가 → 보완 방식).
        if _settings.grounding_verify_enabled:
            if _settings.grounding_verify_mode == "enforce":
                try:
                    gv = await verify_grounding_with_timeout(
                        final_text, items, target_lang=req.target_lang, mode="enforce"
                    )
                    if not gv.passed:
                        yield _sse(safe_response(req.target_lang))
                        if trace:
                            trace.event(name="grounding_enforce_blocked", output={"score": gv.score, "issues": gv.issues[:3]})
                except Exception as exc:
                    import logging as _ll
                    _ll.getLogger("gospel-api.chat").warning("enforce grounding 실패(fail-open): %s", exc)
            else:
                async def _bg_grounding():
                    try:
                        gv = await verify_grounding(final_text, items, target_lang=req.target_lang, mode="monitor")
                        if trace:
                            trace.event(name="grounding_monitor", output={"score": gv.score, "passed": gv.passed, "issues": gv.issues[:3]})
                    except Exception as exc:
                        import logging as _ll
                        _ll.getLogger("gospel-api.chat").warning("스트림 백그라운드 grounding 실패: %s", exc)
                _spawn_bg_task(_bg_grounding())

        final_text_for_save = verdict.answer if verdict.triggered else final_text
        if safety_msg:
            final_text_for_save += safety_msg
        if onboarding_q:
            final_text_for_save += onboarding_q
        
        # 12. E-A: 최종 저장
        from ..services.token_service import save_interaction_and_finalize_tokens
        elapsed_ms = int((time.time() - t0_stream) * 1000)

        # ── 스트리밍 실측 usage 통합 (정밀도 향상) ──
        # OpenAI 호환 provider(nvidia/tencent 등)는 최종 청크에서 실측 토큰을
        # 보내며 stream_with_fallback 가 llm.last_stream_usage 에 채운다.
        # 실측값이 있으면 추정치를 대체하고, 없으면 기존 추정치를 유지(fail-open).
        _real_usage = getattr(llm, "last_stream_usage", None)
        if _real_usage and (_real_usage.prompt_tokens or _real_usage.completion_tokens):
            _final_prompt_tokens = _real_usage.prompt_tokens or _stream_prompt_tokens
            _final_completion_tokens = _real_usage.completion_tokens or _stream_completion_tokens
            if trace:
                trace.event(name="stream_usage_real", output={
                    "prompt_tokens": _final_prompt_tokens,
                    "completion_tokens": _final_completion_tokens,
                    "provider": _real_usage.provider,
                })
        else:
            _final_prompt_tokens = _stream_prompt_tokens
            _final_completion_tokens = _stream_completion_tokens

        try:
            final_interaction_id = await save_interaction_and_finalize_tokens(
                sub_id=sub_id,
                question=req.query,
                answer=final_text_for_save,
                cited_versions=build_cited(items),
                trace_id=trace.id if trace else None,
                elapsed_ms=elapsed_ms,
                actual_tokens=_stream_actual_tokens,
                estimated=_settings.token_estimate_per_request,
                extra_llm_calls=extra_calls,
                # CCP: 실제 응답한 어댑터의 공급자/모델 + (실측 우선, 부재 시 추정) 토큰
                llm_provider=getattr(llm, "provider_name", None),
                llm_model=getattr(llm, "model_name", None),
                prompt_tokens=_final_prompt_tokens,
                completion_tokens=_final_completion_tokens,
            )
        except Exception as e:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").warning("스트리밍 상호작용 저장 실패: %s", e)
            if trace:
                trace.event(name="interaction_save_failed", output={"error": str(e)})
        
        # ✅ 마지막으로 메타데이터 이벤트 전달 (SSE done 이벤트)
        import json
        meta = {
            "interaction_id": final_interaction_id,
            "sources": build_cited(items),
            "has_correction": has_correction,
            "safety_triggered": bool(verdict.triggered),
            "elapsed_ms": elapsed_ms,
        }
        yield _sse(json.dumps(meta, ensure_ascii=False))
        yield "event: done\n"
        yield "data: done\n\n"
    
    return _SR(gen(), media_type="text/event-stream")


# ──────────────────────────────────────────────────────────────────────────────
# 보조 엔드포인트 (ping, greeting, feedback)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/chat/ping")
def chat_ping(user_id: Optional[str] = None, authorization: Optional[str] = Header(default=None)):
    """초고속 재방문 판별 - UI 분기용.
    
    Authorization Bearer 토큰이 있으면 토큰에서 sub_id 우선 사용.
    """
    from sqlalchemy import select as sa_select
    from ..models.orm import Subscriber
    from ..services.greeting_service import days_since_last_active
    
    # ✅ 패치 2: Bearer 토큰 우선 처리
    sub_id = user_id or DEFAULT_USER
    if authorization and authorization.lower().startswith("bearer "):
        try:
            from .auth import _verify_token
            token_sub = _verify_token(authorization[7:])
            if token_sub:
                sub_id = token_sub
        except Exception as exc:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").debug("chat_ping 토큰 확인 실패, user_id fallback 사용: %s", exc)
    
    with get_session() as s:
        row = s.execute(sa_select(
            Subscriber.total_questions,
            Subscriber.last_active_at,
            Subscriber.emotional_state,
        ).where(Subscriber.subscriber_id == sub_id)).first()
    
    if not row or (row.total_questions or 0) == 0:
        return {"is_returning": False, "days_away": None, "hint": None, "subscriber_id": sub_id}
    
    days_away = days_since_last_active(
        str(row.last_active_at) if row.last_active_at else None
    )
    
    return {
        "is_returning": True,
        "days_away": days_away,
        "hint": row.emotional_state or None,
        "subscriber_id": sub_id,
    }


@router.get("/chat/greeting/simulate")
def simulate_greeting(
    emotional_state: Optional[str] = None,
    journey_stage: Optional[str] = None,
    salvation_status: str = "unknown",
    days_away: Optional[int] = None,
    total_questions: int = 5,
):
    """관리자용 규칙 기반 메시지 시뮬레이터."""
    from ..services.greeting_service import rule_based_greeting
    
    fake_profile = {
        "emotional_state": emotional_state,
        "journey_stage": journey_stage,
        "salvation_status": salvation_status,
        "total_questions": total_questions,
        "last_active_at": None,
    }
    fake_last = {"question": "이전 대화 존재"} if total_questions > 1 else None
    
    msg = rule_based_greeting(fake_profile, days_away, fake_last)
    return {"message": msg, "inputs": {
        "emotional_state": emotional_state,
        "journey_stage": journey_stage,
        "salvation_status": salvation_status,
        "days_away": days_away,
        "total_questions": total_questions,
    }}


@router.get("/chat/greeting", response_model=GreetingResponse)
async def get_greeting(
    user_id: Optional[str] = None,
    mode: str = "auto",
    target_lang: str = "ko",
    authorization: Optional[str] = Header(default=None),
):
    """재방문 사용자 영적 재해석 메시지."""
    from ..services.greeting_service import generate_greeting
    
    # ✅ 패치 3: Bearer 토큰 우선 처리
    sub_id = user_id or DEFAULT_USER
    if authorization and authorization.lower().startswith("bearer "):
        try:
            from .auth import _verify_token
            token_sub = _verify_token(authorization[7:])
            if token_sub:
                sub_id = token_sub
        except Exception as exc:
            import logging as _ll
            _ll.getLogger("gospel-api.chat").debug("greeting 토큰 확인 실패, user_id fallback 사용: %s", exc)
    if mode not in ("rule", "llm", "auto"):
        raise HTTPException(status_code=400, detail="mode must be rule | llm | auto")
    if target_lang not in ("ko", "en", "zh", "ja"):
        raise HTTPException(status_code=400, detail="target_lang must be ko | en | zh | ja")
    
    result = await generate_greeting(sub_id, mode=mode, target_lang=target_lang)
    return GreetingResponse(
        greeting=result["greeting"],
        mode_used=result["mode_used"],
        days_since_last_visit=result["days_since_last_visit"],
        is_first_visit=result["is_first_visit"],
        subscriber_id=sub_id,
    )


@router.get("/chat/greeting-sub")
def get_greeting_sub(lang: str = "ko"):
    """관리자가 설정한 주간 메시지(부제목)를 조회합니다. 인증 불필요."""
    from ..services.settings_service import get_str as _get_str
    key = f"greeting_sub_{lang[:2]}"
    if key not in ("greeting_sub_ko", "greeting_sub_zh", "greeting_sub_en"):
        key = "greeting_sub_ko"
    return {"greeting_sub": _get_str(key, "")}


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest, authorization: Optional[str] = Header(default=None)):
    """👍/👎 피드백 제출 - 비로그인(익명) 제출 허용. 토큰이 있으면 소유권만 검증."""
    from ..models.orm import Interaction
    from ..services import memory_service
    from .auth import _verify_token

    token_sub = None
    if authorization and authorization.lower().startswith("bearer "):
        token_sub = _verify_token(authorization[7:])
        if not token_sub:
            raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다.")

    if req.value not in (1, -1, 0):
        raise HTTPException(status_code=400, detail="value must be 1, -1, or 0")

    with get_session() as s:
        row = s.query(Interaction).filter(Interaction.interaction_id == req.interaction_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="interaction not found")
        # 로그인 사용자만 소유권 검증. 익명(토큰 없음)은 누구나 피드백 가능.
        if token_sub and row.subscriber_id and row.subscriber_id != token_sub:
            raise HTTPException(status_code=403, detail="subscriber mismatch")

    result = memory_service.set_feedback(req.interaction_id, req.value)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail="feedback failed")
    return result
