# Interface Alias Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dead gateway HTTP/input aliases and document active bridge/gateway payload compatibility.

**Architecture:** Keep current bridge and gateway callers on canonical `customer_id` / scheduling fields. Retain only compatibility backed by current callers or stored data, and record it in `docs/design-docs/interface-contract.md`.

**Tech Stack:** Python bridge, Hono gateway API, Vitest route tests, pytest bridge tests.

---

### Task 1: Reconfirm And Classify Aliases

**Files:**
- Read: `connector/clawscale_bridge/app.py`
- Read: `gateway/packages/api/src/routes/outbound.ts`
- Read: `gateway/packages/api/src/routes/coke-user-provision.ts`
- Read: `gateway/packages/api/src/routes/coke-bindings.ts`
- Read: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Read: `docs/design-docs/interface-contract.md`

- [x] **Step 1: Verify current code and tests before editing**

Run targeted searches for `account_id`, `customer_id`, `coke_account_id`, `friend_id`, and stored outbound payload fallbacks.

- [x] **Step 2: Classify active compatibility**

Keep and document bridge inbound dual payload shapes, provision `coke_account_id`, and historical outbound stored-payload comparison.

### Task 2: Gateway Alias Tests

**Files:**
- Modify: `gateway/packages/api/src/routes/outbound.test.ts`
- Modify: `gateway/packages/api/src/routes/coke-user-provision.test.ts`
- Modify: `gateway/packages/api/src/routes/coke-bindings.test.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`

- [x] **Step 1: Add failing tests**

Add route tests proving `account_id` is rejected by `/api/outbound` and
`/api/internal/coke-users/provision`, `coke_account_id` is rejected by
`/api/internal/coke-bindings`, and `friend_id` is rejected by
`create_shared_reminder`.

- [x] **Step 2: Verify red**

Run:

```bash
pnpm --dir gateway --filter @clawscale/api test src/routes/outbound.test.ts src/routes/coke-user-provision.test.ts src/routes/coke-bindings.test.ts src/routes/internal-scheduling-routes.test.ts
```

Expected: the new alias-rejection tests fail before implementation.

### Task 3: Gateway And Bridge Cleanup

**Files:**
- Modify: `gateway/packages/api/src/routes/outbound.ts`
- Modify: `gateway/packages/api/src/routes/coke-user-provision.ts`
- Modify: `gateway/packages/api/src/routes/coke-bindings.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `docs/design-docs/interface-contract.md`

- [x] **Step 1: Remove dead aliases**

Remove the dead gateway HTTP/input aliases identified in Task 2 and the bridge
timeout fallback read that referenced a non-normalized `customer_id` field.

- [x] **Step 2: Document active compatibility**

Add active payload compatibility notes to the interface contract for bridge
inbound, outbound stored payloads, provision IDs, bindings IDs, and scheduling
create fields.

### Task 4: Verify And Commit

**Files:**
- Verify gateway nested repository first.
- Verify root bridge/docs changes second.

- [x] **Step 1: Run targeted gateway tests**

Run the route specs from Task 2 and `pnpm --dir gateway --filter @clawscale/api build`.

- [x] **Step 2: Run root bridge/docs checks**

Run focused pytest for bridge app behavior and diff-aware root verification
routing.

- [x] **Step 3: Commit in order**

Commit nested `gateway/` changes first, then commit root bridge/docs and the
updated gateway gitlink.
