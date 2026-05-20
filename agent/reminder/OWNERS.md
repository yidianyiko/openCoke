# Reminder System Owners

Ownership system: Reminder System

Boundary spec:
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`

Owns:

- Runtime Reminder Contract
- reminder lifecycle, recurrence, schedule, and reminder domain state
- internal follow-up reminders

Allowed inbound callers:

- Agent Runtime through `agent/reminder/runtime_contract.py`
- Gateway customer reminder API through Reminder-owned route adapters
- Bridge reminder management adapter for internal integration

Verification surfaces:

- `product-reminder`
- `worker-runtime`
