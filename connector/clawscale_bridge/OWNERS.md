# Bridge System Owners

Ownership system: Bridge System

Boundary spec:
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`

Owns:

- Coke ingress protocol adaptation
- Coke egress protocol adaptation
- synchronous reply waiting and late reply promotion

Allowed inbound callers:

- Channel System and Gateway internal integration routes
- Agent Runtime output flow through bridge dispatchers

Verification surfaces:

- `bridge`
- `gateway-api`
