# Reminder Compatibility Retirement Design

## Summary

`coke` has already moved reminder execution to `deferred_actions`, but the repository still carries compatibility artifacts from the split `future` / `reminder` runtime. Those artifacts are now harmful: they imply old data is still live, keep tests and audits pointed at dead collections, and leave stale fields in new documents.

This change retires those artifacts completely. After it lands, `deferred_actions` and `deferred_action_occurrences` are the only live reminder runtime and reminder audit surfaces.

## Goals

- Remove runtime creation and normalization of `conversation_info.future`
- Remove active references to Mongo `reminders` as a live business collection
- Provide a safe cleanup path for production Mongo data
- Update or delete outdated docs that still describe legacy compatibility as current

## Non-Goals

- No behavioral redesign of deferred actions
- No migration of historical reminder documents into `deferred_actions`
- No broad doc rewrite outside reminder-compatibility surfaces

## Current Compatibility Inventory

### Runtime compatibility

- `dao/conversation_dao.py` still seeds new conversations with `conversation_info.future`
- `ensure_conversation_info_structure()` still backfills `future` into older conversation documents
- Python fixtures still model `future` as part of the expected conversation shape

### Legacy collection compatibility

- `dao/user_dao.py` still audits `reminders.user_id`
- `connector/scripts/verify-auth-retirement.py` still checks `reminders.user_id`
- `gateway/packages/api/src/scripts/audit-customer-id-parity.ts` still expects a live `reminders` touchpoint
- Related tests still encode the same assumption

### Documentation compatibility

- Some active and transitional docs still describe future/reminder compatibility cleanup as pending
- Historical plan/spec files still contain wording that is now misleading if read as current state

## Design

### 1. Runtime state model

Conversation documents will no longer contain `conversation_info.future` by default, and the DAO will stop recreating it for legacy rows. The minimal normalized shape remains:

- `chat_history`
- `input_messages`
- `input_messages_str`
- `chat_history_str`
- `photo_history`
- `turn_sent_contents`

This makes conversation state match the live runtime boundary: proactive scheduling is owned by `deferred_actions`, not embedded in conversation metadata.

### 2. Audit model

All live audit surfaces that previously pointed at `reminders` will be updated to `deferred_actions`.

That means:

- Python-side auth-retirement audits check `deferred_actions.user_id`
- Gateway-side customer-id parity audits check `deferred_actions.user_id`
- Touchpoint descriptions talk about deferred actions, not reminder rows

This preserves the useful invariant, "Coke still owns reminder-like business state in Mongo," without encoding the dead collection name.

### 3. Data cleanup path

The repository will gain a one-time cleanup script for live Mongo data. The script will:

1. report how many conversation documents still contain `conversation_info.future`
2. report whether the legacy `reminders` collection exists and how many documents it contains
3. on execute mode, `$unset` `conversation_info.future`
4. on execute mode, archive the legacy `reminders` collection by renaming it to a dated backup name, then leave the live `reminders` name absent

Renaming instead of immediate hard-drop keeps the cleanup reversible while still removing the live compatibility surface.

### 4. Documentation policy

Canonical docs must describe only the final state:

- deferred actions own all reminder/proactive scheduling
- no runtime path depends on `conversation_info.future`
- the legacy `reminders` collection is retired

Transitional docs will be trimmed or annotated when they still read like live instructions. Historical docs that merely mention the old design as history can stay, but stale "pending cleanup" wording should be removed.

## File-Level Plan

- `dao/conversation_dao.py`
  - remove `future` from default conversation structures
  - stop backfilling `future` in normalization
- `tests/conftest.py` and targeted unit tests
  - remove `future` from fixtures and update assertions
- `dao/user_dao.py`
  - replace `reminders` audit spec with `deferred_actions`
- `connector/scripts/verify-auth-retirement.py`
  - replace `reminders` collection path with `deferred_actions`
- `gateway/packages/api/src/scripts/audit-customer-id-parity.ts`
  - replace `reminders` touchpoint detection with `deferred_actions`
- `gateway/packages/api/src/scripts/audit-customer-id-parity.test.ts`
  - update expected collection names and file evidence
- `scripts/`
  - add the cleanup script for legacy conversation fields and legacy reminder collection retirement
- `docs/architecture.md`, `docs/exec-plans/2026-04-21-deferred-actions-apscheduler-plan.md`, and related transitional docs
  - remove stale compatibility wording or mark it historical

## Testing Strategy

### Python

- conversation/context regression tests prove the runtime no longer expects `future`
- auth-retirement audit tests prove the live collection is now `deferred_actions`
- repo-os checks protect updated task/plan/doc artifacts

### Gateway

- targeted Vitest for `audit-customer-id-parity` proves the JS audit now scans for `deferred_actions`

### Manual / Operational

- run the cleanup script in dry-run mode first
- then run it in execute mode against the target environment
- verify no live documents still expose `conversation_info.future`
- verify `reminders` no longer exists under the live collection name

## Risks And Mitigations

- Risk: old code paths still assume `future` exists in fixture data
  - Mitigation: remove it from shared fixtures first and let failing tests reveal the remaining callers
- Risk: production still has legacy reminder rows someone may want to inspect
  - Mitigation: rename to a dated archive collection instead of hard-dropping immediately
- Risk: historical docs become harder to interpret after cleanup
  - Mitigation: trim only misleading "current state" wording; keep genuine historical context when it is clearly framed as history
