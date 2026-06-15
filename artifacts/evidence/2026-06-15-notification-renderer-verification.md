# Notification And ReminderFire Renderer Migration Verification

Date: 2026-06-15

Scope:
- Route `NotificationTurn` and `ReminderFireTurn` render turns through the
  stateless Express-style renderer.
- Keep unmigrated render turns on retained render-mode Interaction.
- Preserve notification and reminder-fire delivery lifecycle behavior.
- For ReminderFire, hydrate trusted facts before rendering, pass recent
  conversation history for tone/continuity, and do not run title/time
  string-match validation on the Express path.

Commands:

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/turn/test_turn_runner.py::test_notification_turn_uses_renderer_not_interaction_agent \
  tests/unit/coke/settings/test_settings_composition.py::test_composition_exposes_active_turn_pipeline \
  tests/integration/coke/test_runtime_wiring.py::test_runtime_wires_media_text_resolver_when_media_models_are_configured \
  -q
```

Result: 3 passed.

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_turn_uses_renderer_with_hydrated_facts \
  tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_renderer_accepts_natural_reply_without_fact_literals \
  tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_renderer_receives_recent_conversation_history \
  tests/unit/coke/turn/test_turn_runner.py::test_reminder_fire_renderer_failure_does_not_fallback_or_deliver \
  tests/unit/coke/test_delivery_lifecycle_callbacks.py::test_reminder_fire_render_failure_does_not_mark_fire_delivery \
  tests/unit/coke/turn/inbound/test_express.py::test_reminder_fire_prompt_keeps_history_as_style_context_not_fact_source \
  -q
```

Result: 6 passed.

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/turn/test_turn_runner.py \
  tests/unit/coke/test_delivery_lifecycle_callbacks.py \
  tests/unit/coke/turn/inbound/test_express.py \
  -q
```

Result: 49 passed.

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py -q
```

Result: 78 passed.

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Result:
- suggested command:
  `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs`

```bash
zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs
```

Result:
- `clean-rebuild-docs`: passed.
- `clean-rebuild-backend`: 1011 passed, 1 skipped (`COKE_TEST_DATABASE_URL` not set).
- `repo-os-docs`: passed.

Risk report:

```bash
zsh scripts/review-trigger --base HEAD~1
```

Result:
- `human_review_required: no`
- Risk triggers were docs-sensitive change and oversized diff. No blocking
  human review was required.

```bash
zsh scripts/review-trigger --base HEAD
```

Result:
- `human_review_required: no`
- Risk trigger was docs-sensitive change. The report also listed two unrelated
  untracked May 22 plan files; they were left untouched and unstaged.
