# Test Matrix

Observed with `python -m pytest -q` on 2026-09-12; wall-clock time varies by
machine:

```text
36 passed
```

| Area | Coverage | Count | Evidence |
|---|---|---:|---|
| Normal workflow | Inputs pause at `await_confirmation` with three candidates | 24 | `test_twenty_four_normal_scenarios_pause_for_confirmation` |
| Lifecycle and idempotency | Confirm, decline, unknown run, repeated resume | 4 | `test_resume_requires_confirmation_and_is_audited`, `test_decline_does_not_save_or_send`, `test_unknown_run_cannot_resume`, `test_repeated_resume_is_safe_and_does_not_duplicate_completion` |
| Tool reliability | Error retry and timeout fallback | 2 | `test_tool_errors_retry_then_succeed`, `test_tool_timeout_uses_fallback` |
| Model reliability | Temporary and permanent invalid structured output | 2 | `test_structured_output_recovery_is_bounded`, `test_permanent_invalid_output_fails_after_bounded_recovery` |
| Safety | High-risk input exits before confirmation | 1 | `test_high_risk_input_exits_before_confirmation` |
| Checkpoint safety | Stale write and same-version thread race | 2 | `test_checkpoint_version_rejects_stale_state`, `test_concurrent_checkpoint_compare_and_set_allows_one_writer` |
| MCP transport | Official SDK subprocess stdio discovery and call | 1 | `test_official_mcp_stdio_adapter_discovers_and_calls_tool` |

The count is a deterministic contract check. It is not a task-quality score,
availability target, or distributed-systems guarantee.
