# Frontend Platform Channel Boundary Plan Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the complete plan package for the Frontend / Platform / Channel ownership-boundary design before executing any one implementation plan.

**Architecture:** This package is a plan index plus nine executable child plans. The index owns execution order and dependency rules; child plans own exact file changes, tests, and verification for each independent slice.

**Tech Stack:** Markdown plans, repo-OS docs checks, zsh verification wrappers, TypeScript/Vitest, Python pytest.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Before executing any child plan, verify the spec at `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md` and current `main`.

## Scope

Included:

- Create the complete set of child plans before execution begins.
- Preserve the dependency order from the boundary spec.
- Make every spec follow-up item point at a real plan file.
- Keep each child plan independently executable and verifiable.

Excluded:

- Implementing the child plans in this package-creation change.
- Merging plan content into one large implementation plan.
- Creating lifecycle subdirectories under `docs/superpowers/plans/`.

## Child Plans

Execute in this order:

1. `docs/superpowers/plans/2026-05-19-platform-channel-canonical-doc-sync.md`
2. `docs/superpowers/plans/2026-05-19-shared-channel-package-boundary.md`
3. `docs/superpowers/plans/2026-05-19-channel-management-service-contract.md`
4. `docs/superpowers/plans/2026-05-19-channel-type-field-inventory.md`
5. `docs/superpowers/plans/2026-05-19-product-action-availability-contract.md`
6. `docs/superpowers/plans/2026-05-19-route-contract-ownership-registry.md`
7. `docs/superpowers/plans/2026-05-19-ownership-fitness-surfaces.md`
8. `docs/superpowers/plans/2026-05-19-system-owners-metadata.md`
9. `docs/superpowers/plans/2026-05-19-data-retention-policy-durations.md`

## Dependency Rules

The dependency graph below is a DAG, not a strict linear sequence. Plans that
have no edge between them MAY run in parallel.

```text
canonical-doc-sync
   ├── shared-channel-package-boundary
   │      ├── channel-management-service-contract
   │      ├── channel-type-field-inventory
   │      └── product-action-availability-contract
   └── route-contract-ownership-registry
          ├── ownership-fitness-surfaces
          └── system-owners-metadata
                 └── data-retention-policy-durations
```

Explicit edges:

- The canonical doc sync plan must execute first. Later guardrails depend on those docs being the durable review surface.
- The shared channel package boundary must execute before channel type inventory, channel management service contract, and product action availability (each adds files under a backend-only Channel module or the shared package whose boundary the split establishes), and before machine import-boundary enforcement can be considered CI-blocking.
- The channel management service field contract depends on the backend-only channel package shape from the shared boundary plan.
- Product action availability depends on the shared package split because it adds a new shared DTO file alongside the channel split.
- Route ownership registry must execute after canonical doc sync (ownership vocabulary) but is independent of the shared package work — it MAY run in parallel with `shared-channel-package-boundary` and its descendants.
- Ownership fitness surfaces and system OWNERS metadata both depend on the route registry vocabulary; they MAY run in parallel.
- Data retention duration work is intentionally last because it needs system owners and current state table names.

## Evidence Emission Requirement

Every child plan writes verification evidence under
`artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/<plan-slug>/`.
The plan-package check (Task 1 Step 4 below) validates that each plan's
evidence directory exists and contains at least one log or JSON file before
the package is considered complete.

Each child plan's verification commands must:

- Emit structured log lines (`[BEGIN]`, `[STEP <name>]`, `[OK <name>]`, `[FAIL <name> <reason>]`) so failure triage is fast.
- `tee` test output into the evidence directory so reviewers can see what was actually run.
- Write at least one machine-readable artifact (a `.json`, `.jsonl`, or `.yaml`) summarizing the verification result.

## Work Breakdown

### Task 1: Confirm The Plan Package Is Complete

**Files:**
- Read: `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`
- Read: all child plans listed in [Child Plans](#child-plans)

- [x] **Step 1: Verify each spec planned path exists**

Run:

```bash
for path in \
  docs/superpowers/plans/2026-05-19-platform-channel-canonical-doc-sync.md \
  docs/superpowers/plans/2026-05-19-shared-channel-package-boundary.md \
  docs/superpowers/plans/2026-05-19-channel-management-service-contract.md \
  docs/superpowers/plans/2026-05-19-channel-type-field-inventory.md \
  docs/superpowers/plans/2026-05-19-product-action-availability-contract.md \
  docs/superpowers/plans/2026-05-19-route-contract-ownership-registry.md \
  docs/superpowers/plans/2026-05-19-ownership-fitness-surfaces.md \
  docs/superpowers/plans/2026-05-19-system-owners-metadata.md \
  docs/superpowers/plans/2026-05-19-data-retention-policy-durations.md
do
  test -f "$path" && echo "OK $path" || { echo "MISSING $path"; exit 1; }
done
```

Expected: every path prints `OK`.

- [x] **Step 2: Verify no child plan contains forbidden plan markers**

Run:

```bash
rg -n "T[B]D|TO[D]O|f[i]ll in|implement late[r]|Similar to Tas[k]|Unresolved Seam[s]|Follow-up Question[s]" \
  docs/superpowers/plans/2026-05-19-*-*.md
```

Expected: no matches.

- [x] **Step 3: Verify repo-OS docs checks**

Run:

```bash
zsh scripts/check
zsh scripts/verify-surface repo-os-docs
```

Expected: both commands exit 0.

- [x] **Step 4: Validate evidence directories exist for completed child plans**

Once child plans land, each must have emitted evidence under
`artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/<plan-slug>/`.
Verify:

```bash
ROOT=artifacts/evidence/2026-05-19-frontend-platform-channel-boundary
for slug in \
  platform-channel-canonical-doc-sync \
  shared-channel-package-boundary \
  channel-management-service-contract \
  channel-type-field-inventory \
  product-action-availability-contract \
  route-contract-ownership-registry \
  ownership-fitness-surfaces \
  system-owners-metadata \
  data-retention-policy-durations
do
  if [[ -d "$ROOT/$slug" ]] && [[ -n "$(ls -A "$ROOT/$slug" 2>/dev/null)" ]]; then
    echo "OK   $slug"
  else
    echo "MISS $slug"
  fi
done
```

Expected: every completed plan has evidence; plans not yet executed print `MISS`
and that is acceptable while work is in progress.

### Task 2: Execute Child Plans In Order

**Files:**
- Read: each child plan listed in [Child Plans](#child-plans)

- [x] **Step 1: Execute canonical doc sync**

Run the tasks in:

```bash
docs/superpowers/plans/2026-05-19-platform-channel-canonical-doc-sync.md
```

Expected: canonical docs are aligned and repo-OS docs verification passes.

- [x] **Step 2: Execute the remaining plans sequentially**

Run each child plan in [Child Plans](#child-plans), preserving the dependency order. After each child plan, run its listed verification commands before starting the next plan.

Expected: each child plan leaves a focused, verified diff and no unchecked follow-up in the boundary spec.

## Verification

Run:

```bash
zsh scripts/check
zsh scripts/verify-surface repo-os-docs
```

Expected: repo-OS structure and docs verification pass after the plan package is created.
