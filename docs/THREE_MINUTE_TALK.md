# Three-Minute Project Talk

## 0:00-0:25 | Problem and positioning

I built a **Reliable Agent Runtime MVP**. The point is not to chain an LLM
call into a demo reply. The runtime owns one Agent run from input to a safe,
user-confirmed side effect: it persists state, calls tools, handles failure,
supports resume, and records an audit trail.

The conversation scenario is only a deterministic workload. The engineering
problem is reusable for research assistants, workflow agents, and any Agent
that needs to survive tool or model failures.

## 0:25-0:55 | Architecture

The workflow is:

```text
extract -> retrieve -> generate -> safety -> await_confirmation -> persist
```

`AgentState` is the contract between stages. Each transition writes a
versioned SQLite checkpoint and an append-only event. The `await_confirmation`
stage is an explicit interrupt: no reply is persisted before the user confirms.

The model and MCP clients are adapters. The workflow does not depend on a
specific model provider or transport.

## 0:55-1:35 | Live demo

I start a run with a roommate-conflict input. The runtime returns
`paused / await_confirmation`, not an automatic send. I inspect the candidate
replies and checkpoint, then call `resume(run_id, confirmed=True)`. The run
ends at `complete`, and `save_recap` receives the run id as its idempotency key.

The audit sequence is:

```text
run_started -> extraction_completed -> retrieval_completed
-> generation_completed -> awaiting_confirmation
-> confirmation_received -> run_completed
```

Calling resume a second time is a no-op, so the side effect is not duplicated.

## 1:35-2:15 | Failure paths

For a tool error, the boundary retries with a bounded budget. For repeated
timeouts, it records the attempts and uses an explicitly marked fallback. For
invalid structured output, Pydantic validation triggers bounded recovery; a
permanently invalid model ends with `run_failed` instead of looping forever.

I also inject a stale checkpoint and two same-version writers. The store
rejects the stale write, and the test only claims this guarantee for one
in-process shared store. A separate subprocess test launches the official MCP
SDK over stdio, discovers `echo`, invokes it, and closes the session.

## 2:15-2:45 | Design choices

I kept the first coordinator as an explicit state machine because its state
transitions are small and inspectable. LangGraph can be added when the system
needs richer graph composition or interrupts; it is not required to prove the
runtime contract. MCP is treated as a tool boundary, not as business logic.

## 2:45-3:00 | Scope and next step

The 36 tests validate deterministic runtime behavior, not production SLO,
model quality, or distributed locking. The next engineering step would be
database-level multi-process compare-and-swap, a hosted structured-model
adapter, and a fixed benchmark for latency, recovery, and task success.
