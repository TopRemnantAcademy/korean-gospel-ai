"""멘토링 5단계 파이프라인 — Pydantic 구조체."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


FaithStatus = Literal[
    "unknown", "unbeliever", "new_believer", "believer",
    "lifelong_christian", "other_religion", "other",
]


class UserProfileSlots(BaseModel):
    age_band: Optional[str] = None
    faith_status: FaithStatus = "unknown"
    addiction_types: list[str] = Field(default_factory=list)
    family_context: Optional[str] = None
    notes: Optional[str] = None
    confidence: float = 0.0


class CrisisAssessment(BaseModel):
    risk_score: int = Field(ge=1, le=10, default=1)
    categories: list[str] = Field(default_factory=list)
    rationale: str = ""
    hijack: bool = False


class ContextSummary(BaseModel):
    one_line_summary: str = ""
    compressed: bool = False


class EvaluationResult(BaseModel):
    passed: bool = True
    doctrine_score: float = Field(ge=0, le=1, default=1.0)
    empathy_score: float = Field(ge=0, le=1, default=1.0)
    addiction_score: float = Field(ge=0, le=1, default=1.0)
    issues: list[str] = Field(default_factory=list)
    corrected_answer: Optional[str] = None


class MentorRuntimeSettings(BaseModel):
    llm_route: Literal["auto", "gemini", "deepseek"] = "auto"
    crisis_threshold: int = Field(default=8, ge=1, le=10)
    disclaimer_enforced: bool = True


class MentorChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    history: list[dict[str, str]] = Field(default_factory=list)
    profile_override: Optional[UserProfileSlots] = None


class PipelineStagePayload(BaseModel):
    stage: str
    data: dict[str, Any] = Field(default_factory=dict)
