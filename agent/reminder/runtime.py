from __future__ import annotations

from typing import Any


class ReminderRuntime:
    """In-process Reminder capability object owned by Coke runtime wiring."""

    def __init__(self, *, contract: Any, scheduler: Any, fire_consumer: Any) -> None:
        self.contract = contract
        self.scheduler = scheduler
        self.fire_consumer = fire_consumer

    def start(self) -> None:
        self.scheduler.start()

    def load_from_storage(self) -> None:
        self.scheduler.load_from_storage()

    def shutdown(self) -> None:
        self.scheduler.shutdown()


_runtime_instance: ReminderRuntime | None = None


def set_reminder_runtime_instance(runtime: ReminderRuntime | None) -> None:
    global _runtime_instance
    _runtime_instance = runtime


def get_reminder_runtime_instance() -> ReminderRuntime | None:
    return _runtime_instance
