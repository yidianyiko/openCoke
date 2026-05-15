# Agent Capability Contract

This document defines the durable design rule for agent-facing external
capabilities in Coke.

Use this rule when adding or redesigning a capability that an agent can invoke,
such as reminders, memory, calendar import, channel delivery, tasks, or billing
state.

## Core Rule

Every agent-facing external capability must expose a stable domain contract.
Adapters such as Agno tools, HTTP routes, MCP tools, CLI commands, and web UI
must call that contract instead of owning business behavior.

The agent should know what capability it can invoke and what structured result
it receives. It should not know the capability's storage layout, scheduler
mechanism, provider details, gateway tables, or prompt-specific implementation
choices.

## Boundary Shape

Use this shape for new or redesigned capabilities:

```text
Agent
  -> capability port or tool wrapper
  -> domain runtime contract
  -> runtime core
  -> storage, scheduler, provider APIs, or delivery infrastructure
```

For example, the Reminder System should expose a Reminder Runtime Contract.
That contract owns reminder creation, mutation, listing, firing, visibility,
and callback semantics. Agno tools, bridge APIs, future MCP tools, future CLI
commands, and the web board are adapters over that contract.

## Shared Contract Requirements

Capability contracts should define, when relevant:

- `owner` and authenticated scope
- permission and human-approval boundaries
- structured request and response shapes
- stable error taxonomy
- lifecycle states
- visibility semantics
- `idempotency_key` for externally repeatable writes
- `trace_id` or equivalent correlation id
- audit or event records for durable side effects
- callback, delivery, or result-notification semantics

These requirements are shared across capabilities. They are not a license to
collapse different domains into one generic action model.

## Domain Contracts Stay Specific

Do not introduce a universal `GenericAction` or `execute(payload)` abstraction
just because several capabilities share common fields.

Each domain keeps its own contract:

- Reminder: at a future time, bring something back into a context.
- Memory: store or retrieve durable context with provenance.
- Channel delivery: send output to an external route and report delivery
  status.
- Calendar import: preflight, dedupe, and import external calendar events.
- Task or work tracking: represent work state, ownership, blockers, and
  completion.

Shared fields such as owner, visibility, idempotency, and trace belong in the
contract style. Domain behavior belongs in the domain contract.

## Adapter Rule

Adapters translate transport or UI concerns into the domain contract. They must
not become parallel business implementations.

Examples:

- An Agno tool wrapper may collect model-facing arguments, then call the
  contract.
- An HTTP route may authenticate the customer and validate JSON, then call the
  contract.
- An MCP server may expose tool schemas, then call the contract.
- A CLI command may parse flags and print structured output, then call the
  contract.
- A web page may render and submit forms through an API, then call the
  contract indirectly.

If an adapter needs business rules that are not in the contract, update the
contract or add a narrowly scoped domain service. Do not leave the rule only in
the adapter.

## Design Check

Before adding a new agent-facing capability or external entrypoint, answer:

- What is the domain contract?
- Which adapters call it?
- What state does the agent see, and what state stays internal?
- What are the structured success and error shapes?
- Which operations are idempotent?
- How are owner scope, visibility, and human approval enforced?
- What evidence proves the adapter exercises the real contract path?

If these questions cannot be answered, the boundary is not ready for a new
MCP, CLI, HTTP, web, or agent-tool surface.
