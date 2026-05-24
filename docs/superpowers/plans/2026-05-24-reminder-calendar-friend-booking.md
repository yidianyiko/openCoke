# Reminder Calendar Friend Booking Implementation Plan

**Plan Status:** completed
**Status Date:** 2026-05-24
**Freshness Check:** Verified against `main`, `docs/ARCHITECTURE.md`, and
touched runtime code before merge.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable friend-gated lesson booking where Coke reminders are the calendar source, Gateway returns privacy-preserving busy facts, and the LLM owns scheduling reasoning.

**Architecture:** Reminder Runtime stores optional occupied duration on reminder schedules and expands bounded occurrences for calendar reads. Bridge exposes an internal privacy-preserving calendar-facts read path, while Gateway checks active friendship, persists shared reminder interval timing, and routes a `list_friend_calendar_facts` scheduling tool to the agent. The backend never cuts free slots, recommends lesson times, applies class-duration defaults, or rejects shared reminders because of overlap.

**Tech Stack:** Python dataclasses and pytest, MongoDB Reminder Runtime, Flask Bridge internal API, TypeScript/Hono Gateway API, Prisma/Postgres, Vitest, Agno runtime scheduling tools, prompt instruction unit tests.

---

## Scope And Execution Notes

This plan implements `docs/superpowers/specs/2026-05-24-reminder-calendar-friend-booking-design.md`.

Touched planning surfaces:

- `worker-runtime`: reminder duration model, occurrence expansion, scheduling tool args, prompt policy.
- `bridge`: internal reminder calendar facts read path and reminder duration serialization.
- `gateway-api`: friend-gated calendar facts service/route, shared reminder duration persistence/projection.
- `gateway-web`: shared customer reminder duration projection only; no new booking UI.
- `repo-os`: feature tree and architecture docs.

Hard product boundaries:

- Coke reminders are the only calendar source in this slice.
- The backend returns busy intervals and records the interval chosen by the LLM.
- The backend does not produce recommended slots, subtract free intervals for the user, default "class" to 60 minutes, choose course types, or reject a shared reminder because it overlaps another reminder.
- A friend calendar read must not expose reminder ids, titles, prompts, locations, output targets, metadata, or internal reminders.
- The agent resolves friend ambiguity before calling `list_friend_calendar_facts`.

The repository has a nested `gateway/` checkout. Gateway implementation commits are made from `/data/projects/coke/gateway`. Root Python/docs commits are made from `/data/projects/coke`; when Gateway changes are committed, the root commit must include the updated `gateway` gitlink.

## File Structure

### Reminder Runtime And Bridge

- Modify: `agent/reminder/models.py`
  - Add `duration_minutes: int | None` to `ReminderSchedule`.
  - Add a `ReminderOccurrence` dataclass for bounded occupied occurrences.
- Modify: `agent/reminder/schedule.py`
  - Thread `duration_minutes` through `build_schedule_from_anchor`.
  - Add positive-duration validation.
  - Add bounded local-date occurrence expansion for recurring schedules.
- Modify: `agent/reminder/service.py`
  - Store and map `schedule.duration_minutes`.
  - Add `list_occupied_occurrences_in_local_date_range`.
- Modify: `agent/reminder/runtime_contract.py`
  - Add `list_occupied_reminder_occurrences_in_local_date_range`.
- Modify: `dao/reminder_dao.py`
  - Keep owner, visibility, lifecycle, and local-date filtering for one-shot reminders.
  - Add a bounded recurring-source query helper if the service cannot reuse the existing list.
- Modify: `connector/clawscale_bridge/reminder_management_service.py`
  - Accept `durationMinutes` on create/update requests.
  - Serialize `schedule.durationMinutes`.
  - Add `list_calendar_facts`.
- Modify: `connector/clawscale_bridge/app.py`
  - Add `GET /bridge/internal/reminder-calendar-facts`.
- Tests:
  - `tests/unit/reminder/test_models.py`
  - `tests/unit/reminder/test_schedule.py`
  - `tests/unit/reminder/test_service.py`
  - `tests/unit/reminder/test_runtime_contract.py`
  - `tests/unit/dao/test_reminder_dao.py`
  - `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`

### Gateway API

- Modify: `gateway/packages/api/prisma/schema.prisma`
  - Add nullable `durationMinutes Int? @map("duration_minutes")` to `SharedReminderRequest`.
- Create: `gateway/packages/api/prisma/migrations/20260524100000_shared_reminder_duration/migration.sql`
  - Add the `duration_minutes` column.
- Modify: `gateway/packages/api/src/lib/reminder-runtime-client.ts`
  - Add `durationMinutes` to create/update reminder inputs.
  - Add `listRuntimeCalendarFacts`.
- Create: `gateway/packages/api/src/scheduling/friend-calendar-facts-service.ts`
  - Verify active friendship.
  - Call Reminder Runtime calendar facts through the Bridge client.
  - Return busy facts only; do not cut free slots.
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
  - Persist shared reminder duration.
  - Pass duration into requester and invitee reminder projections.
  - Preserve active-friendship checks and idempotency.
  - Do not add overlap checks.
- Modify: `gateway/packages/api/src/scheduling/types.ts`
  - Add `FriendCalendarFactsResult` and duration-aware shared reminder types.
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
  - Add `list_friend_calendar_facts`.
  - Pass `duration_minutes` to `createSharedReminder`.
- Modify: `gateway/packages/api/src/routes/customer-reminder-routes.ts`
  - Accept and return reminder `durationMinutes` for customer reminder management.
- Tests:
  - `gateway/packages/api/src/lib/reminder-runtime-client.test.ts`
  - `gateway/packages/api/src/scheduling/friend-calendar-facts-service.test.ts`
  - `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`
  - `gateway/packages/api/src/scheduling/schema-contract.test.ts`
  - `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`
  - `gateway/packages/api/src/routes/customer-reminder-routes.test.ts`

### Gateway Shared And Web Projection

- Modify: `gateway/packages/shared/src/types/scheduling.ts`
  - Export `durationMinutes?: number | null` for shared reminder DTOs.
- Modify: `gateway/packages/shared/src/index.ts`
  - Re-export updated scheduling DTOs if this file uses named exports.
- Modify: `gateway/packages/web/lib/customer-reminders.ts`
  - Carry `durationMinutes` through list/create/update wrappers.
- Modify: `gateway/packages/web/lib/customer-reminders.test.ts`
  - Prove web wrapper passes and reads duration.

### Agent Runtime

- Modify: `agent/agno_agent/capabilities/scheduling.py`
  - Add `list_friend_calendar_facts` to tool names and read-only tools.
- Modify: `agent/agno_agent/runtime/scheduling_types.py`
  - Add `target_account_id`, `from_date`, `to_date`, and `duration_minutes`.
- Modify: `agent/agno_agent/runtime/execution_agents.py`
  - Expose those args in `_make_scheduling_tool_fn`.
  - Update scheduling execution prompt to call calendar facts only after friend resolution.
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
  - Add LLM policy for reminder-as-calendar, 7-day default query range, privacy, and 60-minute fitness lesson default.
  - Explicitly say Google Calendar is not the source for friend availability in this feature.
- Tests:
  - `tests/unit/agent/test_scheduling_capability.py`
  - `tests/unit/agent/test_agent_runtime_scheduling_tools.py`
  - `tests/unit/agent/test_chat_response_scheduling_instructions.py`
  - `tests/unit/agent/test_scheduling_types.py`

### Docs

- Modify: `docs/ARCHITECTURE.md`
  - Mention reminder duration, Bridge calendar facts read path, and Gateway `list_friend_calendar_facts`.
- Modify: `docs/product-specs/FEATURE_TREE.md`
  - Add the Bridge internal calendar facts route and worker scheduling tool.

## Route And Tool Map

New Bridge route:

- `GET /bridge/internal/reminder-calendar-facts?customer_id=:targetAccountId&from=:YYYY-MM-DD&to=:YYYY-MM-DD&timezone=:IANA`

Updated Gateway internal route:

- `POST /api/internal/scheduling/tools/list_friend_calendar_facts`

New worker scheduling tool:

- `list_friend_calendar_facts`

Tool request:

```json
{
  "target_account_id": "acct_coach",
  "from_date": "2026-05-25",
  "to_date": "2026-05-31",
  "timezone": "Asia/Tokyo"
}
```

Tool success result:

```json
{
  "target_account_id": "acct_coach",
  "range": {
    "from": "2026-05-25",
    "to": "2026-05-31",
    "timezone": "Asia/Tokyo"
  },
  "busy_intervals": [
    {
      "start_at": "2026-05-25T01:00:00+00:00",
      "end_at": "2026-05-25T02:00:00+00:00",
      "local_start": "2026-05-25 10:00",
      "local_end": "2026-05-25 11:00"
    }
  ],
  "privacy": {
    "event_details_included": false
  }
}
```

Friendship-required result:

```json
{
  "status": "friendship_required",
  "target_account_id": "acct_coach",
  "busy_intervals": [],
  "privacy": {
    "event_details_included": false
  }
}
```

## Task 1: Reminder Duration Model And Serialization

**Files:**
- Modify: `agent/reminder/models.py`
- Modify: `agent/reminder/schedule.py`
- Modify: `agent/reminder/service.py`
- Modify: `agent/reminder/runtime_contract.py`
- Modify: `connector/clawscale_bridge/reminder_management_service.py`
- Modify: `gateway/packages/api/src/lib/reminder-runtime-client.ts`
- Modify: `gateway/packages/api/src/routes/customer-reminder-routes.ts`
- Modify: `gateway/packages/web/lib/customer-reminders.ts`
- Test: `tests/unit/reminder/test_models.py`
- Test: `tests/unit/reminder/test_service.py`
- Test: `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`
- Test: `gateway/packages/api/src/lib/reminder-runtime-client.test.ts`
- Test: `gateway/packages/api/src/routes/customer-reminder-routes.test.ts`
- Test: `gateway/packages/web/lib/customer-reminders.test.ts`

- [x] **Step 1: Write failing Python duration storage and serialization tests**

Add this test to `tests/unit/reminder/test_service.py`:

```python
def test_create_update_and_map_schedule_duration_minutes():
    service, dao, scheduler = make_service()

    reminder = service.create(
        owner_user_id="user-1",
        command=create_command(
            reminder_schedule=ReminderSchedule(
                anchor_at=FUTURE,
                local_date=date(2026, 4, 29),
                local_time=time(10, 0),
                timezone="Asia/Tokyo",
                rrule=None,
                duration_minutes=60,
            )
        ),
    )

    assert reminder.schedule.duration_minutes == 60
    assert dao.documents[reminder.id]["schedule"]["duration_minutes"] == 60

    updated = service.update(
        reminder_id=reminder.id,
        owner_user_id="user-1",
        patch=ReminderPatch(
            schedule=ReminderSchedule(
                anchor_at=datetime(2026, 4, 30, 1, 0, tzinfo=UTC),
                local_date=date(2026, 4, 30),
                local_time=time(10, 0),
                timezone="Asia/Tokyo",
                rrule=None,
                duration_minutes=90,
            )
        ),
    )

    assert updated.schedule.duration_minutes == 90
    assert dao.documents[reminder.id]["schedule"]["duration_minutes"] == 90
    scheduler.reschedule_reminder.assert_called_once()
```

Add this test to `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`:

```python
def test_create_reminder_accepts_duration_minutes_and_serializes_schedule():
    runtime_contract = MagicMock()
    runtime_contract.create_visible_reminder.return_value = _reminder(
        schedule=ReminderSchedule(
            anchor_at=datetime(2026, 5, 13, 0, 30, tzinfo=UTC),
            local_date=date(2026, 5, 13),
            local_time=time(9, 30),
            timezone="Asia/Tokyo",
            rrule=None,
            duration_minutes=60,
        )
    )
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    result = _service(
        reminder_runtime=runtime_contract,
        conversation_dao=conversation_dao,
    ).create_reminder(
        customer_id="customer-1",
        body={
            "title": "lesson",
            "localDate": "2026-05-13",
            "localTime": "09:30",
            "timezone": "Asia/Tokyo",
            "durationMinutes": 60,
        },
    )

    schedule = runtime_contract.create_visible_reminder.call_args.kwargs["schedule"]
    assert schedule.duration_minutes == 60
    assert result["schedule"]["durationMinutes"] == 60
```

Add this test to `gateway/packages/api/src/lib/reminder-runtime-client.test.ts`:

```ts
it('sends durationMinutes to bridge create and update requests', async () => {
  const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, body: JSON.parse(String(init.body)) as Record<string, unknown> });
      return new Response(JSON.stringify({ ok: true, data: { id: 'rem_1' } }), { status: 200 });
    }),
  );

  await createRuntimeReminder({
    customerId: 'acct_a',
    title: 'lesson',
    localDate: '2026-05-25',
    localTime: '10:00',
    timezone: 'Asia/Tokyo',
    durationMinutes: 60,
  });
  await updateRuntimeReminder({
    customerId: 'acct_a',
    reminderId: 'rem_1',
    localDate: '2026-05-25',
    localTime: '11:00',
    timezone: 'Asia/Tokyo',
    durationMinutes: 90,
  });

  expect(calls[0]?.body.durationMinutes).toBe(60);
  expect(calls[1]?.body.durationMinutes).toBe(90);
});
```

- [x] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_service.py::test_create_update_and_map_schedule_duration_minutes tests/unit/connector/clawscale_bridge/test_reminder_management_service.py::test_create_reminder_accepts_duration_minutes_and_serializes_schedule -v
pnpm --dir gateway/packages/api test -- src/lib/reminder-runtime-client.test.ts
```

Expected: FAIL because `ReminderSchedule.duration_minutes`, Bridge `durationMinutes`, and Gateway client duration input do not exist.

- [x] **Step 3: Add duration to the reminder schedule model**

In `agent/reminder/models.py`, replace `ReminderSchedule` with:

```python
@dataclass
class ReminderSchedule:
    anchor_at: datetime
    local_date: date
    local_time: time
    timezone: str
    rrule: str | None
    duration_minutes: int | None = None
```

In `agent/reminder/schedule.py`, update `build_schedule_from_anchor`:

```python
def build_schedule_from_anchor(
    anchor_at: datetime,
    timezone: str,
    rrule: str | None,
    duration_minutes: int | None = None,
) -> ReminderSchedule:
    anchor_at = _ensure_aware(anchor_at, "anchor_at").astimezone(UTC)
    timezone = validate_timezone(timezone)
    rrule = validate_rrule_subset(rrule)
    duration_minutes = validate_duration_minutes(duration_minutes)

    local_anchor = anchor_at.astimezone(ZoneInfo(timezone))
    return ReminderSchedule(
        anchor_at=anchor_at,
        local_date=local_anchor.date(),
        local_time=local_anchor.timetz().replace(tzinfo=None),
        timezone=timezone,
        rrule=rrule,
        duration_minutes=duration_minutes,
    )
```

Add this helper in `agent/reminder/schedule.py`:

```python
def validate_duration_minutes(duration_minutes: int | None) -> int | None:
    if duration_minutes is None:
        return None
    if not isinstance(duration_minutes, int) or isinstance(duration_minutes, bool):
        raise InvalidSchedule(
            "Reminder duration must be a positive integer number of minutes",
            detail={"field": "schedule.duration_minutes"},
        )
    if duration_minutes <= 0:
        raise InvalidSchedule(
            "Reminder duration must be positive",
            detail={"field": "schedule.duration_minutes"},
        )
    return duration_minutes
```

- [x] **Step 4: Store and map duration in ReminderService**

In `agent/reminder/service.py`, import `validate_duration_minutes` from `agent.reminder.schedule`.

Update `_schedule_to_document` so it returns:

```python
    def _schedule_to_document(self, schedule: ReminderSchedule) -> dict:
        return {
            "anchor_at": schedule.anchor_at,
            "local_date": schedule.local_date.isoformat(),
            "local_time": schedule.local_time.isoformat(),
            "timezone": schedule.timezone,
            "rrule": schedule.rrule,
            "duration_minutes": validate_duration_minutes(schedule.duration_minutes),
        }
```

Update `_map_schedule` or the existing schedule mapping block in `_map_document` to pass:

```python
duration_minutes=schedule_document.get("duration_minutes"),
```

If `_map_document` currently builds the schedule inline, keep the current field parsing and only add the duration field.

- [x] **Step 5: Accept and serialize duration in Bridge reminder management**

In `connector/clawscale_bridge/reminder_management_service.py`, update `serialize_reminder` schedule JSON:

```python
"durationMinutes": reminder.schedule.duration_minutes,
```

Update `build_schedule` signature:

```python
def build_schedule(
    *,
    local_date: str,
    local_time: str,
    timezone: str,
    rrule: str | None = None,
    duration_minutes: int | None = None,
) -> ReminderSchedule:
```

Inside it, pass `duration_minutes=duration_minutes` into `ReminderSchedule(...)`.

Add:

```python
def _validate_optional_duration_minutes(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("invalid_body")
    return value
```

In `_build_schedule_from_body`, pass:

```python
duration_minutes=_validate_optional_duration_minutes(body.get("durationMinutes")),
```

- [x] **Step 6: Pass duration through Gateway API and web wrappers**

In `gateway/packages/api/src/lib/reminder-runtime-client.ts`, add to `CreateReminderInput` and `UpdateReminderInput`:

```ts
durationMinutes?: number | null;
```

Include it in create and update request bodies:

```ts
...(input.durationMinutes !== undefined ? { durationMinutes: input.durationMinutes } : {}),
```

In `gateway/packages/api/src/routes/customer-reminder-routes.ts`, add this schema:

```ts
const durationMinutesSchema = z.number().int().positive().nullable().optional();
```

Add `durationMinutes: durationMinutesSchema` to `createReminderBodySchema` and `updateReminderBodySchema`.

In `mapReminderForBoard`, add:

```ts
durationMinutes:
  typeof schedule?.durationMinutes === 'number'
    ? schedule.durationMinutes
    : typeof reminder.durationMinutes === 'number'
      ? reminder.durationMinutes
      : null,
```

Pass `durationMinutes` into `createRuntimeReminder` and `updateRuntimeReminder` when present.

In `gateway/packages/web/lib/customer-reminders.ts`, update `CustomerReminder` and `CustomerReminderFormInput`:

```ts
durationMinutes?: number | null;
```

In `reminderBody`, include:

```ts
durationMinutes: input.durationMinutes ?? null,
```

- [x] **Step 7: Run focused tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_service.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py -v
pnpm --dir gateway/packages/api test -- src/lib/reminder-runtime-client.test.ts src/routes/customer-reminder-routes.test.ts
pnpm --dir gateway/packages/web test -- lib/customer-reminders.test.ts
```

Expected: PASS. Existing tests that instantiate `ReminderSchedule` without duration continue to pass because the field defaults to `None`.

- [x] **Step 8: Commit**

From `/data/projects/coke/gateway`, commit Gateway files:

```bash
git add packages/api/src/lib/reminder-runtime-client.ts packages/api/src/routes/customer-reminder-routes.ts packages/api/src/lib/reminder-runtime-client.test.ts packages/api/src/routes/customer-reminder-routes.test.ts packages/web/lib/customer-reminders.ts packages/web/lib/customer-reminders.test.ts
git commit -m "feat: project reminder duration through gateway"
```

From `/data/projects/coke`, commit root files plus the updated gateway gitlink:

```bash
git add agent/reminder/models.py agent/reminder/schedule.py agent/reminder/service.py agent/reminder/runtime_contract.py connector/clawscale_bridge/reminder_management_service.py tests/unit/reminder/test_models.py tests/unit/reminder/test_service.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py gateway
git commit -m "feat: add reminder duration to runtime"
```

## Task 2: Bounded Occurrence Expansion And Bridge Calendar Facts

**Files:**
- Modify: `agent/reminder/models.py`
- Modify: `agent/reminder/schedule.py`
- Modify: `agent/reminder/service.py`
- Modify: `agent/reminder/runtime_contract.py`
- Modify: `dao/reminder_dao.py`
- Modify: `connector/clawscale_bridge/reminder_management_service.py`
- Modify: `connector/clawscale_bridge/app.py`
- Test: `tests/unit/reminder/test_schedule.py`
- Test: `tests/unit/reminder/test_service.py`
- Test: `tests/unit/reminder/test_runtime_contract.py`
- Test: `tests/unit/dao/test_reminder_dao.py`
- Test: `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`

- [x] **Step 1: Write failing occurrence expansion tests**

Add to `tests/unit/reminder/test_schedule.py`:

```python
def test_expands_recurring_schedule_anchors_inside_local_date_range():
    from agent.reminder.schedule import expand_schedule_anchors_in_local_date_range

    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 5, 25, 1, 0, tzinfo=UTC),
        local_date=date(2026, 5, 25),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule="FREQ=DAILY",
        duration_minutes=60,
    )

    anchors = expand_schedule_anchors_in_local_date_range(
        schedule,
        from_date=date(2026, 5, 26),
        to_date=date(2026, 5, 28),
    )

    assert anchors == [
        datetime(2026, 5, 26, 1, 0, tzinfo=UTC),
        datetime(2026, 5, 27, 1, 0, tzinfo=UTC),
        datetime(2026, 5, 28, 1, 0, tzinfo=UTC),
    ]
```

Add to `tests/unit/reminder/test_service.py`:

```python
def test_list_occupied_occurrences_filters_visibility_and_duration():
    service, dao, _scheduler = make_service()
    service.create(
        owner_user_id="coach",
        command=create_command(
            title="lesson",
            reminder_schedule=ReminderSchedule(
                anchor_at=datetime(2026, 5, 25, 1, 0, tzinfo=UTC),
                local_date=date(2026, 5, 25),
                local_time=time(10, 0),
                timezone="Asia/Tokyo",
                rrule="FREQ=DAILY",
                duration_minutes=60,
            ),
        ),
    )
    service.create(
        owner_user_id="coach",
        command=create_command(
            title="point reminder",
            reminder_schedule=ReminderSchedule(
                anchor_at=datetime(2026, 5, 26, 2, 0, tzinfo=UTC),
                local_date=date(2026, 5, 26),
                local_time=time(11, 0),
                timezone="Asia/Tokyo",
                rrule=None,
                duration_minutes=None,
            ),
        ),
    )
    service.create(
        owner_user_id="other",
        command=create_command(
            title="other",
            reminder_schedule=ReminderSchedule(
                anchor_at=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
                local_date=date(2026, 5, 26),
                local_time=time(12, 0),
                timezone="Asia/Tokyo",
                rrule=None,
                duration_minutes=120,
            ),
        ),
    )

    occurrences = service.list_occupied_occurrences_in_local_date_range(
        owner_user_id="coach",
        from_date=date(2026, 5, 26),
        to_date=date(2026, 5, 27),
        lifecycle_states=["active"],
    )

    assert [(item.start_at, item.end_at) for item in occurrences] == [
        (
            datetime(2026, 5, 26, 1, 0, tzinfo=UTC),
            datetime(2026, 5, 26, 2, 0, tzinfo=UTC),
        ),
        (
            datetime(2026, 5, 27, 1, 0, tzinfo=UTC),
            datetime(2026, 5, 27, 2, 0, tzinfo=UTC),
        ),
    ]
    assert all(item.owner_user_id == "coach" for item in occurrences)
```

Add to `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`:

```python
def test_list_calendar_facts_returns_busy_intervals_without_private_details():
    runtime_contract = MagicMock()
    runtime_contract.list_occupied_reminder_occurrences_in_local_date_range.return_value = [
        SimpleNamespace(
            owner_user_id="coach",
            start_at=datetime(2026, 5, 25, 1, 0, tzinfo=UTC),
            end_at=datetime(2026, 5, 25, 2, 0, tzinfo=UTC),
            timezone="Asia/Tokyo",
        )
    ]

    result = _service(reminder_runtime=runtime_contract).list_calendar_facts(
        customer_id="coach",
        from_date="2026-05-25",
        to_date="2026-05-31",
        timezone="Asia/Tokyo",
    )

    assert result == {
        "targetAccountId": "coach",
        "range": {
            "from": "2026-05-25",
            "to": "2026-05-31",
            "timezone": "Asia/Tokyo",
        },
        "busyIntervals": [
            {
                "startAt": "2026-05-25T01:00:00+00:00",
                "endAt": "2026-05-25T02:00:00+00:00",
                "localStart": "2026-05-25 10:00",
                "localEnd": "2026-05-25 11:00",
            }
        ],
        "privacy": {"eventDetailsIncluded": False},
    }
```

- [x] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_schedule.py::test_expands_recurring_schedule_anchors_inside_local_date_range tests/unit/reminder/test_service.py::test_list_occupied_occurrences_filters_visibility_and_duration tests/unit/connector/clawscale_bridge/test_reminder_management_service.py::test_list_calendar_facts_returns_busy_intervals_without_private_details -v
```

Expected: FAIL because occurrence expansion, occupied occurrence objects, and `list_calendar_facts` are absent.

- [x] **Step 3: Add occurrence type and expansion helper**

In `agent/reminder/models.py`, add:

```python
@dataclass
class ReminderOccurrence:
    owner_user_id: str
    start_at: datetime
    end_at: datetime
    timezone: str
```

In `agent/reminder/schedule.py`, add:

```python
def expand_schedule_anchors_in_local_date_range(
    schedule: ReminderSchedule,
    *,
    from_date: date,
    to_date: date,
) -> list[datetime]:
    if from_date > to_date:
        raise InvalidSchedule(
            "Reminder occurrence range is invalid",
            detail={"from_date": from_date.isoformat(), "to_date": to_date.isoformat()},
        )
    validate_timezone(schedule.timezone)
    validate_rrule_subset(schedule.rrule)
    timezone = ZoneInfo(schedule.timezone)
    range_start = datetime.combine(from_date, datetime.min.time(), tzinfo=timezone)
    range_end = datetime.combine(to_date, datetime.max.time(), tzinfo=timezone)

    if schedule.rrule is None:
        local_anchor = schedule.anchor_at.astimezone(timezone)
        return [schedule.anchor_at.astimezone(UTC)] if range_start <= local_anchor <= range_end else []

    local_start = datetime.combine(
        date=schedule.local_date,
        time=schedule.local_time,
        tzinfo=timezone,
    )
    rule = rrulestr(schedule.rrule, dtstart=local_start)
    return [item.astimezone(UTC) for item in rule.between(range_start, range_end, inc=True)]
```

- [x] **Step 4: Add occupied occurrence service method**

In `agent/reminder/service.py`, import `timedelta`, `ReminderOccurrence`, and `expand_schedule_anchors_in_local_date_range`.

Add method:

```python
    def list_occupied_occurrences_in_local_date_range(
        self,
        *,
        owner_user_id: str,
        from_date: date,
        to_date: date,
        lifecycle_states: list[str],
    ) -> list[ReminderOccurrence]:
        reminders = self.list_for_user_in_local_date_range(
            owner_user_id=owner_user_id,
            from_date=from_date,
            to_date=to_date,
            lifecycle_states=lifecycle_states,
        )
        occurrences: list[ReminderOccurrence] = []
        for reminder in reminders:
            duration = reminder.schedule.duration_minutes
            if duration is None:
                continue
            for start_at in expand_schedule_anchors_in_local_date_range(
                reminder.schedule,
                from_date=from_date,
                to_date=to_date,
            ):
                occurrences.append(
                    ReminderOccurrence(
                        owner_user_id=reminder.owner_user_id,
                        start_at=start_at,
                        end_at=start_at + timedelta(minutes=duration),
                        timezone=reminder.schedule.timezone,
                    )
                )
        return sorted(occurrences, key=lambda item: item.start_at)
```

If existing DAO date filtering misses recurring reminders whose `schedule.local_date` is before `from_date`, add `ReminderDAO.list_visible_recurrence_sources_for_owner(...)` and have the service merge active recurring sources with the one-shot date-range results. Keep the same selector fields: `owner_user_id`, `visibility: "visible"`, and `lifecycle_state`.

- [x] **Step 5: Expose runtime contract and Bridge facts method**

In `agent/reminder/runtime_contract.py`, add:

```python
    def list_occupied_reminder_occurrences_in_local_date_range(
        self,
        *,
        owner_user_id: str,
        from_date: date,
        to_date: date,
        lifecycle_states: list[str],
    ) -> list[ReminderOccurrence]:
        return self.reminder_service.list_occupied_occurrences_in_local_date_range(
            owner_user_id=owner_user_id,
            from_date=from_date,
            to_date=to_date,
            lifecycle_states=lifecycle_states,
        )
```

In `connector/clawscale_bridge/reminder_management_service.py`, add:

```python
def _format_local_interval(value: datetime, timezone: str) -> str:
    return value.astimezone(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
```

Add method:

```python
    def list_calendar_facts(
        self,
        *,
        customer_id: str,
        from_date: str,
        to_date: str,
        timezone: str,
    ) -> dict[str, Any]:
        parsed_from_date = _parse_local_date(from_date)
        parsed_to_date = _parse_local_date(to_date)
        if parsed_from_date > parsed_to_date:
            raise ValueError("invalid_body")
        if (parsed_to_date - parsed_from_date).days + 1 > _MAX_LIST_RANGE_DAYS_INCLUSIVE:
            raise ValueError("invalid_body")
        ReminderRuntimeContract.validate_timezone(timezone)
        occurrences = self.reminder_runtime.list_occupied_reminder_occurrences_in_local_date_range(
            owner_user_id=_require_string(customer_id, "customer_id"),
            from_date=parsed_from_date,
            to_date=parsed_to_date,
            lifecycle_states=["active"],
        )
        return {
            "targetAccountId": customer_id,
            "range": {
                "from": parsed_from_date.isoformat(),
                "to": parsed_to_date.isoformat(),
                "timezone": timezone,
            },
            "busyIntervals": [
                {
                    "startAt": _datetime_to_json(item.start_at),
                    "endAt": _datetime_to_json(item.end_at),
                    "localStart": _format_local_interval(item.start_at, timezone),
                    "localEnd": _format_local_interval(item.end_at, timezone),
                }
                for item in occurrences
            ],
            "privacy": {"eventDetailsIncluded": False},
        }
```

- [x] **Step 6: Add Bridge route**

In `connector/clawscale_bridge/app.py`, add a route matching existing internal auth patterns:

```python
@app.get("/bridge/internal/reminder-calendar-facts")
def bridge_internal_reminder_calendar_facts():
    auth_response = _require_internal_bridge_auth()
    if auth_response is not None:
        return auth_response

    service, service_error = _reminder_service_or_error()
    if service_error is not None:
        return service_error

    try:
        result = service.list_calendar_facts(
            customer_id=request.args.get("customer_id"),
            from_date=request.args.get("from"),
            to_date=request.args.get("to"),
            timezone=request.args.get("timezone", "UTC"),
        )
    except ValueError as exc:
        return _reminder_error_response(exc)
    return jsonify({"ok": True, "data": result})
```

- [x] **Step 7: Run focused tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_schedule.py tests/unit/reminder/test_service.py tests/unit/reminder/test_runtime_contract.py tests/unit/dao/test_reminder_dao.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py -v
```

Expected: PASS. The new calendar facts result contains no reminder ids, titles, prompts, output target, or metadata.

- [x] **Step 8: Commit**

```bash
git add agent/reminder/models.py agent/reminder/schedule.py agent/reminder/service.py agent/reminder/runtime_contract.py dao/reminder_dao.py connector/clawscale_bridge/reminder_management_service.py connector/clawscale_bridge/app.py tests/unit/reminder/test_models.py tests/unit/reminder/test_schedule.py tests/unit/reminder/test_service.py tests/unit/reminder/test_runtime_contract.py tests/unit/dao/test_reminder_dao.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py
git commit -m "feat: expose reminder calendar busy facts"
```

## Task 3: Gateway Friend Calendar Facts Service And Internal Tool Route

**Files:**
- Modify: `gateway/packages/api/src/lib/reminder-runtime-client.ts`
- Create: `gateway/packages/api/src/scheduling/friend-calendar-facts-service.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/scheduling/types.ts`
- Test: `gateway/packages/api/src/lib/reminder-runtime-client.test.ts`
- Test: `gateway/packages/api/src/scheduling/friend-calendar-facts-service.test.ts`
- Test: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`

- [x] **Step 1: Write failing Gateway client and service tests**

Create `gateway/packages/api/src/scheduling/friend-calendar-facts-service.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { listFriendCalendarFacts } from './friend-calendar-facts-service.js';

function clientWithFriendship(friendship: Record<string, unknown> | null) {
  return {
    friendship: {
      findFirst: vi.fn().mockResolvedValue(friendship),
    },
  };
}

describe('friend calendar facts service', () => {
  it('requires an active friendship before reading target calendar facts', async () => {
    const client = clientWithFriendship(null);
    const runtime = { listRuntimeCalendarFacts: vi.fn() };

    const result = await listFriendCalendarFacts(client as never, runtime, {
      requesterAccountId: 'acct_student',
      targetAccountId: 'acct_coach',
      fromDate: '2026-05-25',
      toDate: '2026-05-31',
      timezone: 'Asia/Tokyo',
    });

    expect(result).toEqual({
      status: 'friendship_required',
      target_account_id: 'acct_coach',
      busy_intervals: [],
      privacy: { event_details_included: false },
    });
    expect(runtime.listRuntimeCalendarFacts).not.toHaveBeenCalled();
  });

  it('returns privacy-preserving busy facts for active friends', async () => {
    const client = clientWithFriendship({
      id: 'fs_1',
      accountAId: 'acct_student',
      accountBId: 'acct_coach',
      status: 'active',
    });
    const runtime = {
      listRuntimeCalendarFacts: vi.fn().mockResolvedValue({
        ok: true,
        data: {
          targetAccountId: 'acct_coach',
          range: { from: '2026-05-25', to: '2026-05-31', timezone: 'Asia/Tokyo' },
          busyIntervals: [
            {
              startAt: '2026-05-25T01:00:00+00:00',
              endAt: '2026-05-25T02:00:00+00:00',
              localStart: '2026-05-25 10:00',
              localEnd: '2026-05-25 11:00',
            },
          ],
          privacy: { eventDetailsIncluded: false },
        },
      }),
    };

    const result = await listFriendCalendarFacts(client as never, runtime, {
      requesterAccountId: 'acct_student',
      targetAccountId: 'acct_coach',
      fromDate: '2026-05-25',
      toDate: '2026-05-31',
      timezone: 'Asia/Tokyo',
    });

    expect(runtime.listRuntimeCalendarFacts).toHaveBeenCalledWith({
      customerId: 'acct_coach',
      from: '2026-05-25',
      to: '2026-05-31',
      timezone: 'Asia/Tokyo',
    });
    expect(result).toEqual({
      target_account_id: 'acct_coach',
      range: { from: '2026-05-25', to: '2026-05-31', timezone: 'Asia/Tokyo' },
      busy_intervals: [
        {
          start_at: '2026-05-25T01:00:00+00:00',
          end_at: '2026-05-25T02:00:00+00:00',
          local_start: '2026-05-25 10:00',
          local_end: '2026-05-25 11:00',
        },
      ],
      privacy: { event_details_included: false },
    });
    expect(JSON.stringify(result)).not.toContain('title');
    expect(JSON.stringify(result)).not.toContain('metadata');
  });
});
```

Add a route test to `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`:

```ts
it('routes list_friend_calendar_facts with trusted requester identity', async () => {
  friendCalendarFacts.listFriendCalendarFacts.mockResolvedValue({
    target_account_id: 'acct_coach',
    range: { from: '2026-05-25', to: '2026-05-31', timezone: 'Asia/Tokyo' },
    busy_intervals: [],
    privacy: { event_details_included: false },
  });

  const res = await createApp().request('/api/internal/scheduling/tools/list_friend_calendar_facts', {
    method: 'POST',
    headers: {
      authorization: 'Bearer internal-key',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      customer_id: 'acct_student',
      target_account_id: 'acct_coach',
      from_date: '2026-05-25',
      to_date: '2026-05-31',
      timezone: 'Asia/Tokyo',
    }),
  });

  expect(res.status).toBe(200);
  expect(friendCalendarFacts.listFriendCalendarFacts).toHaveBeenCalledWith(
    db as never,
    { listRuntimeCalendarFacts: reminderRuntime.listRuntimeCalendarFacts },
    {
      requesterAccountId: 'acct_student',
      targetAccountId: 'acct_coach',
      fromDate: '2026-05-25',
      toDate: '2026-05-31',
      timezone: 'Asia/Tokyo',
    },
  );
});
```

Add a hoisted mock in that test file:

```ts
const friendCalendarFacts = vi.hoisted(() => ({
  listFriendCalendarFacts: vi.fn(),
}));
```

And mock the module:

```ts
vi.mock('../scheduling/friend-calendar-facts-service.js', () => friendCalendarFacts);
```

- [x] **Step 2: Run focused tests to verify failure**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/friend-calendar-facts-service.test.ts src/routes/internal-scheduling-routes.test.ts src/lib/reminder-runtime-client.test.ts
```

Expected: FAIL because the new service, route wiring, and `listRuntimeCalendarFacts` client are absent.

- [x] **Step 3: Add Bridge client method**

In `gateway/packages/api/src/lib/reminder-runtime-client.ts`, add:

```ts
export interface ListCalendarFactsInput {
  customerId: string;
  from: string;
  to: string;
  timezone: string;
}

export async function listRuntimeCalendarFacts(
  input: ListCalendarFactsInput,
): Promise<ReminderRuntimeResult<ReminderRuntimeRecord>> {
  const url = new URL(`${readBridgeBaseUrl()}/bridge/internal/reminder-calendar-facts`);
  url.searchParams.set('customer_id', input.customerId);
  url.searchParams.set('from', input.from);
  url.searchParams.set('to', input.to);
  url.searchParams.set('timezone', input.timezone);

  const bridge = await requestBridgeJson(`${url.pathname}${url.search}`, {
    method: 'GET',
  });
  if (!bridge.ok) {
    return { ok: false, error: bridgeFailureError(bridge) };
  }
  if (!bridge.response.ok || bridge.json.ok !== true) {
    return { ok: false, error: bridgeFailureError(bridge) };
  }
  return { ok: true, data: readBridgeData<ReminderRuntimeRecord>(bridge.json) };
}
```

- [x] **Step 4: Add friend calendar facts service**

Create `gateway/packages/api/src/scheduling/friend-calendar-facts-service.ts`:

```ts
import type {
  ListCalendarFactsInput,
  ReminderRuntimeRecord,
  ReminderRuntimeResult,
} from '../lib/reminder-runtime-client.js';

interface FriendshipRecord {
  id: string;
  accountAId: string;
  accountBId: string;
  status: 'active' | 'removed';
}

export interface FriendCalendarFactsClient {
  friendship: {
    findFirst(args: { where: Record<string, unknown> }): Promise<FriendshipRecord | null>;
  };
}

export interface FriendCalendarFactsRuntimePort {
  listRuntimeCalendarFacts(input: ListCalendarFactsInput): Promise<ReminderRuntimeResult<ReminderRuntimeRecord>>;
}

export interface ListFriendCalendarFactsInput {
  requesterAccountId: string;
  targetAccountId: string;
  fromDate: string;
  toDate: string;
  timezone: string;
}

function nonEmpty(value: string, code: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error(code);
  }
  return trimmed;
}

async function findActiveFriendship(
  client: FriendCalendarFactsClient,
  accountAId: string,
  accountBId: string,
): Promise<FriendshipRecord | null> {
  return client.friendship.findFirst({
    where: {
      status: 'active',
      OR: [
        { accountAId, accountBId },
        { accountAId: accountBId, accountBId: accountAId },
      ],
    },
  });
}

function normalizeBusyIntervals(value: unknown): Array<Record<string, string>> {
  const intervals = Array.isArray(value) ? value : [];
  return intervals
    .map((item) => (typeof item === 'object' && item !== null ? (item as Record<string, unknown>) : null))
    .filter((item): item is Record<string, unknown> => item !== null)
    .map((item) => ({
      start_at: String(item.startAt ?? ''),
      end_at: String(item.endAt ?? ''),
      local_start: String(item.localStart ?? ''),
      local_end: String(item.localEnd ?? ''),
    }))
    .filter((item) => item.start_at && item.end_at && item.local_start && item.local_end);
}

export async function listFriendCalendarFacts(
  client: FriendCalendarFactsClient,
  reminderRuntime: FriendCalendarFactsRuntimePort,
  input: ListFriendCalendarFactsInput,
): Promise<Record<string, unknown>> {
  const requesterAccountId = nonEmpty(input.requesterAccountId, 'invalid_account');
  const targetAccountId = nonEmpty(input.targetAccountId, 'invalid_account');
  const fromDate = nonEmpty(input.fromDate, 'invalid_body');
  const toDate = nonEmpty(input.toDate, 'invalid_body');
  const timezone = nonEmpty(input.timezone, 'invalid_body');

  const friendship = await findActiveFriendship(client, requesterAccountId, targetAccountId);
  if (!friendship) {
    return {
      status: 'friendship_required',
      target_account_id: targetAccountId,
      busy_intervals: [],
      privacy: { event_details_included: false },
    };
  }

  const facts = await reminderRuntime.listRuntimeCalendarFacts({
    customerId: targetAccountId,
    from: fromDate,
    to: toDate,
    timezone,
  });
  if (!facts.ok) {
    throw new Error(facts.error);
  }
  const data = facts.data;
  const range = typeof data.range === 'object' && data.range !== null
    ? (data.range as Record<string, unknown>)
    : { from: fromDate, to: toDate, timezone };

  return {
    target_account_id: targetAccountId,
    range: {
      from: String(range.from ?? fromDate),
      to: String(range.to ?? toDate),
      timezone: String(range.timezone ?? timezone),
    },
    busy_intervals: normalizeBusyIntervals(data.busyIntervals),
    privacy: { event_details_included: false },
  };
}
```

- [x] **Step 5: Wire internal scheduling route**

In `gateway/packages/api/src/routes/internal-scheduling-routes.ts`, import:

```ts
  listRuntimeCalendarFacts,
```

from the reminder client and:

```ts
import { listFriendCalendarFacts } from '../scheduling/friend-calendar-facts-service.js';
```

Add route branch before `create_shared_reminder`:

```ts
  if (toolName === 'list_friend_calendar_facts') {
    return runCustomerTool(c, body, (customerId) =>
      listFriendCalendarFacts(
        db as never,
        { listRuntimeCalendarFacts },
        {
          requesterAccountId: customerId,
          targetAccountId: stringField(body, 'target_account_id'),
          fromDate: stringField(body, 'from_date'),
          toDate: stringField(body, 'to_date'),
          timezone: stringField(body, 'timezone', 'UTC'),
        },
      ),
    );
  }
```

Do not add any free-slot calculation in this route or service.

- [x] **Step 6: Run focused tests to verify pass**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/friend-calendar-facts-service.test.ts src/routes/internal-scheduling-routes.test.ts src/lib/reminder-runtime-client.test.ts
```

Expected: PASS. Tests prove active friendship is required and private reminder details are absent from the returned facts.

- [x] **Step 7: Commit**

From `/data/projects/coke/gateway`:

```bash
git add packages/api/src/lib/reminder-runtime-client.ts packages/api/src/lib/reminder-runtime-client.test.ts packages/api/src/scheduling/friend-calendar-facts-service.ts packages/api/src/scheduling/friend-calendar-facts-service.test.ts packages/api/src/scheduling/types.ts packages/api/src/routes/internal-scheduling-routes.ts packages/api/src/routes/internal-scheduling-routes.test.ts
git commit -m "feat: add friend calendar facts tool route"
```

## Task 4: Shared Reminder Duration Persistence And Projection

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260524100000_shared_reminder_duration/migration.sql`
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `gateway/packages/shared/src/types/scheduling.ts`
- Test: `gateway/packages/api/src/scheduling/schema-contract.test.ts`
- Test: `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`
- Test: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`

- [x] **Step 1: Write failing schema and shared reminder tests**

Add to `gateway/packages/api/src/scheduling/schema-contract.test.ts`:

```ts
it('stores shared reminder duration as optional interval timing', () => {
  const schema = readFileSync(schemaPath, 'utf8');
  const migration = readFileSync(
    join(process.cwd(), 'prisma/migrations/20260524100000_shared_reminder_duration/migration.sql'),
    'utf8',
  );

  expect(schema).toContain('durationMinutes Int?');
  expect(schema).toContain('@map("duration_minutes")');
  expect(migration).toContain('ALTER TABLE "shared_reminder_requests" ADD COLUMN "duration_minutes" INTEGER');
});
```

Add to `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`:

```ts
it('persists duration and projects it into requester reminder', async () => {
  const client = fakeSharedReminderClient({
    friendship: { id: 'fs_1', accountAId: 'acct_a', accountBId: 'acct_b', status: 'active' },
  });
  const reminderRuntime = fakeReminderRuntime({
    create: { ok: true, data: { id: 'rem_req_1' } },
  });

  await createSharedReminder(client as never, reminderRuntime, {
    requesterAccountId: 'acct_b',
    inviteeAccountId: 'acct_a',
    title: 'lesson',
    fireAt: '2026-05-22T07:00:00.000Z',
    timezone: 'Asia/Shanghai',
    durationMinutes: 60,
    idempotencyKey: 'shared:duration',
  });

  expect(client.sharedReminderRequest.create).toHaveBeenCalledWith({
    data: expect.objectContaining({
      durationMinutes: 60,
    }),
  });
  expect(reminderRuntime.createRuntimeReminder).toHaveBeenCalledWith(
    expect.objectContaining({
      durationMinutes: 60,
    }),
  );
});

it('does not reject shared reminders because another reminder overlaps', async () => {
  const client = fakeSharedReminderClient({
    friendship: { id: 'fs_1', accountAId: 'acct_a', accountBId: 'acct_b', status: 'active' },
  });
  const reminderRuntime = fakeReminderRuntime({
    create: { ok: true, data: { id: 'rem_req_1' } },
  });

  await expect(
    createSharedReminder(client as never, reminderRuntime, {
      requesterAccountId: 'acct_b',
      inviteeAccountId: 'acct_a',
      title: 'lesson',
      fireAt: '2026-05-22T07:00:00.000Z',
      timezone: 'Asia/Shanghai',
      durationMinutes: 60,
      idempotencyKey: 'shared:no-overlap-check',
    }),
  ).resolves.toMatchObject({ status: 'pending_invitee_confirmation' });

  expect('reminderFindMany' in client).toBe(false);
});
```

- [x] **Step 2: Run focused tests to verify failure**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/schema-contract.test.ts src/scheduling/shared-reminder-service.test.ts src/routes/internal-scheduling-routes.test.ts
```

Expected: FAIL because schema duration, route duration args, and service projection duration are absent.

- [x] **Step 3: Add schema and migration**

In `gateway/packages/api/prisma/schema.prisma`, add this field to `SharedReminderRequest` after `timezone`:

```prisma
  durationMinutes    Int?                        @map("duration_minutes")
```

Create `gateway/packages/api/prisma/migrations/20260524100000_shared_reminder_duration/migration.sql`:

```sql
ALTER TABLE "shared_reminder_requests"
  ADD COLUMN "duration_minutes" INTEGER;
```

- [x] **Step 4: Add duration to shared reminder service input and projection**

In `gateway/packages/api/src/scheduling/shared-reminder-service.ts`, add `durationMinutes?: number | null;` to `SharedReminderRequestRecord`, `createProjection` input, and `createSharedReminder` input.

Add:

```ts
function optionalPositiveInteger(value: number | null | undefined, code: string): number | null {
  if (value === undefined || value === null) {
    return null;
  }
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(code);
  }
  return value;
}
```

In `createSharedReminder`, add:

```ts
const durationMinutes = optionalPositiveInteger(input.durationMinutes, 'invalid_body');
```

Add to `sharedReminderRequest.create({ data })`:

```ts
durationMinutes,
```

When calling `createProjection`, pass:

```ts
durationMinutes: request.durationMinutes ?? null,
```

In `createProjection`, pass to Runtime:

```ts
...(input.durationMinutes ? { durationMinutes: input.durationMinutes } : {}),
```

Do not add a query that checks existing runtime reminders for overlap.

- [x] **Step 5: Wire duration through internal route**

In `gateway/packages/api/src/routes/internal-scheduling-routes.ts`, update the `create_shared_reminder` branch:

```ts
durationMinutes: numberField(body, 'duration_minutes', 0) > 0
  ? numberField(body, 'duration_minutes', 0)
  : null,
```

If `numberField` returns only a fallback for missing values, keep invalid duration handling inside `createSharedReminder`.

- [x] **Step 6: Run focused tests to verify pass**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/schema-contract.test.ts src/scheduling/shared-reminder-service.test.ts src/routes/internal-scheduling-routes.test.ts
```

Expected: PASS. The overlap test proves this backend layer persists the LLM-chosen interval and does not become a conflict-decision engine.

- [x] **Step 7: Commit**

From `/data/projects/coke/gateway`:

```bash
git add packages/api/prisma/schema.prisma packages/api/prisma/migrations/20260524100000_shared_reminder_duration/migration.sql packages/api/src/scheduling/shared-reminder-service.ts packages/api/src/scheduling/shared-reminder-service.test.ts packages/api/src/scheduling/schema-contract.test.ts packages/api/src/routes/internal-scheduling-routes.ts packages/api/src/routes/internal-scheduling-routes.test.ts packages/shared/src/types/scheduling.ts packages/shared/src/index.ts
git commit -m "feat: persist shared reminder duration"
```

## Task 5: Agent Scheduling Capability And Runtime Args

**Files:**
- Modify: `agent/agno_agent/capabilities/scheduling.py`
- Modify: `agent/agno_agent/runtime/scheduling_types.py`
- Modify: `agent/agno_agent/runtime/execution_agents.py`
- Test: `tests/unit/agent/test_scheduling_capability.py`
- Test: `tests/unit/agent/test_agent_runtime_scheduling_tools.py`
- Test: `tests/unit/agent/test_scheduling_types.py`

- [x] **Step 1: Write failing scheduling capability tests**

Add to `tests/unit/agent/test_scheduling_capability.py`:

```python
def test_list_friend_calendar_facts_is_read_only_and_forwards_range_args():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured.update({"tool_name": tool_name, "payload": payload})
        return {
            "ok": True,
            "data": {
                "target_account_id": "acct_a",
                "range": {
                    "from": "2026-05-25",
                    "to": "2026-05-31",
                    "timezone": "Asia/Tokyo",
                },
                "busy_intervals": [],
                "privacy": {"event_details_included": False},
            },
        }

    port = SchedulingCapabilityPort(tool_name="list_friend_calendar_facts", handler=handler)
    result = port.run(
        "What free time does Coach A have this week?",
        _run_context(user_id="acct_b"),
        {
            "target_account_id": "acct_a",
            "from_date": "2026-05-25",
            "to_date": "2026-05-31",
            "timezone": "Asia/Tokyo",
        },
    )

    assert result.ok is True
    assert result.durable_write is False
    assert captured["tool_name"] == "list_friend_calendar_facts"
    assert captured["payload"]["customer_id"] == "acct_b"
    assert captured["payload"]["target_account_id"] == "acct_a"
    assert captured["payload"]["from_date"] == "2026-05-25"
    assert captured["payload"]["to_date"] == "2026-05-31"
```

Add to `tests/unit/agent/test_agent_runtime_scheduling_tools.py`:

```python
@pytest.mark.asyncio
async def test_scheduling_tool_fn_exposes_calendar_fact_and_duration_args():
    port = RecordingPort(name="list_friend_calendar_facts")
    fn = _make_scheduling_tool_fn(
        "list_friend_calendar_facts",
        port,
        input_message="What free time does Coach A have this week?",
        run_context=_run_context(),
        domain_results=[],
    )
    result = await fn(
        target_account_id="acct_a",
        from_date="2026-05-25",
        to_date="2026-05-31",
        timezone="Asia/Tokyo",
    )

    assert result["domain"] == "scheduling"
    assert port.calls[0][2] == {
        "target_account_id": "acct_a",
        "from_date": "2026-05-25",
        "to_date": "2026-05-31",
        "timezone": "Asia/Tokyo",
    }

    create_fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        RecordingPort(name="create_shared_reminder"),
        input_message="Let's do a class Tuesday at 10",
        run_context=_run_context(),
        domain_results=[],
    )
    function = tool(name="create_shared_reminder")(create_fn)
    assert "duration_minutes" in function.parameters["properties"]
```

- [x] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py::test_list_friend_calendar_facts_is_read_only_and_forwards_range_args tests/unit/agent/test_agent_runtime_scheduling_tools.py::test_scheduling_tool_fn_exposes_calendar_fact_and_duration_args -v
```

Expected: FAIL because `list_friend_calendar_facts`, range args, and `duration_minutes` are not exposed to the scheduling runtime.

- [x] **Step 3: Add scheduling tool name and read-only classification**

In `agent/agno_agent/capabilities/scheduling.py`, add `"list_friend_calendar_facts"` to `SCHEDULING_TOOL_NAMES` after `"list_friends"`.

Add it to `_READ_ONLY_TOOL_NAMES`:

```python
"list_friend_calendar_facts",
```

- [x] **Step 4: Extend scheduling args model**

In `agent/agno_agent/runtime/scheduling_types.py`, replace `SharedReminderSchedulingArgs` with:

```python
class SharedReminderSchedulingArgs(BaseModel):
    target_account_id: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    invitee_account_id: str | None = None
    title: str | None = None
    fire_at: str | None = None
    duration_minutes: int | None = None
    timezone: str | None = None
    request_id: str | None = None
    friendship_id: str | None = None
    blocked_account_id: str | None = None
    idempotency_key: str | None = None
```

- [x] **Step 5: Expose args in scheduling tool function**

In `agent/agno_agent/runtime/execution_agents.py`, add parameters to `scheduling_tool`:

```python
target_account_id: str | None = None,
from_date: str | None = None,
to_date: str | None = None,
duration_minutes: int | None = None,
```

Add them to `_compact_scheduling_args(...)`:

```python
"target_account_id": target_account_id,
"from_date": from_date,
"to_date": to_date,
"duration_minutes": duration_minutes,
```

In `_scheduling_entity_type`, add:

```python
if tool_name == "list_friend_calendar_facts":
    return "friend_calendar_facts"
```

- [x] **Step 6: Run focused tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_scheduling_types.py -v
```

Expected: PASS. `list_friend_calendar_facts` is read-only, while `create_shared_reminder` remains a durable write.

- [x] **Step 7: Commit**

```bash
git add agent/agno_agent/capabilities/scheduling.py agent/agno_agent/runtime/scheduling_types.py agent/agno_agent/runtime/execution_agents.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_scheduling_types.py
git commit -m "feat: add friend calendar scheduling tool"
```

## Task 6: Prompt Policy And Runtime Tests For LLM-Owned Scheduling

**Files:**
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
- Modify: `agent/agno_agent/runtime/execution_agents.py`
- Test: `tests/unit/agent/test_chat_response_scheduling_instructions.py`
- Test: `tests/unit/agent/test_agent_runtime_scheduling_tools.py`

- [x] **Step 1: Write failing prompt-policy tests**

Add to `tests/unit/agent/test_chat_response_scheduling_instructions.py`:

```python
def test_friend_calendar_policy_uses_coke_reminders_not_google_calendar():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())

    assert "Coke reminders are the calendar source for friend availability" in text
    assert "Do not use Google Calendar for friend availability" in text
    assert "list_friend_calendar_facts" in text


def test_friend_calendar_policy_keeps_backend_facts_and_llm_reasoning_separate():
    text = build_chat_response_instructions(_run_context(), _user_turn_input())

    assert "When no date range is provided, supply the next 7 local calendar days" in text
    assert "only free intervals" in text
    assert "Do not reveal reminder titles, prompts, metadata, ids, or output targets" in text
    assert "For a fitness class, lesson, or session, use 60 minutes unless the user states another duration" in text
    assert "The tool returns busy intervals only; you calculate how to describe free time" in text
```

Add to `tests/unit/agent/test_agent_runtime_scheduling_tools.py`:

```python
def test_scheduling_execution_prompt_keeps_defaults_out_of_backend_policy():
    from agent.agno_agent.runtime import execution_agents

    prompt = execution_agents._SCHEDULING_SYSTEM_PROMPT

    assert "Call list_friends before list_friend_calendar_facts when the friend is not resolved" in prompt
    assert "Do not ask the backend for recommended slots" in prompt
    assert "Do not use Google Calendar for friend availability" in prompt
    assert "Pass duration_minutes only after the conversation or policy determines it" in prompt
```

- [x] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py::test_friend_calendar_policy_uses_coke_reminders_not_google_calendar tests/unit/agent/test_chat_response_scheduling_instructions.py::test_friend_calendar_policy_keeps_backend_facts_and_llm_reasoning_separate tests/unit/agent/test_agent_runtime_scheduling_tools.py::test_scheduling_execution_prompt_keeps_defaults_out_of_backend_policy -v
```

Expected: FAIL because the new reminder-calendar policy is not present.

- [x] **Step 3: Update main chat response delegation policy**

In `agent/agno_agent/runtime/chat_response_instructions.py`, add these bullets to `_DELEGATION_BOUNDARY`:

```text
- Coke reminders are the calendar source for friend availability. Do not use Google Calendar for friend availability in this feature.
- For friend availability, resolve the target friend with list_friends first. If exactly one active friend matches, call list_friend_calendar_facts with that account id. If multiple friends match, ask the user to choose one friend and do not call the calendar facts tool.
- When no date range is provided, supply the next 7 local calendar days using the target friend's timezone when available, otherwise the current conversation timezone.
- list_friend_calendar_facts returns privacy-preserving busy intervals only; you calculate how to describe free time and you show only free intervals to the user.
- Do not reveal reminder titles, prompts, metadata, ids, or output targets from a friend's calendar facts.
- For a fitness class, lesson, or session, use 60 minutes unless the user states another duration. This duration choice is LLM policy; the backend must only persist the chosen interval.
```

- [x] **Step 4: Update scheduling execution worker prompt**

In `agent/agno_agent/runtime/execution_agents.py`, replace `_SCHEDULING_SYSTEM_PROMPT` with:

```python
_SCHEDULING_SYSTEM_PROMPT = (
    "You are the friend-link, friend-calendar, and shared-reminder execution worker. "
    "Call exactly one scheduling tool that matches the intent. "
    "Call list_friends before list_friend_calendar_facts when the friend is not resolved. "
    "Do not create shared reminder state unless the named person resolves to one active friend. "
    "Ask for clarification when the name is ambiguous. "
    "Coke reminders are the source for friend availability. "
    "Do not use Google Calendar for friend availability. "
    "Do not ask the backend for recommended slots. "
    "Pass duration_minutes only after the conversation or policy determines it. "
    "Ordinary personal reminders are not scheduling-domain work. "
    "Do not treat an iLink QR as a public user-link QR."
)
```

- [x] **Step 5: Run focused tests to verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_agent_runtime_scheduling_tools.py -v
```

Expected: PASS. These tests prove the 7-day query range and 60-minute fitness lesson default live in prompt/runtime policy, not in Gateway services.

- [x] **Step 6: Commit**

```bash
git add agent/agno_agent/runtime/chat_response_instructions.py agent/agno_agent/runtime/execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_agent_runtime_scheduling_tools.py
git commit -m "feat: teach agent friend calendar policy"
```

## Task 7: Product Surface Docs And Verification Routing

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/superpowers/specs/2026-05-24-reminder-calendar-friend-booking-design.md` only if implementation discovers the accepted spec has a factual error.

- [x] **Step 1: Update architecture docs**

In `docs/ARCHITECTURE.md`, update the Reminder System section with:

```markdown
- visible reminder schedules may include optional `duration_minutes`, exposed as
  `durationMinutes` through Bridge/Gateway APIs; positive duration makes the
  reminder occupy calendar time, while absent duration remains a point reminder
- Bridge exposes `/bridge/internal/reminder-calendar-facts` for internal
  privacy-preserving busy interval reads; it filters by owner, visible
  reminders, active lifecycle state, bounded local date range, and occupied
  duration before returning busy intervals without reminder private details
```

Update the scheduling domain paragraph to add `list_friend_calendar_facts` to the tool list.

- [x] **Step 2: Update product feature tree**

In `docs/product-specs/FEATURE_TREE.md`, update the Reminder System entry:

```markdown
  - bridge internal reminder calendar facts API:
    `/bridge/internal/reminder-calendar-facts`
```

Update Friend Link And Shared Reminders:

```markdown
  - internal agent scheduling tool: `list_friend_calendar_facts`
  - shared reminders persist `durationMinutes` and project that duration into
    participant Reminder Runtime records
```

- [x] **Step 3: Run docs structure checks**

Run:

```bash
zsh scripts/check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected:

- `scripts/check` passes.
- `suggest-verification` includes the surfaces touched by this feature, at minimum `repo-os`, `worker-runtime`, `bridge`, and `gateway-api`.
- `review-trigger` may require human review because this is a cross-surface feature; record that output in the implementation final response.

- [x] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md docs/product-specs/FEATURE_TREE.md docs/superpowers/specs/2026-05-24-reminder-calendar-friend-booking-design.md gateway
git commit -m "docs: document friend calendar booking surfaces"
```

If the spec file was not changed, omit it from `git add`.

## Task 8: Full Verification And Handoff

**Files:**
- No new source files unless a previous task found a spec/code mismatch that required a documented correction.

- [x] **Step 1: Check worktree boundaries**

Run:

```bash
git status --short
git -C gateway status --short
```

Expected:

- Root status is clean, or only the `gateway` gitlink is modified before the final root commit.
- Gateway status is clean after Gateway commits.
- No unrelated user edits are staged.

- [x] **Step 2: Run root Python unit tests for touched runtime surfaces**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_models.py tests/unit/reminder/test_schedule.py tests/unit/reminder/test_service.py tests/unit/reminder/test_runtime_contract.py tests/unit/dao/test_reminder_dao.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_scheduling_types.py -v
```

Expected: PASS.

- [x] **Step 3: Run Gateway API tests for touched surfaces**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/reminder-runtime-client.test.ts src/scheduling/friend-calendar-facts-service.test.ts src/scheduling/shared-reminder-service.test.ts src/scheduling/schema-contract.test.ts src/routes/internal-scheduling-routes.test.ts src/routes/customer-reminder-routes.test.ts
```

Expected: PASS.

- [x] **Step 4: Run Gateway web projection tests**

Run:

```bash
pnpm --dir gateway/packages/web test -- lib/customer-reminders.test.ts
```

Expected: PASS.

- [x] **Step 5: Run diff-aware verification routing**

Run from `/data/projects/coke`:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/verify-surface worker-runtime bridge gateway-api gateway-web repo-os-docs
zsh scripts/review-trigger --base HEAD~1
```

Expected:

- `verify-surface` passes for all named surfaces, or the implementation final response records the exact failing command and failure class.
- `review-trigger` output is reported exactly; do not suppress a human-review requirement.

- [x] **Step 6: Final implementation response**

Report:

```text
Status: DONE / DONE_WITH_CONCERNS / BLOCKED
Root commit SHA:
Gateway commit SHA(s):
Verification commands run:
- ...
Spec coverage:
- reminder duration model/storage/API serialization: covered by Tasks 1 and 4
- bounded occurrence expansion: covered by Task 2
- bridge/internal read path for friend calendar facts: covered by Task 2
- Gateway scheduling tool/route: covered by Task 3
- scheduling capability/runtime args: covered by Task 5
- shared reminder duration projection: covered by Task 4
- prompt/runtime tests for LLM policy: covered by Task 6
- docs/product surface updates and verification: covered by Tasks 7 and 8
Concerns:
- ...
```

## Plan Self-Review

Spec coverage:

- Reminder duration model/storage/API serialization is covered in Task 1.
- Bounded occurrence expansion is covered in Task 2.
- Bridge/internal read path for friend calendar facts is covered in Task 2.
- Gateway scheduling tool/route is covered in Task 3.
- Scheduling capability/runtime args are covered in Task 5.
- Shared reminder duration projection is covered in Task 4.
- Prompt/runtime tests for LLM policy are covered in Task 6.
- Docs/product surface updates and verification are covered in Tasks 7 and 8.

Placeholder scan:

- This plan contains no deferred implementation markers and no copy-by-reference task shortcuts.
- Each task has exact files, focused tests, commands, expected failure/pass behavior, and commit steps.

Type consistency:

- Runtime storage uses `schedule.duration_minutes`.
- Python dataclasses use `duration_minutes`.
- Bridge and customer APIs use `durationMinutes`.
- Gateway internal scheduling tool args use snake_case: `duration_minutes`, `target_account_id`, `from_date`, and `to_date`.
- Gateway Prisma field uses `durationMinutes` mapped to `duration_minutes`.
- Calendar facts use Bridge camelCase internally and Gateway/agent snake_case externally.
