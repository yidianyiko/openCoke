# Segmented Delivery And Reminder Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Normalize product requirements storage, then implement segmented message delivery and reminder keyword/filter operations.

**Architecture:** Product requirements live in `docs/product-requirements/current.md`; legacy comparison evidence lives in `docs/issues/`. Runtime reply segments remain the Interaction Agent output contract, but delivery requests are emitted per outbound message segment. Reminder lookup stays owner-scoped inside the Reminder domain and exposes safe keyword resolution through the existing reminder tool adapter.

**Tech Stack:** Markdown repo-OS docs, Python domain services, Turn runner, Agno interaction prompt, pytest.

---

### Task 1: Documentation Boundary

**Files:**
- Move: `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md` -> `docs/product-requirements/current.md`
- Create: `docs/product-requirements/README.md`
- Create: `docs/issues/2026-05-31-legacy-capability-gap-analysis.md`
- Modify: `AGENTS.md`
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/design-docs/coke-working-contract.md`

- [x] **Step 1: Move the requirements baseline**

Run: `mkdir -p docs/product-requirements && git mv docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md docs/product-requirements/current.md`

Expected: the product requirements baseline is no longer in `docs/superpowers/specs/`.

- [x] **Step 2: Split requirement content from gap evidence**

Add `docs/product-requirements/README.md` describing that requirements contain only user goals, required behavior, boundaries, and acceptance criteria. Add the legacy gap issue for comparison evidence and selected implementation decisions.

- [x] **Step 3: Remove duplicated requirements from `FEATURE_TREE`**

Keep only module, web, API, webhook, and internal runtime discovery. Delete the detailed user-journey section from `docs/product-specs/FEATURE_TREE.md`.

### Task 2: Segmented Reply Delivery

**Files:**
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `coke/turn/runner.py`
- Modify: `docs/ARCHITECTURE.md`

- [x] **Step 1: Write the failing test**

Add a turn-runner test that returns `{"type":"reply","segments":["one","two"]}` and asserts two delivery requests, each with a single segment, its own outbound `message_id`, and a segment-specific idempotency key.

- [x] **Step 2: Run the focused test and confirm RED**

Run: `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reply_segments_deliver_as_separate_ordered_messages -q`

Expected: FAIL because the current runner sends one delivery request with joined text.

- [x] **Step 3: Implement per-segment delivery requests**

Change `TurnRunner._reply_delivery_requests` to create one `DeliveryRequest` per recipient per outbound segment. Each request uses the segment text as `visible_text`, a one-item `segments` tuple, the matching outbound message id, and an idempotency key containing the segment index.

### Task 3: Reminder Filtering And Keyword Resolution

**Files:**
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `coke/domains/reminder/models.py`
- Modify: `coke/domains/reminder/repository.py`
- Modify: `coke/domains/reminder/service.py`
- Modify: `coke/composition.py`
- Modify: `coke/llm/agno_interaction_agent.py`

- [x] **Step 1: Write failing Reminder-domain tests**

Add tests for keyword/time/status/type filtering, one-match keyword completion,
and ambiguous keyword completion returning `needs-follow-up` without mutation.

- [x] **Step 2: Run focused reminder tests and confirm RED**

Run: `.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py -q`

Expected: FAIL because filter and keyword-resolution APIs do not exist.

- [x] **Step 3: Implement owner-scoped filtering and safe keyword mutation**

Add service methods for `filter_reminders`, `complete_reminder_by_keyword`, `delete_reminder_by_keyword`, and `update_reminder_by_keyword`. Resolve keyword operations only when exactly one matching active, user-mutable reminder exists.

- [x] **Step 4: Expose operations through `ReminderToolAdapter`**

Add `filter_reminders`; allow `complete_reminder`, `delete_reminder`, and `update_reminder` to accept `keyword` when `reminder_id` is absent.

### Task 4: Prompt Micro-Rules And Verification

**Files:**
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`

- [x] **Step 1: Write prompt-contract tests**

Assert the prompt includes short message-style segmentation guidance, avoids generic customer-service closers, and instructs ordinary final statement segments not to end with `.` or `。`.

- [x] **Step 2: Implement prompt guidance**

Update `CokeVoicePolicy`, reminder-tool docs, and output contract instructions with the selected micro-rules.

- [x] **Step 3: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/llm/test_interaction_agent.py -q
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```
