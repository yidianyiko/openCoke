# System Owners Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lightweight `OWNERS.md` metadata to primary ownership-system directories so ownership is visible outside the long boundary spec.

**Architecture:** Each primary system directory gets a one-page `OWNERS.md` naming the ownership system, exposed contracts, allowed inbound callers, and verification surfaces. Repo-OS checks require these files for the first-pass primary directories.

**Tech Stack:** Markdown, Python repo-OS tests, zsh checks.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Execute after ownership registry and fitness surfaces exist.

## Scope

Included:

- Add `OWNERS.md` to primary system directories.
- Add repo-OS structure tests for required owners files.
- Link owner metadata to the boundary spec.

Excluded:

- CODEOWNERS.
- Per-file ownership inventory.
- GitHub review automation.

## File Map

- `agent/reminder/OWNERS.md`
- `memo-runtime/OWNERS.md`
- `connector/clawscale_bridge/OWNERS.md`
- `agent/agno_agent/OWNERS.md`
- `gateway/packages/api/src/channel/OWNERS.md`
- `gateway/packages/web/OWNERS.md`
- `tests/unit/test_repo_os_structure.py`

## Work Breakdown

### Task 1: Add First-Pass Owners Files

**Files:**
- Create: listed `OWNERS.md` files

- [x] **Step 1: Add Reminder owners file**

Create `agent/reminder/OWNERS.md`:

```markdown
# Reminder System Owners

Ownership system: Reminder System

Boundary spec:
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`

Owns:

- Runtime Reminder Contract
- reminder lifecycle, recurrence, schedule, and reminder domain state
- internal follow-up reminders

Allowed inbound callers:

- Agent Runtime through `agent/reminder/runtime_contract.py`
- Gateway customer reminder API through Reminder-owned route adapters
- Bridge reminder management adapter for internal integration

Verification surfaces:

- `product-reminder`
- `worker-runtime`
```

- [x] **Step 2: Add Bridge owners file**

Create `connector/clawscale_bridge/OWNERS.md` with ownership system `Bridge System`, owned ingress/egress protocol adaptation, and allowed callers Channel/Gateway internal integration and Agent Runtime output flow.

- [x] **Step 3: Add Channel owners file**

Create `gateway/packages/api/src/channel/OWNERS.md` with ownership system `Channel System`, owned provider config schemas and channel management service contract.

- [x] **Step 4: Add remaining owners files**

Create owners files for:

- `memo-runtime/OWNERS.md` as Memo System.
- `agent/agno_agent/OWNERS.md` as Agent Runtime adapter/capability host.
- `gateway/packages/web/OWNERS.md` as Frontend App.

Use the same section structure as Reminder.

### Task 2: Add Repo-OS Owners Check

**Files:**
- Modify: `tests/unit/test_repo_os_structure.py`
- Modify: `scripts/check`

- [x] **Step 1: Add required owners existence and content tests**

Add to `tests/unit/test_repo_os_structure.py`. The test must verify (a) the file exists, (b) it links to the boundary spec, (c) it names an ownership system, and (d) the named system matches a system from the ownership registry once that exists:

```python
import re

REQUIRED_OWNERS = [
    ("agent/reminder/OWNERS.md", "Reminder System"),
    ("memo-runtime/OWNERS.md", "Memo System"),
    ("connector/clawscale_bridge/OWNERS.md", "Bridge System"),
    ("agent/agno_agent/OWNERS.md", "Agent Runtime"),
    ("gateway/packages/api/src/channel/OWNERS.md", "Channel System"),
    ("gateway/packages/web/OWNERS.md", "Frontend App"),
]

BOUNDARY_SPEC = "docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md"


def test_primary_ownership_directories_have_owners_metadata():
    missing = [path for path, _ in REQUIRED_OWNERS if not (ROOT / path).exists()]
    assert missing == []


def test_owners_files_reference_boundary_spec():
    for path, _ in REQUIRED_OWNERS:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert BOUNDARY_SPEC in text, f"{path} missing reference to {BOUNDARY_SPEC}"


def test_owners_files_name_expected_system():
    for path, expected_system in REQUIRED_OWNERS:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert re.search(
            rf"Ownership system:\s*{re.escape(expected_system)}", text
        ), f"{path} does not declare ownership system {expected_system!r}"


def test_owners_systems_appear_in_registry():
    """Cross-check: every system named in an OWNERS.md must exist as a registered
    system in docs/fitness/ownership-registry.yaml. This catches typos and drift.
    """
    import yaml

    registry_path = ROOT / "docs" / "fitness" / "ownership-registry.yaml"
    if not registry_path.exists():
        # Registry plan has not landed yet; skip cross-check.
        return
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    systems = {str(s) for s in registry.get("systems", [])}

    # Map human-readable system names from OWNERS.md to the registry's kebab-case ids.
    mapping = {
        "Reminder System": "reminder",
        "Memo System": "memo",
        "Bridge System": "bridge",
        "Agent Runtime": "agent-runtime",
        "Channel System": "channel",
        "Frontend App": "frontend-app",
    }
    for path, expected_system in REQUIRED_OWNERS:
        registry_id = mapping.get(expected_system)
        assert registry_id in systems, (
            f"system {expected_system!r} (declared in {path}) not in registry"
        )
```

These tests catch both missing OWNERS files AND drift between OWNERS files and the registry.

- [x] **Step 2: Add `scripts/check` required files**

Add each `OWNERS.md` path to the `required_files` array in `scripts/check`.

### Task 3: Verify Owners Metadata

**Files:**
- Read: owners files and repo-OS tests

- [x] **Step 1: Run repo-OS tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_repo_os_structure.py -v
zsh scripts/check
```

Expected: tests and check pass.

- [x] **Step 2: Scan owners files for boundary spec link with evidence emission**

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/system-owners-metadata
rg -n "2026-05-19-frontend-platform-channel-boundary-design.md" \
  agent/reminder/OWNERS.md memo-runtime/OWNERS.md connector/clawscale_bridge/OWNERS.md \
  agent/agno_agent/OWNERS.md gateway/packages/api/src/channel/OWNERS.md gateway/packages/web/OWNERS.md \
  | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/system-owners-metadata/spec-links.txt
.venv/bin/python -m pytest tests/unit/test_repo_os_structure.py -v \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/system-owners-metadata/pytest.log
```

Expected: every owners file links to the boundary spec; structure tests pass.

### Task 4: E2E Owners Metadata Verifier

**Files:**
- Create: `scripts/e2e/system-owners-metadata.sh`

- [x] **Step 1: Add e2e verifier**

Create `scripts/e2e/system-owners-metadata.sh` (executable) that:

1. Iterates the six required `OWNERS.md` paths.
2. For each: prints the declared `Ownership system:` line, the count of bullet items under `Allowed inbound callers:`, and the count under `Verification surfaces:`.
3. Confirms every file has all four sections (`Owns`, `Allowed inbound callers`, `Verification surfaces`, and a link to the boundary spec).
4. Writes `{path, system, sections_present, missing}` JSON lines to `artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/system-owners-metadata/e2e.jsonl`.
5. Prints `[BEGIN]`/`[STEP <path>]`/`[OK <path>]`/`[FAIL <path> <reason>]` lines and exits non-zero on the first failure.

Expected: every OWNERS.md is structurally complete and discoverable.

