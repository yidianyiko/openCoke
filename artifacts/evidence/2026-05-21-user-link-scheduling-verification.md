# User Link Scheduling Verification

Date: 2026-05-21

## Environment Notes

- Root branch: `user-link-scheduling`; Gateway branch: `user-link-scheduling-gateway`.
- Gateway scheduling implementation is verified through nested Gateway commit `4b5608a`.
- `memo-runtime` could not be checked out at the root gitlink commit because local source `/data/projects/coke-memo-runtime` does not contain `769aa46bf1d3e5f769236913846230fe4b0c654f`; a local uncommitted `memo-runtime/OWNERS.md` fixture was used only so repo-OS guardrails could read the required metadata file.
- Gateway API/Web package test scripts run their full package suites even when file paths are supplied.
- `zsh scripts/verify-surface product-memo` fails because that script invokes `pytest memo-runtime/tests` from the root cwd while memo-runtime schema tests read paths relative to the submodule root. Running the same submodule test suite from `memo-runtime/` passed.

## Command Results

### pnpm --dir gateway/packages/api test -- src/scheduling/appointment-service.test.ts src/scheduling/notification-service.test.ts src/scheduling/schema-contract.test.ts

Exit code: 0

```text
Test Files  76 passed (76)
Tests  686 passed (686)
```

### pnpm --dir gateway/packages/api build

Exit code: 0

```text
> @clawscale/api@0.1.0 build /data/projects/coke/.worktrees/user-link-scheduling/gateway/packages/api
> tsc -p tsconfig.json
```

### pnpm --dir gateway/packages/web test -- 'app/u/[code]/page.test.tsx' 'app/u/[code]/qr/route.test.ts' 'app/(customer)/auth/login/page.test.tsx' 'app/(customer)/auth/register/page.test.tsx' 'app/(customer)/auth/verify-email/page.test.tsx'

Exit code: 0

```text
Test Files  43 passed (43)
Tests  166 passed (166)
```

### pnpm --dir gateway/packages/web build

Exit code: 0

```text
├ ○ /auth/forgot-password
├ ○ /auth/login
├ ○ /auth/register
├ ○ /auth/reset-password
├ ○ /auth/verify-email
├ ○ /channels
├ ○ /channels/wechat-personal
├ ○ /demos
├ ○ /faqs
├ ○ /global
├ ○ /handoff/calendar-import
├ ○ /privacy
├ ○ /terms
├ ƒ /u/[code]
└ ƒ /u/[code]/qr

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```

### .venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_chat_response_scheduling_instructions.py -v

Exit code: 0

```text
85 passed in 3.34s
```

### Gateway final code review

Exit code: n/a

```text
No correctness blockers found in the latest Gateway diff (4b5608a^..4b5608a).
Prior replay-notification, scoped transition idempotency, and request idempotency uniqueness findings were verified fixed.
Residual risk: notification ensuring is covered at service-unit level rather than a real DB integration path with Prisma unique conflicts.
```

### zsh scripts/suggest-verification --base HEAD~1

Exit code: 0

```text
suggested_command: zsh scripts/verify-surface repo-os-docs product-memo
```

### zsh scripts/verify-surface repo-os-docs gateway-api gateway-web bridge worker-runtime

Exit code: 0

```text
Completed repo-os-docs, gateway-api, gateway-web, bridge, and worker-runtime verification surfaces successfully.
```

### zsh scripts/review-trigger --base HEAD~1

Exit code: 0

```text
human_review_required: no
```

### zsh scripts/verify-surface product-memo

Exit code: 1

```text
FileNotFoundError: [Errno 2] No such file or directory: 'memo_runtime/storage/postgres.py'
FAILED memo-runtime/tests/test_postgres_schema.py::test_initial_schema_contains_core_tables_and_indexes
FAILED memo-runtime/tests/test_postgres_schema.py::test_review_items_allow_proposal_card_ids
FAILED memo-runtime/tests/test_postgres_schema.py::test_event_idempotency_index_is_not_unique
FAILED memo-runtime/tests/test_postgres_schema.py::test_mutations_store_result_snapshots_for_idempotent_replay
FAILED memo-runtime/tests/test_postgres_schema.py::test_postgres_proposal_transitions_are_status_guarded
FAILED memo-runtime/tests/test_postgres_schema.py::test_postgres_empty_mutation_snapshots_fail_closed
```

### (cd memo-runtime && ../.venv/bin/python -m pytest tests -v)

Exit code: 0

```text
38 passed, 3 skipped
```

## Final Task 8 Addendum

Date: 2026-05-22

### Final Commit Context

- Root branch: `feature/friend-link-shared-reminders`.
- Root docs/gitlink commit: final Task 8 commit containing this addendum.
- Gateway gitlink commit recorded by root: `e007781db16afbfabdda6e8ebdc7d6f83f74f566`.
- The final `HEAD~1..HEAD` diff contains repo docs, the retention consistency
  test, and the parent `gateway` gitlink. Earlier Task 1-7 runtime, bridge,
  Gateway API, and Gateway Web changes were verified before the final docs
  commit; therefore fresh diff-aware routing on the final commit narrows to the
  repo-OS docs surface.

### zsh scripts/suggest-verification --base HEAD~1

Exit code: 0

```text
changed_surfaces: repo-os-docs
suggested_command: zsh scripts/verify-surface repo-os-docs
```

### zsh scripts/review-trigger --base HEAD~1

Exit code: 1

```text
human_review_required: yes
- sensitive_repo_os_change [medium]
  reason: changed path: docs/ARCHITECTURE.md
  reason: changed path: docs/design-docs/data-retention-policy.md
  reason: changed path: docs/product-specs/FEATURE_TREE.md
```

Required review gate: human review is required before merge because
`review-trigger` returned `human_review_required: yes` for the final Task 8
commit.

### Focused Final Verification

Exit code: 0 for all commands below.

```text
pnpm --dir gateway/packages/api test -- src/scheduling src/routes/public-user-link-routes.test.ts src/routes/customer-scheduling-routes.test.ts src/routes/internal-scheduling-routes.test.ts src/lib/reminder-runtime-client.test.ts
Test Files 74 passed; Tests 758 passed.

pnpm --dir gateway/packages/web test -- app/u/[code]/page.test.tsx app/u/[code]/claim-handoff.test.tsx app/u/[code]/qr/route.test.ts lib/user-link-api.test.ts
Test Files 45 passed; Tests 173 passed.

.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_scheduling_types.py tests/unit/test_data_retention_policy_consistency.py -q
52 passed.

zsh scripts/check
passed.

git diff --check
passed.
```
