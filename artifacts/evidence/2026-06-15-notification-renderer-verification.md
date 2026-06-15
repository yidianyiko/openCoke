# Notification Renderer Migration Verification

Date: 2026-06-15

Scope:
- Route `NotificationTurn` render turns through the stateless Express-style renderer.
- Keep unmigrated render turns on retained render-mode Interaction.
- Preserve notification delivery lifecycle behavior.

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
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -q
```

Result: 12 passed.

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/worker/test_notification_render_trigger.py \
  tests/unit/coke/test_delivery_lifecycle_callbacks.py \
  -q
```

Result: 20 passed.

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/inbound/test_express.py -q
```

Result: 15 passed.

```bash
zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs
```

Result:
- `clean-rebuild-docs`: passed.
- `clean-rebuild-backend`: 1002 passed, 1 skipped (`COKE_TEST_DATABASE_URL` not set).
- `repo-os-docs`: passed.

Risk report:

```bash
zsh scripts/review-trigger --base HEAD~1
```

Initial result before adding this evidence file:
- `human_review_required: no`
- Risk triggers were docs-sensitive change and missing evidence artifact.
