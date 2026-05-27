# Gateway-Hosted Scheduling Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Scheduling from route-owned behavior to a Gateway-hosted, contract-owned domain boundary, then close the multi-pending shared-reminder regression class.

**Architecture:** Gateway keeps hosting Scheduling, but route handlers become adapters over `SchedulingDomainContract`. Scheduling owns Postgres shared-reminder/focus state, Reminder Runtime access goes through a port, and Agent Runtime obtains actionable focus through the Scheduling contract instead of trusting inbound `product_notification` candidates.

**Tech Stack:** Hono, TypeScript, Prisma/Postgres, Vitest, Python Agent Runtime, pytest, Coke bridge/deploy scripts.

---

### Task 1: Contract Inventory And Drift Fixtures

**Files:**
- Create: `gateway/packages/api/src/scheduling/runtime-contract-fixtures.ts`
- Modify: `gateway/packages/api/src/scheduling/schema-contract.test.ts`
- Modify: `tests/unit/agent/test_scheduling_capability.py`

- [ ] **Step 1: Add shared fixture definitions**

Define the supported tool names, read/write classification, stable error codes, and response DTO keys in `runtime-contract-fixtures.ts`. Include future fixture records for `resolve_agent_focus`, `bind_agent_focus_selection`, and bulk shared-reminder tools as data only.

- [ ] **Step 2: Add executable TS fixture checks**

Assert current Gateway route/service names match the fixture for existing operations. Do not assert future operations until their implementation tasks.

- [ ] **Step 3: Add Python fixture parity checks**

Load the same fixture or mirror its current tool list in a focused pytest to make `SCHEDULING_TOOL_NAMES` drift visible.

- [ ] **Step 4: Verify**

Run:

```bash
cd gateway/packages/api && pnpm vitest run src/scheduling/schema-contract.test.ts
.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py -q
```

Expected: tests pass before behavior refactors.

### Task 2: SchedulingDomainContract Facade And Thin Routes

**Files:**
- Create: `gateway/packages/api/src/scheduling/runtime-contract.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`
- Modify: `gateway/packages/api/src/routes/customer-scheduling-routes.test.ts`

- [ ] **Step 1: Introduce the contract facade**

Move route-local tool dispatch, friend/request resolution, error taxonomy, and Reminder Runtime port wiring behind `createSchedulingDomainContract({ db, reminderRuntime })`.

- [ ] **Step 2: Keep routes as adapters**

Routes may authorize, parse JSON, validate transport fields, call the contract, and serialize `{ ok, data | error }`. They must not query `sharedReminderRequest` directly or call scheduling services directly.

- [ ] **Step 3: Preserve HTTP paths**

Keep `/api/internal/scheduling/tools/:toolName`, `/api/internal/scheduling/notifications/retry`, and current customer scheduling paths stable.

- [ ] **Step 4: Verify**

Run:

```bash
cd gateway/packages/api && pnpm vitest run src/routes/internal-scheduling-routes.test.ts src/routes/customer-scheduling-routes.test.ts
```

Expected: existing route behavior stays green while mocks target the contract boundary.

### Task 3: Business-Key Idempotency

**Files:**
- Create: `gateway/packages/api/prisma/migrations/20260528090000_shared_reminder_business_key/migration.sql`
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`
- Modify: `gateway/packages/api/src/scheduling/schema-contract.test.ts`

- [ ] **Step 1: Add NULL-safe partial unique index**

Add raw SQL:

```sql
CREATE UNIQUE INDEX "shared_reminder_requests_pending_business_key"
ON "shared_reminder_requests" (
  "requester_account_id",
  "invitee_account_id",
  "title",
  "fire_at",
  "timezone",
  COALESCE("duration_minutes", -1)
)
WHERE "status" = 'pending_invitee_confirmation';
```

- [ ] **Step 2: Return existing pending row on business-key collision**

In `createSharedReminder`, if `sharedReminderRequest.create` raises a unique conflict and the per-turn idempotency lookup misses, look up an existing pending request by the business key and return it after projection reconciliation with `already_pending: true`.

- [ ] **Step 3: Preserve legitimate re-invite**

Ensure rejected/cancelled/accepted/expired rows no longer participate in the partial index because status changes happen in the same transition update.

- [ ] **Step 4: Verify**

Run:

```bash
cd gateway/packages/api && pnpm vitest run src/scheduling/shared-reminder-service.test.ts src/scheduling/schema-contract.test.ts
```

Expected: duplicate pending creates collapse, `duration_minutes = NULL` duplicates collapse, and post-rejection re-invite succeeds.

### Task 4: Scheduling-Owned Focus Binding

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260528100000_scheduling_focus_bindings/migration.sql`
- Create: `gateway/packages/api/src/scheduling/focus-binding-service.ts`
- Create: `gateway/packages/api/src/scheduling/focus-binding-service.test.ts`
- Modify: `gateway/packages/api/src/scheduling/runtime-contract.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`

- [ ] **Step 1: Add Postgres focus binding storage**

Add Scheduling-owned focus binding rows keyed by opaque `focus_token`, with actor account, conversation key, state, expires-at, and candidate handle rows that map opaque handles to request IDs and kind.

- [ ] **Step 2: Implement `resolveAgentFocus`**

Return `none_actionable`, `single`, or `multi_pending` by reading current pending actionable friend/shared-reminder state for the actor and conversation. Candidate summaries must be domain DTOs, not raw Prisma rows.

- [ ] **Step 3: Implement `bindAgentFocusSelection`**

Validate token, handle, expiry, and current request state. Return typed conflicts: `already_consumed`, `expired`, or `unknown_handle`.

- [ ] **Step 4: Add endpoints**

Add internal endpoints under `/api/internal/scheduling/focus/resolve` and `/api/internal/scheduling/focus/bind` through the contract facade.

- [ ] **Step 5: Verify**

Run:

```bash
cd gateway/packages/api && pnpm vitest run src/scheduling/focus-binding-service.test.ts src/routes/internal-scheduling-routes.test.ts
```

Expected: focus tokens/handles are opaque, multi-pending candidates bind across turns, and stale/consumed selections fail closed.

### Task 5: Python Scheduling Contract Client And Agent Session Binding

**Files:**
- Modify: `agent/agno_agent/capabilities/scheduling.py`
- Modify: `agent/agno_agent/runtime/focus.py`
- Modify: `agent/agno_agent/runtime/semantic_interpreter.py`
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `tests/unit/agent/test_focus_channel.py`
- Modify: `tests/unit/agent/test_semantic_interpreter.py`
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`
- Modify: `tests/unit/agent/test_scheduling_capability.py`

- [ ] **Step 1: Rename/wrap Gateway client as contract client**

Keep backwards-compatible class imports only if tests require them, but new calls should use `SchedulingContractClient` methods for tools, focus resolve, and focus bind.

- [ ] **Step 2: Resolve focus from Scheduling**

Agent runtime should call `resolve_agent_focus` using `customer_id`, `conversation_id`, `platform`, and timezone. `product_notification` may remain only as an actionable hint, not the source of candidate truth.

- [ ] **Step 3: Persist disambiguation session**

Store `focus_token`, offered handles, rendered enumeration text, expected action, and expiry in `run_context.session_state`/`agent_sessions` compatible JSON.

- [ ] **Step 4: Extend semantic interpreter**

Allow ordinal, delivery-time, and summary-text references to resolve against offered handles and return the matched `handle` in `args`. Do not add Python regex/keyword routing for language matching.

- [ ] **Step 5: Bind before mutation**

When a user selects a handle, call `bind_agent_focus_selection` and map the resolved request to the scheduling mutation. Re-render focus on typed conflicts.

- [ ] **Step 6: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_focus_channel.py tests/unit/agent/test_semantic_interpreter.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_scheduling_capability.py -q
```

Expected: multi-pending no longer loops after ordinal selection, and stale selections fail closed.

### Task 6: Bulk Shared-Reminder Operations

**Files:**
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`
- Modify: `gateway/packages/api/src/scheduling/runtime-contract.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`
- Modify: `agent/agno_agent/capabilities/scheduling.py`
- Modify: `agent/agno_agent/runtime/semantic_interpreter.py`
- Modify: `agent/agno_agent/runtime/execution_agents.py`
- Modify: `tests/unit/agent/test_execution_agents.py`
- Modify: `tests/unit/agent/test_scheduling_capability.py`

- [ ] **Step 1: Add contract methods and tools**

Add `accept_pending_shared_reminders_from`, `reject_pending_shared_reminders_from`, and `cancel_pending_shared_reminders_for` with optional counterparty filters.

- [ ] **Step 2: Implement per-candidate outcomes**

Iterate pending candidates through existing single-candidate transitions and return `{ handle, request_id, status, ok, error? }[]`. Each candidate must be atomic; the batch may report mixed outcomes.

- [ ] **Step 3: Teach agent bulk intents**

Add semantic/tool support for "全部确认", "全部拒绝", and scoped variants. The visible summary must reflect per-handle outcomes.

- [ ] **Step 4: Verify**

Run:

```bash
cd gateway/packages/api && pnpm vitest run src/scheduling/shared-reminder-service.test.ts src/routes/internal-scheduling-routes.test.ts
.venv/bin/python -m pytest tests/unit/agent/test_execution_agents.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_semantic_interpreter.py -q
```

Expected: bulk operations return faithful mixed summaries and reuse focus handles.

### Task 7: Docs, Full Verification, Deploy, Smoke

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/design-docs/interface-contract.md`
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/superpowers/specs/2026-05-28-gateway-hosted-scheduling-boundary-design.md` only if implementation discovers spec drift.

- [ ] **Step 1: Sync canonical docs**

Document Scheduling as Gateway-hosted but contract-owned, add Scheduling routes to the interface contract, and mark bulk shared-reminder flows discoverable in the feature tree.

- [ ] **Step 2: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: route suggestions include repo-os docs, gateway-api, bridge, and worker-runtime. `review-trigger` is a risk report, not a commit blocker.

- [ ] **Step 3: Run selected surfaces**

Run:

```bash
zsh scripts/verify-surface repo-os-docs gateway-api bridge worker-runtime
zsh scripts/check
git diff --check
```

Expected: commands exit 0, or any failure is classified before editing.

- [ ] **Step 4: Commit root and nested Gateway changes**

Commit nested `gateway/` changes first if the nested checkout has its own dirty state, then commit the root gitlink/docs/tests update on `main`.

- [ ] **Step 5: Deploy**

Run:

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

Expected: deployment completes and services restart.

- [ ] **Step 6: Runtime smoke**

Use the shared-reminder smoke skill or equivalent real-user path to prove duplicate pending collapse, reject then re-invite, accept, multi-pending disambiguation by ordinal/time/summary, bulk confirm/reject, projection existence, and reminder firing path.
