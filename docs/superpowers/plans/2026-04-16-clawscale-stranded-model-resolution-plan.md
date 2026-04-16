# ClawScale Stranded Model Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire gateway-owned business history and workflow state before auth cutover, and only delete backend-selection tables after a compatible customer-owned replacement exists.

**Architecture:** Do this in two compatibility stages. First, introduce an explicit route-binding snapshot centered on `DeliveryRoute`, stop persisting chat transcripts in gateway Postgres, and dual-read/dual-write `customer_id` plus `coke_account_id` and `businessConversationKey` plus optional `gatewayConversationId` across gateway, bridge, and Coke. Second, drop only the stranded tables that no longer participate in live routing; if `AiBackend` and `EndUserBackend` are still the only backend-routing source after the contract cutover, keep them as routing-only compatibility survivors and document their deferred retirement instead of inventing a new backend-routing system inside this plan.

**Tech Stack:** TypeScript, Prisma, PostgreSQL, Hono, Vitest, tsx, Python 3.12, PyMongo, pytest, pnpm, ripgrep

---

## Scope Check

This plan is **follow-up plan 1a** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- audit + verdict for `Conversation`, `Message`, `AiBackend`, `Workflow`, `EndUserBackend`
- moving gateway routing off business-history persistence
- adding a route-binding compatibility layer that prefers `businessConversationKey` and only uses `gatewayConversationId` as an establishment fallback
- dual-read/dual-write bridge/Coke contracts for `customer_id` and `coke_account_id`
- deleting or tombstoning gateway routes that depended on stranded models
- explicitly deferring `AiBackend` / `EndUserBackend` deletion when no replacement routing source exists yet

This plan does **not** cover:

- customer auth ownership migration
- frontend relocation of `/coke/*` to `/auth/*` and `/channels/*`
- admin MVP rebuild
- shared-channel runtime
- inventing a new customer-owned backend preference system
- removing `gatewayConversationId` from Coke before all live consumers stop preferring it as a fallback

## Compatibility Rules

- `businessConversationKey` is the durable business route key after this plan. `gatewayConversationId` may still be emitted and read, but only as an establishment fallback while old Coke consumers remain live.
- `customer_id` / `customerId` must be accepted and emitted alongside `coke_account_id` / `cokeAccountId` until auth ownership migration lands. No task in this plan is allowed to switch the system to `customer_id`-only.
- Gateway `Message` writes cannot be removed until a replacement history source feeds `route-message.ts` / `loadHistory()`. Task 2 may add route-binding metadata, but Task 4 is the first point where dropping message-history persistence is allowed.
- `AiBackend` and `EndUserBackend` cannot be dropped by this plan unless Task 4 verification proves no runtime path still reads them. If they are still required, keep them as routing-only compatibility survivors and remove only dashboard CRUD / business semantics.
- TypeScript script commands in this plan use `pnpm --dir <pkg> exec tsx <script>` rather than `pnpm --dir <pkg> tsx <script>`.

## File Structure

### New Gateway API files

- `gateway/packages/api/src/lib/route-binding.ts`
  Minimal helpers for resolving/upserting the surviving delivery-route conversation binding without storing message history.
- `gateway/packages/api/src/lib/route-binding.test.ts`
  Covers route-binding creation, conflict handling, and business-conversation-key updates.
- `gateway/packages/api/src/lib/stranded-model-audit.ts`
  Audit helpers that count stranded rows and classify them as migrate / drop.
- `gateway/packages/api/src/lib/stranded-model-audit.test.ts`
  Covers the per-model verdict summary and drift detection.
- `gateway/packages/api/src/scripts/audit-stranded-models.ts`
  CLI that prints row counts plus migrate/drop verdicts before destructive work.
- `gateway/packages/api/src/scripts/backfill-route-bindings.ts`
  CLI to derive minimal route bindings from legacy `Conversation` rows before table removal.
- `gateway/packages/api/src/scripts/verify-stranded-model-retirement.ts`
  CLI that confirms replacement records exist and stranded tables are empty or absent.

### Modified Gateway API files

- `gateway/packages/api/prisma/schema.prisma`
  Remove `Message` and `Workflow`; collapse `Conversation` to the route-binding minimum or replace it with `RouteBinding`; only remove `AiBackend` and `EndUserBackend` if later verification proves no live dependency remains.
- `gateway/packages/api/src/lib/route-message.ts`
  Stop reading/writing durable chat history from Postgres; keep backend selection compatibility if `AiBackend` / `EndUserBackend` are still the only live routing source.
- `gateway/packages/api/src/lib/business-conversation.ts`
  Rebind business-conversation keys against the surviving route-binding model instead of the legacy message-history contract while preserving conflict and stale-route semantics.
- `gateway/packages/api/src/lib/ai-backend.ts`
  Keep this file as a transport adapter / payload parser only. Do not invent a new backend source here; if gateway still owns backend selection after Task 3, this file remains a compatibility layer.
- `gateway/packages/api/src/routes/conversations.ts`
  Replace with a tombstone or delete if no supported read path remains.
- `gateway/packages/api/src/routes/ai-backends.ts`
  Replace with a tombstone or restrict it to compatibility-only behavior if `AiBackend` survives as a routing table.
- `gateway/packages/api/src/routes/workflows.ts`
  Replace with a tombstone or delete.
- `gateway/packages/api/src/index.ts`
  Unmount removed routes or mount tombstone endpoints explicitly.

### Modified Coke-side files

- `connector/clawscale_bridge/app.py`
  Normalize `customer_id` plus `coke_account_id`, prefer `business_conversation_key`, and keep `gateway_conversation_id` only as a compatibility fallback.
- `connector/clawscale_bridge/message_gateway.py`
  Accept the thinner route-binding payload and dual-write compatibility fields into `business_protocol`.
- `connector/clawscale_bridge/reply_waiter.py`
  Continue returning `business_conversation_key` on sync replies while treating `gateway_conversation_id` as optional.
- `connector/clawscale_bridge/output_dispatcher.py`
  Keep outbound dispatch keyed by `business_conversation_key`; do not require `gateway_conversation_id`.
- `agent/runner/message_processor.py`
  Prefer `business_conversation_key` during ClawScale conversation acquisition and fall back to `gatewayConversationId` only during establishment.
- `agent/util/message_util.py`
  Build outbound routing metadata from `business_conversation_key` first and stop reconstructing business route state from gateway chat history where avoidable.

### Modified Web files

- `gateway/packages/web/app/dashboard/conversations/page.tsx`
- `gateway/packages/web/app/dashboard/ai-backends/page.tsx`
- `gateway/packages/web/app/dashboard/workflows/page.tsx`
  Convert these pages to explicit "moved to Coke / deprecated" screens so they do not query removed gateway tables while plan 6 is still pending.

### Modified Test files

- `gateway/packages/api/src/lib/business-conversation.test.ts`
- `gateway/packages/api/src/lib/route-message.test.ts`
- `gateway/packages/api/src/routes/outbound.test.ts`
- `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
- `tests/unit/connector/clawscale_bridge/test_reply_waiter.py`
- `tests/unit/runner/test_message_acquirer_clawscale.py`
- `tests/unit/agent/test_message_util_clawscale_routing.py`
  Update these tests to cover the compatibility contract and deferred survivor rules.

## Task 1: Audit stranded models and lock the target verdict

**Files:**
- Create: `gateway/packages/api/src/lib/stranded-model-audit.ts`
- Create: `gateway/packages/api/src/lib/stranded-model-audit.test.ts`
- Create: `gateway/packages/api/src/scripts/audit-stranded-models.ts`

- [ ] Write failing audit tests that encode the target verdicts:
  - `Conversation` => migrate only the route-binding minimum
  - `Message` => drop after verifying Coke-side durability exists
  - `AiBackend` => drop
  - `Workflow` => drop
  - `EndUserBackend` => keep only if it is proven to be pure routing
- [ ] Run: `pnpm --dir gateway/packages/api test -- src/lib/stranded-model-audit.test.ts`
- [ ] Implement the audit helper plus CLI so it prints:

```json
{
  "counts": {
    "conversations": 0,
    "messages": 0,
    "aiBackends": 0,
    "workflows": 0,
    "endUserBackends": 0
  },
  "verdicts": {
    "Conversation": "migrate_route_minimum",
    "Message": "drop_after_history_cutover",
    "AiBackend": "drop",
    "Workflow": "drop",
    "EndUserBackend": "drop_or_move"
  }
}
```

- [ ] Run: `pnpm --dir gateway/packages/api test -- src/lib/stranded-model-audit.test.ts`
- [ ] Run:

```bash
DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/postgres?schema=public' \
  pnpm --dir gateway/packages/api exec tsx src/scripts/audit-stranded-models.ts
```

## Task 2: Move routing off gateway-owned history

**Files:**
- Create: `gateway/packages/api/src/lib/route-binding.ts`
- Create: `gateway/packages/api/src/lib/route-binding.test.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/business-conversation.ts`
- Create: `gateway/packages/api/src/scripts/backfill-route-bindings.ts`

- [ ] Write failing tests proving `route-message.ts` can route using only:
  - `Channel`
  - `EndUser`
  - `DeliveryRoute`
  - the minimal route-binding helper
  - compatibility metadata that prefers `businessConversationKey` and only includes `gatewayConversationId` as fallback context
  - existing backend selection behavior while `AiBackend` / `EndUserBackend` still exist
- [ ] Run: `pnpm --dir gateway/packages/api test -- src/lib/route-binding.test.ts src/lib/route-message.test.ts src/lib/business-conversation.test.ts`
- [ ] Implement the route-binding helper with a shape like:

```ts
export interface RouteBindingSnapshot {
  tenantId: string;
  channelId: string;
  endUserId: string;
  externalEndUserId: string;
  cokeAccountId: string | null;
  customerId: string | null;
  gatewayConversationId: string | null;
  businessConversationKey: string | null;
  previousBusinessConversationKey: string | null;
  previousClawscaleUserId: string | null;
}
```

- [ ] Update `route-message.ts` so:
  - gateway emits the new route-binding metadata while preserving the current `Message` writes needed by `loadHistory()`
  - bridge / agent payloads carry both `customer_id` and `coke_account_id`, plus any `business_conversation_key`
  - `gatewayConversationId` is forwarded only as compatibility metadata while old Coke consumers still need it
  - backend routing stays in gateway until Task 3 proves a replacement exists; `AiBackend` / `EndUserBackend` are treated as routing-only compatibility tables, not deleted here
- [ ] Update `business-conversation.ts` so the binder consumes `RouteBindingSnapshot`, keeps current conflict detection, and still deactivates stale `DeliveryRoute` rows when the business key changes.
- [ ] Add the backfill CLI to derive the minimal route-binding records from existing `Conversation` rows before table removal.
- [ ] Re-run: `pnpm --dir gateway/packages/api test -- src/lib/route-binding.test.ts src/lib/route-message.test.ts src/lib/business-conversation.test.ts`

## Task 3: Cut over bridge and Coke to the compatibility contract

**Files:**
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `connector/clawscale_bridge/message_gateway.py`
- Modify: `connector/clawscale_bridge/reply_waiter.py`
- Modify: `connector/clawscale_bridge/output_dispatcher.py`
- Modify: `agent/runner/message_processor.py`
- Modify: `agent/util/message_util.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_reply_waiter.py`
- Modify: `tests/unit/runner/test_message_acquirer_clawscale.py`
- Modify: `tests/unit/agent/test_message_util_clawscale_routing.py`

- [ ] Write failing Python tests that assert:
  - bridge accepts `customer_id` / `customerId` and legacy `coke_account_id` / `cokeAccountId`
  - `business_conversation_key` is the primary durable key
  - `gateway_conversation_id` is optional fallback metadata during establishment only
  - outbound dispatch still requires `business_conversation_key` and does not regress sync replies
- [ ] Run:

```bash
pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  tests/unit/connector/clawscale_bridge/test_message_gateway.py \
  tests/unit/connector/clawscale_bridge/test_output_dispatcher.py \
  tests/unit/connector/clawscale_bridge/test_reply_waiter.py \
  tests/unit/runner/test_message_acquirer_clawscale.py \
  tests/unit/agent/test_message_util_clawscale_routing.py -v
```

- [ ] Update `connector/clawscale_bridge/app.py` so inbound normalization and trust checks accept `customer_id` aliases while still populating the existing Coke-account field expected by current auth/runtime code.
- [ ] Update `connector/clawscale_bridge/message_gateway.py` and `connector/clawscale_bridge/reply_waiter.py` so `business_protocol` always carries `business_conversation_key` when available and only carries `gateway_conversation_id` as optional compatibility context.
- [ ] Update `agent/runner/message_processor.py` and `agent/util/message_util.py` so live conversation acquisition prefers `business_conversation_key` and only falls back to `gatewayConversationId` while old payloads still exist.
- [ ] Re-run the same `pytest` command and keep the compatibility contract green before touching schema retirement.

## Task 4: Retire safe stranded Prisma models and old gateway APIs

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Modify: `gateway/packages/api/src/routes/conversations.ts`
- Modify: `gateway/packages/api/src/routes/ai-backends.ts`
- Modify: `gateway/packages/api/src/routes/workflows.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Modify: `gateway/packages/web/app/dashboard/conversations/page.tsx`
- Modify: `gateway/packages/web/app/dashboard/ai-backends/page.tsx`
- Modify: `gateway/packages/web/app/dashboard/workflows/page.tsx`

- [ ] Write failing schema and route tests that assert:
  - `Workflow` is retired
  - `Message` is retired only after `loadHistory()` no longer depends on it
  - `Conversation` no longer carries business-history-only columns such as `backendId`
  - old dashboard routes are tombstoned
  - `AiBackend` / `EndUserBackend` are only dropped if no runtime path still queries them
- [ ] Run: `pnpm --dir gateway/packages/api test -- src/lib/platformization-schema.test.ts src/routes/outbound.test.ts`
- [ ] Remove the stranded models from Prisma, keeping only the routing minimum chosen in Task 2.
- [ ] Drop `Workflow` once Task 2 and Task 3 are green. Drop `Message` only after verification proves `route-message.ts` no longer depends on it for history continuity. Remove `Conversation.backendId` and any other history-only columns at the same time.
- [ ] Drop `AiBackend` and `EndUserBackend` only if Task 2 and Task 3 verification plus a repo search show no live reads remain. If they are still needed, keep them in Prisma with comments marking them as routing-only compatibility survivors and update the plan notes at the end of this file.
- [ ] Either delete the old routes from `index.ts` or make them return a stable tombstone payload:

```json
{ "ok": false, "error": "moved_to_agent_storage" }
```

- [ ] Update the old dashboard pages to render an explicit deprecation state instead of querying removed APIs.
- [ ] Re-run:
  - `pnpm --dir gateway/packages/api build`
  - `pnpm --dir gateway/packages/web test -- app/dashboard/page.test.tsx app/dashboard/layout.test.tsx`

## Task 5: Verify data migration, drop only safe legacy records, and document deferrals

**Files:**
- Create: `gateway/packages/api/src/scripts/verify-stranded-model-retirement.ts`
- Modify: `gateway/packages/api/prisma/migrations/20260417010000_stranded_model_retirement/migration.sql`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `docs/superpowers/plans/2026-04-16-clawscale-stranded-model-resolution-plan.md`

- [ ] Add a migration that drops only the retired tables proven safe by Task 4 after the route-binding backfill has run successfully.
- [ ] Add a verification CLI that checks:
  - no gateway message-history rows remain in active use
  - no gateway workflow rows remain referenced
  - surviving route bindings resolve every active `DeliveryRoute`
  - bridge / Coke compatibility consumers can resolve established conversations from `businessConversationKey` without requiring `gatewayConversationId`
  - if `AiBackend` / `EndUserBackend` remain live, they are reported as deferred routing survivors rather than causing the verification command to fail
- [ ] Run:

```bash
pnpm --dir gateway/packages/api exec prisma migrate reset --force
pnpm --dir gateway/packages/api exec tsx src/scripts/backfill-route-bindings.ts
pnpm --dir gateway/packages/api exec tsx src/scripts/verify-stranded-model-retirement.ts
```

- [ ] Run Coke-side verification:

```bash
pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  tests/unit/connector/clawscale_bridge/test_message_gateway.py \
  tests/unit/connector/clawscale_bridge/test_output_dispatcher.py \
  tests/unit/connector/clawscale_bridge/test_reply_waiter.py \
  tests/unit/runner/test_message_acquirer_clawscale.py \
  tests/unit/agent/test_message_util_clawscale_routing.py -v
```

- [ ] Document any route tombstones and any deferred `AiBackend` / `EndUserBackend` survivor status that remains until the backend-routing replacement plan lands.

## Implementation Notes

- `/api/conversations`, `/api/ai-backends`, and `/api/workflows` now return the stable tombstone payload `{ "ok": false, "error": "moved_to_agent_storage" }` with HTTP `410`.
- `gateway/packages/web/app/dashboard/conversations/page.tsx`, `gateway/packages/web/app/dashboard/ai-backends/page.tsx`, and `gateway/packages/web/app/dashboard/workflows/page.tsx` now render explicit deprecation screens instead of calling the retired dashboard APIs.
- `Workflow` is the only stranded Prisma model physically retired by this plan. The safe-retirement migration also drops `Conversation.backendId`, which was a history-only column no longer needed after the route-binding cutover.
- `Conversation`, `Message`, `AiBackend`, and `EndUserBackend` remain compatibility survivors for now:
  - `Conversation`: retained as the route-binding minimum while gateway conversation ids still participate in cutover compatibility.
  - `Message`: retained because `route-message.ts` / `loadHistory()` still read gateway transcript history.
  - `AiBackend`: retained because bridge delivery, backend attribution, tenant stats, and Coke bootstrap still read the gateway backend registry.
  - `EndUserBackend`: retained because active per-end-user backend selection still lives in gateway storage.
- `verify-stranded-model-retirement.ts` treats those survivor models as deferred rather than failed retirement work. It reports both the survivor reasons and live row counts, and it now fails active-route verification if an active `DeliveryRoute` no longer resolves its `Channel`, `EndUser`, `ClawscaleUser`, `coke_account_id`, or `business_conversation_key`.
- The branch now carries `20260416000000_legacy_schema_baseline` so `prisma migrate reset` works on an empty database before applying the platformization and stranded-retirement migrations.
