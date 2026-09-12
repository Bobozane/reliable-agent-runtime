from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .model import DeterministicConversationModel, StructuredModel
from .models import AgentState, CandidateReply, Extraction, RunResult, SafetyResult
from .reliability import RetryPolicy
from .store import SQLiteRunStore
from .tools import LocalMCPClient, build_local_client, reliable_tool_call


class AgentRuntime:
    """Explicit, resumable workflow. LangGraph can replace this coordinator later."""

    def __init__(
        self,
        *,
        store: SQLiteRunStore | None = None,
        tools: Any | None = None,
        model: StructuredModel | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.store = store or SQLiteRunStore()
        self.tools = tools or build_local_client()
        self.model = model or DeterministicConversationModel()
        self.retry_policy = retry_policy or RetryPolicy()

    def start(self, user_input: str, run_id: str | None = None) -> RunResult:
        state = AgentState(user_input=user_input, run_id=run_id) if run_id else AgentState(user_input=user_input)
        self.store.save_checkpoint(state, event_type="run_started", payload={"input_length": len(user_input)})
        return self._advance(state)

    def resume(self, run_id: str, *, confirmed: bool) -> RunResult:
        state = self.store.load(run_id)
        if state is None:
            raise KeyError(f"unknown run: {run_id}")
        if state.stage != "await_confirmation":
            return RunResult(run_id=run_id, status=state.status, stage=state.stage, state=state, message="run is not waiting for confirmation")
        state.confirmed = confirmed
        state.pending_confirmation = False
        if not confirmed:
            state.status = "complete"
            state.stage = "complete"
            state.final_reply = None
            self._commit(state, "run_cancelled", {"confirmed": False})
            return RunResult(run_id=run_id, status=state.status, stage=state.stage, state=state, message="user declined to send")
        state.stage = "persist"
        state.status = "running"
        self._commit(state, "confirmation_received", {"confirmed": True})
        return self._advance(state)

    def _advance(self, state: AgentState) -> RunResult:
        try:
            if state.stage == "extract":
                state.extraction = self._generate_with_recovery("extract", {"user_input": state.user_input})
                state.stage = "retrieve"
                self._commit(state, "extraction_completed", {"facts": len(state.extraction.facts)})
            if state.stage == "retrieve":
                query = " ".join((state.extraction.needs if state.extraction else []) + [state.user_input])
                result = reliable_tool_call(self.tools, "search_knowledge", {"query": query}, self.retry_policy, fallback=lambda _: [{"id": "fallback", "title": "具体表达", "text": "使用具体观察、感受和请求，避免给对方贴标签。"}])
                state.tool_outcomes.append(self._tool_outcome("search_knowledge", result))
                state.retrieved_docs = result.value or []
                state.stage = "generate"
                self._commit(state, "retrieval_completed", {"documents": len(state.retrieved_docs), "fallback": result.used_fallback})
            if state.stage == "generate":
                if hasattr(self.model, "generate_candidates"):
                    state.candidate_replies = list(self.model.generate_candidates({"user_input": state.user_input, "docs": state.retrieved_docs}))
                else:
                    raise TypeError("model adapter must implement generate_candidates")
                state.stage = "safety"
                self._commit(state, "generation_completed", {"candidates": len(state.candidate_replies)})
            if state.stage == "safety":
                state.safety = self._generate_with_recovery("safety", {"user_input": state.user_input}, schema=SafetyResult)
                if state.safety.level == "high":
                    state.status = "safety_exit"
                    state.stage = "safety_exit"
                    self._commit(state, "safety_exit", {"reasons": state.safety.reasons})
                    return RunResult(run_id=state.run_id, status=state.status, stage=state.stage, state=state, message=state.safety.user_message)
                state.pending_confirmation = True
                state.status = "paused"
                state.stage = "await_confirmation"
                self._commit(state, "awaiting_confirmation", {"candidate_count": len(state.candidate_replies)})
                return RunResult(run_id=state.run_id, status=state.status, stage=state.stage, state=state, message="waiting for explicit user confirmation")
            if state.stage == "persist":
                chosen = state.candidate_replies[0].text
                result = reliable_tool_call(self.tools, "save_recap", {"idempotency_key": state.run_id, "reply": chosen}, self.retry_policy)
                state.tool_outcomes.append(self._tool_outcome("save_recap", result))
                if not result.value:
                    raise RuntimeError(result.error or "save_recap failed")
                state.final_reply = chosen
                state.status = "complete"
                state.stage = "complete"
                self._commit(state, "run_completed", {"saved": True})
            return RunResult(run_id=state.run_id, status=state.status, stage=state.stage, state=state, message="completed")
        except Exception as exc:
            state.status = "failed"
            state.last_error = str(exc)
            self._commit(state, "run_failed", {"error": str(exc)})
            return RunResult(run_id=state.run_id, status=state.status, stage=state.stage, state=state, message=str(exc))

    def _generate_with_recovery(self, task: str, payload: dict[str, Any], schema: Any | None = None):
        schema = schema or Extraction
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                return self.model.generate(task, payload, schema)
            except (ValidationError, ValueError, TypeError) as exc:
                if attempt == self.retry_policy.max_attempts:
                    raise RuntimeError(f"structured output recovery exhausted for {task}: {exc}") from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _tool_outcome(name: str, result: Any):
        from .models import ToolOutcome
        return ToolOutcome(tool=name, ok=result.value is not None, attempts=result.attempts, used_fallback=result.used_fallback, value=result.value, error=result.error)

    def _commit(self, state: AgentState, event_type: str, payload: dict[str, Any]) -> None:
        state.state_version += 1
        self.store.save_checkpoint(state, event_type=event_type, payload=payload)


def demo_runtime(path: str | Path = ":memory:") -> None:
    runtime = AgentRuntime(store=SQLiteRunStore(path))
    first = runtime.start("室友没有提前说就带朋友来宿舍，我很生气，不知道怎么沟通。")
    print(first.run_id, first.status, first.stage)
    second = runtime.resume(first.run_id, confirmed=True)
    print(second.run_id, second.status, second.stage, second.state.final_reply)
    print(runtime.store.events(first.run_id))
