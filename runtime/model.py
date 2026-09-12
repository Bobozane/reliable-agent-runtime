from __future__ import annotations

import json
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from .models import CandidateReply, Extraction, SafetyResult


T = TypeVar("T", bound=BaseModel)


class StructuredModel(Protocol):
    def generate(self, task: str, payload: dict[str, Any], schema: type[T]) -> T: ...


class DeterministicConversationModel:
    """Offline model adapter used for reproducible runtime tests and demos."""

    def __init__(self, *, invalid_outputs: int = 0) -> None:
        self.invalid_outputs = invalid_outputs

    def generate(self, task: str, payload: dict[str, Any], schema: type[T]) -> T:
        if self.invalid_outputs:
            self.invalid_outputs -= 1
            raise ValueError("injected invalid structured output")
        text = str(payload.get("user_input", ""))
        if schema is Extraction:
            return schema.model_validate({
                "facts": [text[:160]],
                "emotions": ["不安" if any(word in text for word in ("生气", "难受", "委屈")) else "困惑"],
                "needs": ["被理解", "明确的下一步"],
                "boundaries": ["避免人身攻击"],
                "goal": "在不升级冲突的前提下表达诉求",
            })
        if schema is list[CandidateReply]:  # pragma: no cover - kept for adapter documentation
            raise TypeError("use CandidateReplyList in a production adapter")
        if schema is SafetyResult:
            high_terms = ("自杀", "伤害我", "暴力", "威胁", "跟踪")
            high = next((term for term in high_terms if term in text), None)
            if high:
                return schema.model_validate({"level": "high", "reasons": [f"包含风险词：{high}"], "user_message": "这可能涉及现实安全风险，请优先联系可信任的人和当地紧急支持。"})
            return schema.model_validate({"level": "normal"})
        raise TypeError(f"unsupported schema: {schema}")

    def generate_candidates(self, payload: dict[str, Any]) -> list[CandidateReply]:
        return [
            CandidateReply(strategy="repair", text="我想把这件事说清楚。我感到有些难受，也想先听听你的感受。我们能找个合适的时间聊十分钟吗？", when_to_use="关系仍可修复，且双方都能冷静沟通时"),
            CandidateReply(strategy="boundary", text="这件事让我不太舒服。我愿意继续讨论，但不接受人身攻击；如果继续发生，我会先暂停这次对话。", when_to_use="需要明确自己的底线时"),
            CandidateReply(strategy="collaboration", text="我们先把具体分工和截止时间写下来，再约定出现问题时怎么提醒彼此。你觉得这样可以吗？", when_to_use="问题主要是任务和责任不清时"),
        ]


def serialize_for_prompt(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)

