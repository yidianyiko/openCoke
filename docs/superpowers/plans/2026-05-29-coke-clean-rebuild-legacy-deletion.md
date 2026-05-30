# Coke Clean Rebuild Web Extraction And Legacy Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the top-level Next.js web extraction, remove the Gateway and memo-runtime submodules, delete the old Python runtime and legacy tests, and leave guardrails proving the clean rebuild imports only the `coke/` package.

**Architecture:** This is a destructive clean rebuild operation. The top-level `web/` package becomes the only web client and talks to the Python API through one configurable public base URL; all Gateway API, Bridge, Mongo, memo-runtime, legacy agent/runtime, and compatibility test surfaces are removed rather than shimmed.

**Tech Stack:** Python 3.12, pytest, Flask clean API package, SQLAlchemy schema metadata, zsh/bash guardrails, Next.js 16, TypeScript, Vitest.

---

**Plan Status:** complete
**Status Date:** 2026-05-30
**Source Specs:**
- `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md` Task 11, Task 12, and Architecture Issues To Watch During Execution.
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md` sections 5.1, 5.2, 5.3, 5.6, 5.7, 5.10, 5.11, 5.12, and 5.13.
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md` sections 3, 4, 8, 9, and deletion/out-of-scope notes.

## File Structure

- Modify `web/package.json`: rename the package to `@coke/web`.
- Modify `web/lib/customer-api.ts`, `web/lib/admin-api.ts`, `web/lib/user-link-api.ts`, and nearby tests: use `NEXT_PUBLIC_API_BASE_URL` as the single Python API base and keep `/api/*` paths as backend-owned paths.
- Create `web/lib/api-types.ts`: vendor the small API/user-link response types currently imported from the deleted shared package.
- Modify `web/OWNERS.md`: make ownership point to top-level `web`, not Gateway web.
- Modify `web/app/**` only where needed to remove Gateway or ClawScale-specific references while keeping required product pages.
- Delete `.gitmodules`, `gateway`, `memo-runtime`, `agent/`, `alibabacloud-nls-python-sdk-dev/`, `conf/`, `connector/`, `dao/`, `entity/`, `framework/`, `tools/`, `util/`, old process scripts, and non-`tests/unit/coke` tests.
- Modify `requirements.txt`, `pyproject.toml`, `Dockerfile`, and `docker-compose.prod.yml` to target the clean Python services and remove Mongo/legacy runtime dependencies.
- Modify `scripts/check`, `scripts/guardrails.py`, `scripts/verify-surface`, `scripts/suggest-verification`, `scripts/review-trigger`, `docs/fitness/ownership-registry.yaml`, `docs/fitness/surfaces.yaml`, and `scripts/e2e/clean-rebuild-canonical-doc-sync.sh` so repo-OS checks no longer require deleted paths.
- Create `tests/unit/coke/test_clean_rebuild_no_legacy_imports.py`: scan `coke/`, `migrations/`, and `tests/unit/coke/` for forbidden legacy imports.
- Modify current canonical docs only when they still present Gateway, Bridge, Mongo, or memo-runtime as a current runtime owner.

### Task 1: RED Guard Tests

**Files:**
- Create: `tests/unit/coke/test_clean_rebuild_no_legacy_imports.py`

- [x] **Step 1: Add the forbidden-import scanner**

Create the test with this structure:

```python
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCANNED_TREES = (ROOT / "coke", ROOT / "migrations", ROOT / "tests/unit/coke")
FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(from|import)\s+(pymongo|dao|connector|agent|entity|framework|util|memo_runtime|gateway)\b"
)


def test_clean_rebuild_sources_do_not_import_legacy_runtime() -> None:
    violations: list[str] = []
    for tree in SCANNED_TREES:
        for path in sorted(tree.rglob("*.py")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if FORBIDDEN_IMPORT_RE.match(line):
                    violations.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert violations == []
```

- [x] **Step 2: Run the new test and verify RED**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/test_clean_rebuild_no_legacy_imports.py -q`

Expected before implementation: FAIL because the scanner flags at least one forbidden import in the clean rebuild test file itself if the regex is too broad, or PASS if the current clean package already has no legacy imports. If it passes immediately, continue because this is an anti-regression guard for the deletion wave and not production code.

### Task 2: Web Extraction

**Files:**
- Modify: `web/package.json`
- Modify: `web/lib/customer-api.ts`
- Modify: `web/lib/admin-api.ts`
- Modify: `web/lib/user-link-api.ts`
- Create: `web/lib/api-types.ts`
- Modify: `web/lib/customer-api.test.ts`
- Modify: `web/lib/admin-api.test.ts`
- Modify: `web/lib/user-link-api.test.ts`
- Modify: `web/OWNERS.md`

- [x] **Step 1: Repoint package ownership**

Change `web/package.json` package name from `@clawscale/web` to `@coke/web`.

- [x] **Step 2: Vendor shared types inside web**

Create `web/lib/api-types.ts` with `ApiResponse`, `PublicUserLinkResponse`, `PublicLinkSessionResponse`, `PublicLinkSessionStatusResponse`, and `DirectFriendshipResponse` shapes used by `web/lib/user-link-api.ts`.

- [x] **Step 3: Replace shared package imports**

In `web/lib/user-link-api.ts`, replace `../../shared/src/types/*` imports with imports from `./api-types`.

- [x] **Step 4: Use one public API base**

In `web/lib/customer-api.ts` and `web/lib/admin-api.ts`, resolve only `NEXT_PUBLIC_API_BASE_URL`, trim trailing slashes, and append existing `/api/*` paths. Tests should assert `https://api.example.com/api/auth/me`, not Gateway or Bridge names.

- [x] **Step 5: Confirm required web routes still exist**

Run: `test -f` checks for auth, account, access-status or subscription, claim, channels, reminders, friends, shared reminders or equivalent shared-reminder route, settings/my-agent, calendar-import, `/`, `/faqs`, `/demos`, `/privacy`, `/terms`, and `web/app/u/[code]/page.tsx`.

- [x] **Step 6: Confirm no ClawScale package dependency remains**

Run: `rg -n "@clawscale|from '../../shared|from \"../../shared" web`

Expected: no matches except historical prose in already generated build output if generated output has not been removed; if `web/out` carries stale generated text, delete `web/out`.

- [x] **Step 7: Run web tests/build when possible**

Run from `web/`:

```bash
pnpm test
pnpm build
```

Expected: pass. If `pnpm` or dependencies are unavailable and network install would be required, skip and record the blocker.

Result: skipped full web test/build because `web/node_modules` is absent and `pnpm test` reports `vitest: not found`; no network install was performed.

- [x] **Step 8: Commit web extraction**

Run:

```bash
git add web
git commit -m "feat: extract coke web client"
```

### Task 3: Delete Legacy Runtime And Tests

**Files:**
- Delete: `.gitmodules`
- Delete: `gateway`
- Delete: `memo-runtime`
- Delete: `agent/`, `alibabacloud-nls-python-sdk-dev/`, `conf/`, `connector/`, `dao/`, `entity/`, `framework/`, `tools/`, `util/`
- Delete: `start.sh`, `stop.sh`, `pm2-manager.sh`, `ecosystem.config.json`
- Delete: everything under `tests/` except `tests/unit/coke/`
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Modify: `Dockerfile`
- Modify: `docker-compose.prod.yml`

- [x] **Step 1: Remove submodules**

Run:

```bash
git submodule deinit -f gateway
git rm -f gateway
rm -rf .git/modules/gateway
git submodule deinit -f memo-runtime
git rm -f memo-runtime
rm -rf .git/modules/memo-runtime
git rm .gitmodules
```

- [x] **Step 2: Uninstall the legacy editable package**

Run: `/data/projects/coke/.venv/bin/pip uninstall -y coke-memo-runtime`

- [x] **Step 3: Delete legacy runtime directories and process scripts**

Run `git rm -r` for the listed legacy directories and old process scripts.

- [x] **Step 4: Delete legacy tests**

Remove every tracked test outside `tests/unit/coke/`.

- [x] **Step 5: Remove legacy-only dependencies**

Remove `pymongo`, local `./alibabacloud-nls-python-sdk-dev`, and media/provider packages used only by deleted runtime code from `requirements.txt`. Keep clean rebuild dependencies: Agno, Flask, gunicorn, APScheduler, pydantic, Redis, SQLAlchemy, Alembic, psycopg, OpenTelemetry, pytest, and timezone/date helpers.

- [x] **Step 6: Narrow coverage**

Set `[tool.coverage.run].source` in `pyproject.toml` to `["coke"]`.

- [x] **Step 7: Repoint deploy files**

Update `Dockerfile` to start the Flask clean API by default and `docker-compose.prod.yml` to run `coke-api`, `coke-worker`, `coke-scheduler`, `web`, `postgres`, and `redis`, with no Mongo, Gateway, Bridge, or legacy agent command.

- [x] **Step 8: Commit legacy deletion**

Run:

```bash
git add -A
git commit -m "refactor: remove legacy coke runtime"
```

### Task 4: Repo-OS Guardrails

**Files:**
- Modify: `scripts/check`
- Modify: `scripts/guardrails.py`
- Modify: `scripts/verify-surface`
- Modify: `scripts/suggest-verification`
- Modify: `scripts/review-trigger`
- Modify: `docs/fitness/ownership-registry.yaml`
- Modify: `docs/fitness/surfaces.yaml`
- Modify: `scripts/e2e/clean-rebuild-canonical-doc-sync.sh`
- Modify: current canonical docs only if they still claim deleted runtime owners.

- [x] **Step 1: Update required-file checks**

Remove required files under deleted legacy paths from `scripts/check`; require `web/OWNERS.md`; remove the Gateway gitlink check.

- [x] **Step 2: Update ownership registry**

Remove legacy route/contract entries and retain clean rebuild ownership entries for `coke/**`, `web/**`, `migrations/**`, `docs/**`, and deployment/tooling.

- [x] **Step 3: Update surfaces**

Remove legacy surfaces and review triggers for `agent`, `connector`, `dao`, `gateway/packages`, `memo-runtime`, and similar paths. Repoint `clean-rebuild-web` and `web` to `web/**` with `cd web && pnpm test` and `cd web && pnpm build`.

- [x] **Step 4: Update guardrail scripts**

Change helper scripts that inspect tracked Gateway web files or legacy route registries so they inspect `web/**` and `coke/api/**`, or delete legacy-specific checks if no current clean-rebuild owner remains.

- [x] **Step 5: Strengthen canonical doc sync**

Keep current-target checks for The Turn, clean modules, Postgres/Redis, Mongo removed, and web over Python API. Add forbidden checks for current claims assigning product/API ownership to Gateway, Bridge, Mongo, or memo-runtime.

- [x] **Step 6: Commit repo-OS cleanup**

Run:

```bash
git add scripts docs pyproject.toml requirements.txt Dockerfile docker-compose.prod.yml tests/unit/coke
git commit -m "chore: repoint repo os to clean rebuild"
```

### Task 5: Final Verification And Plan Closeout

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-legacy-deletion.md`

- [x] **Step 1: Run clean unit suite**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`

Expected: at least `312 passed`; include the new no-legacy guard.

- [x] **Step 2: Run repo-OS and canonical sync**

Run:

```bash
zsh scripts/check
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
```

Expected: both exit 0.

- [x] **Step 3: Confirm removed root directories**

Run:

```bash
for path in agent connector dao entity framework util conf tools alibabacloud-nls-python-sdk-dev memo-runtime gateway; do test ! -e "$path"; done
```

Expected: exit 0.

- [x] **Step 4: Inspect status and commits**

Run:

```bash
git status --short
git log --oneline main..HEAD
```

Expected: status clean after the final plan-status commit; log lists this slice's coherent commits.

- [x] **Step 5: Mark plan complete**

After all verification commands pass, change `Plan Status` to `complete`, update status date if needed, and commit the plan closeout.
