# Agent R&D Code Walkthrough

Use this order in a code interview. It follows one run from contract to
failure recovery, then ends at the transport boundary.

## 1. State contract: `runtime/models.py`

Start with `AgentState`. Point out `stage`, `status`, `state_version`, the
validated extraction and candidates, confirmation flags, tool outcomes, and
`last_error`. The persisted state contains the next resumable boundary; it
does not contain transient thread or event-loop objects.

## 2. Coordinator: `runtime/workflow.py`

Read `AgentRuntime.start`, `resume`, and `_advance` in that order.

- `start` creates the state and records `run_started`.
- `_advance` performs the explicit stage transitions.
- `safety` is before confirmation and persistence, making the no-send-before-
  confirmation invariant visible and testable.
- `resume` only advances a run waiting at `await_confirmation`.
- `_commit` increments the state version before every persisted transition.

Then show `_generate_with_recovery`: schema failures are retried within a
bounded budget and become an audited terminal failure when exhausted.

## 3. Tool reliability: `runtime/reliability.py`

`call_with_retry` wraps one operation with a timeout, exponential backoff, a
maximum attempt count, and an optional fallback. The return value is a
`RetryResult`, so the workflow can record attempts, fallback usage, and the
last error without treating fallback data as a normal success.

## 4. Persistence and audit: `runtime/store.py`

`save_checkpoint` writes the run row and event in one SQLite transaction. The
in-process `RLock` protects the version check and write when two threads share
one store. A lower or equal version raises `stale checkpoint`; the concurrency
test verifies that only one same-version writer appends an event.

Be explicit that this is not a distributed lock or a multi-process CAS.

## 5. MCP boundary: `runtime/official_mcp.py`

The adapter owns one asynchronous official MCP stdio session in a background
event loop and exposes synchronous `list_tools` and `call_tool` methods to the
runtime. The workflow therefore keeps retry, fallback, confirmation, and
audit semantics independent from transport details.

## 6. Evidence: `tests/test_runtime.py`

Show the 24 normal scenarios first, then the focused tests for tool errors,
timeouts, temporary and permanent invalid output, safety exit, stale writes,
same-version concurrency, repeated resume, and real stdio MCP integration.
Finish with `FAILURE_INJECTION_REPORT.md`: it reports observed deterministic
behavior and deliberately does not call it a production SLO.
