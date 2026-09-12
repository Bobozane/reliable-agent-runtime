# English Resume Project Entry

## Project

**Reliable Agent Runtime | Stateful, Recoverable and Auditable Agent Runtime MVP**

## Stack

Python, Pydantic, SQLite, MCP protocol boundary, pytest; an explicit
conditional state workflow with an optional adapter for the official MCP
Python SDK.

## Resume bullets

- Built a stateful Agent Runtime for sensitive conversation workloads with an `extract → retrieve → generate → safety → confirmation → persist` workflow, conditional routing, structured state, and user-confirmation interrupts.
- Implemented timeout handling, exponential backoff, bounded retries, fallback results, structured tool errors, and idempotent persistence at the MCP tool boundary; stored versioned SQLite checkpoints and append-only audit events for resume and replay.
- Enforced model output contracts with Pydantic and added a high-risk safety exit plus a no-send-before-confirmation invariant; created 24 deterministic scenarios and fault-injection tests covering tool errors, timeouts, permanent invalid outputs, duplicate confirmation, stale checkpoints, and an official MCP stdio fixture, with 36 tests passing.

## Interview positioning

This is an independent MVP built around open-source Agent engineering ideas.
The core coordinator is currently an explicit state machine; the official MCP
SDK adapter has a real stdio fixture integration test. I do not claim to have
reimplemented LangGraph or MCP.

## Claims to avoid until measured

- Production availability, throughput, or cost reduction;
- Long-term memory, a full Phoenix deployment, or complex multi-agent debate;
- Unmeasured task success or recovery percentages;
- “Built LangGraph/MCP from scratch.”
