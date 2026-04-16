# ClawScale Stranded Model Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove or relocate gateway-owned business models (`Conversation`, `Message`, `AiBackend`, `Workflow`, `EndUserBackend`) so the gateway only keeps routing and delivery data before auth cutover.

**Architecture:** Replace the current gateway conversation/history/backend ownership with a thinner routing record centered on `DeliveryRoute`, `EndUser`, `Channel`, and a new minimal route-binding helper. Message history, workflow state, backend preference, and other business semantics move to Coke-owned Mongo and bridge contracts. Obsolete dashboard APIs become explicit read-only tombstones instead of silently querying removed tables.

**Tech Stack:** TypeScript, Prisma, PostgreSQL, Hono, Vitest, tsx, Python 3.12, PyMongo, pytest, pnpm, ripgrep

---

## Scope Check

This plan is **follow-up plan 1a** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- audit + verdict for `Conversation`, `Message`, `AiBackend`, `Workflow`, `EndUserBackend`
- moving gateway routing off business-history persistence
- moving surviving business data to Coke-owned Mongo / bridge contracts
- deleting or tombstoning gateway routes that depended on stranded models

This plan does **not** cover:

- customer auth ownership migration
- frontend relocation of `/coke/*` to `/auth/*` and `/channels/*`
- admin MVP rebuild
- shared-channel runtime

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
  Remove `Message`, `AiBackend`, `Workflow`, and `EndUserBackend`; replace `Conversation` with the minimal routing record required by `route-message.ts`, or delete it entirely if `DeliveryRoute` proves sufficient.
- `gateway/packages/api/src/lib/route-message.ts`
  Stop reading/writing durable chat history from Postgres.
- `gateway/packages/api/src/lib/business-conversation.ts`
  Rebind business-conversation keys against the surviving route-binding model instead of the legacy `Conversation` table.
- `gateway/packages/api/src/lib/ai-backend.ts`
  Remove gateway-owned backend lookup and accept backend routing only from bridge / agent contracts.
- `gateway/packages/api/src/routes/conversations.ts`
  Replace with a tombstone or delete if no supported read path remains.
- `gateway/packages/api/src/routes/ai-backends.ts`
  Replace with a tombstone or delete.
- `gateway/packages/api/src/routes/workflows.ts`
  Replace with a tombstone or delete.
- `gateway/packages/api/src/index.ts`
  Unmount removed routes or mount tombstone endpoints explicitly.

### Modified Coke-side files

- `connector/clawscale_bridge/app.py`
  Forward any history / backend-routing requests to Coke-owned storage instead of assuming gateway-owned history.
- `connector/clawscale_bridge/message_gateway.py`
  Accept the thinner route-binding payload and stop expecting gateway conversation history.
- `dao/conversation_dao.py`
  Becomes the durable history source of truth where gateway history previously existed.
- `dao/user_dao.py`
  If `EndUserBackend` carried business preference, migrate that preference into Mongo-owned records here.

### Modified Web files

- `gateway/packages/web/app/dashboard/conversations/page.tsx`
- `gateway/packages/web/app/dashboard/ai-backends/page.tsx`
- `gateway/packages/web/app/dashboard/workflows/page.tsx`
  Convert these pages to explicit "moved to Coke / deprecated" screens so they do not query removed gateway tables while plan 6 is still pending.

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
  pnpm --dir gateway/packages/api tsx src/scripts/audit-stranded-models.ts
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
- [ ] Run: `pnpm --dir gateway/packages/api test -- src/lib/route-binding.test.ts src/lib/route-message.test.ts`
- [ ] Implement the route-binding helper with a shape like:

```ts
export interface RouteBindingSnapshot {
  tenantId: string;
  channelId: string;
  endUserId: string;
  customerId: string | null;
  businessConversationKey: string | null;
}
```

- [ ] Update `route-message.ts` so:
  - gateway no longer persists message content in Postgres
  - bridge / agent payloads carry `customer_id` plus any `business_conversation_key`
  - backend routing comes from Coke-owned state, not `AiBackend` / `EndUserBackend`
- [ ] Add the backfill CLI to derive the minimal route-binding records from existing `Conversation` rows before table removal.
- [ ] Re-run: `pnpm --dir gateway/packages/api test -- src/lib/route-binding.test.ts src/lib/route-message.test.ts src/lib/business-conversation.test.ts`

## Task 3: Retire stranded Prisma models and old gateway APIs

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Modify: `gateway/packages/api/src/routes/conversations.ts`
- Modify: `gateway/packages/api/src/routes/ai-backends.ts`
- Modify: `gateway/packages/api/src/routes/workflows.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Modify: `gateway/packages/web/app/dashboard/conversations/page.tsx`
- Modify: `gateway/packages/web/app/dashboard/ai-backends/page.tsx`
- Modify: `gateway/packages/web/app/dashboard/workflows/page.tsx`

- [ ] Write failing schema and route tests that assert the retired tables/routes are no longer active.
- [ ] Run: `pnpm --dir gateway/packages/api test -- src/lib/platformization-schema.test.ts src/routes/outbound.test.ts`
- [ ] Remove the stranded models from Prisma, keeping only the routing minimum chosen in Task 2.
- [ ] Either delete the old routes from `index.ts` or make them return a stable tombstone payload:

```json
{ "ok": false, "error": "moved_to_agent_storage" }
```

- [ ] Update the old dashboard pages to render an explicit deprecation state instead of querying removed APIs.
- [ ] Re-run:
  - `pnpm --dir gateway/packages/api build`
  - `pnpm --dir gateway/packages/web test -- app/dashboard/page.test.tsx app/dashboard/layout.test.tsx`

## Task 4: Verify data migration and remove legacy records

**Files:**
- Create: `gateway/packages/api/src/scripts/verify-stranded-model-retirement.ts`
- Modify: `gateway/packages/api/prisma/migrations/20260417010000_stranded_model_retirement/migration.sql`
- Modify: `dao/conversation_dao.py`
- Modify: `connector/clawscale_bridge/app.py`

- [ ] Add a migration that drops the retired tables only after the route-binding backfill has run successfully.
- [ ] Add a verification CLI that checks:
  - no gateway message-history rows remain in active use
  - no gateway workflow / AI-backend rows remain referenced
  - surviving route bindings resolve every active `DeliveryRoute`
- [ ] Run:

```bash
pnpm --dir gateway/packages/api exec prisma migrate reset --force
pnpm --dir gateway/packages/api tsx src/scripts/backfill-route-bindings.ts
pnpm --dir gateway/packages/api tsx src/scripts/verify-stranded-model-retirement.ts
```

- [ ] Run Coke-side verification:

```bash
pytest tests/unit/ -k "conversation or reminder or identity"
```

- [ ] Document any route tombstones that remain until plan 6 deletes the old dashboard entirely.
