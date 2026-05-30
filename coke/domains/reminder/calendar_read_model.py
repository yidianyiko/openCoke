from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from coke.domains.reminder.models import CalendarEntry, CalendarQueryResult
from coke.domains.reminder.recurrence import occurrences_between
from coke.domains.reminder.repository import ReminderRepository


class ReminderCalendarReadModel:
    def __init__(
        self,
        repository: ReminderRepository,
        friend_identifiers: Callable[[str, str], list[str]] | None = None,
    ) -> None:
        self.repository = repository
        self._friend_identifiers = friend_identifiers or (
            lambda _shared_id, _viewer_id: []
        )

    def query(
        self,
        owner_account_id: str,
        visible_start: datetime,
        visible_end: datetime,
        display_timezone: str,
    ) -> CalendarQueryResult:
        zone = ZoneInfo(display_timezone)
        entries: list[CalendarEntry] = []
        reminders = [
            reminder
            for reminder in self.repository.list_active_reminders(owner_account_id)
            if not reminder.hidden_from_calendar
        ]

        for reminder in reminders:
            if reminder.kind == "no_trigger_time":
                entries.append(
                    CalendarEntry(
                        entry_type="unscheduled",
                        reminder_id=reminder.id,
                        fire_id=None,
                        display_start=None,
                        display_end=None,
                        content=reminder.content,
                        action_handles=["edit", "complete", "delete"],
                        fact={"kind": reminder.kind},
                    )
                )
                continue
            if reminder.next_fire_at is None:
                continue
            if reminder.kind == "recurring":
                for occurrence in occurrences_between(
                    reminder.recurrence_rule,
                    reminder.next_fire_at,
                    reminder.captured_timezone,
                    visible_start,
                    visible_end,
                ):
                    entries.append(
                        CalendarEntry(
                            entry_type="recurring_occurrence",
                            reminder_id=reminder.id,
                            fire_id=None,
                            display_start=occurrence.astimezone(zone),
                            display_end=(
                                occurrence
                                + timedelta(minutes=reminder.duration_minutes)
                            ).astimezone(zone),
                            content=reminder.content,
                            action_handles=[
                                "complete_occurrence",
                                "edit_series",
                                "delete_series",
                            ],
                            fact={
                                "kind": reminder.kind,
                                "occurrence_key": occurrence.isoformat(),
                            },
                        )
                    )
                continue
            if not (visible_start <= reminder.next_fire_at <= visible_end):
                continue
            if reminder.kind == "shared_projection":
                shared_id = reminder.shared_reminder_id or ""
                entries.append(
                    CalendarEntry(
                        entry_type="shared_projection",
                        reminder_id=reminder.id,
                        fire_id=None,
                        display_start=reminder.next_fire_at.astimezone(zone),
                        display_end=(
                            reminder.next_fire_at
                            + timedelta(minutes=reminder.duration_minutes)
                        ).astimezone(zone),
                        content=reminder.content,
                        action_handles=[
                            "complete_own_projection",
                            "cancel_whole_shared_reminder",
                        ],
                        friend_identifiers=self._friend_identifiers(
                            shared_id,
                            owner_account_id,
                        ),
                        fact={"kind": reminder.kind, "shared_reminder_id": shared_id},
                    )
                )
            else:
                entries.append(
                    CalendarEntry(
                        entry_type="one_time",
                        reminder_id=reminder.id,
                        fire_id=None,
                        display_start=reminder.next_fire_at.astimezone(zone),
                        display_end=(
                            reminder.next_fire_at
                            + timedelta(minutes=reminder.duration_minutes)
                        ).astimezone(zone),
                        content=reminder.content,
                        action_handles=["edit", "complete", "delete"],
                        fact={"kind": reminder.kind},
                    )
                )

        entries.extend(
            self._merged_groups(
                owner_account_id=owner_account_id,
                visible_start=visible_start,
                visible_end=visible_end,
                zone=zone,
            )
        )
        entries.extend(self._undelivered_entries(owner_account_id, zone))
        return CalendarQueryResult(owner_account_id=owner_account_id, entries=entries)

    def _merged_groups(
        self,
        owner_account_id: str,
        visible_start: datetime,
        visible_end: datetime,
        zone: ZoneInfo,
    ) -> list[CalendarEntry]:
        grouped: dict[datetime, list[str]] = defaultdict(list)
        for reminder in self.repository.list_active_reminders(owner_account_id):
            if (
                reminder.hidden_from_calendar
                or reminder.next_fire_at is None
                or not (visible_start <= reminder.next_fire_at <= visible_end)
            ):
                continue
            grouped[reminder.next_fire_at].append(reminder.id)
        return [
            CalendarEntry(
                entry_type="merged_group",
                reminder_id=None,
                fire_id=None,
                display_start=due_at.astimezone(zone),
                display_end=due_at.astimezone(zone),
                content="",
                action_handles=["expand"],
                member_reminder_ids=member_ids,
                fact={"due_at": due_at.isoformat()},
            )
            for due_at, member_ids in sorted(grouped.items())
            if len(member_ids) > 1
        ]

    def _undelivered_entries(
        self,
        owner_account_id: str,
        zone: ZoneInfo,
    ) -> list[CalendarEntry]:
        entries: list[CalendarEntry] = []
        for fire in self.repository.list_fires_for_owner(owner_account_id):
            if fire.delivery_result != "undelivered" or fire.handled_at is not None:
                continue
            reminder = self.repository.get_reminder(fire.reminder_id)
            if reminder is None or reminder.lifecycle != "active":
                continue
            entries.append(
                CalendarEntry(
                    entry_type="undelivered",
                    reminder_id=reminder.id,
                    fire_id=fire.id,
                    display_start=fire.due_at.astimezone(zone),
                    display_end=fire.due_at.astimezone(zone),
                    content=reminder.content,
                    action_handles=["complete", "delete"],
                    fact={"delivery_result": "undelivered"},
                )
            )
        return entries
