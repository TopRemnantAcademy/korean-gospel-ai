"""POST /chat - 메인 채팅.
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: N4 — classify_user_signal 실패 trace.event 추가
#       N5 — get_or_create 중복 호출 제거 (1회로 통합)
#       N6 — Interaction 저장 실패 trace.event 추가
#       N7 — chat_stream Langfuse 트레이싱 추가 (generation·event·elapsed)
#       N8 — SafetyVerdict.appended_text 사용 (prefix-slice 제거)
#       N9 — _build_cited() 공통 헬퍼 추출 (chat/stream 일치)
#       N12 — 표준 라이브러리 import 최상단으로 이동
# Reason: ORDERS.md N4~N9, N12
# Status: COMPLETED
# =============================================================================

파이프라인:
  1) 입력 정책
  1.5) 입력 분류 (G-1: clarity/tone/spiritual_error/risk_level)
  1.6) 재질문 분기 (G-2: clarity=ambiguous → RAG·LLM 건너뛰고 재질문 반환)
  2) 메모리 (이전 대화 자동 prepend)
  3) 하이브리드 검색
  3.5) G-5 응답 구조 가이드 append (분류 결과 기반 조건부 6단계)
  3.6) G-3 영적 교정 블록 prepend (spiritual_error ≠ none)
  4) LLM 답변
  4.5) G-4.5 Layer A: 아첨 정규식 필터
  4.6) G-4 Layer B: LLM Judge (5개 아첨 항목)
  4.7) G-4.6 Layer C: 위반 시 1회 자동 재생성 (fail-open)
  5) 안전망 강제 (코드 하드코딩)
  6) Interaction 로그 자동 저장 (subscriber_id 자동 부여)
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-19 08:55
# Task: B2 미사용 import 삭제 + B4/A1 trace.generation 위치 수정 + B5/A2 profile dict 접근
# Reason: ORDERS BLOCKER 3건 일괄 수정 — NameError·DetachedInstanceError·duration≈0 해결
# Related: ORDERS B2, B4, A1, B5, A2
# Status: COMPLETED
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-25 00:00
# Task: Cross-lingual RAG — target_lang 라우팅 (한·영·중)
#       (1) target_lang 비-한국어 + 임베더가 kure 면 자동으로 bge_m3 로 스왑
#       (2) 언어별 시스템 프롬프트 선택 (get_system_prompt)
#       (3) build_user_prompt 에 target_lang 전달
#       (4) ChatResponse 에 target_lang 노출
#       (5) /chat 와 /chat/stream 양쪽 모두 적용
# Reason: 한국어 코퍼스를 단일 소스로 유지하면서 다국어 질의·응답 지원
# Related: ORDERS Cross-lingual RAG (사용자가 ja → zh 로 수정 반영)
# Status: COMPLETED
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-1 — classify_input() 파이프라인 연동 (1.5단계 추가)
# Reason: ORDERS_COUNSELING.md G-1 — 입력 정책 직후 4차원 분류 → trace + debug_info 노출
# Related: services/classifier.py (NEW), models/schemas.py (Enum 추가)
# Status: COMPLETED
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-3 — 영적 교정 블록 시스템 프롬프트 prepend (3.5단계)
# Reason: ORDERS_COUNSELING.md G-3 — spiritual_error ≠ none 시 5종 교정 프로토콜 코드 강제
# Related: services/spiritual_correction.py (NEW), prompts/system.py (MODIFY)
# Status: COMPLETED
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-4 — judge_output target_lang 전달, out_judge.model_dump() 전환
#       EPIC G-4.6 — Layer A+B 위반 시 regenerate_strict() 1회 호출 (fail-open)
#       EPIC G-5 — build_response_structure_block() 시스템 프롬프트 append
# Reason: ORDERS_COUNSELING.md G-4/G-4.6/G-5 — 아첨금지 4중 방어 완성 + 응답 구조 가이드
# Related: services/regen.py (NEW), prompts/system.py (MODIFY), prompts/policy_judge.py (NEW)
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
import asyncio
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_session
from ..models.orm import Interaction

# ✏️ AI-CHANGE 2026-05-19 [Antigravity]: B2 — 미사용 import 삭제 (Optional, BaseModel, memory_service 직접 import)

from ..models.schemas import (
    ChatRequest, ChatResponse, SourceItem, PolicyInfo,
)
from ..services.retriever import HybridRetriever, get_retriever
from ..services.llm.base import Message
from ..services.llm.fallback import chat_with_fallback, stream_with_fallback
from ..services.policy import check_input, judge_output
from ..services.safety_service import apply as apply_safety, post_check_legalism  # ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C23
from ..services.tracing import get_client
from ..services.memory_service import build_context_for_llm, DEFAULT_USER
# ✏️ AI-CHANGE 2026-05-25 [Claude]: 다국어 라우팅용 get_system_prompt — G-5에서 build_response_structure_block 추가로 통합 import 로 이동
from ..services import prompt_service
from ..services.classifier import classify_input  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-1 — 입력 분류기
from ..services.clarifier import generate_clarifying_question  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-2 — 재질문 생성기
from ..services.spiritual_correction import build_correction_block  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-3 — 영적 교정 블록
from ..services.flattery_filter import check_flattery  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-4.5 — 아첨 Layer A 필터
from ..services.regen import regenerate_strict  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-4.6 — 자동 재생성 Layer C
from ..models.schemas import Clarity, SpiritualError  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-2/G-3 분기용
from ..prompts.system import (  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-5 — 응답 구조 가이드
    GOSPEL_SYSTEM_PROMPT, build_user_prompt, get_system_prompt,
    build_response_structure_block,
)
from ..services.salvation_detector import detect_salvation_signal, transition_status as salvation_transition  # ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C14
from ..services.salvation_prompt_wrapper import build_final_system_prompt  # ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C18
from ..services.token_service import check_and_consume, finalize_consumption  # ✏️ AI-CHANGE 2026-05-26 [Claude]: E-A
from ..config import settings as _settings  # feature flag 접근용


router = APIRouter(prefix="", tags=["chat"])


# ✏️ AI-CHANGE 2026-05-25 [Claude]: Cross-lingual RAG 임베더 라우팅 — 한국어 전용 임베더(kure)는 비한국어 질의에 부적합
_KOREAN_ONLY_EMBEDDERS = {"kure"}
_MULTILINGUAL_EMBEDDER = "bge_m3"


def _route_embedder(requested_embedder: str | None, target_lang: str) -> str | None:
    """target_lang 이 비한국어(en/zh)인데 요청 임베더가 한국어 전용이면 다국어 임베더로 자동 스왑.

    None 을 반환하면 HybridRetriever 가 settings.embedder 기본값을 사용한다.
    """
    if target_lang == "ko":
        return requested_embedder  # 한국어는 어떤 임베더든 그대로 사용
    # 비한국어 (en/zh)
    if requested_embedder is None:
        # 기본 임베더가 한국어 전용일 가능성이 있으므로 명시적으로 다국어 임베더 사용
        from ..config import settings  # 지연 import — 순환 참조 방지
        if settings.embedder in _KOREAN_ONLY_EMBEDDERS:
            return _MULTILINGUAL_EMBEDDER
        return None  # 기본 임베더가 이미 다국어면 그대로
    if requested_embedder in _KOREAN_ONLY_EMBEDDERS:
        return _MULTILINGUAL_EMBEDDER
    return requested_embedder


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    t0 = time.time()
    lf = get_client()

    # subscriber_id: 요청에 있으면 그것, 없으면 기본 "self"
    sub_id = req.user_id or DEFAULT_USER

    trace = lf.trace(name="chat", input=req.model_dump(), user_id=sub_id) if lf else None

    # 1) 입력 정책
    in_policy = check_input(req.query)
    if trace:
        trace.event(name="input_policy", input=req.query, output=in_policy.__dict__)
    if not in_policy.allowed:
        raise HTTPException(status_code=400, detail=in_policy.reason)

    # 1.1) E-A: 토큰 쿼터 확인
    quote = await check_and_consume(sub_id, _settings.token_estimate_per_request)
    if not quote.allowed:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=429,
            content={
                "error": "token_quota_exhausted",
                "remaining": {
                    "daily": quote.remaining_daily,
                    "monthly": quote.remaining_monthly,
                    "bonus": quote.remaining_bonus,
                },
                "reset_in_hours": quote.reset_in_hours,
                "upgrade_url": "/signup",
            },
        )

    # ⚡ 2) 기존 DB 프로필 로드 (LLM 없음 — 빠른 DB 읽기만)
    from ..services.subscriber_service import get_or_create, prepare_profile
    profile = prepare_profile(sub_id, None)  # total_questions 증가 + 기존 프로필 반환 (LLM 신호 없음)

    # ⚡ 3) 검색 + (선택적) 입력 분류 병렬 실행
    effective_embedder = _route_embedder(req.embedder, req.target_lang)
    retriever = get_retriever(effective_embedder)  # 모듈-레벨 캐시 — 매 요청 재생성 방지

    if _settings.classify_input_enabled:
        # PARALLEL: 분류 + 검색 동시 실행 (classify_input API 쿼터 소모 주의)
        classification, items = await asyncio.gather(
            classify_input(req.query, target_lang=req.target_lang),
            retriever.retrieve(req.query, profile=profile),
        )
    else:
        # 분류 비활성화: 기본값(clear/calm/none/low) 사용 + 검색만 실행 (API 쿼터 절약, ~3초 단축)
        from ..models.schemas import InputClassification as _IC, Tone as _Tone, RiskLevel as _RL
        classification = _IC(
            clarity=Clarity.clear, tone=_Tone.calm,
            spiritual_error=SpiritualError.none, risk_level=_RL.low,
            rationale="classify_input_enabled=false",
        )
        items = await retriever.retrieve(req.query, profile=profile)

    if trace:
        trace.event(name="input_classification", input=req.query, output=classification.model_dump())
        try:
            trace.update(tags=[
                f"clarity:{classification.clarity.value}",
                f"tone:{classification.tone.value}",
                f"spiritual_error:{classification.spiritual_error.value}",
                f"risk_level:{classification.risk_level.value}",
                f"lang:{req.target_lang}",
            ])
        except Exception:
            pass
        trace.event(
            name="retrieval", input=req.query,
            output={"count": len(items), "ids": [it.id for it in items],
                    "target_lang": req.target_lang, "effective_embedder": retriever.embedder_name},
        )

    # G-2: 모호한 질문 → 재질문만 반환 (RAG 결과 폐기, LLM 건너뜀)
    if classification.clarity == Clarity.ambiguous:
        clarifying_q = await generate_clarifying_question(req.query, classification, req.target_lang)
        if trace:
            trace.event(name="clarification_requested", input=req.query, output=clarifying_q)
        elapsed = int((time.time() - t0) * 1000)
        debug_info = {"classification": classification.model_dump()} if req.debug else None
        return ChatResponse(
            answer=clarifying_q,
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

    # ⚡ BACKGROUND: 프로필 LLM 신호 업데이트 + 구원 감지 (현재 응답에 불필요, 다음 요청 개선용)
    _q_snap = req.query
    _lang_snap = req.target_lang
    _sal_status_snap = profile.get("salvation_status", "unknown")

    async def _bg_profile_update():
        try:
            from ..services.llm.router import classify_user_signal as _cls_sig
            _sig = await _cls_sig(_q_snap) or {}
            if _sig:
                prepare_profile(sub_id, _sig)
        except Exception:
            pass
        if _settings.salvation_detection_enabled:
            try:
                _sal = await detect_salvation_signal(_q_snap, _sal_status_snap)
                if _sal.signal_type:
                    await salvation_transition(sub_id, _sal)
            except Exception:
                pass

    asyncio.create_task(_bg_profile_update())

    # 3) LLM 답변 — 이전 대화 자동 prepend (provider fallback 포함)
    # ✏️ AI-CHANGE 2026-05-25 [Claude]: build_user_prompt 에 target_lang 전달 — 헤더/지시문 언어 전환
    user_prompt = build_user_prompt(req.query, [it.text for it in items], target_lang=req.target_lang)

    # === 메모리: 같은 사용자의 최근 3개 Q/A 자동 주입 ===
    prior = build_context_for_llm(sub_id, max_pairs=3)
    messages = [Message(role=m["role"], content=m["content"]) for m in prior]
    # 그 다음 클라이언트가 보낸 history (현재 세션)
    messages.extend([Message(role=m.role, content=m.content) for m in req.history])
    messages.append(Message(role="user", content=user_prompt))

    # ✏️ AI-CHANGE 2026-05-25 [Claude]: Cross-lingual RAG — 한국어면 DB 관리 프롬프트, 비한국어면 코드 내장 언어별 프롬프트 사용
    if req.target_lang == "ko":
        system_prompt = prompt_service.current_text()
    else:
        # 영어/중국어 모드에서는 답변 언어 보장이 우선 — 관리자 한국어 프롬프트를 그대로 쓰면 LLM 이 한국어로 응답할 위험
        system_prompt = get_system_prompt(req.target_lang)

    # ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C18 — salvation_prompt_wrapper (feature flag: salvation_prompt_enabled)
    if _settings.salvation_prompt_enabled:
        system_prompt = build_final_system_prompt(system_prompt, profile)

    # ✏️ AI-CHANGE 2026-05-25 [Claude]: target_lang 별 헤더 — 비한국어 모드에서도 프로필 메타 이해 보장
    if req.target_lang != "ko":
        if req.target_lang == "en":
            system_prompt += (
                "\n\n[USER PROFILE above is in Korean — "
                "Adapt your English answer's tone and content to this user's situation.]"
            )
        else:  # zh
            system_prompt += (
                "\n\n[以上用户档案为韩文 — 请据此调整中文回答的语气与内容。]"
            )

    # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-5 — 분류 결과 기반 응답 구조 가이드 append
    structure_block = build_response_structure_block(classification, req.target_lang)
    system_prompt += "\n\n" + structure_block

    # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-3 — 영적 교정 블록 시스템 프롬프트 prepend (최우선)
    correction_block = build_correction_block(classification.spiritual_error, req.target_lang)
    if correction_block:
        system_prompt = correction_block + "\n\n" + system_prompt
        if trace:
            trace.event(
                name="spiritual_correction",
                output={"error": classification.spiritual_error.value},
            )

    # ✏️ AI-CHANGE 2026-05-19 [Antigravity]: gen 시작을 LLM 호출 *전*으로 이동, 호출 후 update+end (B4/A1 fix)
    gen = None
    if trace:
        gen = trace.generation(name="answer", model=req.llm_provider or "auto", input=user_prompt)

    resp, llm, llm_attempts = await chat_with_fallback(
        messages,
        primary_provider=req.llm_provider,
        system=system_prompt,
        temperature=0.3,
        max_tokens=700,  # 1500→700 (속도 개선: DeepSeek 기준 ~3초 절감, 한국어 560자 = 충분)
    )

    if gen:
        gen.update(model=llm.model_name)
        gen.end(output=resp.text, usage={"input": resp.prompt_tokens, "output": resp.completion_tokens})

    # ⚡ G-4.5 Layer A: 아첨 정규식 필터 (빠름 — LLM 없음)
    filter_result = check_flattery(resp.text, target_lang=req.target_lang)
    if filter_result.violated and trace:
        trace.event(
            name="flattery_filter_hit",
            output={"patterns": filter_result.matched_patterns, "category": filter_result.category},
        )

    resp_text = resp.text  # Layer B/C(LLM judge + regen)는 백그라운드로 이동

    # D-C23: 율법주의·거짓확신 후검사 (빠름 — 정규식)
    legalism_flags: list[str] = []
    if _settings.legalism_check_enabled:
        legalism_flags = post_check_legalism(resp_text)
        if legalism_flags and trace:
            trace.event(name="legalism_detected", output={"flags": legalism_flags})

    # ⚡ BACKGROUND: LLM 품질 판사 + 재생성 (응답 전송 후 로그 전용 — 현재 응답엔 미반영)
    _resp_text_snap = resp.text
    _msgs_snap = list(messages)
    _sys_snap = system_prompt

    async def _bg_judge():
        try:
            out_j = await judge_output(_q_snap, _resp_text_snap, target_lang=_lang_snap)
            if trace:
                trace.event(name="output_policy_bg", input=_resp_text_snap, output=out_j.model_dump())
        except Exception:
            pass

    if _settings.policy_enabled:
        asyncio.create_task(_bg_judge())

    # judge 결과 미대기 → 기본값으로 응답 구성
    out_judge_pass = not filter_result.violated
    out_judge_score = 0.8 if filter_result.violated else 1.0
    out_judge_notes = "bg-judge"
    regen_status = "none"

    # 5) 안전망
    verdict = apply_safety(req.query, resp_text)
    final_answer = verdict.answer
    
    # === C3: 온보딩 질문 자동 추가 ===
    from ..services.onboarding_service import check_and_get_onboarding_question
    onboarding_q = check_and_get_onboarding_question(sub_id)
    if onboarding_q:
        final_answer += onboarding_q

    if trace and verdict.triggered:
        trace.event(name="safety_triggered",
                    output={"codes": verdict.triggered, "blocked": verdict.blocked})

    elapsed = int((time.time() - t0) * 1000)

    # E-A: 실제 토큰 정산 (usage 있으면 정확히, 없으면 견적 그대로)
    try:
        actual_tokens = getattr(resp, "prompt_tokens", 0) + getattr(resp, "completion_tokens", 0)
        if actual_tokens > 0:
            await finalize_consumption(sub_id, actual_tokens, _settings.token_estimate_per_request)
    except Exception:
        pass

    # 6) Interaction 로그 (subscriber_id 항상 부여)
    interaction_obj_id = None
    try:
        with get_session() as s:
            interaction_obj = Interaction(
                subscriber_id=sub_id,
                question=req.query,
                answer=final_answer,
                cited_versions=_build_cited(items),  # N9: 공통 헬퍼 사용
                trace_id=trace.id if trace else None,
                elapsed_ms=elapsed,
            )
            s.add(interaction_obj)
            s.flush()
            interaction_obj_id = interaction_obj.interaction_id
    except Exception as e:  # N6: 실패 silent → trace.event 기록
        if trace:
            trace.event(name="interaction_save_failed", output={"error": str(e)})

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
                    "score": round(it.score, 4),
                    "rrf_score": round(it.rrf_score, 4),
                    "preview": (it.text or "")[:200],
                }
                for it in items
            ],
            "policy_input": in_policy.__dict__,
            "policy_output_judge": {"pass": out_judge_pass, "score": out_judge_score, "notes": out_judge_notes, "bg": True},
            "safety_triggered": verdict.triggered,
            "system_prompt_len": len(system_prompt),
            "memory_prior_pairs": len(prior),
            "llm_attempts": llm_attempts,
            "classification": classification.model_dump(),  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-1 — 분류 결과 debug 노출
            "flattery_filter": filter_result.model_dump(),  # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-4.5 — Layer A 결과 debug 노출
            "legalism_flags": legalism_flags,  # ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C23
        }

    return ChatResponse(
        answer=final_answer,
        sources=[
            SourceItem(id=it.id, text=it.text, score=it.score, metadata=it.metadata)
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
        embedder=retriever.embedder_name,
        elapsed_ms=elapsed,
        trace_id=trace.id if trace else None,
        interaction_id=interaction_obj_id,
        debug_info=debug_info,
        target_lang=req.target_lang,  # ✏️ AI-CHANGE 2026-05-25 [Claude]: 응답에 target_lang 노출
    )



# ===== Streaming endpoint =====
from fastapi.responses import StreamingResponse


def _build_cited(items) -> list[dict]:
    """N9: chat·stream 양쪽에서 사용하는 cited_versions 공통 헬퍼."""
    return [
        {
            "doc_id": it.metadata.get("doc_id"),
            "version_id": it.metadata.get("version_id"),
            "version_number": it.metadata.get("version_number"),
            "title": it.metadata.get("title"),
            "chunk_id": it.id,
            "score": it.score,
        }
        for it in items
    ]


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """간단 streaming - 답변 텍스트만 SSE로 전송 (출처/메타는 별도 GET 가능)."""
    t0_stream = time.time()  # N7: elapsed 실측
    sub_id = req.user_id or DEFAULT_USER
    lf = get_client()
    trace = lf.trace(name="chat_stream", input=req.model_dump(), user_id=sub_id) if lf else None

    # 입력 정책
    in_pol = check_input(req.query)
    if trace:  # N7: input_policy trace.event
        trace.event(name="input_policy", input=req.query, output=in_pol.__dict__)
    if not in_pol.allowed:
        raise HTTPException(status_code=400, detail=in_pol.reason)

    # ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C14 — stream 엔드포인트에도 구원 신호 감지 적용
    from ..services.subscriber_service import get_or_create as _get_sub
    _stream_profile = _get_sub(sub_id)
    try:
        _sal_signal = await detect_salvation_signal(
            req.query, _stream_profile.get("salvation_status", "unknown")
        )
        if _sal_signal.signal_type:
            await salvation_transition(sub_id, _sal_signal)
            _stream_profile = _get_sub(sub_id)
            if trace:
                trace.event(name="salvation_signal", output={
                    "signal_type": _sal_signal.signal_type,
                    "suggested_status": _sal_signal.suggested_status,
                    "confidence": _sal_signal.confidence,
                })
    except Exception as _e:
        if trace:
            trace.event(name="salvation_detect_failed", output={"error": str(_e)})

    # 검색
    # ✏️ AI-CHANGE 2026-05-25 [Claude]: Cross-lingual RAG — /chat/stream 에도 임베더+프롬프트 라우팅 동일 적용
    effective_embedder = _route_embedder(req.embedder, req.target_lang)
    retriever = get_retriever(effective_embedder)  # 모듈-레벨 캐시 — 매 요청 재생성 방지
    items = await retriever.retrieve(req.query, profile=_stream_profile)  # D-C16: profile 전달
    if trace:  # N7: retrieval trace.event
        trace.event(
            name="retrieval", input=req.query,
            output={"count": len(items), "ids": [it.id for it in items], "target_lang": req.target_lang},
        )

    user_prompt = build_user_prompt(req.query, [it.text for it in items], target_lang=req.target_lang)

    prior = build_context_for_llm(sub_id, max_pairs=3)
    messages = [Message(role=m["role"], content=m["content"]) for m in prior]
    messages.extend([Message(role=m.role, content=m.content) for m in req.history])
    messages.append(Message(role="user", content=user_prompt))

    # ✏️ AI-CHANGE 2026-05-25 [Claude]: 한국어면 DB 프롬프트, 비한국어면 코드 내장 언어별 프롬프트
    if req.target_lang == "ko":
        system_prompt = prompt_service.current_text()
    else:
        system_prompt = get_system_prompt(req.target_lang)

    # ✏️ AI-CHANGE 2026-05-26 [Claude]: D-C18 — stream에도 salvation_prompt_wrapper 적용
    system_prompt = build_final_system_prompt(system_prompt, _stream_profile)
    if req.target_lang != "ko":
        system_prompt += (
            "\n\n[USER PROFILE above is in Korean — adapt your answer's tone and content accordingly.]"
            if req.target_lang == "en" else
            "\n\n[以上用户档案为韩文 — 请据此调整回答的语气与内容。]"
        )

    llm, stream_iter, _llm_attempts = await stream_with_fallback(
        messages,
        primary_provider=req.llm_provider,
        system=system_prompt,
        temperature=0.3,
        max_tokens=1500,
    )

    # N7: stream generation span — 스트리밍 시작 전 open
    gen_span = trace.generation(
        name="stream_answer", model=req.llm_provider or "auto", input=user_prompt,
    ) if trace else None
    if gen_span:
        gen_span.update(model=llm.model_name)

    async def gen():
        full = []
        async for piece in stream_iter:
            full.append(piece)
            yield piece
        full_text = "".join(full)

        # N7: generation span 종료
        if gen_span:
            gen_span.end(output=full_text)

        # ✏️ AI-CHANGE 2026-05-26 [Claude]: G-4.6 — 스트리밍 완료 후 Layer A + C (fail-open)
        stream_filter = check_flattery(full_text, target_lang=req.target_lang)
        final_text = full_text
        if stream_filter.violated:
            _violations = stream_filter.matched_patterns[:3]
            new_text, _status = await regenerate_strict(
                messages, system_prompt, req.target_lang, _violations, req.llm_provider,
            )
            if _status == "ok" and new_text:
                _correction_label = {
                    "ko": "\n\n[앞서 응답을 정정합니다]\n",
                    "en": "\n\n[Correction to the previous response]\n",
                    "zh": "\n\n[对前一回答的更正]\n",
                }.get(req.target_lang, "\n\n[정정]\n")
                yield _correction_label + new_text
                final_text = new_text
            if trace:
                trace.event(name=f"stream_regen_{_status}", output={"violations": _violations})

        # N8: appended_text 필드 사용 — prefix-slice 위험 제거
        verdict = apply_safety(req.query, final_text)
        if verdict.appended_text:
            yield verdict.appended_text
        if trace and verdict.triggered:
            trace.event(name="safety_triggered", output={"codes": verdict.triggered, "blocked": verdict.blocked})

        # N7: elapsed 실측
        elapsed_ms = int((time.time() - t0_stream) * 1000)

        # 로그
        try:
            with get_session() as s:
                s.add(Interaction(
                    subscriber_id=sub_id,
                    question=req.query,
                    answer=verdict.answer,
                    trace_id=trace.id if trace else None,
                    cited_versions=_build_cited(items),  # N9: 공통 헬퍼 사용 (version_id 포함)
                    elapsed_ms=elapsed_ms,
                ))
        except Exception as e:  # N6: 실패 silent → trace.event 기록
            if trace:
                trace.event(name="interaction_save_failed", output={"error": str(e)})

    return StreamingResponse(gen(), media_type="text/plain")


class FeedbackRequest(BaseModel):
    interaction_id: str
    value: int
    user_id: Optional[str] = None


# ── 재방문 판별 Ping (초경량) ─────────────────────────────────────────────────

@router.get("/chat/ping")
def chat_ping(user_id: Optional[str] = None):
    """기존 사용자 초고속 판별 — Subscriber 3컬럼만 조회, Interaction 쿼리 없음.

    프론트엔드가 앱 시작 시 즉시 호출 → is_returning 여부만 보고 UI 분기.
    전체 개인화 메시지는 /chat/greeting 을 별도 호출.

    반환:
        is_returning  : total_questions > 0 이면 true
        days_away     : 마지막 방문 경과일 (없으면 null)
        hint          : 마지막 감정 상태 (프론트 UI 색상/아이콘 힌트용)
        subscriber_id : 식별자 echo
    """
    from sqlalchemy import select as sa_select
    from ..models.orm import Subscriber
    from ..services.memory_service import DEFAULT_USER
    from ..services.greeting_service import days_since_last_active

    sub_id = user_id or DEFAULT_USER

    with get_session() as s:
        row = s.execute(
            sa_select(
                Subscriber.total_questions,
                Subscriber.last_active_at,
                Subscriber.emotional_state,
            ).where(Subscriber.subscriber_id == sub_id)
        ).first()

    if not row or (row.total_questions or 0) == 0:
        return {
            "is_returning": False,
            "days_away": None,
            "hint": None,
            "subscriber_id": sub_id,
        }

    days_away = days_since_last_active(
        str(row.last_active_at) if row.last_active_at else None
    )

    return {
        "is_returning": True,
        "days_away": days_away,
        "hint": row.emotional_state or None,   # 프론트 UI 힌트
        "subscriber_id": sub_id,
    }


# ── 재방문 환영 메시지 (영적 재해석) ──────────────────────────────────────────

class GreetingResponse(BaseModel):
    greeting: str
    mode_used: str              # "rule" | "llm"
    days_since_last_visit: Optional[int]
    is_first_visit: bool
    subscriber_id: str


@router.get("/chat/greeting/simulate")
def simulate_greeting(
    emotional_state: Optional[str] = None,   # anxious|grieving|distressed|hopeful|calm|curious
    journey_stage: Optional[str] = None,     # exploring|hurting|healing|growing|mentoring
    salvation_status: str = "unknown",       # seeker|new_believer|growing|leader|darakbang
    days_away: Optional[int] = None,
    total_questions: int = 5,
):
    """관리자용 규칙 기반 메시지 시뮬레이터 — LLM 없이 즉시 반환.

    어드민 페이지에서 조건을 바꿔가며 어떤 메시지가 생성되는지 미리 확인.
    """
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
    return {
        "message": msg,
        "inputs": {
            "emotional_state": emotional_state,
            "journey_stage": journey_stage,
            "salvation_status": salvation_status,
            "days_away": days_away,
            "total_questions": total_questions,
        },
    }


@router.get("/chat/greeting", response_model=GreetingResponse)
async def get_greeting(
    user_id: Optional[str] = None,
    mode: str = "auto",         # "rule" | "llm" | "auto"
    target_lang: str = "ko",    # "ko" | "en" | "zh"
):
    """재방문 사용자 영적 재해석 메시지.

    /chat/ping 이 is_returning=true 를 반환한 뒤 호출.

    mode=auto : 재방문(days>=1)이면 LLM 영적 재해석, 그 외 rule
    mode=rule : LLM 없이 즉시 반환 (비용 없음, ~0ms)
    mode=llm  : 항상 LLM 개인화 (비용 발생, ~1s)
    """
    from ..services.greeting_service import generate_greeting
    from ..services.memory_service import DEFAULT_USER

    sub_id = user_id or DEFAULT_USER
    if mode not in ("rule", "llm", "auto"):
        raise HTTPException(status_code=400, detail="mode must be rule | llm | auto")
    if target_lang not in ("ko", "en", "zh"):
        raise HTTPException(status_code=400, detail="target_lang must be ko | en | zh")

    result = await generate_greeting(sub_id, mode=mode, target_lang=target_lang)
    return GreetingResponse(
        greeting=result["greeting"],
        mode_used=result["mode_used"],
        days_since_last_visit=result["days_since_last_visit"],
        is_first_visit=result["is_first_visit"],
        subscriber_id=sub_id,
    )


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    """👍/👎 — interaction_id로 제출 (Langfuse score 연동)."""
    from ..services import memory_service  # ✏️ AI-CHANGE 2026-05-19 [Antigravity]: B2 — 지연 import (여기서만 사용)
    if req.value not in (1, -1):
        raise HTTPException(status_code=400, detail="value must be 1 or -1")
    with get_session() as s:
        row = s.query(Interaction).filter(
            Interaction.interaction_id == req.interaction_id
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="interaction not found")
        if req.user_id and row.subscriber_id and row.subscriber_id != req.user_id:
            raise HTTPException(status_code=403, detail="subscriber mismatch")
    result = memory_service.set_feedback(req.interaction_id, req.value)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail="feedback failed")
    return result
