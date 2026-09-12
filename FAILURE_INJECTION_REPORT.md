# Failure Injection Test Report

This report records deterministic runtime behavior, not a production SLO. The
tests use local doubles so they can run without an API key or network service.

## Reproduction

```bash
python -m pytest -q
```

Observed on 2026-09-12:

```text
36 passed in 3.36s
```

## Failure matrix

| ID | Injected condition | Configuration | Expected behavior | Observed result | Evidence |
|---|---|---|---|---|---|
| F-01 | Knowledge tool raises errors twice | `max_attempts=3` | Retry the same tool call and continue after recovery | Run paused at `await_confirmation`; `attempts=3`, `used_fallback=false` | `test_tool_errors_retry_then_succeed` |
| F-02 | Knowledge tool exceeds timeout on every attempt | `max_attempts=2`, `timeout=0.02s` | Stop after bounded retries and use a recorded fallback document | Run paused; `attempts=2`, `used_fallback=true`, first document id is `fallback` | `test_tool_timeout_uses_fallback` |
| F-03 | First two structured model responses are invalid | `max_attempts=3` | Retry validation and accept the third valid response | Run paused at `await_confirmation`; no terminal error | `test_structured_output_recovery_is_bounded` |
| F-04 | Structured model never becomes valid | `max_attempts=3` | End with an audited `run_failed` instead of looping forever | Run failed at `extract`; error records exhausted recovery and final event is `run_failed` | `test_permanent_invalid_output_fails_after_bounded_recovery` |
| F-05 | User declines confirmation | `confirmed=false` | Do not persist or send a candidate reply | Terminal `complete`; `final_reply=null`; no `run_completed` event | `test_decline_does_not_save_or_send` |
| F-06 | User confirms the same run twice | Same `run_id` | Second confirmation is a no-op; recap is saved once | Exactly one `run_completed` event | `test_repeated_resume_is_safe_and_does_not_duplicate_completion` |
| F-07 | Input contains an immediate safety risk | Input includes a threat indicator | Exit before confirmation and do not persist a reply | Terminal `safety_exit`; `pending_confirmation=false` | `test_high_risk_input_exits_before_confirmation` |
| F-08 | Older worker writes a stale checkpoint | Lower `state_version` | Reject the write so newer state cannot be overwritten | `ValueError("stale checkpoint ...")` | `test_checkpoint_version_rejects_stale_state` |
| F-09 | Resume references an unknown run | Missing `run_id` | Return a clear lookup error | `KeyError` | `test_unknown_run_cannot_resume` |
| F-10 | Two threads submit the same next checkpoint version | Shared in-process SQLite store | Allow one write and reject the stale peer without duplicate audit events | One write succeeds, one receives `stale checkpoint`; exactly one concurrent event is appended | `test_concurrent_checkpoint_compare_and_set_allows_one_writer` |
| F-11 | Official MCP stdio server is launched as a subprocess | Official `mcp` SDK v2.2.0 | Discover and invoke a tool across the real stdio transport | `echo` discovered and returned its structured payload; session closed through context manager | `test_official_mcp_stdio_adapter_discovers_and_calls_tool` |

## Audit expectations

Normal confirmed run:

```text
run_started
extraction_completed
retrieval_completed
generation_completed
awaiting_confirmation
confirmation_received
run_completed
```

Failure and safety paths are explicit:

- high-risk input ends with `safety_exit`;
- a declined confirmation ends with `run_cancelled`;
- exhausted model or tool boundaries end with `run_failed`;
- fallback use is included in the `retrieval_completed` payload and in the
  corresponding `ToolOutcome`.

## Scope limits

The current report does not claim throughput, availability, or model quality.
The timeout test uses a local sleeping handler, and the model is deterministic.
The stdio transport and an in-process concurrency race are covered, but this
does not claim multi-process/distributed locking, hosted-model behavior, or
production measurements. Those require a fixed benchmark dataset and a
production deployment environment.
