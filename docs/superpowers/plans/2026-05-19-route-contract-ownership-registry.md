# Route Contract Ownership Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a machine-readable ownership registry so every current `gateway/packages/api/src/routes/*.ts` file and selected cross-system contracts declare an ownership system.

**Architecture:** Store ownership metadata in `docs/fitness/ownership-registry.yaml` and check it from `scripts/check`. The first guardrail covers all current non-test files under `gateway/packages/api/src/routes/` plus selected cross-system contracts, and fails on missing registry entries, missing files, or invalid owners. It does not yet enforce import direction or cover `gateway/packages/api/src/gateway/**`.

**Tech Stack:** YAML, Python guardrails, pytest, zsh repo-OS checks.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Execute after canonical doc sync so ownership vocabulary is stable.

## Scope

Included:

- Add a registry for current route/contract ownership.
- Add Python validation for required registry entries.
- Wire validation into `scripts/check`.

Excluded:

- Import-boundary enforcement.
- Full file inventory.
- CODEOWNERS integration.

## File Map

- `docs/fitness/ownership-registry.yaml`: new registry.
- `docs/fitness/README.md`: document registry purpose.
- `scripts/guardrails.py`: load and validate ownership registry.
- `tests/unit/test_guardrail_scripts.py`: registry validation tests.
- `scripts/check`: invoke registry check.

## Work Breakdown

### Task 1: Create Ownership Registry

**Files:**
- Create: `docs/fitness/ownership-registry.yaml`
- Modify: `docs/fitness/README.md`

- [x] **Step 1: Create initial registry**

Create `docs/fitness/ownership-registry.yaml`:

```yaml
schema: coke-ownership-registry-v1

systems:
  - frontend-app
  - platform
  - channel
  - reminder
  - memo
  - calendar-import
  - timezone
  - other-capability
  - bridge
  - agent-runtime
  - state-infrastructure

routes:
  - path: gateway/packages/api/src/routes/admin-admins.ts
    owner: platform
  - path: gateway/packages/api/src/routes/admin-auth-routes.ts
    owner: platform
  - path: gateway/packages/api/src/routes/admin-customers.ts
    owner: platform
  - path: gateway/packages/api/src/routes/admin-deliveries.ts
    owner: channel
    secondary_owner: platform
  - path: gateway/packages/api/src/routes/admin-shared-channels.ts
    owner: channel
    secondary_owner: platform
  - path: gateway/packages/api/src/routes/calendar-import-handoff-routes.ts
    owner: calendar-import
  - path: gateway/packages/api/src/routes/coke-bindings.ts
    owner: platform
    secondary_owner: bridge
  - path: gateway/packages/api/src/routes/coke-delivery-routes.ts
    owner: channel
    secondary_owner: bridge
  - path: gateway/packages/api/src/routes/coke-user-provision.ts
    owner: platform
    secondary_owner: bridge
  - path: gateway/packages/api/src/routes/customer-auth-routes.ts
    owner: platform
  - path: gateway/packages/api/src/routes/customer-channel-routes.ts
    owner: platform
    secondary_owner: channel
  - path: gateway/packages/api/src/routes/customer-claim-routes.ts
    owner: platform
  - path: gateway/packages/api/src/routes/customer-google-calendar-import-callback-routes.ts
    owner: calendar-import
  - path: gateway/packages/api/src/routes/customer-google-calendar-import-routes.ts
    owner: calendar-import
  - path: gateway/packages/api/src/routes/customer-reminder-routes.ts
    owner: reminder
  - path: gateway/packages/api/src/routes/customer-subscription-routes.ts
    owner: platform
  - path: gateway/packages/api/src/routes/outbound.ts
    owner: channel
  - path: gateway/packages/api/src/routes/user-wechat-channel.ts
    owner: channel
    secondary_owner: platform

contracts:
  - path: agent/reminder/runtime_contract.py
    owner: reminder
  - path: memo-runtime/memo_runtime/contract.py
    owner: memo
  - path: agent/agno_agent/capabilities/timezone_port.py
    owner: timezone
  - path: agent/agno_agent/capabilities/calendar_import_port.py
    owner: calendar-import
```

- [x] **Step 2: Document registry in fitness README**

Add a short section:

```markdown
## Ownership Registry

`docs/fitness/ownership-registry.yaml` maps route and contract files to the
ownership systems defined in
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`.
It complements planning surfaces; it does not replace `surfaces.yaml`.
```

### Task 2: Add Registry Validation

**Files:**
- Modify: `scripts/guardrails.py`
- Modify: `tests/unit/test_guardrail_scripts.py`
- Modify: `scripts/check`

- [x] **Step 1: Add failing tests**

Add tests that call `guardrails.validate_ownership_registry` with an invalid owner, a missing route path, and a current route file that is omitted from the registry. Expected errors:

```python
[
    "ownership registry missing route entry: gateway/packages/api/src/routes/customer-subscription-routes.ts",
    "ownership registry route missing file: gateway/packages/api/src/routes/missing.ts",
    "ownership registry invalid owner made-up for gateway/packages/api/src/routes/customer-auth-routes.ts",
]
```

- [x] **Step 2: Implement registry validation**

Add to `scripts/guardrails.py`:

```python
OWNERSHIP_REGISTRY_PATH = ROOT / "docs" / "fitness" / "ownership-registry.yaml"

def load_ownership_registry() -> dict[str, Any]:
    return yaml.safe_load(OWNERSHIP_REGISTRY_PATH.read_text(encoding="utf-8")) or {}

def expected_route_registry_paths() -> set[str]:
    routes_root = ROOT / "gateway" / "packages" / "api" / "src" / "routes"
    return {
        str(path.relative_to(ROOT))
        for path in routes_root.glob("*.ts")
        if not path.name.endswith(".test.ts")
    }

def validate_ownership_registry(registry: dict[str, Any] | None = None) -> list[str]:
    data = registry or load_ownership_registry()
    systems = {str(system) for system in data.get("systems", [])}
    errors: list[str] = []
    registered_route_paths: set[str] = set()
    for section in ("routes", "contracts"):
        for item in data.get(section, []):
            path = str(item.get("path", ""))
            owner = str(item.get("owner", ""))
            if section == "routes" and path:
                registered_route_paths.add(path)
            if path and not (ROOT / path).exists():
                errors.append(f"ownership registry {section[:-1]} missing file: {path}")
            if owner not in systems:
                errors.append(f"ownership registry invalid owner {owner} for {path}")
            secondary = item.get("secondary_owner")
            if secondary is not None and str(secondary) not in systems:
                errors.append(f"ownership registry invalid secondary_owner {secondary} for {path}")
    for path in sorted(expected_route_registry_paths() - registered_route_paths):
        errors.append(f"ownership registry missing route entry: {path}")
    return errors
```

Wire a `check-ownership-registry` subcommand that prints `OK ownership registry` when clean.

- [x] **Step 3: Wire into `scripts/check`**

Add:

```zsh
if ! "$python_cmd" scripts/guardrails.py check-ownership-registry; then
  missing=1
fi
```

### Task 3: Verify Registry

**Files:**
- Read: registry and guardrail files
- Create: `scripts/e2e/route-contract-ownership-registry.sh`

- [x] **Step 1: Run focused tests**

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/route-contract-ownership-registry
.venv/bin/python -m pytest tests/unit/test_guardrail_scripts.py -v \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/route-contract-ownership-registry/pytest.log
```

Expected: guardrail tests pass.

- [x] **Step 2: Run repo-OS verification**

```bash
zsh scripts/check
zsh scripts/verify-surface repo-os \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/route-contract-ownership-registry/verify-surface.log
```

Expected: registry validation is part of repo-OS checks and passes.

- [x] **Step 3: E2E perturbation script — registry must fail when invariants break**

Create `scripts/e2e/route-contract-ownership-registry.sh` (executable). The script must prove the registry is *enforced*, not just declared. It performs three perturbations on a temporary copy of the registry and verifies each causes a non-zero exit:

1. **Invalid owner**: copy `docs/fitness/ownership-registry.yaml` to a temp file, change one route's owner to `made-up`, run `python scripts/guardrails.py check-ownership-registry --registry <tmp>` (or equivalent), expect non-zero plus an error mentioning `invalid owner made-up`.
2. **Missing file reference**: add a route entry pointing at `gateway/packages/api/src/routes/does-not-exist.ts`, expect non-zero plus an error mentioning `missing file`.
3. **Unregistered route**: remove one current route from the registry, expect non-zero plus an error mentioning `missing route entry`.

For each perturbation, write `{scenario, exit_code, matched_error}` to `artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/route-contract-ownership-registry/e2e-perturbations.jsonl`. Restore the original registry before exit. Print `[BEGIN]`/`[STEP <scenario>]`/`[OK <scenario>]`/`[FAIL <scenario>]` lines.

Expected: every perturbation correctly fails the check, and the script restores the registry to a clean state.

### Task 4: Optional Follow-up Scope — Gateway Subdir Coverage

**Files:**
- Modify: `docs/fitness/ownership-registry.yaml` (additional entries only)

- [x] **Step 1: Document the deferred scope**

The current implementation covers `gateway/packages/api/src/routes/*.ts` only. The boundary spec also identifies channel-owned code under `gateway/packages/api/src/gateway/` and `gateway/packages/api/src/adapters/`. Add a `## Deferred Scope` section to the inventory comment in the registry file naming these paths and a follow-up issue/bead reference. **Do not expand the check to those paths in this plan** — they require a separate file-pattern handler. The deferred scope documentation is the deliverable, not the expansion.

Expected: future readers can see the registry's known blind spot, and an explicit decision is recorded that it remains advisory for now.
