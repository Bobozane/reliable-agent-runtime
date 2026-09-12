from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


Stage = Literal[
    "extract",
    "retrieve",
    "generate",
    "safety",
    "await_confirmation",
    "persist",
    "complete",
    "safety_exit",
]
RunStatus = Literal["running", "paused", "complete", "failed", "safety_exit"]


class Extraction(BaseModel):
    facts: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    goal: str = "理解冲突并选择合适的沟通方式"


class CandidateReply(BaseModel):
    strategy: Literal["repair", "boundary", "collaboration"]
    text: str = Field(min_length=1, max_length=800)
    when_to_use: str = Field(min_length=1, max_length=200)


class SafetyResult(BaseModel):
    level: Literal["normal", "elevated", "high"] = "normal"
    reasons: list[str] = Field(default_factory=list)
    user_message: str = ""


class ToolOutcome(BaseModel):
    tool: str
    ok: bool
    attempts: int = 1
    used_fallback: bool = False
    value: Any = None
    error: str | None = None


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: uuid4().hex)
    state_version: int = 0
    stage: Stage = "extract"
    status: RunStatus = "running"
    user_input: str
    extraction: Extraction | None = None
    retrieved_docs: list[dict[str, Any]] = Field(default_factory=list)
    candidate_replies: list[CandidateReply] = Field(default_factory=list)
    safety: SafetyResult | None = None
    pending_confirmation: bool = False
    confirmed: bool = False
    final_reply: str | None = None
    tool_outcomes: list[ToolOutcome] = Field(default_factory=list)
    attempts: dict[str, int] = Field(default_factory=dict)
    last_error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RunResult(BaseModel):
    run_id: str
    status: RunStatus
    stage: Stage
    state: AgentState
    message: str = ""

