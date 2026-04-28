from __future__ import annotations

from typing import Any


class ReminderError(Exception):
    code = "ReminderError"

    def __init__(
        self,
        user_message: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail or {}


class InvalidSchedule(ReminderError):
    code = "InvalidSchedule"


class RRULENotSupported(ReminderError):
    code = "RRULENotSupported"


class ReminderNotFound(ReminderError):
    code = "ReminderNotFound"


class OwnershipViolation(ReminderError):
    code = "OwnershipViolation"


class InvalidOutputTarget(ReminderError):
    code = "InvalidOutputTarget"


class InvalidArgument(ReminderError):
    code = "InvalidArgument"


class ReminderFireFailed(ReminderError):
    code = "ReminderFireFailed"
