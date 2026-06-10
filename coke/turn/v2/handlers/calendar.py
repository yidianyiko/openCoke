from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from coke.domains.calendar_import.models import (
    CalendarImportError,
    CalendarImportSummary,
)
from coke.domains.calendar_import.service import CalendarImportService
from coke.turn.v2.contracts import ActionOutcome, CompiledAction


class CalendarImportActionHandler:
    def __init__(self, calendar_import_service: CalendarImportService) -> None:
        self.calendar_import_service = calendar_import_service

    def resolve_and_stage(
        self,
        compiled_action: CompiledAction,
        guard: Any,
    ) -> ActionOutcome:
        action = compiled_action.action
        if action is None:
            return ActionOutcome(
                category="not_possible",
                status="invalid_compiled_action",
            )
        if action.operation != "import":
            return ActionOutcome(
                category="not_possible",
                status="unsupported_operation",
                data={"domain": "calendar_import", "operation": action.operation},
            )
        return self._import(dict(action.params), guard)

    def _import(self, params: Mapping[str, Any], guard: Any) -> ActionOutcome:
        account_id = _optional_str(
            params.get("account_id") or params.get("owner_account_id")
        )
        if account_id is None:
            return _missing_input("account_id")
        source = _optional_str(params.get("source"))
        if source not in {"google_calendar", "google"}:
            return ActionOutcome(
                category="not_possible",
                status="unsupported_source",
                data={"source": source},
            )
        auth_handle = _optional_str(params.get("auth_handle"))
        if auth_handle is None:
            return _missing_input("auth_handle")
        visible_start = _optional_datetime(params.get("visible_start"))
        if visible_start is None:
            return _missing_input("visible_start")
        visible_end = _optional_datetime(params.get("visible_end"))
        if visible_end is None:
            return _missing_input("visible_end")
        captured_timezone = str(params.get("captured_timezone") or "UTC")
        try:
            summary = self.calendar_import_service.import_google_calendar(
                account_id=account_id,
                auth_handle=auth_handle,
                provider_account_id=params.get("provider_account_id"),
                visible_start=visible_start,
                visible_end=visible_end,
                captured_timezone=captured_timezone,
                auth_artifact_id=params.get("auth_artifact_id"),
            )
        except (CalendarImportError, ValueError) as error:
            return _calendar_error_outcome(error)
        data = _summary_data(summary)
        status = "partial" if summary.failed_count > 0 else "imported"
        staged_id = _stage_calendar_command(
            guard,
            command_payload={
                "operation": "import_google_calendar",
                "account_id": account_id,
                "auth_handle": auth_handle,
                "provider_account_id": params.get("provider_account_id"),
                "visible_start": visible_start,
                "visible_end": visible_end,
                "captured_timezone": captured_timezone,
                "auth_artifact_id": params.get("auth_artifact_id"),
            },
            preview_facts={
                "status": "staged",
                "operation": "import_google_calendar",
                "account_id": account_id,
            },
        )
        return ActionOutcome(
            category="done",
            status=status,
            data=data,
            staged_command_id=staged_id,
        )


def _summary_data(summary: CalendarImportSummary) -> dict[str, Any]:
    return {
        "run_id": summary.run_id,
        "imported": summary.imported_count,
        "skipped": summary.skipped_count,
        "downgraded": summary.downgraded_count,
        "failed": summary.failed_count,
    }


def _calendar_error_outcome(error: BaseException) -> ActionOutcome:
    if isinstance(error, CalendarImportError):
        return ActionOutcome(
            category="not_possible",
            status=error.code,
            data=error.fact or {"reason": error.code},
        )
    return ActionOutcome(
        category="not_possible",
        status=str(error) or "calendar_import_failed",
    )


def _stage_calendar_command(
    guard: Any,
    *,
    command_payload: Mapping[str, Any],
    preview_facts: Mapping[str, Any],
) -> str | None:
    stage_command = getattr(guard, "stage_command", None)
    if not callable(stage_command):
        return None
    staged = stage_command(
        domain="calendar_import",
        operation="import_google_calendar",
        command_payload={
            key: value
            for key, value in dict(command_payload).items()
            if value is not None
        },
        preview_facts=dict(preview_facts),
        item_index=1,
    )
    return getattr(staged, "id", None)


def _optional_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("invalid_datetime")


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _missing_input(field: str) -> ActionOutcome:
    return ActionOutcome(
        category="needs_input",
        status=f"missing_{field}",
        data={"field": field},
    )
