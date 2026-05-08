# Coke Repo OS Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a canonical repo-OS skeleton to Coke while preserving the current `docs/superpowers` design/plan history.

**Architecture:** Introduce a small repository-control layer on top of the
existing runtime repository: new canonical doc homes, task and execution-plan
directories, a repository-level structure check, and updated routing docs.
Treat `docs/superpowers` as the existing design/plan archive and transition
zone instead of deleting or mass-moving it.

**Tech Stack:** Markdown, zsh, pytest, existing Coke repository layout

---

### Task 1: Add a failing repository-structure regression test

**Files:**
- Create: `tests/unit/test_repo_os_structure.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_repo_os_required_files_exist():
    required = [
        ROOT / "docs" / "design-docs" / "index.md",
        ROOT / "docs" / "design-docs" / "core-beliefs.md",
        ROOT / "docs" / "design-docs" / "golden-rules.md",
        ROOT / "docs" / "adr" / "README.md",
        ROOT / "docs" / "fitness" / "README.md",
        ROOT / "docs" / "exec-plans" / "README.md",
        ROOT / "tasks" / "README.md",
        ROOT / "scripts" / "check",
    ]

    missing = [path for path in required if not path.exists()]
    assert missing == []


def test_scripts_check_passes():
    result = subprocess.run(
        ["zsh", "scripts/check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "check passed" in result.stdout
```

- [ ] **Step 2: Run the test to confirm it fails**

Run:

```bash
pytest tests/unit/test_repo_os_structure.py -v
```

Expected: FAIL because the new canonical files and `scripts/check` do not exist
yet.

### Task 2: Add the canonical repo-OS skeleton and verification entrypoint

**Files:**
- Create: `docs/design-docs/index.md`
- Create: `docs/design-docs/core-beliefs.md`
- Create: `docs/design-docs/golden-rules.md`
- Create: `docs/adr/README.md`
- Create: `docs/adr/_template.md`
- Create: `docs/adr/0001-canonical-repo-os-structure.md`
- Create: `docs/fitness/README.md`
- Create: `docs/fitness/verification-checklist.md`
- Create: `docs/exec-plans/README.md`
- Create: `docs/exec-plans/_template.md`
- Create: `tasks/README.md`
- Create: `tasks/_template.md`
- Create: `scripts/check`

- [ ] **Step 1: Add the new canonical docs and templates**

Add focused markdown files that explain:

```md
- `docs/design-docs/` is the canonical home for repo-level beliefs and rules.
- `docs/adr/` records durable repository/workflow decisions.
- `docs/fitness/` defines what counts as verification evidence.
- `docs/exec-plans/` is the canonical home for new execution plans.
- `tasks/` stores task-local state.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` remain valid
  historical and transitional design/plan artifacts.
```

- [ ] **Step 2: Add the repo-level structure check**

Create a zsh entrypoint that validates the required skeleton:

```zsh
#!/usr/bin/env zsh
set -euo pipefail

typeset -a required_files=(
  "AGENTS.md"
  "CLAUDE.md"
  "README.md"
  "docs/design-docs/index.md"
  "docs/design-docs/core-beliefs.md"
  "docs/design-docs/golden-rules.md"
  "docs/adr/README.md"
  "docs/adr/_template.md"
  "docs/adr/0001-canonical-repo-os-structure.md"
  "docs/exec-plans/README.md"
  "docs/exec-plans/_template.md"
  "docs/fitness/README.md"
  "docs/fitness/verification-checklist.md"
  "tasks/README.md"
  "tasks/_template.md"
  "scripts/check"
)
```

- [ ] **Step 3: Make `scripts/check` executable and run the targeted test**

Run:

```bash
chmod +x scripts/check
pytest tests/unit/test_repo_os_structure.py -v
```

Expected: PASS.

### Task 3: Update the root routing docs to use the new canonical structure

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Rewrite `AGENTS.md` as a routing layer**

Ensure `AGENTS.md` covers:

```md
- reading order for new agents
- repository map
- documentation, delivery, and validation rules
- when to use `tasks/` and `docs/exec-plans/`
- the relationship between canonical docs and `docs/superpowers`
```

- [ ] **Step 2: Align `CLAUDE.md` and `README.md` with the new map**

Add references so the root docs consistently point to:

```md
- `docs/design-docs/index.md`
- `docs/fitness/README.md`
- `docs/exec-plans/`
- `tasks/`
```

- [ ] **Step 3: Run final verification**

Run:

```bash
pytest tests/unit/test_repo_os_structure.py -v
zsh scripts/check
```

Expected: both commands succeed and `scripts/check` ends with `check passed`.

## Notes

- Do not move or rename historical `docs/superpowers` artifacts in this change.
- Keep Coke’s runtime, product, architecture, and deployment docs intact; only
  add the repository-control layer above them.
