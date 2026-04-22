# Reminder Compatibility Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all remaining legacy reminder/future compatibility fields, audits, and stale docs so `deferred_actions` is the only live reminder runtime.

**Architecture:** Retire compatibility in three layers: runtime state, audit surfaces, and documentation/operations. Runtime and tests stop creating legacy fields, audits move from `reminders` to `deferred_actions`, and a dedicated cleanup script retires live Mongo remnants by unsetting `conversation_info.future` and archiving the old `reminders` collection.

**Tech Stack:** Python 3.12 / pytest, TypeScript / Vitest / pnpm, MongoDB, git worktrees

---

### Task 1: Remove `conversation_info.future` Runtime Compatibility

**Files:**
- Modify: `dao/conversation_dao.py`
- Modify: `tests/conftest.py`
- Modify: `tests/unit/test_context_timezone.py`
- Test: `tests/unit/test_context_timezone.py`

- [ ] **Step 1: Write the failing tests**

Add or update tests so they assert normalized/new conversation data does not include `conversation_info.future`.

```python
def test_context_prepare_omits_future_from_conversation_info(...):
    ...
    assert "future" not in ctx["conversation"]["conversation_info"]
```

```python
def test_sample_context_fixture_has_no_future(...):
    assert "future" not in sample_context["conversation"]["conversation_info"]
```

- [ ] **Step 2: Run tests to verify they fail for the right reason**

Run: `pytest tests/unit/test_context_timezone.py -v`
Expected: failure caused by legacy `future` still being present in conversation defaults or fixtures.

- [ ] **Step 3: Write the minimal implementation**

Remove `future` from the default conversation payloads and from `ensure_conversation_info_structure()`.

```python
if "turn_sent_contents" not in info:
    info["turn_sent_contents"] = []
```

```python
"conversation_info": {
    "chat_history": [],
    "input_messages": [],
    "input_messages_str": "",
    "chat_history_str": "",
    "photo_history": [],
    "turn_sent_contents": [],
}
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `pytest tests/unit/test_context_timezone.py tests/unit/runner/test_background_handler_deferred_only.py -v`
Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add dao/conversation_dao.py tests/conftest.py tests/unit/test_context_timezone.py
git commit -m "refactor: remove conversation future compatibility"
```

### Task 2: Replace Legacy `reminders` Audits With `deferred_actions`

**Files:**
- Modify: `dao/user_dao.py`
- Modify: `connector/scripts/verify-auth-retirement.py`
- Modify: `gateway/packages/api/src/scripts/audit-customer-id-parity.ts`
- Modify: `gateway/packages/api/src/scripts/audit-customer-id-parity.test.ts`
- Modify: `tests/unit/dao/test_user_dao_auth_retirement_audit.py`
- Test: `tests/unit/dao/test_user_dao_auth_retirement_audit.py`
- Test: `gateway/packages/api/src/scripts/audit-customer-id-parity.test.ts`

- [ ] **Step 1: Write the failing tests**

Update expectations to require `deferred_actions` instead of `reminders`.

```python
assert report["collectionsChecked"] == ["outputmessages", "deferred_actions", "conversations"]
```

```ts
expect(report.collectionsChecked).toEqual(['outputmessages', 'deferred_actions', 'conversations']);
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/dao/test_user_dao_auth_retirement_audit.py -v`
Expected: failure because Python audit code still returns `reminders`.

Run: `pnpm --dir gateway/packages/api test -- --run src/scripts/audit-customer-id-parity.test.ts`
Expected: failure because gateway audit still scans for `reminders`.

- [ ] **Step 3: Write the minimal implementation**

Replace each live collection spec and touchpoint matcher.

```python
AUDIT_CUSTOMER_ID_COLLECTION_SPECS = (
    {"collection": "outputmessages", "fieldPath": "account_id"},
    {"collection": "deferred_actions", "fieldPath": "user_id"},
    {"collection": "conversations", "fieldPath": "talkers.id"},
)
```

```ts
{
  collection: 'deferred_actions',
  description: 'DAO layer still stores Coke-owned deferred action rows',
  matches: (files) =>
    [...files.entries()].some(
      ([relativePath, content]) =>
        relativePath.startsWith('dao/')
        && content.includes('deferred_actions')
        && content.includes('user_id'),
    ),
},
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `pytest tests/unit/dao/test_user_dao_auth_retirement_audit.py -v`
Expected: all selected Python audit tests pass.

Run: `pnpm --dir gateway/packages/api test -- --run src/scripts/audit-customer-id-parity.test.ts`
Expected: Vitest passes for the audit script.

- [ ] **Step 5: Commit**

```bash
git add dao/user_dao.py connector/scripts/verify-auth-retirement.py tests/unit/dao/test_user_dao_auth_retirement_audit.py gateway/packages/api/src/scripts/audit-customer-id-parity.ts gateway/packages/api/src/scripts/audit-customer-id-parity.test.ts
git commit -m "refactor: point reminder audits to deferred actions"
```

### Task 3: Add Live Data Cleanup Script

**Files:**
- Create: `scripts/retire_legacy_reminder_compat.py`
- Test: `tests/unit/test_repo_os_structure.py`

- [ ] **Step 1: Write the failing verification expectation**

Add a structure assertion only if needed, otherwise use the script contract as the failing executable check:

```bash
python3 scripts/retire_legacy_reminder_compat.py --help
```

Expected: command exists and documents dry-run plus execute behavior.

- [ ] **Step 2: Run the command to verify it fails because the script does not exist**

Run: `python3 scripts/retire_legacy_reminder_compat.py --help`
Expected: file not found.

- [ ] **Step 3: Write the minimal implementation**

Create a script that reports legacy counts by default and performs cleanup under `--execute`.

```python
parser.add_argument("--execute", action="store_true")
...
future_result = conversations.update_many(
    {"conversation_info.future": {"$exists": True}},
    {"$unset": {"conversation_info.future": ""}},
)
legacy_name = f"reminders_legacy_retired_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
db["reminders"].rename(legacy_name)
```

- [ ] **Step 4: Run the command to verify it works**

Run: `python3 scripts/retire_legacy_reminder_compat.py --help`
Expected: exit 0 and usage text that includes dry-run and `--execute`.

- [ ] **Step 5: Commit**

```bash
git add scripts/retire_legacy_reminder_compat.py
git commit -m "feat: add legacy reminder compatibility retirement script"
```

### Task 4: Clean Docs And Run Final Verification

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/exec-plans/2026-04-21-deferred-actions-apscheduler-plan.md`
- Modify: `docs/superpowers/specs/2026-04-20-deferred-actions-apscheduler-design.md`
- Modify: `tasks/2026-04-22-reminder-compat-retirement.md`
- Modify: `docs/superpowers/specs/2026-04-22-reminder-compat-retirement-design.md`
- Modify: `docs/exec-plans/2026-04-22-reminder-compat-retirement-plan.md`
- Test: `tests/unit/test_repo_os_structure.py`

- [ ] **Step 1: Write the failing doc/structure expectation**

Use repo-os verification as the red phase and remove stale wording before the green phase.

```bash
pytest tests/unit/test_repo_os_structure.py -v
```

Expected: passes after docs/task artifacts are consistent and present.

- [ ] **Step 2: Update docs**

Trim or rewrite wording that still frames legacy reminder cleanup as pending. Keep genuine history, but remove misleading current-state descriptions.

```md
- no runtime path depends on `conversation_info.future`
- legacy `reminders` collection references have been retired in favor of `deferred_actions`
```

- [ ] **Step 3: Run final verification**

Run: `pytest tests/unit/test_context_timezone.py tests/unit/runner/test_background_handler_deferred_only.py tests/unit/dao/test_user_dao_auth_retirement_audit.py tests/unit/test_repo_os_structure.py -v`
Expected: all selected Python tests pass.

Run: `pnpm --dir gateway/packages/api test -- --run src/scripts/audit-customer-id-parity.test.ts`
Expected: target Vitest passes.

Run: `zsh scripts/check`
Expected: repo-os checks pass.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture.md docs/exec-plans/2026-04-21-deferred-actions-apscheduler-plan.md docs/superpowers/specs/2026-04-20-deferred-actions-apscheduler-design.md tasks/2026-04-22-reminder-compat-retirement.md docs/superpowers/specs/2026-04-22-reminder-compat-retirement-design.md docs/exec-plans/2026-04-22-reminder-compat-retirement-plan.md
git commit -m "docs: retire legacy reminder compatibility references"
```
