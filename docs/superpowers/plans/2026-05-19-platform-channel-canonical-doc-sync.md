# Platform Channel Canonical Doc Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current canonical docs reflect the ownership model from the Frontend / Platform / Channel boundary spec before code guardrails are built.

**Architecture:** Keep the boundary spec as the detailed ownership source, then update existing canonical docs as concise entry points. `interface-contract.md` owns route namespace rules, `FEATURE_TREE.md` owns discoverability, `ARCHITECTURE.md` owns runtime topology, and `coke-working-contract.md` owns planning-surface versus ownership-system routing.

**Tech Stack:** Markdown docs, repo-OS checks, `scripts/suggest-verification`, `scripts/verify-surface`.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Verify against `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`, `docs/design-docs/interface-contract.md`, `docs/product-specs/FEATURE_TREE.md`, `docs/ARCHITECTURE.md`, and `docs/design-docs/coke-working-contract.md` before editing.

## Scope

Included:

- Align canonical docs with the ownership systems in the boundary spec.
- Reference the boundary spec from `coke-working-contract.md`.
- Remove stale Bridge/platform/channel ownership wording from canonical docs.
- Preserve existing planning-surface names used by verification routing.

Excluded:

- Code changes.
- Route registry implementation.
- Shared package split.
- Full file-by-file ownership inventory.

## File Map

- `docs/design-docs/interface-contract.md`: add ownership-system notes for namespace classes and list current customer/admin/internal routes with owner labels.
- `docs/product-specs/FEATURE_TREE.md`: split feature tree into Runtime, Product, Channel, Platform/Gateway, Bridge, and Operations surfaces.
- `docs/ARCHITECTURE.md`: update topology wording so Bridge is not described as owning user auth/bind flow and gateway is not treated as one ownership system.
- `docs/design-docs/coke-working-contract.md`: add the ownership axis and link to the boundary spec while preserving planning-surface routing.

## Work Breakdown

### Task 1: Update Interface Contract Ownership Notes

**Files:**
- Modify: `docs/design-docs/interface-contract.md`

- [x] **Step 1: Add ownership vocabulary after Core Rule**

Insert this section after the two Core Rule questions:

```markdown
## Ownership Axis

Interface namespaces describe audience and transport shape. Ownership systems
describe who owns the behavior behind that interface. Use
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`
when deciding whether a route is Platform, Channel, Reminder, Calendar Import,
Bridge, Agent Runtime, or another product system.

A route under `gateway/packages/api` is not automatically Platform-owned. For
example, `/api/customer/reminders` is customer-facing but Reminder-owned, while
`/api/customer/channels/wechat-personal` is Platform-shaped at the HTTP edge
and Channel-owned for provider semantics.
```

- [x] **Step 2: Add owner annotations to Current Canonical Surface**

Replace the unannotated Public API list with owner-labelled bullets. Keep existing routes and add the Calendar Import routes named in the boundary spec Contract Catalog.

Use this shape:

```markdown
- `/api/customer/channels/wechat-personal` — Platform edge, Channel semantics
- `/api/customer/reminders` — Reminder System
- `/api/customer/google-calendar-import` — Calendar Import System
- `/api/customer/calendar-import-handoffs` — Calendar Import System
```

Expected: route bullets identify owner without changing namespace rules.

- [x] **Step 3: Verify no stale namespace wording remains**

Run:

```bash
rg -n "gateway-owned|Bridge-owned product|automatically Platform" docs/design-docs/interface-contract.md
```

Expected: no stale ownership shortcut remains, except intentional explanatory text that says a route is not automatically Platform-owned.

### Task 2: Update Feature Tree Discoverability

**Files:**
- Modify: `docs/product-specs/FEATURE_TREE.md`

- [x] **Step 1: Add boundary spec reference near the intro**

Add:

```markdown
For ownership-system classification, use
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`.
This feature tree remains a discovery map; it does not decide ownership by
directory alone.
```

- [x] **Step 2: Split Gateway surfaces by ownership**

Replace the current `Gateway Surfaces` section with subsections:

```markdown
## Platform / Gateway Surfaces

- Frontend App
  - `gateway/packages/web`
  - public homepage, customer auth, customer account, and customer product-entry surfaces
- Platform System
  - `gateway/packages/api/src/routes/customer-auth-routes.ts`
  - `gateway/packages/api/src/routes/customer-claim-routes.ts`
  - subscription and account-management routes

## Channel Surfaces

- Channel System
  - `gateway/packages/api/src/gateway/message-router.ts`
  - `gateway/packages/api/src/lib/route-message.ts`
  - `gateway/packages/api/src/routes/customer-channel-routes.ts`
  - `gateway/packages/api/src/routes/outbound.ts`
  - provider-specific config and dispatch helpers under `gateway/packages/api/src/lib/`
```

Expected: gateway remains a planning surface, but feature discovery separates Platform and Channel ownership.

- [x] **Step 3: Promote Calendar Import and Timezone entries**

Add product-system bullets for Calendar Import and Timezone using the paths from the boundary spec contract catalog.

Expected: Calendar Import and Timezone no longer appear as generic helper capabilities.

### Task 3: Update Architecture Runtime Ownership Wording

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [x] **Step 1: Add an ownership-axis note after the opening paragraph**

Add:

```markdown
This document describes runtime topology. Ownership boundaries are defined in
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`.
Planning surfaces and ownership systems are related but not identical.
```

- [x] **Step 2: Correct Bridge topology bullets**

Replace the `connector/clawscale_bridge/app.py` bullets that say it handles user auth and bind flow with:

```markdown
- `connector/clawscale_bridge/app.py`
  - validates bridge/internal integration requests
  - adapts Coke ingress and egress protocol traffic
  - waits for synchronous replies and promotes late replies
  - dispatches outbound replies to the gateway
```

Expected: Bridge no longer owns customer auth or bind flow in the canonical architecture doc.

- [x] **Step 3: Correct gateway ownership bullets**

Replace the gateway bullets that say `gateway/` owns all shared-channel state with:

```markdown
- `gateway/`
  - serves the web UI on `4040`
  - serves the API on `4041`
  - hosts Platform, Channel, Reminder customer API, and Calendar Import routes in one process
  - keeps provider webhook normalization and outbound dispatch under Channel ownership
```

Expected: gateway process hosting is separated from ownership.

- [x] **Step 4: Update Shared-Channel Boundary wording**

Rename `## 6. Shared-Channel Boundary` to `## 6. Channel System Boundary` and make the first paragraph say:

```markdown
Shared-channel implementation currently lives under `gateway/`, but provider
webhook handling, normalization, route binding, and outbound provider dispatch
belong to the Channel System. Platform owns customer/account context and the
customer-facing management edge.
```

Expected: the section matches the boundary spec distinction.

### Task 4: Update Coke Working Contract

**Files:**
- Modify: `docs/design-docs/coke-working-contract.md`

- [x] **Step 1: Add ownership-axis section before Core Runtime Surfaces**

Add:

```markdown
## Ownership Axis

Planning surfaces describe where verification runs. Ownership systems describe
who owns behavior and contracts. Use
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`
for Frontend App, Platform System, Channel System, Reminder System, Memo
System, Calendar Import System, Timezone System, Bridge System, Agent Runtime
System, and State/Infrastructure ownership.

A change can touch one planning surface while affecting multiple ownership
systems. Name both in non-trivial plans and reviews.
```

- [x] **Step 2: Adjust Gateway Platform Layer text**

Change the Gateway surface title to:

```markdown
### 3. Gateway Planning Surface
```

Then replace the `Use this surface when` bullets with:

```markdown
- gateway-hosted API or web files change
- customer, channel, admin, reminder, calendar-import, or subscription routes under `gateway/` change
- shared frontend/backend DTOs under `gateway/packages/shared` change
- Prisma schema or gateway platformization logic changes
```

Expected: planning surface does not claim ownership.

### Task 5: Verify Canonical Doc Sync

**Files:**
- Read: modified docs

- [x] **Step 1: Scan for stale ownership shortcuts**

Run:

```bash
rg -n "gateway-owned|handles user auth, bind flow|not automatically owned|automatically owned by Platform|Unresolved Seam[s]|Follow-up Question[s]" \
  docs/ARCHITECTURE.md docs/design-docs/interface-contract.md docs/product-specs/FEATURE_TREE.md docs/design-docs/coke-working-contract.md
```

Expected: no stale claims remain. Intentional explanatory text about routes not being automatically Platform-owned is acceptable if phrased consistently.

- [x] **Step 2: Run repo-OS docs verification with evidence emission**

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/platform-channel-canonical-doc-sync
zsh scripts/check \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/platform-channel-canonical-doc-sync/check.log
zsh scripts/verify-surface repo-os-docs \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/platform-channel-canonical-doc-sync/verify-surface.log
```

Expected: both commands exit 0.

### Task 6: Automated Boundary-Spec Link Check (E2E)

**Files:**
- Create: `scripts/e2e/platform-channel-canonical-doc-sync.sh`

- [x] **Step 1: Add structured link verifier**

The whole point of this plan is that the four canonical docs link to the boundary spec and use the ownership vocabulary. Create `scripts/e2e/platform-channel-canonical-doc-sync.sh` (executable, zsh or bash) that:

1. Checks each of the four docs (`docs/ARCHITECTURE.md`, `docs/design-docs/interface-contract.md`, `docs/product-specs/FEATURE_TREE.md`, `docs/design-docs/coke-working-contract.md`) contains:
   - A reference to `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`.
   - The substring `Ownership` (heading or vocabulary use).
2. Checks `interface-contract.md` lists owner labels for at least `/api/customer/reminders`, `/api/customer/channels/wechat-personal`, `/api/customer/google-calendar-import`, and `/api/customer/calendar-import-handoffs`.
3. Checks `ARCHITECTURE.md` no longer claims Bridge handles user auth/bind flow.
4. Writes per-doc results (`{doc, missing_refs, found_refs}`) to `artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/platform-channel-canonical-doc-sync/link-check.json`.
5. Emits `[BEGIN]`/`[STEP <doc>]`/`[OK <doc>]`/`[FAIL <doc> <reason>]` log lines and exits non-zero on the first failure.

Expected: the script exits 0, proving the doc sync actually achieved its goal.
