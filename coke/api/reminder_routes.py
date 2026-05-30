from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from coke.domains.reminder.models import ReminderBatchItem, ReminderError


def create_reminder_blueprint(reminder_service) -> Blueprint:
    blueprint = Blueprint("reminders", __name__, url_prefix="/api/reminders")

    @blueprint.errorhandler(ReminderError)
    def handle_reminder_error(error: ReminderError):
        return jsonify(_error_body(error.code, error.fact)), 400

    @blueprint.post("/batch")
    def batch():
        payload = _json_payload()
        result = reminder_service.execute_batch(
            owner_account_id=_body_str_field(payload, "owner_account_id"),
            items=[_batch_item(item) for item in _body_list_field(payload, "items")],
        )
        return jsonify(
            {
                "owner_account_id": result.owner_account_id,
                "items": [_item_result_body(item) for item in result.items],
            }
        )

    @blueprint.get("/calendar")
    def calendar():
        result = reminder_service.calendar_entries(
            owner_account_id=_query_str_field("owner_account_id"),
            visible_start=_parse_datetime(_query_str_field("visible_start")),
            visible_end=_parse_datetime(_query_str_field("visible_end")),
            display_timezone=_query_str_field("display_timezone"),
        )
        return jsonify(
            {
                "owner_account_id": result.owner_account_id,
                "entries": [_calendar_entry_body(entry) for entry in result.entries],
            }
        )

    @blueprint.post("/<reminder_id>/schedule-unscheduled")
    def schedule_unscheduled(reminder_id: str):
        payload = _json_payload()
        result = reminder_service.schedule_unscheduled(
            owner_account_id=_body_str_field(payload, "owner_account_id"),
            reminder_id=_path_str_field(reminder_id, "reminder_id"),
            trigger_time=_parse_datetime(_body_str_field(payload, "trigger_time")),
            captured_timezone=_body_str_field(payload, "captured_timezone"),
        )
        return jsonify(_item_result_body(result))

    @blueprint.post("/<reminder_id>/clear-trigger-time")
    def clear_trigger_time(reminder_id: str):
        payload = _json_payload()
        result = reminder_service.clear_trigger_time(
            owner_account_id=_body_str_field(payload, "owner_account_id"),
            reminder_id=_path_str_field(reminder_id, "reminder_id"),
        )
        return jsonify(_item_result_body(result))

    @blueprint.post("/<reminder_id>/complete")
    def complete(reminder_id: str):
        payload = _json_payload()
        result = reminder_service.complete_reminder(
            owner_account_id=_body_str_field(payload, "owner_account_id"),
            reminder_id=_path_str_field(reminder_id, "reminder_id"),
        )
        return jsonify(_item_result_body(result))

    @blueprint.post("/<reminder_id>/delete")
    def delete(reminder_id: str):
        payload = _json_payload()
        result = reminder_service.delete_reminder(
            owner_account_id=_body_str_field(payload, "owner_account_id"),
            reminder_id=_path_str_field(reminder_id, "reminder_id"),
            user_initiated=True,
        )
        return jsonify(_item_result_body(result))

    return blueprint


def _batch_item(payload: dict) -> ReminderBatchItem:
    if not isinstance(payload, dict):
        raise ReminderError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": "items",
                "reason": "object_required",
            },
        )
    trigger_time = payload.get("trigger_time")
    return ReminderBatchItem(
        operation=_body_str_field(payload, "operation"),
        content=payload.get("content"),
        raw_text=payload.get("raw_text"),
        reminder_id=payload.get("reminder_id"),
        trigger_time=(
            _parse_datetime(trigger_time) if isinstance(trigger_time, str) else None
        ),
        captured_timezone=payload.get("captured_timezone", "UTC"),
        recurrence_rule=payload.get("recurrence_rule") or {},
        duration_minutes=payload.get("duration_minutes"),
        kind=payload.get("kind"),
        entry_point=payload.get("entry_point"),
        time_state=payload.get("time_state"),
        incomplete_date=bool(payload.get("incomplete_date", False)),
        shared_reminder_id=payload.get("shared_reminder_id"),
    )


def _item_result_body(item) -> dict:
    return {
        "state": item.state,
        "reminder_id": item.reminder_id,
        "reason": item.reason,
        "time_state": item.time_state,
        "fact": item.fact,
    }


def _calendar_entry_body(entry) -> dict:
    return {
        "entry_type": entry.entry_type,
        "reminder_id": entry.reminder_id,
        "fire_id": entry.fire_id,
        "display_start": (
            entry.display_start.isoformat() if entry.display_start is not None else None
        ),
        "display_end": (
            entry.display_end.isoformat() if entry.display_end is not None else None
        ),
        "content": entry.content,
        "action_handles": list(entry.action_handles),
        "friend_identifiers": list(entry.friend_identifiers),
        "member_reminder_ids": list(entry.member_reminder_ids),
        "fact": entry.fact,
    }


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ReminderError(
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
        raise ReminderError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    return payload[field]


def _body_list_field(payload: dict, field: str) -> list:
    value = _body_field(payload, field)
    if not isinstance(value, list):
        raise ReminderError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "list_field_required",
            },
        )
    return value


def _body_str_field(payload: dict, field: str) -> str:
    value = _body_field(payload, field)
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise ReminderError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _path_str_field(value: str, field: str) -> str:
    if value.strip() == "" or value != value.strip():
        raise ReminderError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "path",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _query_str_field(field: str) -> str:
    value = request.args.get(field)
    if value is None:
        raise ReminderError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    if value.strip() == "" or value != value.strip():
        raise ReminderError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ReminderError(
            "invalid_request",
            fact={"type": "invalid_request", "reason": "invalid_datetime"},
        ) from error
    if parsed.tzinfo is None:
        raise ReminderError(
            "invalid_request",
            fact={"type": "invalid_request", "reason": "timezone_required"},
        )
    return parsed


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body
