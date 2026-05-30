from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from coke.domains.social_scheduling.models import SocialSchedulingError


def create_shared_reminder_blueprint(social_scheduling_service) -> Blueprint:
    blueprint = Blueprint(
        "shared_reminders",
        __name__,
        url_prefix="/api/shared-reminders",
    )

    @blueprint.errorhandler(SocialSchedulingError)
    def handle_social_scheduling_error(error: SocialSchedulingError):
        return jsonify(_error_body(error.code, error.fact)), 400

    @blueprint.post("/availability")
    def availability():
        payload = _json_payload()
        result = social_scheduling_service.query_availability(
            requester_account_id=_body_str_field(payload, "requester_account_id"),
            friend_account_ids=_body_str_list_field(payload, "friend_account_ids"),
            local_start=_body_datetime_field(payload, "local_start"),
            local_end=_body_datetime_field(payload, "local_end"),
            requester_timezone=_body_str_field(payload, "requester_timezone"),
        )
        results = result if isinstance(result, list) else [result]
        return jsonify({"friends": [_availability_body(item) for item in results]})

    @blueprint.post("")
    def create_shared_reminder():
        payload = _json_payload()
        result = social_scheduling_service.create_shared_reminder(
            creator_account_id=_body_str_field(payload, "creator_account_id"),
            receiver_account_ids=_body_str_list_field(payload, "receiver_account_ids"),
            title=_body_optional_str_field(payload, "title"),
            local_trigger_at=_body_optional_datetime_field(payload, "local_trigger_at"),
            captured_timezone=_body_str_field(payload, "captured_timezone"),
            duration_minutes=_body_int_field(payload, "duration_minutes"),
            context=payload.get("context"),
        )
        status_code = 201 if result.status == "created" else 200
        return jsonify(_create_result_body(result)), status_code

    @blueprint.get("")
    def list_shared_reminders():
        reminders = social_scheduling_service.list_shared_reminders(
            account_id=_query_str_field("account_id")
        )
        return jsonify(
            {"shared_reminders": [_shared_reminder_body(item) for item in reminders]}
        )

    @blueprint.get("/<shared_reminder_id>")
    def view_shared_reminder(shared_reminder_id: str):
        reminder = social_scheduling_service.view_shared_reminder(
            account_id=_query_str_field("account_id"),
            shared_reminder_id=_path_str_field(
                shared_reminder_id, "shared_reminder_id"
            ),
        )
        return jsonify(_shared_reminder_body(reminder))

    @blueprint.post("/<shared_reminder_id>/cancel")
    def cancel_shared_reminder(shared_reminder_id: str):
        payload = _json_payload()
        result = social_scheduling_service.cancel_shared_reminder(
            account_id=_body_str_field(payload, "account_id"),
            shared_reminder_id=_path_str_field(
                shared_reminder_id, "shared_reminder_id"
            ),
        )
        return jsonify(
            {
                "status": result.status,
                "shared_reminder": _shared_reminder_body(result.shared_reminder),
            }
        )

    @blueprint.post("/<shared_reminder_id>/complete-own-projection")
    def complete_own_projection(shared_reminder_id: str):
        payload = _json_payload()
        projection = social_scheduling_service.complete_own_projection(
            account_id=_body_str_field(payload, "account_id"),
            shared_reminder_id=_path_str_field(
                shared_reminder_id, "shared_reminder_id"
            ),
        )
        return jsonify(
            {
                "account_id": projection.account_id,
                "completion_status": projection.completion_status,
            }
        )

    return blueprint


def _create_result_body(result) -> dict:
    return {
        "status": result.status,
        "shared_reminder": (
            _shared_reminder_body(result.shared_reminder)
            if result.shared_reminder is not None
            else None
        ),
        "projections": [
            {
                "account_id": projection.account_id,
                "completion_status": getattr(projection, "completion_status", None),
            }
            for projection in result.projections
        ],
        "breakdown": result.breakdown,
        "follow_up_facts": result.follow_up_facts,
    }


def _availability_body(result) -> dict:
    return {
        "friend_account_id": result.friend_account_id,
        "windows": [window.to_public_dict() for window in result.windows],
    }


def _shared_reminder_body(reminder) -> dict:
    return {
        "shared_reminder_id": reminder.id,
        "creator_account_id": reminder.creator_account_id,
        "participant_account_ids": list(reminder.participant_account_ids),
        "title": reminder.title,
        "local_trigger_at": reminder.local_trigger_at.isoformat(),
        "captured_timezone": reminder.captured_timezone,
        "duration_minutes": reminder.duration_minutes,
        "status": reminder.status,
    }


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise SocialSchedulingError(
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
        raise SocialSchedulingError(
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
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _body_optional_str_field(payload: dict, field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _body_str_list_field(payload: dict, field: str) -> list[str]:
    value = _body_field(payload, field)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or item.strip() == "" or item != item.strip()
        for item in value
    ):
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_list_field_required",
            },
        )
    return value


def _body_int_field(payload: dict, field: str) -> int:
    value = _body_field(payload, field)
    if not isinstance(value, int) or value <= 0:
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "positive_integer_field_required",
            },
        )
    return value


def _body_datetime_field(payload: dict, field: str) -> datetime:
    return _parse_datetime(_body_str_field(payload, field), field)


def _body_optional_datetime_field(payload: dict, field: str) -> datetime | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "datetime_field_required",
            },
        )
    return _parse_datetime(value, field)


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "datetime_field_required",
            },
        ) from error


def _query_str_field(field: str) -> str:
    value = request.args.get(field)
    if value is None:
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    if value.strip() == "" or value != value.strip():
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _path_str_field(value: str, field: str) -> str:
    if value.strip() == "" or value != value.strip():
        raise SocialSchedulingError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "path",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body
