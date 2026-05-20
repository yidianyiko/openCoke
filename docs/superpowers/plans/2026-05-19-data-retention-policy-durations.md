# Data Retention Policy Durations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace retention policy names without durations with concrete durations, cleanup owners, and evidence requirements.

**Architecture:** Add a dedicated data-retention policy document and link it from the boundary spec. In the same change, replace the spec’s “still needs a data-governance decision” wording with a concrete pointer to that policy doc. Keep cleanup commands as named future operational entry points unless an existing cleanup command already exists.

**Tech Stack:** Markdown docs, repo-OS checks, optional future cleanup scripts.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Execute after system owners metadata exists.

## Scope

Included:

- Define concrete durations for retention policy identifiers in the boundary spec.
- Name cleanup owners and required evidence for deletion/retention jobs.
- Link the policy doc from canonical architecture docs.

Excluded:

- Implementing destructive cleanup commands.
- Changing live database retention behavior in the same plan.
- Legal policy approval workflow outside the repo.

## File Map

- `docs/design-docs/data-retention-policy.md`: new policy document.
- `docs/design-docs/index.md`: link policy document.
- `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`: link policy doc and remove duration ambiguity from retention section.

## Work Breakdown

### Task 1: Add Data Retention Policy Doc

**Files:**
- Create: `docs/design-docs/data-retention-policy.md`
- Modify: `docs/design-docs/index.md`

- [x] **Step 1: Create policy doc**

Create `docs/design-docs/data-retention-policy.md`:

```markdown
# Data Retention Policy

This document defines retention policy identifiers used by ownership-system
docs. Durations are product defaults and do not replace customer-specific legal
requirements.

| Policy | Duration | Cleanup owner | Evidence required |
| --- | --- | --- | --- |
| `user_content_retention` | account lifetime plus 30 days | Reminder System | deletion run id, affected owner ids, dry-run count |
| `short_lived_workflow_retention` | 30 days after terminal workflow state | Reminder System | workflow count by terminal state |
| `conversation_retention` | 180 days | Agent Runtime System | input/output message count by owner and cutoff |
| `calendar_import_retention` | 365 days | Calendar Import System | import run count by cutoff |
| `handoff_session_retention` | 14 days after expiry | Calendar Import System | handoff session count by cutoff |
| `timezone_state_retention` | account lifetime plus 30 days | Timezone System | owner ids and changed settings count |
| `memo_retention` | account lifetime plus 30 days | Memo System | memo card count by owner and cutoff |
| `ephemeral_runtime_retention` | 7 days | Agent Runtime System | lock/batch state count |
| `ephemeral_trigger_retention` | 24 hours | Agent Runtime System | Redis key or stream trim evidence |
| `migration_retention` | 90 days after migration closeout | Owning migration plan | migration evidence path and archive count |
```

## Rule

Any plan that introduces deletion behavior must include a dry-run command,
a non-dry-run command, and evidence output under `artifacts/evidence/`.
```

- [x] **Step 2: Link from design docs index**

Add `docs/design-docs/data-retention-policy.md` to `docs/design-docs/index.md`.

### Task 2: Link Policy From Boundary Spec

**Files:**
- Modify: `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`

- [x] **Step 1: Replace retention ambiguity sentence**

In the State and Infrastructure section, replace the paragraph about durations needing a data-governance decision with:

```markdown
Concrete duration defaults live in
`docs/design-docs/data-retention-policy.md`. A change that introduces deletion
behavior must define dry-run evidence and cleanup ownership in the same plan.
```

- [x] **Step 2: Rewrite the follow-up item as a concrete pointer**

In the Follow-up Work Items section, replace the Retention policy durations item with a short concrete pointer so the promoted spec no longer says durations still need a separate unnamed decision:

```markdown
### Retention policy durations

- **Owner:** State and Infrastructure System with each data owner.
- **Status:** planned by `docs/superpowers/plans/2026-05-19-data-retention-policy-durations.md`; resolved when `docs/design-docs/data-retention-policy.md` lands.
```

### Task 3: Add Automated Cross-Doc Consistency Test

**Files:**
- Create: `tests/unit/test_data_retention_policy_consistency.py`

- [x] **Step 1: Add a Python test that parses both docs and verifies policy names align**

The boundary spec's State table names retention policy identifiers (`user_content_retention`, etc.) and the new policy doc table defines durations for those same identifiers. The two MUST stay in sync. Add `tests/unit/test_data_retention_policy_consistency.py`:

```python
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_DOC = ROOT / "docs" / "design-docs" / "data-retention-policy.md"
BOUNDARY_SPEC = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-05-19-frontend-platform-channel-boundary-design.md"
)

POLICY_NAME_RE = re.compile(r"`([a-z][a-z_]+_retention)`")


def _extract_policy_names(path: Path) -> set[str]:
    return set(POLICY_NAME_RE.findall(path.read_text(encoding="utf-8")))


def test_every_policy_in_boundary_spec_is_documented():
    spec_names = _extract_policy_names(BOUNDARY_SPEC)
    doc_names = _extract_policy_names(POLICY_DOC)
    missing = spec_names - doc_names
    assert missing == set(), (
        f"Retention policies named in boundary spec are missing from policy doc: {sorted(missing)}"
    )


def test_policy_doc_does_not_declare_unused_policies():
    spec_names = _extract_policy_names(BOUNDARY_SPEC)
    doc_names = _extract_policy_names(POLICY_DOC)
    extra = doc_names - spec_names
    # Allow `migration_retention` if it is documented but not yet referenced in spec.
    extra.discard("migration_retention")
    assert extra == set(), (
        f"Policy doc declares policies not used by boundary spec: {sorted(extra)}"
    )


def test_policy_doc_table_has_duration_and_owner_for_every_policy():
    text = POLICY_DOC.read_text(encoding="utf-8")
    for name in _extract_policy_names(POLICY_DOC):
        row_re = re.compile(
            rf"\|\s*`{re.escape(name)}`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
            re.MULTILINE,
        )
        match = row_re.search(text)
        assert match, f"policy {name} has no row in the policy doc table"
        duration, owner = match.group(1).strip(), match.group(2).strip()
        assert duration and "T" + "BD" not in duration, (
            f"policy {name} has empty or TBD duration"
        )
        assert owner, f"policy {name} has empty cleanup owner"
```

Expected: the test fails today (the docs do not exist yet) and passes after Task 1 and Task 2 land.

### Task 4: Verify Retention Docs

**Files:**
- Read: retention docs and boundary spec

- [x] **Step 1: Scan for unresolved retention wording with evidence**

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/data-retention-policy-durations
rg -n "duration.*need|still need|data-governance decision|unknown|T[B]D|TO[D]O" \
  docs/design-docs/data-retention-policy.md \
  docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md \
  | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/data-retention-policy-durations/unresolved-scan.txt
```

Expected: no unresolved wording remains.

- [x] **Step 2: Run repo-OS docs and consistency verification**

```bash
.venv/bin/python -m pytest tests/unit/test_data_retention_policy_consistency.py -v \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/data-retention-policy-durations/pytest.log
zsh scripts/check
zsh scripts/verify-surface repo-os-docs \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/data-retention-policy-durations/verify-surface.log
```

Expected: consistency test passes; docs verification passes.

### Task 5: E2E Policy Coverage Report

**Files:**
- Create: `scripts/e2e/data-retention-policy-durations.sh`

- [x] **Step 1: Add a coverage e2e**

Create `scripts/e2e/data-retention-policy-durations.sh` (executable) that:

1. Extracts every `*_retention` identifier from the boundary spec State table.
2. For each identifier, looks up its row in the policy doc and prints `policy=<name> duration=<value> owner=<value> evidence=<value>`.
3. Writes a JSON summary to `artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/data-retention-policy-durations/coverage.json` listing each policy, its duration, owner, and evidence-required field.
4. Prints `[BEGIN]`/`[STEP <policy>]`/`[OK <policy>]`/`[FAIL <policy> <missing>]` lines and exits non-zero if any spec-declared policy is missing from the doc.

Expected: every retention policy identifier in the spec has a concrete duration, owner, and evidence requirement in the policy doc.
