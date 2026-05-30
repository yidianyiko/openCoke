from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from coke.api.auth_helpers import require_customer_account_id
from coke.domains.calendar_import.models import CalendarImportError


def create_calendar_import_blueprint(
    calendar_import_service,
    identity_service,
) -> Blueprint:
    blueprint = Blueprint(
        "calendar_import",
        __name__,
        url_prefix="/api/calendar-import",
    )

    @blueprint.errorhandler(CalendarImportError)
    def handle_calendar_import_error(error: CalendarImportError):
        return jsonify(_error_body(error.code, error.fact)), _status_code(error.code)

    @blueprint.post("/google/import")
    def import_google():
        account_id = _customer_account_id(identity_service)
        payload = _json_payload()
        summary = calendar_import_service.import_google_calendar(
            account_id=account_id,
            auth_handle=_body_str_field(payload, "auth_handle"),
            provider_account_id=_optional_str_field(payload, "provider_account_id"),
            visible_start=_parse_datetime(_body_str_field(payload, "visible_start")),
            visible_end=_parse_datetime(_body_str_field(payload, "visible_end")),
            captured_timezone=_body_str_field(payload, "captured_timezone"),
            auth_artifact_id=_optional_str_field(payload, "auth_artifact_id"),
        )
        return jsonify({"summary": _summary_body(summary)})

    @blueprint.post("/google/stop")
    def stop_google():
        account_id = _customer_account_id(identity_service)
        payload = _json_payload()
        state = calendar_import_service.stop_authorization(
            account_id=account_id,
            auth_handle=_body_str_field(payload, "auth_handle"),
        )
        return jsonify({"authorization": _authorization_body(state)})

    @blueprint.post("/google/revoke")
    def revoke_google():
        account_id = _customer_account_id(identity_service)
        payload = _json_payload()
        state = calendar_import_service.revoke_authorization(
            account_id=account_id,
            auth_handle=_body_str_field(payload, "auth_handle"),
        )
        return jsonify({"authorization": _authorization_body(state)})

    return blueprint


def _customer_account_id(identity_service) -> str:
    return require_customer_account_id(identity_service, CalendarImportError)


def _summary_body(summary) -> dict:
    return {
        "run_id": summary.run_id,
        "imported_count": summary.imported_count,
        "skipped_count": summary.skipped_count,
        "downgraded_count": summary.downgraded_count,
        "failed_count": summary.failed_count,
        "items": [_item_body(item) for item in summary.items],
        "downgraded_items": [_item_body(item) for item in summary.downgraded_items],
        "failed_items": [_item_body(item) for item in summary.failed_items],
    }


def _item_body(item) -> dict:
    return {
        "id": item.id,
        "provider_calendar_id": item.provider_calendar_id,
        "source_event_id": item.source_event_id,
        "recurrence_instance_key": item.recurrence_instance_key,
        "status": item.status,
        "reason": item.reason,
        "source_metadata": dict(item.source_metadata),
        "reminder_id": item.reminder_id,
    }


def _authorization_body(state) -> dict:
    return {
        "account_id": state.account_id,
        "auth_handle": state.auth_handle,
        "state": state.state,
    }


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise CalendarImportError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "reason": "json_body_required",
            },
        )
    return payload


def _body_field(payload: dict, field: str):
    if field not in payload:
        raise CalendarImportError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    return payload[field]


def _body_str_field(payload: dict, field: str) -> str:
    value = _body_field(payload, field)
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CalendarImportError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _optional_str_field(payload: dict, field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CalendarImportError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CalendarImportError(
            "invalid_request",
            fact={"type": "invalid_request", "reason": "invalid_datetime"},
        ) from error
    if parsed.tzinfo is None:
        raise CalendarImportError(
            "invalid_request",
            fact={"type": "invalid_request", "reason": "timezone_required"},
        )
    return parsed


def _error_body(code: str, fact: dict | None) -> dict:
    return {"error": {"code": code, "fact": fact or {}}}


def _status_code(code: str) -> int:
    return 401 if code == "unauthorized" else 400
