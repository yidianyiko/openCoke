from __future__ import annotations

from typing import Protocol

from agent.reminder.models import ReminderFiredEvent, ReminderFireResult


class ReminderFireConsumer(Protocol):
    async def handle_fire_event(
        self,
        event: ReminderFiredEvent,
    ) -> ReminderFireResult: ...
