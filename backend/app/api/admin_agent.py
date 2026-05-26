"""자연어 관제탑 에이전트 API (Agentic Admin)"""
from __future__ import annotations
import json
import re
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ..config import settings
from ..db import get_session
from ..models.orm import Subscriber, Category
from ..services.subscriber_service import update_profile
from ..services.llm.fallback import chat_with_fallback
from ..services.llm.base import Message

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-18
# Task: Create admin_agent.py for Phase 5 (Agentic Admin)
# Reason: 자연어로 명령하면 AI가 판단하여 Tool을 호출하고 DB를 수정/조회함
# Related: backend/app/main.py, admin/pages/10_🤖_AI_관제.py
# Status: COMPLETED
# =============================================================================

router = APIRouter(prefix="/admin/agent", tags=["admin_agent"])

def _check_admin(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=403, detail="missing admin token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="invalid admin token")

class AgentChatReq(BaseModel):
    query: str
    history: List[dict] = []

# ================= Tools (Functions) =================

def tool_get_users(args: dict) -> str:
    emotion = args.get("emotion")
    faith = args.get("faith")
    with get_session() as s:
        q = s.query(Subscriber)
        if emotion: q = q.filter(Subscriber.emotional_state == emotion)
        if faith: q = q.filter(Subscriber.faith_stage == faith)
        users = q.limit(50).all()
        res = [{"id": u.subscriber_id, "name": u.display_name or "Unknown", "emotion": u.emotional_state, "faith": u.faith_stage} for u in users]
        return json.dumps(res, ensure_ascii=False)

def tool_update_users(args: dict) -> str:
    ids = args.get("ids", [])
    faith = args.get("faith_stage")
    emotion = args.get("emotional_state")
    if not ids: return "Error: No user IDs provided."
    success = 0
    for sid in ids:
        fields = {}
        if faith: fields["faith_stage"] = faith
        if emotion: fields["emotional_state"] = emotion
        if fields:
            update_profile(sid, fields)
            success += 1
    return f"Success: {success} users updated."

def tool_get_categories(args: dict) -> str:
    ctype = args.get("type")
    with get_session() as s:
        q = s.query(Category)
        if ctype: q = q.filter(Category.category_type == ctype)
        cats = [{"type": c.category_type, "name": c.name, "desc": c.description} for c in q.all()]
        return json.dumps(cats, ensure_ascii=False)

def tool_add_category(args: dict) -> str:
    ctype = args.get("type")
    name = args.get("name")
    desc = args.get("desc")
    if not ctype or not name: return "Error: 'type' and 'name' are required."
    with get_session() as s:
        s.add(Category(category_type=ctype, name=name, description=desc))
        s.commit()
    return f"Success: Category '{name}' added to {ctype}."

TOOLS_MAP = {
    "GET_USERS": tool_get_users,
    "UPDATE_USERS": tool_update_users,
    "GET_CATEGORIES": tool_get_categories,
    "ADD_CATEGORY": tool_add_category
}

SYSTEM_PROMPT = """당신은 한국 기독교 복음 AI의 최고 데이터베이스 관리자(Agentic Admin)입니다.
당신은 운영자의 자연어 명령을 해석하여 백엔드 데이터를 조회하거나 수정합니다.

다음 도구(Tool)들을 사용할 수 있습니다:
1. GET_USERS: 조건에 맞는 유저 검색. 파라미터: {"emotion": "...", "faith": "..."}
2. UPDATE_USERS: 유저 일괄 수정. 파라미터: {"ids": ["user_id_1", "user_id_2"], "faith_stage": "...", "emotional_state": "..."}
3. GET_CATEGORIES: 카테고리(분류) 목록 조회. 파라미터: {"type": "faith_stage" 또는 "emotional_state"}
4. ADD_CATEGORY: 카테고리 추가. 파라미터: {"type": "...", "name": "...", "desc": "..."}

도구를 호출하려면 반드시 아래 형식으로 응답하세요:
[CALL: 도구이름]
```json
{ 파라미터 JSON }
```

시스템이 도구 실행 결과를 반환하면, 그 결과를 바탕으로 최종 답변을 작성하세요.
도구 호출이 끝났거나 도구가 필요 없으면 [CALL: ...] 없이 자연스럽게 사용자에게 보고하세요.
주의사항:
- 데이터를 '삭제(Delete)'해달라는 요청은 권한이 없다며 정중히 거절하세요.
- 친절하고 전문적인 톤으로 보고하세요.
"""

@router.post("/chat")
async def agent_chat(req: AgentChatReq, authorization: Optional[str] = Header(default=None)):
    _check_admin(authorization)
    
    messages = [Message(role=m["role"], content=m["content"]) for m in req.history]
    messages.append(Message(role="user", content=req.query))
    
    max_loops = 5
    for _ in range(max_loops):
        resp, _, _ = await chat_with_fallback(
            messages,
            primary_provider="gemini",
            system=SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=1500
        )
        
        reply_text = resp.text.strip()
        
        # Check if LLM wants to call a tool
        call_match = re.search(r"\[CALL:\s*([A-Z_]+)\]\s*```json\s*(\{.*?\})\s*```", reply_text, re.DOTALL)
        if not call_match:
            # No tool call, return final answer
            return {"answer": reply_text, "messages": [{"role": "assistant", "content": reply_text}]}
            
        tool_name = call_match.group(1)
        tool_args_str = call_match.group(2)
        
        messages.append(Message(role="assistant", content=reply_text))
        
        try:
            tool_args = json.loads(tool_args_str)
            if tool_name in TOOLS_MAP:
                tool_result = TOOLS_MAP[tool_name](tool_args)
            else:
                tool_result = f"Error: Unknown tool '{tool_name}'"
        except Exception as e:
            tool_result = f"Error executing tool: {str(e)}"
            
        # Append tool result as system observation
        observation = f"[SYSTEM: Tool {tool_name} returned]\n{tool_result}"
        messages.append(Message(role="user", content=observation))
        
    return {"answer": "내부 처리 횟수 초과. 더 명확하게 명령해주세요.", "messages": []}
