# Reminder Core Redesign

**Status:** draft for implementation
**Date:** 2026-04-28
**Supersedes:** `docs/superpowers/specs/2026-04-28-reminder-tool-contract-refactor-design.md`
**Surfaces:**
- new package `reminder/` (core, ingress, storage)
- bridge `connector/clawscale_bridge/app.py` (new HTTP routes)
- agent runtime `agent/runner/agent_runner.py` (scheduler boot moves into reminder core)
- agent surfaces `agent/agno_agent/workflows/post_analyze_workflow.py`,
  `agent/agno_agent/agents/__init__.py`,
  `agent/prompt/agent_instructions_prompt.py`,
  `agent/agno_agent/workflows/prepare_workflow.py`
- calendar import `connector/clawscale_bridge/google_calendar_import_service.py`
- removed: `agent/agno_agent/tools/deferred_action/`,
  `agent/runner/deferred_action_*.py`,
  `dao/deferred_action_dao.py`,
  collection `deferred_action_actions`

## Goal

Replace the `deferred_action` abstraction with a first-class `ReminderCore`
subsystem that owns all scheduled reminders regardless of who created them.
ReminderCore is independent of the agent runtime: the agent is one of several
clients, not the gatekeeper.

The system must satisfy:

- a non-LLM creation path (HTTP) works without any active conversation
- the LLM tool is a thin adapter that calls into ReminderCore
- agent-initiated proactive follow-ups are modeled as reminders
  (`actor=agent`, `visibility=internal`), not as a parallel concept
- failure to schedule a reminder is surfaced to the user, never silently dropped
- `trigger_at` and `rrule` semantics are validated in core, not in the prompt

## Non-Goals

- Non-chat delivery channels (push notification, email, webhook). Delivery
  abstraction exists, but v1 ships with chat delivery only.
- Gateway TypeScript route work. Web ingress lands at the bridge layer; the
  gateway-side proxy and UI are downstream tasks.
- Migration of historical `deferred_action_actions` data. The product is
  pre-launch; the collection is dropped.
- Multi-tenant separation beyond the existing `owner_user_id` model.
- Calendar export, ICS files, VEVENT/VTODO compatibility.

## Architecture

### End-state package layout

```text
reminder/
  core/
    service.py          # ReminderService (the only public ingress for domain ops)
    scheduler.py        # apscheduler-backed timing layer
    schedule_policy.py  # RRULE parsing, dtstart resolution, retry backoff
    trigger_loop.py     # claim lease, build delivery payload, hand to dispatcher
    delivery.py         # DeliveryDispatcher, channel registry
    delivery_chat.py    # ChatDeliveryAdapter (re-enters agent turn pipeline)
    errors.py           # structured exceptions (see Error Model)
    models.py           # Reminder dataclass / TypedDict
  ingress/
    llm_tool.py         # visible_reminder_tool (adapter, calls ReminderService)
    web_api.py          # FastAPI router mounted by bridge under /bridge/internal/reminders
  storage/
    dao.py              # ReminderDAO (collection: reminders)
```

### Removal manifest

These are deleted in the same change. No deprecation period.

```text
agent/agno_agent/tools/deferred_action/{__init__.py, service.py, tool.py}
agent/runner/deferred_action_executor.py
agent/runner/deferred_action_scheduler.py
agent/runner/deferred_action_policy.py
dao/deferred_action_dao.py
collection: deferred_action_actions  (dropped from Mongo)
tests/unit/agent/test_deferred_action_service.py     (replaced)
tests/unit/dao/test_deferred_action_dao.py           (replaced)
tests/e2e/test_deferred_actions_flow.py              (replaced)
tests/unit/agent/test_visible_reminder_time_parser.py (deleted; tool no longer parses)
```

### Caller migrations

| caller | before | after |
|---|---|---|
| `agent/runner/agent_runner.py` | starts `DeferredActionScheduler` | starts `reminder.core.scheduler.ReminderScheduler` |
| `agent/agno_agent/agents/__init__.py` | imports `visible_reminder_tool` from `tools.deferred_action` | imports from `reminder.ingress.llm_tool` |
| `agent/agno_agent/workflows/prepare_workflow.py` | imports `set_deferred_action_session_state` | uses new context binding from `reminder.ingress.llm_tool` |
| `agent/agno_agent/workflows/post_analyze_workflow.py` | calls `DeferredActionService.create_or_replace_internal_followup` | calls `ReminderService.upsert(actor="agent", visibility="internal", upsert_key=f"proactive_followup:{conversation_id}")` |
| `agent/agno_agent/tools/timezone_tools.py` | calls `realign_visible_reminders_for_timezone_change` | calls `ReminderService.realign_for_timezone_change` |
| `connector/clawscale_bridge/google_calendar_import_service.py` | calls `create_imported_*_reminder` | calls `ReminderService.create(actor="import", ...)` |

## Domain Model

### Reminder

```python
@dataclass
class Reminder:
    id: str
    owner_user_id: str
    actor: Literal["user", "agent", "import"]
    visibility: Literal["visible", "internal"]
    upsert_key: str | None

    title: str
    prompt: str                       # what to say at fire time; defaults to title
    metadata: dict[str, Any]

    dtstart: datetime                 # aware (UTC stored)
    timezone: str                     # IANA name, used for floating recurrences
    rrule: str | None                 # RFC 5545 subset

    delivery_channel: Literal["chat"]  # v1 only
    conversation_id: str | None
    character_id: str | None

    lifecycle_state: Literal["active", "cancelled", "completed", "failed"]
    next_run_at: datetime | None
    last_run_at: datetime | None
    run_count: int
    expires_at: datetime | None
    last_error: str | None

    revision: int
    created_at: datetime
    updated_at: datetime
```

### Discriminator semantics

- `actor` = who originated the reminder. Determines audit and update
  permissions, not behavior.
- `visibility` = whether the user can see this reminder when listing.
  `internal` reminders are filtered out of `list_for_user`.
- `upsert_key` = optional uniqueness scope under `(owner_user_id, upsert_key)`
  for active records. Used by the agent for "at most one active proactive
  follow-up per conversation" semantics. `None` means uniqueness is not
  enforced (the default for user-typed reminders).
- `delivery_channel` is forward-looking; v1 only accepts `"chat"`.

## ReminderService API

The service is a plain Python class. No agno, no contextvars, no session state.

```python
class ReminderService:
    def create(
        self,
        *,
        actor: Literal["user", "agent", "import"],
        owner_user_id: str,
        title: str,
        trigger_at: datetime,                # must be aware
        timezone: str,
        rrule: str | None = None,
        visibility: Literal["visible", "internal"] = "visible",
        upsert_key: str | None = None,
        delivery_channel: Literal["chat"] = "chat",
        conversation_id: str | None = None,
        character_id: str | None = None,
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Reminder: ...

    def upsert(self, **kwargs) -> Reminder:
        """create() that requires upsert_key and replaces any existing
        active record under (owner_user_id, upsert_key)."""

    def update(
        self,
        *,
        reminder_id: str,
        owner_user_id: str,                  # ownership check
        title: str | _UNSET = _UNSET,
        trigger_at: datetime | _UNSET = _UNSET,
        timezone: str | _UNSET = _UNSET,
        rrule: str | None | _UNSET = _UNSET, # explicit None clears recurrence
        prompt: str | _UNSET = _UNSET,
    ) -> Reminder: ...

    def list_for_user(
        self,
        *,
        owner_user_id: str,
        include_internal: bool = False,
        include_terminal: bool = False,
    ) -> list[Reminder]: ...

    def get(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...

    def delete(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...

    def complete(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...

    def realign_for_timezone_change(
        self,
        *,
        owner_user_id: str,
        timezone: str,
    ) -> list[Reminder]: ...
```

Notes:

- All datetimes in API contracts are timezone-aware. Naive datetimes are a
  hard error.
- Keyword-based target resolution lives in adapters, not core. Core operates
  on `reminder_id` only.
- `update`, `delete`, `complete`, `get` enforce `owner_user_id` and raise
  `OwnershipViolation` on mismatch (including for internal reminders).
- `_UNSET` sentinel separates "not provided" from "set to None"; `rrule=None`
  clears recurrence, `rrule=_UNSET` leaves it.

## Time Contract

### One-shot reminders (`rrule is None`)

- `trigger_at` must be aware ISO 8601.
- If `trigger_at <= now`, raise `InvalidTriggerAt(reason="past")`. Core never
  fires a one-shot reminder whose nominal time has already passed.
- `next_run_at = trigger_at`.

### Recurring reminders (`rrule is not None`)

- `dtstart = trigger_at` may be in the past; the schedule treats it as the
  recurrence anchor.
- `next_run_at` is the first `rrule` occurrence `> now`. If no such occurrence
  exists (e.g. `UNTIL` is already past), raise
  `InvalidTriggerAt(reason="no_future_occurrence")`.

### Floating-local

`floating_local` semantics from the existing system are preserved. A recurring
reminder with `timezone="Asia/Tokyo"` and `rrule="FREQ=DAILY"` and
`trigger_at="2026-04-28T17:58:00+09:00"` continues to fire at 17:58 local time
even after the user's effective timezone changes; reanchoring is performed by
`realign_for_timezone_change`.

## Recurrence Contract (RRULE Subset, v1 Locked)

Supported:

- `FREQ=DAILY`
- `FREQ=WEEKLY` with optional `BYDAY=` (subset of `MO,TU,WE,TH,FR,SA,SU`)
- `FREQ=MONTHLY`
- `FREQ=YEARLY`
- modifiers: `COUNT`, `UNTIL`, `INTERVAL`

Rejected (raise `RRULENotSupported`):

- `FREQ=HOURLY`, `FREQ=MINUTELY`, `FREQ=SECONDLY`
- `BYHOUR`, `BYMINUTE`, `BYMONTH`, `BYMONTHDAY`, `BYSETPOS`, `BYWEEKNO`,
  `BYYEARDAY`, `WKST`
- `EXDATE`, `RDATE`
- malformed RRULE strings (no `FREQ=`, unknown tokens, etc.)
- natural-language inputs like `"daily"`, `"every day"`, `"每天"`

`EXDATE` / `RDATE` and broader `BY*` modifiers are explicit v2 work.

## Batch Semantics (Open Question Closed)

Batch is **non-atomic with per-operation reporting**.

- Operations execute in user order.
- Each operation produces an entry of `{ok, summary, error?}` in the result
  array, in the same order.
- A failed operation does not block subsequent operations.
- The tool/HTTP response surfaces the per-operation status array verbatim.
  Adapters MUST NOT collapse partial failure into a generic success message.

## Error Model

Core exceptions (defined in `reminder/core/errors.py`):

| exception | when |
|---|---|
| `InvalidTriggerAt(reason)` | naive datetime, past one-shot, no future occurrence |
| `RRULENotSupported(reason)` | malformed RRULE, unsupported feature |
| `ReminderNotFound` | id does not exist |
| `OwnershipViolation` | owner mismatch on update/delete/complete/get |
| `UpsertConflict` | concurrent upsert raced; retry expected |
| `InvalidArgument(field, reason)` | catch-all for shape validation |

Each exception carries a stable `code` string for adapter translation:

```python
class ReminderError(Exception):
    code: str
    user_message: str        # safe to show to a user
    detail: dict[str, Any]   # for logs / debugging
```

### Error translation path

```text
ReminderService raises
   │
   ├── llm_tool.py: catches, writes append_tool_result(ok=False, summary=user_message),
   │                 returns ChatResponseAgent-readable text. ChatResponseAgent
   │                 then explains the failure to the user in-character.
   │
   ├── web_api.py: catches, returns 4xx with {code, message, detail}.
   │
   └── trigger_loop.py: catches at fire time, marks occurrence failed,
                         retries per retry_policy, surfaces last_error on
                         the reminder record.
```

The current swallow-and-log behavior in
`PrepareWorkflow._run_reminder_detect` is removed: the workflow allows
adapter errors to propagate to `tool_results` so the user sees them.

## Adapter Contracts

### LLM tool (`reminder/ingress/llm_tool.py`)

Tool name: `visible_reminder_tool`. Schema unchanged from the previous
contract refactor:

```json
{ "action": "create", "title": "...", "trigger_at": "ISO", "rrule": "..." }
{ "action": "update", "keyword": "...", "new_title": "...", "new_trigger_at": "ISO", "rrule": "..." }
{ "action": "delete", "keyword": "..." }
{ "action": "complete", "keyword": "..." }
{ "action": "list" }
{ "action": "batch", "operations": [ ... ] }
```

Adapter responsibilities:

- parse and validate ISO datetimes before calling core (cheap pre-validation
  for clear LLM violations)
- resolve `keyword` to `reminder_id` via `ReminderService.list_for_user`
- bind `owner_user_id`, `conversation_id`, `character_id`, `timezone` from
  the agent session
- translate `ReminderError` to `tool_results` entries
- the LLM tool MUST NOT expose `actor`, `visibility`, or `upsert_key`. Those
  are bound to `actor="user"`, `visibility="visible"`, `upsert_key=None`.

The `tool_call_limit=1` constraint stays. Batch is the multi-op path.

### Web API (`reminder/ingress/web_api.py`)

FastAPI router mounted by the bridge:

```text
POST   /bridge/internal/reminders                     create
GET    /bridge/internal/reminders                     list
GET    /bridge/internal/reminders/{id}                get
PATCH  /bridge/internal/reminders/{id}                update
DELETE /bridge/internal/reminders/{id}                delete
POST   /bridge/internal/reminders/{id}/complete       complete
```

Auth: `owner_user_id` is provided by the bridge from the same upstream-trust
header used by `/bridge/internal/google-calendar-import/*`. Cross-user access
returns 403 via `OwnershipViolation`.

Request bodies use JSON with the same field names as `ReminderService.create`.
`actor` is server-set to `"user"` for this surface; `visibility` is fixed to
`"visible"`; `upsert_key` is not exposed.

### Chat delivery (`reminder/core/delivery_chat.py`)

`ChatDeliveryAdapter` owns the existing logic for "reminder fires → run a
synthetic agent turn". It receives a `Reminder` and a `now` instant, builds
the prompt (`[系统提醒触发] {prompt}` / `[系统延迟跟进触发] {prompt}` for
internal-visibility reminders), and calls `agent.runner.handle_message`.

The adapter is registered with `DeliveryDispatcher` at startup. Dispatcher
selects by `delivery_channel`. v1 has only one registration.

## Storage

Collection: `reminders`.

```text
{
  _id: ObjectId,
  owner_user_id: str,                    # required, indexed
  actor: "user" | "agent" | "import",
  visibility: "visible" | "internal",
  upsert_key: str | null,

  delivery_channel: "chat",
  conversation_id: str | null,
  character_id: str | null,

  title: str,
  prompt: str,
  metadata: dict,

  dtstart: BSON datetime (utc),
  timezone: str,
  rrule: str | null,
  next_run_at: BSON datetime (utc) | null,
  expires_at: BSON datetime (utc) | null,

  lifecycle_state: "active" | "cancelled" | "completed" | "failed",
  revision: int,
  run_count: int,
  last_run_at: BSON datetime (utc) | null,
  last_error: str | null,

  lease: { token: str | null, leased_at: ts | null, lease_expires_at: ts | null },
  retry_policy: { max_attempts_per_occurrence, base_backoff_seconds, max_backoff_seconds },

  created_at: ts,
  updated_at: ts,
}
```

Indexes:

- `{owner_user_id: 1, lifecycle_state: 1, visibility: 1}` — list-for-user
- `{owner_user_id: 1, upsert_key: 1, lifecycle_state: 1}` partial where
  `upsert_key != null` — upsert lookup
- `{lifecycle_state: 1, next_run_at: 1}` — scheduler scan
- `{conversation_id: 1, lifecycle_state: 1}` — chat-delivery debugging

The collection `deferred_action_actions` is dropped at deploy time. There is
no migration script; existing data is discarded.

## Acceptance Criteria

- New `reminder/` package exists; old `deferred_action` code is fully removed.
- `agent_runner` boots `ReminderScheduler` only.
- `visible_reminder_tool` lives at `reminder.ingress.llm_tool` and contains
  no domain logic beyond schema validation, keyword resolution, and error
  translation.
- The bridge exposes `/bridge/internal/reminders/*` with full CRUD; an
  end-to-end smoke (create via HTTP → fires through chat delivery) passes.
- PostAnalyze creates internal follow-ups via `ReminderService.upsert(...)`.
- Calendar import calls `ReminderService.create(actor="import", ...)`.
- One-shot past-time creates are rejected by core, not by the LLM prompt.
- Adapter errors reach the user: a tool failure produces a visible
  `tool_results` entry that ChatResponseAgent surfaces in-character.
- `scripts/eval_reminder_tool_calls.py` runs against the full corpus and
  produces a stratified report (one-shot create / recurring / update /
  delete-or-complete / batch / true-negative). Concrete pass-rate targets
  are set during plan execution against the measured baseline; the eval
  must not be reported as a single aggregate number.
- `pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py
  tests/unit/connector/clawscale_bridge/test_reminders_api.py
  tests/e2e/test_reminder_flow.py -q` passes.

## Test Matrix

| layer | test file | covers |
|---|---|---|
| core | `tests/unit/reminder/test_service.py` | every public method, ownership checks, upsert race |
| core | `tests/unit/reminder/test_schedule_policy.py` | RRULE subset accept/reject, past-time rules, next_run_at |
| core | `tests/unit/reminder/test_trigger_loop.py` | claim → dispatch → success/failure paths |
| core | `tests/unit/reminder/test_delivery_chat.py` | prompt shape for visible vs internal |
| storage | `tests/unit/dao/test_reminder_dao.py` | CRUD, upsert behavior, indexes |
| LLM adapter | `tests/unit/reminder/test_llm_tool.py` | schema, keyword resolve, error translation |
| LLM corpus | `scripts/eval_reminder_tool_calls.py` | full corpus, stratified report |
| HTTP adapter | `tests/unit/connector/clawscale_bridge/test_reminders_api.py` | per-route behavior, auth, error codes |
| e2e | `tests/e2e/test_reminder_flow.py` | HTTP create → scheduler → chat delivery; LLM create → scheduler → chat delivery; PostAnalyze upsert → scheduler → chat delivery |

## Open Questions (kept narrow)

- Does the LLM tool ever need to expose `prompt` separately from `title`?
  Today they are equal; if recurring reminders want richer fire-time text,
  the tool may need a separate field. Default: no in v1.
- For `actor="import"`, do we trust the calendar source's `title` and `dtstart`
  verbatim, or run the same validation (e.g., reject past one-shots)? Default:
  same validation; calendar import resolves past events to historical state on
  its side as it does today.
- Concrete pass-rate targets per stratum will be set during plan execution
  once the baseline is measured. Plan must define the targets before
  implementation begins.
