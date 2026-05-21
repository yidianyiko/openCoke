# Dead Code Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove only dead code that is both reported by the scanner and confirmed with repository reference search.

**Architecture:** Use `vulture` as the primary Python dead-code scanner and `rg` as the caller proof. Treat framework routes, schema fields, DAO public methods, prompt constants, and test double signatures as dynamic or boundary surfaces unless a separate owner confirms removal.

**Tech Stack:** Python 3.12, vulture, pytest, zsh repo-OS guardrails.

---

### Task 1: Remove Confirmed Python Dead Code

**Files:**
- Modify: `agent/runner/agent_handler.py`
- Modify: `agent/runner/message_history.py`
- Modify: `agent/runner/rollback_detection.py`
- Modify: `tests/unit/agent/test_reminder_command_executor.py`

- [ ] **Step 1: Confirm scanner findings**

Run:

```bash
.venv/bin/vulture agent dao entity util framework connector tests scripts --exclude "*/__pycache__/*,*/.venv/*,*/node_modules/*,*/artifacts/*,*/logs/*" --min-confidence 90 --sort-by-size
rg -n "record_sent_messages_to_history|merge_pending_messages" agent dao entity util framework connector tests scripts
rg -n "executor_module" tests/unit/agent/test_reminder_command_executor.py
```

Expected: vulture reports the unused imports, unreachable return, and unused test import; `rg` shows the helper functions have no callers beyond their own definitions/imports.

- [ ] **Step 2: Remove unused imports and unreachable return**

In `agent/runner/agent_handler.py`, remove `record_sent_messages_to_history` and `merge_pending_messages` from the imports, and delete the unreachable `return resp_messages, context, is_rollback, is_content_blocked` after the exception re-raise.

- [ ] **Step 3: Remove uncalled internal helpers**

Delete `record_sent_messages_to_history()` from `agent/runner/message_history.py` and `merge_pending_messages()` from `agent/runner/rollback_detection.py`.

- [ ] **Step 4: Remove stale test import**

Delete `from agent.agno_agent.adapters import reminder_command_executor as executor_module` from `tests/unit/agent/test_reminder_command_executor.py`.

- [ ] **Step 5: Verify the cleanup**

Run:

```bash
.venv/bin/vulture agent dao entity util framework connector tests scripts --exclude "*/__pycache__/*,*/.venv/*,*/node_modules/*,*/artifacts/*,*/logs/*" --min-confidence 90 --sort-by-size
.venv/bin/python -m pytest tests/unit/agent/test_agent_handler.py tests/unit/agent/test_reminder_command_executor.py -v
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: vulture no longer reports these deleted items. Remaining reports, if any, are test double signature parameters or unrelated pre-existing modified files and should be documented instead of blindly removed.
