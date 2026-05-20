# Agent Runtime Owners

Ownership system: Agent Runtime

Boundary spec:
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`

Owns:

- turn processing adapters and capability invocation host
- Agno tool wrappers and runtime event capture
- agent-facing adapter integration with owned product contracts

Allowed inbound callers:

- Coke worker runtime turn execution
- Bridge System runtime ingress through worker-owned message processing

Verification surfaces:

- `worker-runtime`
