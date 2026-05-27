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

## Deployment

Command:

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

Result: deployment completed; remote health endpoints and public site checks
passed.

## Production Verification After Deploy

Marker: `routefix-20260527T084358Z`

Input through production bridge:

```text
2分钟后提醒我喝水-routefix-20260527T084358Z。
```

Bridge response:

```json
{"ok": true, "reply": "正在处理中，稍后把结果发给你。"}
```

Route queried from production Postgres:

- account: `ck_SXk_J0U0V5JKcK09QHEuo`
- display name: `olivers`
- business route: `bc_6a16459b790c7841638352b4`
- active: `true`

Create result:

- input `_id=6a16af6977c9fa7c817dd7ba`, `status=handled`
- ack output `_id=6a16af87e82b5fb64e88ed40`, `status=handled`
- visible reminder `_id=6a16af83e82b5fb64e88ed3a`
- title: `喝水-routefix-20260527T084358Z`
- `agent_output_target.route_key=bc_6a16459b790c7841638352b4`

Visible fire result:

- reminder lifecycle: `completed`
- `last_fired_at=2026-05-27T08:48:33Z`
- `completed_at=2026-05-27T08:48:37.920000Z`
- `last_error=null`
- fire output `_id=6a16afe5e82b5fb64e88edd0`
- fire output `status=handled`
- fire output metadata
  `business_conversation_key=bc_6a16459b790c7841638352b4`
- gateway `/api/outbound` returned `200`

Supporting internal follow-up:

- reminder `_id=6a16af8fe82b5fb64e88ed4f`
- output `_id=6a16afc6e82b5fb64e88ed9c`
- output `status=handled`
- output metadata used the same real business key.
