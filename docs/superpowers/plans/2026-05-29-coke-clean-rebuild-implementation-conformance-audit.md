# Coke Clean Rebuild Implementation Conformance Audit Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit the clean Coke rebuild against the requirements matrix and target architecture, then commit a precise prioritized gap report with file:line evidence.

**Architecture:** This is a static/local conformance audit, not a runtime deployment exercise. Evidence must come from the named source docs, `coke/`, `migrations/`, `web/`, and local tests; any safe fix must follow red-green TDD and stay outside the concurrent-edit files named by the task.

**Tech Stack:** Python 3.12 via `/data/projects/coke/.venv/bin/python`, pytest, SQLAlchemy metadata, Flask route blueprints, Next.js/TypeScript source inspection.

---

**Plan Status:** complete
**Status Date:** 2026-05-31

**Source Docs:**
- `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`
- `docs/ARCHITECTURE.md`
- `docs/product-specs/FEATURE_TREE.md`

## File Structure

- Create: `docs/issues/2026-05-31-implementation-conformance-audit.md` - prioritized implementation gap report with requirement/architecture references and file:line evidence.
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-implementation-conformance-audit.md` - checkbox progress and final plan status.
- Optional test files: only if a trivial safe fix is made, create or modify a focused `tests/unit/coke/...` test that fails before the production edit.
- Optional production files: only if a trivial safe fix is made, edit the smallest isolated file outside `coke/turn/runner.py`, `coke/llm/*`, `coke/providers/wechat_personal.py`, `coke/domains/reminder/service.py`, and web channel surfaces.

### Task 1: Scope And Source Reading

- [x] **Step 1: Confirm isolated worktree and branch**

Run:

```bash
git status --short --branch
```

Expected: branch is `audit/impl-conformance`; no unrelated local changes need to be modified.

- [x] **Step 2: Read required master-plan sections**

Read only the plan package rule, Task 13 closeout section, and `Architecture Issues To Watch During Execution` from:

```text
docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md
```

Expected: audit focuses on implementation completeness, turn/disposition separation, adapter/domain boundaries, Interaction Agent prose ownership, and stale intent guarding.

- [x] **Step 3: Read the source contract sections**

Read requirements `§1-§5`, target architecture `§3`, `§4`, `§8`, `§9`, and the current architecture/feature tree.

Expected: build a requirement checklist that covers all journeys, named invariants, API routes, schema usage, and architecture boundaries.

### Task 2: Inventory Actual Implementation

- [x] **Step 1: Inventory code surfaces**

Run:

```bash
rg --files coke migrations web tests/unit/coke
```

Expected: enumerate domains, turn runtime, providers, API routes, worker/scheduler, composition, schema, migrations, web routes, and unit tests.

- [x] **Step 2: Search for explicit placeholders and forbidden legacy imports**

Run:

```bash
rg -n "NotImplemented|TODO|FIXME|pass$|placeholder|pymongo|dao|connector|gateway|memo_runtime|fallback|regex|keyword" coke migrations web tests/unit/coke
```

Expected: every hit is classified as either harmless wording/test fixture or a reportable gap/divergence.

- [x] **Step 3: Inspect agent-callable operations and domain service methods**

Compare `coke/turn/` tool operations to domain service APIs in `coke/domains/**/service.py`.

Expected: report operations that are implemented but not exposed to the agent, exposed but not implemented, or wired to divergent behavior.

- [x] **Step 4: Inspect API and web route parity**

Compare `docs/product-specs/FEATURE_TREE.md` routes to `coke/api/*_routes.py`, `coke/app.py`, and `web/`.

Expected: report missing or unrouted API/public/customer/provider/internal surfaces with evidence.

### Task 3: Requirement And Architecture Classification

- [x] **Step 1: Classify every requirement and user journey**

For each requirement/journey in the requirements matrix, assign `IMPLEMENTED`, `PARTIAL`, `MISSING`, or `DIVERGENT` using concrete code evidence.

Expected: no requirement is omitted; high-risk examples named in the task are explicitly checked.

- [x] **Step 2: Classify each architecture invariant**

Check bounded contexts, turn internals, reminder execution, social scheduling, stale-seq safety, outbox/disposition separation, provider boundaries, and no-legacy constraints.

Expected: each invariant has status and file:line evidence or a documented absence.

- [x] **Step 3: Inspect schema use and invariants**

Compare `coke/schema.py` tables and constraints to repository/service code and migrations.

Expected: report unused schema elements, code paths that rely on unenforced invariants, and missing code enforcement for defined constraints.

### Task 4: Safe Fix Protocol

- [x] **Step 1: Decide whether any gap is safe to fix here**

A fix is allowed only when it is trivial, isolated, outside the concurrent-edit files, and does not invent schema or behavior outside the current contract.

Expected: either no code fix is made, or the report names the exact safe gap chosen.

Result: no code fix was selected. The report-only change avoids active edit areas and records cross-cutting gaps for leader dispatch.

- [x] **Step 2: If fixing, write a failing test first**

Run the smallest focused pytest target with `/data/projects/coke/.venv/bin/python -m pytest ... -v`.

Expected: test fails for the missing behavior, not because of setup or import errors.

Result: not applicable because no safe isolated code fix was made.

- [x] **Step 3: If fixing, implement the minimal code**

Edit only the isolated production file required for the failing test.

Expected: no legacy imports, compatibility shims, fallback prose, keyword routing, schema forks, or unrelated refactors.

Result: not applicable because no production code was changed.

- [x] **Step 4: If fixing, run the focused test green**

Run the exact focused pytest command again.

Expected: the previously failing test passes.

Result: not applicable because no focused failing test was created.

### Task 5: Report, Verification, And Commit

- [x] **Step 1: Write the gap report**

Create `docs/issues/2026-05-31-implementation-conformance-audit.md` with front matter, summary counts, prioritized P0/P1/P2 table, requirement/architecture references, file:line evidence, and verification notes.

Expected: gaps are precise and prioritized; no padding or speculation without evidence.

- [x] **Step 2: Run required local verification**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: unit suite remains green after report-only or any safe fix changes.

Result: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` passed with `429 passed in 11.53s`.

- [x] **Step 3: Update this plan**

Mark completed checkboxes and set `Plan Status` to `complete` only after verification passes.

Expected: the plan records actual progress and final state truthfully.

- [x] **Step 4: Commit the audit artifacts and any safe fixes**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-implementation-conformance-audit.md docs/issues/2026-05-31-implementation-conformance-audit.md
git commit -m "docs: audit clean rebuild implementation conformance"
```

Expected: branch `audit/impl-conformance` contains a coherent audit commit.
