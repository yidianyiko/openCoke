from __future__ import annotations

from datetime import UTC, date, datetime, time
from unittest.mock import Mock

import pytest
from bson import BSON
from bson.errors import InvalidId

from agent.reminder.errors import (
    InvalidArgument,
    InvalidOutputTarget,
    InvalidSchedule,
    ReminderError,
    ReminderNotFound,
)
from agent.reminder.models import (
    AgentOutputTarget,
    ReminderCommand,
    ReminderCreateCommand,
    ReminderPatch,
    ReminderQuery,
    ReminderSchedule,
)
from agent.reminder.service import ReminderService

NOW = datetime(2026, 4, 28, 1, 0, tzinfo=UTC)
FUTURE = datetime(2026, 4, 29, 1, 0, tzinfo=UTC)


class InMemoryReminderDAO:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.next_id = 1

    def insert_reminder(self, document: dict) -> str:
        reminder_id = f"rem-{self.next_id}"
        self.next_id += 1
        self.documents[reminder_id] = {**document, "_id": reminder_id}
        return reminder_id

    def get_reminder_for_owner(
        self, reminder_id: str, owner_user_id: str
    ) -> dict | None:
        document = self.documents.get(reminder_id)
        if (
            document is None
            or document["owner_user_id"] != owner_user_id
            or document.get("visibility") != "visible"
        ):
            return None
        return dict(document)

    def get_reminder(self, reminder_id: str) -> dict | None:
        document = self.documents.get(reminder_id)
        if document is None:
            return None
        return dict(document)

    def list_for_owner(
        self, owner_user_id: str, lifecycle_states: list[str] | None = None
    ) -> list[dict]:
        results = [
            dict(document)
            for document in self.documents.values()
            if document["owner_user_id"] == owner_user_id
            and document.get("visibility") == "visible"
        ]
        if lifecycle_states is not None:
            results = [
                document
                for document in results
                if document["lifecycle_state"] in lifecycle_states
            ]
        return results

    def list_for_owner_in_local_date_range(
        self,
        owner_user_id: str,
        *,
        from_date: date,
        to_date: date,
        lifecycle_states: list[str],
    ) -> list[dict]:
        results = []
        for document in self.documents.values():
            if document["owner_user_id"] != owner_user_id:
                continue
            if document.get("visibility") != "visible":
                continue
            if document["lifecycle_state"] not in lifecycle_states:
                continue
            local_date = date.fromisoformat(document["schedule"]["local_date"])
            if from_date <= local_date <= to_date:
                results.append(dict(document))
        return results

    def list_visible_recurrence_sources_for_owner(
        self,
        owner_user_id: str,
        *,
        to_date: date,
        lifecycle_states: list[str],
    ) -> list[dict]:
        results = []
        for document in self.documents.values():
            if document["owner_user_id"] != owner_user_id:
                continue
            if document.get("visibility") != "visible":
                continue
            if document["lifecycle_state"] not in lifecycle_states:
                continue
            if document["schedule"].get("rrule") is None:
                continue
            local_date = date.fromisoformat(document["schedule"]["local_date"])
            if local_date <= to_date:
                results.append(dict(document))
        return results

    def replace_reminder(
        self,
        reminder_id: str,
        owner_user_id: str,
        updates: dict,
        lifecycle_state: str | None = None,
        visibility: str = "visible",
    ) -> bool:
        document = self.documents.get(reminder_id)
        if (
            document is None
            or document["owner_user_id"] != owner_user_id
            or document.get("visibility") != visibility
        ):
            return False
        if (
            lifecycle_state is not None
            and document["lifecycle_state"] != lifecycle_state
        ):
            return False
        document.update(updates)
        return True

    def find_active_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
    ) -> dict | None:
        for document in self.documents.values():
            if (
                document["owner_user_id"] == owner_user_id
                and document.get("agent_output_target", {}).get("conversation_id")
                == conversation_id
                and document.get("visibility") == "internal"
                and document.get("fire_mode") == "followup"
                and document.get("lifecycle_state") == "active"
            ):
                return dict(document)
        return None


class BSONEncodingReminderDAO(InMemoryReminderDAO):
    def insert_reminder(self, document: dict) -> str:
        BSON.encode(document)
        return super().insert_reminder(document)


class InvalidIdReminderDAO(InMemoryReminderDAO):
    def get_reminder(self, reminder_id: str) -> dict | None:
        if reminder_id == "not-an-object-id":
            raise InvalidId("not-an-object-id is not a valid ObjectId")
        return super().get_reminder(reminder_id)

    def get_reminder_for_owner(
        self, reminder_id: str, owner_user_id: str
    ) -> dict | None:
        if reminder_id == "not-an-object-id":
            raise InvalidId("not-an-object-id is not a valid ObjectId")
        return super().get_reminder_for_owner(reminder_id, owner_user_id)

    def replace_reminder(
        self,
        reminder_id: str,
        owner_user_id: str,
        updates: dict,
        lifecycle_state: str | None = None,
        visibility: str = "visible",
    ) -> bool:
        if reminder_id == "not-an-object-id":
            raise InvalidId("not-an-object-id is not a valid ObjectId")
        return super().replace_reminder(
            reminder_id,
            owner_user_id,
            updates,
            lifecycle_state=lifecycle_state,
            visibility=visibility,
        )


class TerminalRaceReminderDAO(InMemoryReminderDAO):
    def __init__(self) -> None:
        super().__init__()
        self.replace_attempted = False

    def replace_reminder(
        self,
        reminder_id: str,
        owner_user_id: str,
        updates: dict,
        lifecycle_state: str | None = None,
        visibility: str = "visible",
    ) -> bool:
        self.replace_attempted = True
        self.documents[reminder_id].update(
            {
                "lifecycle_state": "completed",
                "completed_at": NOW,
                "next_fire_at": None,
            }
        )
        return super().replace_reminder(
            reminder_id,
            owner_user_id,
            updates,
            lifecycle_state=lifecycle_state,
            visibility=visibility,
        )


def schedule(
    anchor_at: datetime = FUTURE, rrule: str | None = None
) -> ReminderSchedule:
    return ReminderSchedule(
        anchor_at=anchor_at,
        local_date=date(2026, 4, 29),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=rrule,
    )


def target(
    conversation_id: str = "conv-1",
    character_id: str = "char-1",
) -> AgentOutputTarget:
    return AgentOutputTarget(
        conversation_id=conversation_id,
        character_id=character_id,
        route_key="wechat_personal:primary",
    )


def create_command(
    *,
    reminder_schedule: ReminderSchedule | None = None,
    output_target: AgentOutputTarget | None = None,
    title: str = "drink water",
    metadata: dict | None = None,
) -> ReminderCreateCommand:
    kwargs = {
        "title": title,
        "schedule": reminder_schedule or schedule(),
        "agent_output_target": output_target or target(),
        "created_by_system": "agent",
    }
    if metadata is not None:
        kwargs["metadata"] = metadata
    return ReminderCreateCommand(**kwargs)


def make_service(
    dao: InMemoryReminderDAO | None = None,
    scheduler: Mock | None = None,
) -> tuple[ReminderService, InMemoryReminderDAO, Mock]:
    reminder_dao = dao or InMemoryReminderDAO()
    reminder_scheduler = scheduler or Mock()
    return (
        ReminderService(
            reminder_dao=reminder_dao,
            scheduler=reminder_scheduler,
            now_provider=lambda: NOW,
        ),
        reminder_dao,
        reminder_scheduler,
    )


def test_create_validates_output_target_and_writes_next_fire_at():
    service, dao, scheduler = make_service()

    with pytest.raises(InvalidOutputTarget):
        service.create(
            owner_user_id="user-1",
            command=create_command(output_target=target(conversation_id="")),
        )

    reminder = service.create(owner_user_id="user-1", command=create_command())

    assert reminder.id == "rem-1"
    assert reminder.owner_user_id == "user-1"
    assert reminder.created_by_system == "agent"
    assert reminder.lifecycle_state == "active"
    assert reminder.next_fire_at == FUTURE
    assert dao.documents["rem-1"]["next_fire_at"] == FUTURE
    scheduler.register_reminder.assert_called_once_with(reminder)


def test_create_visible_reminder_writes_required_classification_fields():
    service, dao, _ = make_service()

    reminder = service.create(owner_user_id="user-1", command=create_command())

    assert reminder.origin == "user"
    assert reminder.visibility == "visible"
    assert reminder.fire_mode == "notify"
    assert reminder.prompt is None
    assert reminder.metadata == {}
    assert dao.documents[reminder.id]["origin"] == "user"
    assert dao.documents[reminder.id]["visibility"] == "visible"
    assert dao.documents[reminder.id]["fire_mode"] == "notify"
    assert dao.documents[reminder.id]["prompt"] is None
    assert dao.documents[reminder.id]["metadata"] == {}


def test_create_visible_reminder_persists_command_metadata():
    service, dao, _ = make_service()
    metadata = {
        "shared_reminder_request_id": "srr_1",
        "projection_role": "requester",
    }

    reminder = service.create(
        owner_user_id="user-1",
        command=create_command(metadata=metadata),
    )

    assert reminder.metadata == metadata
    assert dao.documents[reminder.id]["metadata"] == metadata


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


@pytest.mark.parametrize("duration_minutes", [0, -1, True, 1.5, "60"])
def test_create_rejects_invalid_schedule_duration_minutes(duration_minutes):
    service, dao, scheduler = make_service()

    with pytest.raises(InvalidSchedule):
        service.create(
            owner_user_id="user-1",
            command=create_command(
                reminder_schedule=ReminderSchedule(
                    anchor_at=FUTURE,
                    local_date=date(2026, 4, 29),
                    local_time=time(10, 0),
                    timezone="Asia/Tokyo",
                    rrule=None,
                    duration_minutes=duration_minutes,
                )
            ),
        )

    assert dao.documents == {}
    scheduler.register_reminder.assert_not_called()


def test_list_occupied_occurrences_filters_visibility_and_duration():
    service, _dao, _scheduler = make_service()
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


def test_create_uses_global_scheduler_when_scheduler_not_injected():
    from agent.reminder.runtime import (
        ReminderRuntime,
        get_reminder_runtime_instance,
        set_reminder_runtime_instance,
    )

    dao = InMemoryReminderDAO()
    scheduler = Mock()
    previous_runtime = get_reminder_runtime_instance()
    runtime = ReminderRuntime(
        contract=object(),
        scheduler=scheduler,
        fire_consumer=object(),
    )
    try:
        set_reminder_runtime_instance(runtime)
        service = ReminderService(
            reminder_dao=dao,
            now_provider=lambda: NOW,
        )

        reminder = service.create(owner_user_id="user-1", command=create_command())

        scheduler.register_reminder.assert_called_once_with(reminder)
    finally:
        set_reminder_runtime_instance(previous_runtime)


def test_create_writes_bson_encodable_schedule_document():
    service, dao, _ = make_service(dao=BSONEncodingReminderDAO())

    reminder = service.create(owner_user_id="user-1", command=create_command())

    assert reminder.schedule.local_date == date(2026, 4, 29)
    assert reminder.schedule.local_time == time(10, 0)
    assert dao.documents["rem-1"]["schedule"]["local_date"] == "2026-04-29"
    assert dao.documents["rem-1"]["schedule"]["local_time"] == "10:00:00"


def test_create_rejects_past_one_shot_reminders():
    service, _, scheduler = make_service()

    with pytest.raises(InvalidSchedule):
        service.create(
            owner_user_id="user-1",
            command=create_command(
                reminder_schedule=schedule(
                    anchor_at=datetime(2026, 4, 27, 1, 0, tzinfo=UTC)
                )
            ),
        )

    scheduler.register_reminder.assert_not_called()


def test_create_rejects_whitespace_only_title():
    service, _, scheduler = make_service()

    with pytest.raises(InvalidArgument):
        service.create(owner_user_id="user-1", command=create_command(title="   "))

    scheduler.register_reminder.assert_not_called()


def test_list_for_user_returns_owner_scoped_reminders():
    service, _, _ = make_service()
    user_reminder = service.create(
        owner_user_id="user-1",
        command=create_command(title="user reminder"),
    )
    service.create(
        owner_user_id="user-2",
        command=create_command(title="other user reminder"),
    )

    reminders = service.list_for_user(
        owner_user_id="user-1",
        query=ReminderQuery(lifecycle_states=["active"]),
    )

    assert reminders == [user_reminder]


def test_list_for_user_excludes_internal_and_missing_visibility_rows():
    service, dao, _ = make_service()
    visible = service.create(
        owner_user_id="user-1",
        command=create_command(title="visible"),
    )
    internal_doc = {
        **dao.documents[visible.id],
        "_id": "rem-internal",
        "title": "internal",
        "origin": "agent",
        "visibility": "internal",
        "fire_mode": "followup",
        "prompt": "ask about progress",
        "metadata": {"proactive_times": 0},
    }
    legacy_doc = {
        **dao.documents[visible.id],
        "_id": "rem-legacy",
        "title": "legacy without visibility",
    }
    for key in ("origin", "visibility", "fire_mode", "prompt", "metadata"):
        legacy_doc.pop(key, None)
    dao.documents["rem-internal"] = internal_doc
    dao.documents["rem-legacy"] = legacy_doc

    reminders = service.list_for_user(
        owner_user_id="user-1",
        query=ReminderQuery(lifecycle_states=["active"]),
    )

    assert [reminder.title for reminder in reminders] == ["visible"]


@pytest.mark.parametrize("action", ["get", "update", "cancel", "complete"])
def test_visible_user_paths_reject_internal_reminders_as_not_found(action):
    service, dao, scheduler = make_service()
    visible = service.create(
        owner_user_id="user-1",
        command=create_command(title="visible"),
    )
    internal_doc = {
        **dao.documents[visible.id],
        "_id": "rem-internal",
        "title": "internal",
        "origin": "agent",
        "visibility": "internal",
        "fire_mode": "followup",
        "prompt": "ask about progress",
        "metadata": {"proactive_times": 0},
    }
    dao.documents["rem-internal"] = internal_doc
    scheduler.reset_mock()

    with pytest.raises(ReminderNotFound):
        if action == "get":
            service.get(reminder_id="rem-internal", owner_user_id="user-1")
        elif action == "update":
            service.update(
                reminder_id="rem-internal",
                owner_user_id="user-1",
                patch=ReminderPatch(title="updated"),
            )
        elif action == "cancel":
            service.cancel(reminder_id="rem-internal", owner_user_id="user-1")
        else:
            service.complete(reminder_id="rem-internal", owner_user_id="user-1")

    assert dao.documents["rem-internal"] == internal_doc
    scheduler.remove_reminder.assert_not_called()
    scheduler.reschedule_reminder.assert_not_called()


def test_list_for_user_in_local_date_range_scopes_by_owner_and_state():
    service, _, _ = make_service()
    service.create(owner_user_id="user-1", command=create_command(title="in range"))
    service.create(owner_user_id="user-2", command=create_command(title="other user"))
    cancelled = service.create(
        owner_user_id="user-1", command=create_command(title="cancelled")
    )
    service.cancel(reminder_id=cancelled.id, owner_user_id="user-1")

    reminders = service.list_for_user_in_local_date_range(
        owner_user_id="user-1",
        from_date=date(2026, 4, 29),
        to_date=date(2026, 4, 29),
        lifecycle_states=["active"],
    )

    assert [reminder.title for reminder in reminders] == ["in range"]


def test_list_for_user_in_local_date_range_can_include_terminal_states():
    service, _, _ = make_service()
    reminder = service.create(
        owner_user_id="user-1", command=create_command(title="done")
    )
    service.complete(reminder_id=reminder.id, owner_user_id="user-1")

    reminders = service.list_for_user_in_local_date_range(
        owner_user_id="user-1",
        from_date=date(2026, 4, 29),
        to_date=date(2026, 4, 29),
        lifecycle_states=["completed"],
    )

    assert [reminder.title for reminder in reminders] == ["done"]


def test_update_rejects_owner_mismatch_as_not_found():
    service, _, _ = make_service()
    reminder = service.create(owner_user_id="user-1", command=create_command())

    with pytest.raises(ReminderNotFound):
        service.update(
            reminder_id=reminder.id,
            owner_user_id="user-2",
            patch=ReminderPatch(title="new title"),
        )


def test_update_rejects_empty_title():
    service, _, _ = make_service()
    reminder = service.create(owner_user_id="user-1", command=create_command())

    with pytest.raises(InvalidArgument):
        service.update(
            reminder_id=reminder.id,
            owner_user_id="user-1",
            patch=ReminderPatch(title=""),
        )


def test_update_rejects_whitespace_only_title():
    service, _, _ = make_service()
    reminder = service.create(owner_user_id="user-1", command=create_command())

    with pytest.raises(InvalidArgument):
        service.update(
            reminder_id=reminder.id,
            owner_user_id="user-1",
            patch=ReminderPatch(title="   "),
        )


@pytest.mark.parametrize("action", ["update", "cancel", "complete"])
def test_mutations_use_active_write_selector_to_reject_terminal_race(action):
    service, dao, scheduler = make_service(dao=TerminalRaceReminderDAO())
    reminder = service.create(owner_user_id="user-1", command=create_command())
    scheduler.reset_mock()

    with pytest.raises(InvalidArgument):
        if action == "update":
            service.update(
                reminder_id=reminder.id,
                owner_user_id="user-1",
                patch=ReminderPatch(title="new title"),
            )
        elif action == "cancel":
            service.cancel(reminder_id=reminder.id, owner_user_id="user-1")
        else:
            service.complete(reminder_id=reminder.id, owner_user_id="user-1")

    assert dao.replace_attempted is True
    assert dao.documents[reminder.id]["lifecycle_state"] == "completed"
    assert dao.documents[reminder.id]["title"] == "drink water"
    scheduler.reschedule_reminder.assert_not_called()
    scheduler.remove_reminder.assert_not_called()


@pytest.mark.parametrize("lifecycle_state", ["completed", "cancelled", "failed"])
@pytest.mark.parametrize("action", ["update", "cancel", "complete"])
def test_terminal_reminders_cannot_be_mutated(lifecycle_state, action):
    service, dao, _ = make_service()
    reminder = service.create(owner_user_id="user-1", command=create_command())
    dao.documents[reminder.id].update(
        {
            "lifecycle_state": lifecycle_state,
            "next_fire_at": None,
            "updated_at": NOW,
        }
    )
    original_document = dict(dao.documents[reminder.id])

    with pytest.raises(InvalidArgument):
        if action == "update":
            service.update(
                reminder_id=reminder.id,
                owner_user_id="user-1",
                patch=ReminderPatch(title="new title"),
            )
        elif action == "cancel":
            service.cancel(reminder_id=reminder.id, owner_user_id="user-1")
        else:
            service.complete(reminder_id=reminder.id, owner_user_id="user-1")

    assert dao.documents[reminder.id] == original_document


def test_cancel_sets_cancelled_at_and_clears_next_fire_at():
    service, dao, scheduler = make_service()
    reminder = service.create(owner_user_id="user-1", command=create_command())

    cancelled = service.cancel(reminder_id=reminder.id, owner_user_id="user-1")

    assert cancelled.lifecycle_state == "cancelled"
    assert cancelled.cancelled_at == NOW
    assert cancelled.next_fire_at is None
    assert dao.documents[reminder.id]["cancelled_at"] == NOW
    assert dao.documents[reminder.id]["next_fire_at"] is None
    scheduler.remove_reminder.assert_called_once_with(reminder.id)


def test_complete_sets_completed_at_and_clears_next_fire_at():
    service, dao, scheduler = make_service()
    reminder = service.create(owner_user_id="user-1", command=create_command())

    completed = service.complete(reminder_id=reminder.id, owner_user_id="user-1")

    assert completed.lifecycle_state == "completed"
    assert completed.completed_at == NOW
    assert completed.next_fire_at is None
    assert dao.documents[reminder.id]["completed_at"] == NOW
    assert dao.documents[reminder.id]["next_fire_at"] is None
    scheduler.remove_reminder.assert_called_once_with(reminder.id)


def test_execute_batch_preserves_order_and_partial_failures():
    service, _, _ = make_service()

    results = service.execute_batch(
        owner_user_id="user-1",
        commands=[
            ReminderCommand(action="create", create=create_command(title="first")),
            ReminderCommand(
                action="update", reminder_id="missing", patch=ReminderPatch(title="x")
            ),
            ReminderCommand(
                action="list", query=ReminderQuery(lifecycle_states=["active"])
            ),
        ],
    )

    assert [result.action for result in results] == ["create", "update", "list"]
    assert [result.ok for result in results] == [True, False, True]
    assert results[0].reminder is not None
    assert results[0].reminders is None
    assert isinstance(results[1].error, ReminderNotFound)
    assert results[2].reminders == [results[0].reminder]
    assert results[2].reminder is None


def test_execute_batch_rejects_action_payload_mismatches():
    service, _, _ = make_service()

    results = service.execute_batch(
        owner_user_id="user-1",
        commands=[
            ReminderCommand(
                action="create",
                reminder_id="unexpected",
                create=create_command(title="first"),
            )
        ],
    )

    assert results[0].ok is False
    assert isinstance(results[0].error, InvalidArgument)


def test_execute_batch_maps_invalid_reminder_id_to_not_found_and_continues():
    service, _, _ = make_service(dao=InvalidIdReminderDAO())

    results = service.execute_batch(
        owner_user_id="user-1",
        commands=[
            ReminderCommand(
                action="update",
                reminder_id="not-an-object-id",
                patch=ReminderPatch(title="new title"),
            ),
            ReminderCommand(action="list", query=ReminderQuery()),
        ],
    )

    assert [result.action for result in results] == ["update", "list"]
    assert [result.ok for result in results] == [False, True]
    assert isinstance(results[0].error, ReminderNotFound)
    assert results[1].reminders == []


def test_execute_batch_maps_scheduler_hook_failure_to_reminder_error_and_continues():
    scheduler = Mock()
    scheduler.register_reminder.side_effect = RuntimeError("scheduler offline")
    service, _, _ = make_service(scheduler=scheduler)

    results = service.execute_batch(
        owner_user_id="user-1",
        commands=[
            ReminderCommand(action="create", create=create_command(title="first")),
            ReminderCommand(action="list", query=ReminderQuery()),
        ],
    )

    assert [result.ok for result in results] == [False, True]
    assert isinstance(results[0].error, ReminderError)
    assert not isinstance(results[0].error, RuntimeError)
    assert len(results[1].reminders) == 1


def test_timed_update_calls_scheduler_reschedule_reminder():
    service, _, scheduler = make_service()
    reminder = service.create(owner_user_id="user-1", command=create_command())
    scheduler.reset_mock()
    new_schedule = schedule(anchor_at=datetime(2026, 4, 30, 1, 0, tzinfo=UTC))

    updated = service.update(
        reminder_id=reminder.id,
        owner_user_id="user-1",
        patch=ReminderPatch(schedule=new_schedule),
    )

    assert updated.schedule == new_schedule
    assert updated.next_fire_at == datetime(2026, 4, 30, 1, 0, tzinfo=UTC)
    scheduler.reschedule_reminder.assert_called_once_with(updated)


def test_create_internal_followup_writes_internal_reminder_and_registers_scheduler():
    service, dao, scheduler = make_service()

    reminder = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key="wechat_personal:primary",
        title="check progress",
        prompt="ask whether the user started",
        schedule=schedule(),
        metadata={"proactive_times": 0},
    )

    assert reminder.origin == "agent"
    assert reminder.visibility == "internal"
    assert reminder.fire_mode == "followup"
    assert reminder.prompt == "ask whether the user started"
    assert reminder.metadata == {"proactive_times": 0}
    assert dao.documents[reminder.id]["created_by_system"] == "agent"
    assert (
        dao.documents[reminder.id]["agent_output_target"]["conversation_id"] == "conv-1"
    )
    scheduler.register_reminder.assert_called_once_with(reminder)


def test_create_internal_followup_replaces_existing_owner_conversation_followup():
    service, _, scheduler = make_service()
    first = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key=None,
        title="first",
        prompt="first prompt",
        schedule=schedule(),
        metadata={"proactive_times": 0},
    )
    scheduler.reset_mock()
    later = ReminderSchedule(
        anchor_at=datetime(2026, 4, 30, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 30),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )

    second = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key=None,
        title="second",
        prompt="second prompt",
        schedule=later,
        metadata={"proactive_times": 1},
    )

    assert second.id == first.id
    assert second.title == "second"
    assert second.prompt == "second prompt"
    assert second.metadata == {"proactive_times": 1}
    assert second.next_fire_at == datetime(2026, 4, 30, 1, 0, tzinfo=UTC)
    scheduler.reschedule_reminder.assert_called_once_with(second)


def test_internal_followup_visible_reminder_in_same_conversation_is_not_replaced():
    service, dao, scheduler = make_service()
    visible = service.create(
        owner_user_id="user-1",
        command=create_command(title="visible reminder"),
    )
    scheduler.reset_mock()

    internal = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key=None,
        title="internal followup",
        prompt="ask later",
        schedule=schedule(),
    )

    assert internal.id != visible.id
    assert dao.documents[visible.id]["visibility"] == "visible"
    assert dao.documents[visible.id]["title"] == "visible reminder"
    assert dao.documents[internal.id]["visibility"] == "internal"
    scheduler.register_reminder.assert_called_once_with(internal)


def test_clear_internal_followup_requires_owner_and_cancels_scheduler_job():
    service, dao, scheduler = make_service()
    reminder = service.create_or_replace_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
        character_id="char-1",
        route_key=None,
        title="check",
        prompt="ask",
        schedule=schedule(),
    )
    scheduler.reset_mock()

    cleared = service.clear_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )

    assert cleared is not None
    assert cleared.id == reminder.id
    assert cleared.lifecycle_state == "cancelled"
    assert cleared.cancelled_at == NOW
    assert cleared.next_fire_at is None
    assert dao.documents[reminder.id]["cancelled_at"] == NOW
    assert dao.documents[reminder.id]["next_fire_at"] is None
    scheduler.remove_reminder.assert_called_once_with(reminder.id)


def test_clear_internal_followup_returns_none_when_no_active_followup_exists():
    service, _, scheduler = make_service()
    service.create(owner_user_id="user-1", command=create_command(title="visible"))
    scheduler.reset_mock()

    cleared = service.clear_internal_followup(
        owner_user_id="user-1",
        conversation_id="conv-1",
    )

    assert cleared is None
    scheduler.remove_reminder.assert_not_called()


def test_internal_followup_rejects_rrule():
    service, _, scheduler = make_service()

    with pytest.raises(InvalidArgument):
        service.create_or_replace_internal_followup(
            owner_user_id="user-1",
            conversation_id="conv-1",
            character_id="char-1",
            route_key=None,
            title="check",
            prompt="ask",
            schedule=schedule(rrule="FREQ=DAILY"),
        )

    scheduler.register_reminder.assert_not_called()


def test_internal_followup_rejects_empty_prompt():
    service, _, scheduler = make_service()

    with pytest.raises(InvalidArgument):
        service.create_or_replace_internal_followup(
            owner_user_id="user-1",
            conversation_id="conv-1",
            character_id="char-1",
            route_key=None,
            title="check",
            prompt="   ",
            schedule=schedule(),
        )

    scheduler.register_reminder.assert_not_called()
