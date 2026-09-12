# Agent R&D Interview Q&A

## 1. Why is this an Agent Runtime rather than a normal LLM call?

The system has a persisted state, conditional transitions, external tool
calls, bounded recovery, user interruption, and an auditable event history. A
normal LLM call does not define what happens after a timeout, process restart,
duplicate confirmation, or unsafe input.

## 2. Why did you not force LangGraph into the first version?

The existing coordinator only needed a small explicit state machine. I kept the
state and adapter boundaries independent so LangGraph can be introduced when
there is a real need for graph visualization, parallel branches, or richer
interrupt semantics. Adding a framework without using those capabilities would
hide the runtime behavior rather than validate it.

## 3. What is persisted in a checkpoint?

The `AgentState` includes the run id, state version, current stage and status,
validated extraction, retrieved documents, candidate replies, safety result,
confirmation status, tool outcomes, errors, and timestamps. The next stage is
the resumable boundary; transient thread objects are not persisted.

## 4. How do you prevent an old worker from overwriting newer state?

Every checkpoint increments `state_version`. The SQLite store compares the
incoming version with the stored version and rejects stale or equal writes. A
production implementation would add an atomic compare-and-swap or database
transaction around the version check and write.

## 5. How does retry differ from fallback?

Retry repeats the same operation within a bounded attempt budget. Fallback is a
different, explicitly marked result used after the retry budget is exhausted.
The audit event and `ToolOutcome` record attempts, fallback usage, and the last
error, so a fallback is never presented as a normal retrieval success.

## 6. What happens when a tool times out?

The call is executed in a worker with a timeout. The runtime cancels the future
where possible, records a timeout error, applies bounded backoff, and then uses
the configured fallback or returns a structured failure. The sleeping local
fault-injection handler demonstrates that the workflow does not wait for the
timed-out worker before proceeding.

## 7. How do you prevent duplicate side effects?

The save tool receives the run id as an idempotency key. The local tool stores
the first result for that key and returns the same result on repeat calls. The
workflow also makes repeated `resume` calls after completion a no-op.

## 8. How do you control invalid LLM output?

The model adapter returns Pydantic models rather than untyped dictionaries.
Validation failures are retried within a separate bounded budget. If the
budget is exhausted, the run emits `run_failed`; it does not silently coerce an
unsafe or malformed result.

## 9. Why is safety a separate workflow node?

Safety must run before the confirmation and persistence boundary. Keeping it as
a visible node makes the invariant testable: high-risk input exits through
`safety_exit`, and no candidate reply is saved. It also prevents safety logic
from being hidden inside a prompt string.

## 10. Why use MCP here?

MCP gives tools a discoverable schema and a transport boundary. The runtime can
test against local doubles, then connect to a real server through the optional
official SDK adapter without changing retry, fallback, or audit behavior.

## 11. How do you evaluate this system?

The first evaluation is deterministic runtime behavior: 24 normal scenarios
plus injected tool errors, timeouts, malformed model output, stale writes,
duplicate confirmation, and high-risk input. The next layer should measure
task success, recovery rate, latency, and token cost against a fixed benchmark;
the current MVP does not claim those production metrics.

## 12. What are the current limitations?

The model and local MCP tools are deterministic test doubles. There is no
distributed lock, queue, hosted model, real network transport, or production
observability deployment. The code validates the runtime contract first; those
components are the next integration steps, not hidden capabilities.

## 13. What would you improve next?

First, compare real transport failures with local fault injection. Next, add
database-level compare-and-swap for multi-process checkpointing. Then add a
hosted structured-model adapter, trace export, and a benchmark report with
pre-registered metrics.

## 14. What part did you write yourself?

I designed the state contract, transition rules, checkpoint schema, retry and
fallback policy, idempotency behavior, audit events, safety boundary, fault
injection plan, and tests. Open-source frameworks are treated as replaceable
infrastructure, with attribution kept in the project documentation.
