# 2026-05-31 Notification Turn Recipient Suppression Evidence

## Production Signal

- Shared reminder `654c9b24-5318-4619-875b-773f08212590` was active for both
  `lizihao` and `olivers`.
- `notification_fact` `069f3fbd-8852-4290-a62a-13ac070b3b3f` had pending
  recipients for both accounts.
- The related `turn.notification` outbox row was published, processed, and
  acked.
- Worker turn `12a6968b-94f5-4578-a454-633066c5d316` completed with
  `no_reply` / `intentional_no_reply`, so no outbound delivery attempt was
  created for `olivers`.

## Fix Verification

Targeted regression:

```text
.venv/bin/python -m pytest \
  tests/unit/coke/worker/test_notification_render_trigger.py::test_notification_event_fans_out_to_recipient_scoped_render_turns \
  tests/integration/coke/test_composition_turn_integration.py::test_notification_render_retries_no_reply_and_delivers_recipients \
  tests/integration/coke/test_composition_turn_integration.py::test_notification_render_persistent_no_reply_fails_recipient_state \
  tests/unit/coke/test_delivery_lifecycle_callbacks.py::test_notification_render_failure_marks_recipient_failed \
  tests/unit/coke/llm/test_interaction_agent.py::test_render_notification_context_exposes_structured_facts_to_agent -q
```

Result: `5 passed in 2.07s`.

Affected-file regression:

```text
.venv/bin/python -m pytest \
  tests/unit/coke/worker/test_notification_render_trigger.py \
  tests/integration/coke/test_composition_turn_integration.py \
  tests/unit/coke/test_delivery_lifecycle_callbacks.py \
  tests/unit/coke/llm/test_interaction_agent.py \
  tests/unit/coke/turn/test_turn_runner.py -q
```

Result: `86 passed in 2.21s`.

Surface verification:

```text
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
```

Result: `549 passed in 17.22s`; `scripts/check` passed.
