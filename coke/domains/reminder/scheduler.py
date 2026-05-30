from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from coke.domains.reminder.models import NightlySummaryTurn, ReminderFireGroup
from coke.domains.reminder.service import ReminderService


class ReminderScheduler:
    def __init__(
        self,
        service: ReminderService,
        jobstore: str = "memory",
        account_timezone: Callable[[str], str] | None = None,
    ) -> None:
        if jobstore != "memory":
            # The production binding is intentionally represented as a pinned
            # facade here; tests use memory and real Postgres wiring belongs to
            # the deployment composition layer.
            self.jobstore = "postgres"
        else:
            self.jobstore = "memory"
        self.service = service
        self._account_timezone = account_timezone or (lambda _account_id: "UTC")

    def collect_due_fire_turns(self, due_at: datetime) -> list[ReminderFireGroup]:
        grouped: dict[tuple[str, datetime], list[str]] = defaultdict(list)
        for reminder in self.service.repository.list_due_reminders(due_at):
            if reminder.next_fire_at is None:
                continue
            fire = self.service.claim_due_fire(
                reminder_id=reminder.id,
                due_at=reminder.next_fire_at,
            )
            grouped[(reminder.owner_account_id, reminder.next_fire_at)].append(fire.id)
        return [
            ReminderFireGroup(
                owner_account_id=owner,
                due_at=group_due_at,
                fire_ids=fire_ids,
                trigger_id=f"reminder_fire:{owner}:{group_due_at.isoformat()}",
            )
            for (owner, group_due_at), fire_ids in sorted(grouped.items())
        ]

    def catch_up_missed(self, now: datetime) -> list[ReminderFireGroup]:
        grouped: dict[tuple[str, datetime], list[str]] = defaultdict(list)
        for reminder in self.service.repository.list_due_reminders(now):
            if reminder.next_fire_at is None:
                continue
            fire = self.service.claim_due_fire(
                reminder_id=reminder.id,
                due_at=reminder.next_fire_at,
                missed_catch_up=True,
            )
            if reminder.kind == "proactive":
                self.service.discard_proactive_fire(fire.id, missed_catch_up=True)
                continue
            grouped[(reminder.owner_account_id, reminder.next_fire_at)].append(fire.id)
        return [
            ReminderFireGroup(
                owner_account_id=owner,
                due_at=group_due_at,
                fire_ids=fire_ids,
                trigger_id=f"reminder_fire:{owner}:{group_due_at.isoformat()}",
            )
            for (owner, group_due_at), fire_ids in sorted(grouped.items())
        ]

    def nightly_summary_turn(
        self,
        owner_account_id: str,
        local_date: date,
    ) -> NightlySummaryTurn:
        timezone = ZoneInfo(self._account_timezone(owner_account_id))
        local_scheduled_at = datetime.combine(
            local_date,
            time(20, 0),
            tzinfo=timezone,
        )
        reminder_ids = [
            reminder.id
            for reminder in self.service.repository.list_active_reminders(
                owner_account_id
            )
            if reminder.kind == "no_trigger_time"
        ]
        return NightlySummaryTurn(
            owner_account_id=owner_account_id,
            local_scheduled_at=local_scheduled_at,
            reminder_ids=reminder_ids,
            trigger_id=f"nightly_summary:{owner_account_id}:{local_scheduled_at.isoformat()}",
        )
