# Coke Verification Matrix

Use this matrix to choose the smallest useful verification set for the surfaces
you changed.

Default entrypoint:

```bash
zsh scripts/verify-surface <surface>
```

Use `--dry-run` when you want to inspect the command mapping without executing
it.

## Repo OS Docs

Use when changing:

- `AGENTS.md`, `CLAUDE.md`, `README.md`
- `docs/ARCHITECTURE.md` and compatibility symlink `docs/architecture.md`
- `docs/design-docs/`, `docs/adr/`, `docs/superpowers/`,
- `docs/issues/`, `docs/product-specs/`
- `docs/design-docs/human-ai-working-contract.md`
- `docs/fitness/README.md`
- `docs/fitness/coke-verification-matrix.md`
- `docs/release-guide.md`, `docs/RELEASE_CHECKLIST.md`
- `artifacts/evidence/`

Commands:

```bash
zsh scripts/check
```

## Repo OS Tooling

Use when changing:

- `docs/fitness/surfaces.yaml`
- `scripts/check`
- `scripts/verify-surface`
- `scripts/suggest-verification`
- `scripts/review-trigger`
- `scripts/guardrails.py`
- `tests/unit/test_repo_os_structure.py`
- `tests/unit/test_guardrail_scripts.py`

Commands:

```bash
pytest tests/unit/test_repo_os_structure.py -v
pytest tests/unit/test_guardrail_scripts.py -v
zsh scripts/check
```

## Worker Runtime

Use when changing:

- `agent/runner/agent_runner.py`
- `agent/runner/message_processor.py`
- `agent/runner/agent_handler.py`
- `agent/runner/reminder_scheduler.py`
- `agent/runner/reminder_event_handler.py`
- `agent/agno_agent/runtime/`
- `agent/agno_agent/capabilities/`
- `agent/agno_agent/adapters/`
- `agent/agno_agent/schemas/`
- `agent/agno_agent/model_factory.py`
- `agent/agno_agent/workflows/`
- `agent/agno_agent/tools/`
- `agent/reminder/`
- `dao/reminder_dao.py`
- `agent/agno_agent/tools/reminder_protocol/`
- `dao/pending_workflow_dao.py`
- `agent/prompt/`

Baseline commands:

```bash
pytest tests/unit/runner/ -v
pytest tests/unit/agent/ -v
pytest tests/unit/test_clawscale_only_topology.py -v
```

Runtime-facing changes often need stronger evidence than this baseline. When a
change affects user-visible reminder behavior, single-Agent runtime orchestration, LLM
provider selection, or scheduler/executor delivery, add the focused command set
below or a documented runtime/eval smoke. Do not treat the baseline as proof of
user-visible behavior when the changed path is mostly exercised through mocks.

Single-Agent runtime commands:

```bash
.venv/bin/python -m pytest tests/unit/agent/ tests/unit/runner/ -v
.venv/bin/python scripts/simulate_user_path.py --case-index 0
```

Focused reminder-system command set:

```bash
pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py tests/unit/runner/test_reminder_message_source.py -v
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v
pytest tests/unit/agent/test_severity_thresholds.py -v
pytest tests/e2e/test_reminder_system_flow.py -v
```

Customer reminder web management command set:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_service.py tests/unit/dao/test_reminder_dao.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -k "reminder or reminders" -v
cd gateway/packages/api && npm test -- src/lib/reminder-runtime-client.test.ts src/routes/customer-reminder-routes.test.ts
cd gateway/packages/web && npm test -- lib/customer-reminders.test.ts app/'(customer)'/account/reminders/page.test.tsx app/'(customer)'/account/layout.test.tsx
cd gateway/packages/api && npm run build
cd gateway/packages/web && npm run lint -- app/'(customer)'/account/reminders/page.tsx lib/customer-reminders.ts components/customer-shell.tsx app/'(customer)'/account/layout.test.tsx
```

Severity-tiered corpus check (run before merging changes to the prompt or
guard helpers; see `docs/design-docs/reminder-corpus-severity.md`):

```bash
.venv/bin/python scripts/run_reminder_eval.py --run-all
# exit 0 requires critical=100%, important>=95%, nice>=80%.
```

Focused pending-workflow command set (feature-flagged, default off):

```bash
pytest tests/unit/agent/test_pending_workflow_models.py tests/unit/dao/test_pending_workflow_dao.py -v
```

## Bridge

Use when changing:

- `connector/clawscale_bridge/app.py`
- `connector/clawscale_bridge/output_dispatcher.py`
- `connector/clawscale_bridge/` helpers

Baseline commands:

```bash
pytest tests/unit/connector/clawscale_bridge/ -v
pytest tests/unit/agent/test_message_util_clawscale_routing.py -v
```

Targeted subsets are acceptable when the task is narrow, but the task or plan
should say exactly which tests cover the touched paths.

## Gateway API

Use when changing:

- `gateway/packages/api`
- `gateway/packages/shared`

Baseline commands:

```bash
pnpm --dir gateway/packages/api test
```

For narrow tasks, run targeted Vitest files first, then broaden if the change
crosses shared routing, schema, auth, or outbound logic.

## Gateway Calendar Import

Use when changing:

- `gateway/packages/api` claim-entry, Google OAuth, or import routes
- `gateway/packages/web` claim-entry or calendar import pages

Commands:

```bash
pnpm --dir gateway/packages/api test -- src/routes/customer-claim-routes.test.ts src/routes/customer-google-calendar-import-routes.test.ts
pnpm --dir gateway/packages/web test -- 'app/(customer)/auth/claim-entry/page.test.tsx' 'app/(customer)/auth/claim/page.test.tsx' 'app/(customer)/account/calendar-import/page.test.tsx'
```

## Bridge Calendar Import Runtime

Use when changing:

- `connector/clawscale_bridge/google_calendar_import_service.py`
- import-aware conversation resolution or reminder creation helpers in the worker/runtime boundary

Commands:

```bash
pytest tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v
pytest tests/unit/dao/test_conversation_dao_calendar_import.py tests/unit/dao/test_reminder_dao_find_imported_duplicate.py tests/unit/reminder/test_service_create_imported.py tests/unit/reminder/test_service_historical_import.py -v
```

## Gateway Web

Use when changing:

- `gateway/packages/web`

Baseline commands:

```bash
pnpm --dir gateway/packages/web test
```

For narrow tasks, targeted page/component tests are preferred before the full
suite.

## Deployment And Rollout

Use when changing:

- `scripts/deploy-compose-to-gcp.sh`
- `docker-compose.prod.yml`
- `deploy/nginx/coke.conf`
- `deploy/systemd/coke-compose.service`
- deployment sections in `docs/deploy.md`

Baseline commands:

```bash
bash scripts/test-deploy-compose-to-gcp.sh
zsh scripts/check
```

If the change affects live rollout behavior, also follow the smoke steps in
`docs/deploy.md`.

## Cross-Surface Changes

If a task spans multiple surfaces, combine the matching verification sets
instead of inventing a new vague one-liner.

Examples:

- `connector/clawscale_bridge/app.py` + `gateway/packages/api`:
  - `pytest tests/unit/connector/clawscale_bridge/ -v`
  - `pnpm --dir gateway/packages/api test`
- `README.md` + `scripts/check` + deploy docs:
  - `pytest tests/unit/test_repo_os_structure.py -v`
  - `zsh scripts/check`
  - `bash scripts/test-deploy-compose-to-gcp.sh`
