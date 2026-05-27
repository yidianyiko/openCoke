---
kind: verification_report
surface:
  - worker-runtime
  - production-smoke
created_at: 2026-05-27T08:42:00Z
---

# Personal Reminder Fire Route Key Regression

## Production Reproduction

Production real-user smoke used the olivers account through the live
`/bridge/inbound` path with marker `fire-arch-20260527T083300Z`.

The create path succeeded after the detector/schema fix:

- reminder id: `6a16ac5a01542df2f901c8c1`
- title: `喝水-fire-arch-20260527T083300Z`
- owner: `ck_SXk_J0U0V5JKcK09QHEuo`
- next fire: `2026-05-27T08:35:00Z`

The fire path failed after scheduler execution:

- fire output id: `6a16acb901542df2f901c93c`
- output status: `failed`
- output message: `喝水时间到！🔔 来一杯吧～`
- metadata business key: `bc_6a166d315ce854421a7e2c6f`
- active olivers delivery route business key:
  `bc_6a16459b790c7841638352b4`

Conclusion: the account had a real active delivery route. The failure was not
missing route binding. The worker stored or reused a synthetic
`bc_<conversation_id>` key instead of the trusted bridge/gateway delivery key.

## Red Tests

Command:

```bash
.venv/bin/python -m pytest \
  tests/unit/runner/test_message_acquirer_clawscale.py::test_message_acquirer_persists_inbound_business_key_for_request_response \
  tests/unit/agent/test_agent_runtime_types.py::test_agent_run_context_uses_business_conversation_key_as_route_key \
  tests/unit/agent/test_visible_reminder_protocol_tool.py::test_coke_reminder_adapter_uses_business_conversation_key_as_route_key \
  tests/unit/runner/test_reminder_event_handler.py::test_handler_prefers_event_route_key_over_conversation_business_key \
  -q
```

Result: 4 failed for the expected missing behavior.

## Green Tests

Command:

```bash
.venv/bin/python -m pytest \
  tests/unit/runner/test_message_acquirer_clawscale.py \
  tests/unit/agent/test_agent_runtime_types.py \
  tests/unit/agent/test_visible_reminder_protocol_tool.py \
  tests/unit/agent/test_reminder_command_executor.py \
  tests/unit/runner/test_reminder_event_handler.py \
  tests/unit/agent/test_message_util_clawscale_routing.py \
  tests/unit/runner/test_reminder_message_source.py \
  -q
```

Result: 123 passed.
