from __future__ import annotations

import inspect
from typing import Any

from agent.reminder.models import ReminderFiredEvent, ReminderFireResult


class CokeReminderFireConsumer:
    def __init__(self, handler: Any) -> None:
        self.handler = handler

    async def handle_fire_event(
        self,
        event: ReminderFiredEvent,
    ) -> ReminderFireResult:
        result = self.handler.handle(event)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, ReminderFireResult):
            raise RuntimeError("invalid reminder fire result")
        return result
