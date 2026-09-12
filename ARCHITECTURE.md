# Runtime Architecture

```mermaid
flowchart TD
    U["User input"] --> X["Extract: validated state"]
    X --> R["Retrieve: MCP tool boundary"]
    R --> G["Generate: candidate replies"]
    G --> S["Safety: risk gate"]
    S -->|"high risk"| E["Safety exit"]
    S -->|"normal or elevated"| C["Interrupt: await confirmation"]
    C -->|"declined"| N["Complete: no side effect"]
    C -->|"confirmed"| P["Persist: idempotency key"]
    P --> D["Complete: saved reply"]

    R -. "timeout/error: bounded retry then fallback" .-> F["Fallback result"]
    F --> G

    X -. "versioned checkpoint" .-> DB[("SQLite run state")]
    R -. "versioned checkpoint" .-> DB
    G -. "versioned checkpoint" .-> DB
    S -. "versioned checkpoint" .-> DB
    C -. "resume boundary" .-> DB
    P -. "versioned checkpoint" .-> DB

    X -. "append-only event" .-> A[("Audit event log")]
    R -. "append-only event" .-> A
    G -. "append-only event" .-> A
    S -. "append-only event" .-> A
    C -. "append-only event" .-> A
    P -. "append-only event" .-> A
```

## Boundary Contract

The workflow owns state transition rules, checkpoint versions, retry budgets,
fallback semantics, confirmation, and audit records. Model and MCP adapters
are replaceable boundaries. The default test path uses deterministic local
adapters; the official MCP adapter is validated against a subprocess stdio
fixture.

## Recovery Scope

- Structured model validation retries are bounded; exhaustion ends in an
  audited `run_failed`.
- Tool timeouts and errors retry within the policy; retrieval can emit a
  recorded fallback result.
- A checkpoint version is accepted at most once by the shared in-process
  SQLite store. This is tested with two threads and does not claim distributed
  coordination.
- A confirmed save uses the run id as an idempotency key; repeated resume after
  completion is a no-op.
