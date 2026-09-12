from __future__ import annotations

import tempfile
import sys
import threading
import time
from pathlib import Path

import pytest

from runtime.model import DeterministicConversationModel
from runtime.reliability import RetryPolicy
from runtime.store import SQLiteRunStore
from runtime.tools import FaultInjectingMCPClient, FailurePlan, build_local_client
from runtime.workflow import AgentRuntime


def make_runtime(*, tools=None, model=None, policy=None):
    db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    db.close()
    store = SQLiteRunStore(db.name)
    return AgentRuntime(store=store, tools=tools, model=model, retry_policy=policy), Path(db.name)


@pytest.mark.parametrize("text", [
    "室友总是很晚回宿舍，我有点困扰。", "小组成员没有按时交任务。", "对象回复消息很慢，我感到不安。",
    "同学在群里否定了我的建议。", "我想和朋友讨论一次误会。", "合租公共区域的卫生没有分工。",
    "社团活动安排反复变更。", "队友没有同步项目进度。", "朋友借东西后没有归还。",
    "我不想参加聚会但不知道如何拒绝。", "舍友经常使用我的物品。", "合作伙伴临时改变了计划。",
    "对方说话让我觉得被忽视。", "我和同学对任务标准理解不同。", "朋友把我们的聊天转发了。",
    "我需要请求对方降低音量。", "团队会议中有人反复打断我。", "我想暂停一段争论。",
    "同学忘记了约定的时间。", "我希望明确下一次合作方式。", "室友没有询问就邀请别人来。",
    "对方道歉后同类事情又发生。", "我担心表达边界会破坏关系。", "我不知道如何开始一次困难的对话。",
])
def test_twenty_four_normal_scenarios_pause_for_confirmation(text):
    runtime, path = make_runtime()
    try:
        result = runtime.start(text)
        assert result.status == "paused"
        assert result.stage == "await_confirmation"
        assert result.state.pending_confirmation is True
        assert len(result.state.candidate_replies) == 3
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_resume_requires_confirmation_and_is_audited():
    runtime, path = make_runtime()
    try:
        first = runtime.start("我想和室友讨论卫生分工。")
        assert runtime.store.load(first.run_id).stage == "await_confirmation"
        final = runtime.resume(first.run_id, confirmed=True)
        assert final.status == "complete"
        assert final.stage == "complete"
        assert final.state.final_reply
        names = [event["event_type"] for event in runtime.store.events(first.run_id)]
        assert names[-2:] == ["confirmation_received", "run_completed"]
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_decline_does_not_save_or_send():
    runtime, path = make_runtime()
    try:
        first = runtime.start("我需要拒绝一次不方便的邀请。")
        result = runtime.resume(first.run_id, confirmed=False)
        assert result.status == "complete"
        assert result.state.final_reply is None
        assert all(event["event_type"] != "run_completed" for event in runtime.store.events(first.run_id))
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_tool_errors_retry_then_succeed():
    client = FaultInjectingMCPClient(build_local_client(), {"search_knowledge": FailurePlan(errors=2)})
    runtime, path = make_runtime(tools=client, policy=RetryPolicy(max_attempts=3, timeout_seconds=0.5, backoff_seconds=0))
    try:
        result = runtime.start("我想和同学明确任务分工。")
        outcome = next(item for item in result.state.tool_outcomes if item.tool == "search_knowledge")
        assert result.status == "paused"
        assert outcome.attempts == 3
        assert outcome.used_fallback is False
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_tool_timeout_uses_fallback():
    client = FaultInjectingMCPClient(build_local_client(), {"search_knowledge": FailurePlan(timeouts=3)})
    runtime, path = make_runtime(tools=client, policy=RetryPolicy(max_attempts=2, timeout_seconds=0.02, backoff_seconds=0))
    try:
        result = runtime.start("室友噪音让我很困扰。")
        outcome = next(item for item in result.state.tool_outcomes if item.tool == "search_knowledge")
        assert result.status == "paused"
        assert outcome.used_fallback is True
        assert outcome.attempts == 2
        assert result.state.retrieved_docs[0]["id"] == "fallback"
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_high_risk_input_exits_before_confirmation():
    runtime, path = make_runtime()
    try:
        result = runtime.start("对方威胁要伤害我，我不知道怎么办。")
        assert result.status == "safety_exit"
        assert result.stage == "safety_exit"
        assert result.state.safety.level == "high"
        assert result.state.pending_confirmation is False
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_checkpoint_version_rejects_stale_state():
    runtime, path = make_runtime()
    try:
        first = runtime.start("测试版本。")
        loaded = runtime.store.load(first.run_id)
        with pytest.raises(ValueError, match="stale checkpoint"):
            runtime.store.save_checkpoint(loaded, event_type="stale")
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_structured_output_recovery_is_bounded():
    runtime, path = make_runtime(model=DeterministicConversationModel(invalid_outputs=2), policy=RetryPolicy(max_attempts=3, timeout_seconds=0.1, backoff_seconds=0))
    try:
        result = runtime.start("我想把误会说清楚。")
        assert result.status == "paused"
        assert result.state.last_error is None
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_unknown_run_cannot_resume():
    runtime, path = make_runtime()
    try:
        with pytest.raises(KeyError):
            runtime.resume("missing", confirmed=True)
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_repeated_resume_is_safe_and_does_not_duplicate_completion():
    runtime, path = make_runtime()
    try:
        first = runtime.start("我想确认一次合作安排。")
        final = runtime.resume(first.run_id, confirmed=True)
        repeated = runtime.resume(first.run_id, confirmed=True)
        assert final.status == "complete"
        assert repeated.status == "complete"
        assert repeated.message == "run is not waiting for confirmation"
        assert [event["event_type"] for event in runtime.store.events(first.run_id)].count("run_completed") == 1
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


class PermanentlyInvalidModel:
    """Model double that never returns a schema-valid response."""

    def generate(self, task, payload, schema):
        raise ValueError("permanent invalid structured output")


def test_permanent_invalid_output_fails_after_bounded_recovery():
    runtime, path = make_runtime(
        model=PermanentlyInvalidModel(),
        policy=RetryPolicy(max_attempts=3, timeout_seconds=0.1, backoff_seconds=0),
    )
    try:
        result = runtime.start("杩欐槸涓€涓案杩滄棤鏁堢殑杈撳嚭娴嬭瘯")
        assert result.status == "failed"
        assert result.stage == "extract"
        assert "structured output recovery exhausted" in result.state.last_error
        events = runtime.store.events(result.run_id)
        assert events[-1]["event_type"] == "run_failed"
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_concurrent_checkpoint_compare_and_set_allows_one_writer():
    runtime, path = make_runtime()
    barrier = threading.Barrier(2)
    outcomes = []
    try:
        first = runtime.start("骞惧彂 checkpoint 娴嬭瘯")
        baseline = runtime.store.load(first.run_id)

        def writer(stage):
            state = baseline.model_copy(deep=True)
            state.stage = stage
            state.state_version += 1
            barrier.wait()
            try:
                runtime.store.save_checkpoint(state, event_type=f"concurrent_{stage}")
                outcomes.append("saved")
            except ValueError as exc:
                outcomes.append(str(exc))

        threads = [threading.Thread(target=writer, args=(stage,)) for stage in ("retrieve", "generate")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        assert sum(value == "saved" for value in outcomes) == 1
        assert sum("stale checkpoint" in value for value in outcomes) == 1
        current = runtime.store.load(first.run_id)
        assert current.state_version == baseline.state_version + 1
        event_types = [event["event_type"] for event in runtime.store.events(first.run_id)]
        assert sum(event.startswith("concurrent_") for event in event_types) == 1
    finally:
        runtime.store.close()
        path.unlink(missing_ok=True)


def test_official_mcp_stdio_adapter_discovers_and_calls_tool():
    pytest.importorskip("mcp")
    from runtime.official_mcp import MCPServerConfig, OfficialMCPClient

    server_path = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"
    with OfficialMCPClient(MCPServerConfig(command=sys.executable, args=(str(server_path),))) as client:
        tools = client.list_tools()
        assert any(tool.name == "echo" for tool in tools)
        assert client.call_tool("echo", {"query": "hello"}) == {"query": "hello", "source": "stdio-fixture"}
