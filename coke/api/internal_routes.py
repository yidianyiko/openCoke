from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request


class InternalRouteError(RuntimeError):
    def __init__(self, code: str, status_code: int = 400, fact: dict | None = None):
        self.code = code
        self.status_code = status_code
        self.fact = fact
        super().__init__(code)


def create_internal_blueprint(
    *,
    delivery_callback_service=None,
    reply_pubsub=None,
    internal_api_key: str | None = None,
) -> Blueprint:
    blueprint = Blueprint("internal", __name__)

    @blueprint.errorhandler(InternalRouteError)
    def handle_internal_error(error: InternalRouteError):
        body = {"error": {"code": error.code}}
        if error.fact is not None:
            body["error"]["fact"] = error.fact
        return jsonify(body), error.status_code

    @blueprint.post("/internal/outbound/delivery-callback")
    def delivery_callback():
        _require_internal_auth(internal_api_key)
        if delivery_callback_service is None:
            raise InternalRouteError("delivery_callback_unavailable", status_code=503)
        payload = _json_payload()
        result = delivery_callback_service.record_delivery_callback(
            provider_type=_body_str_field(payload, "provider_type"),
            provider_idempotency_key=_body_str_field(
                payload, "provider_idempotency_key"
            ),
            status=_delivery_status(_body_str_field(payload, "status")),
            provider_message_id=_optional_str_field(payload, "provider_message_id"),
            error_code=_optional_str_field(payload, "error_code"),
            delivered_at=_optional_str_field(payload, "delivered_at"),
        )
        return jsonify(_delivery_callback_body(result))

    @blueprint.get("/internal/reply-wait/<path:causal_inbound_event_id>")
    def reply_wait(causal_inbound_event_id: str):
        _require_internal_auth(internal_api_key)
        if reply_pubsub is None:
            raise InternalRouteError("reply_wait_unavailable", status_code=503)
        causal_id = _path_str_field(causal_inbound_event_id, "causal_inbound_event_id")
        timeout_s = _timeout_s()
        subscription = reply_pubsub.subscribe(causal_id)
        try:
            reply = reply_pubsub.get_reply(subscription, timeout_s=timeout_s)
        finally:
            close = getattr(subscription, "close", None)
            if callable(close):
                close()
        if reply is None:
            return Response(status=204)
        if not isinstance(reply, Mapping):
            raise InternalRouteError("invalid_reply_payload", status_code=502)
        return jsonify(dict(reply))

    return blueprint


def _require_internal_auth(internal_api_key: str | None) -> None:
    expected = _configured_internal_key(internal_api_key)
    if expected is None:
        raise InternalRouteError("internal_auth_not_configured", status_code=503)
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        raise InternalRouteError(
            "unauthorized",
            status_code=401,
            fact={"type": "unauthorized", "reason": "missing_bearer_token"},
        )
    supplied = header[len(prefix) :]
    if supplied.strip() == "" or supplied != supplied.strip():
        raise InternalRouteError(
            "unauthorized",
            status_code=401,
            fact={"type": "unauthorized", "reason": "missing_bearer_token"},
        )
    if supplied != expected:
        raise InternalRouteError("forbidden", status_code=403)


def _configured_internal_key(internal_api_key: str | None) -> str | None:
    value = (
        internal_api_key
        or current_app.config.get("COKE_INTERNAL_API_KEY")
        or os.environ.get("COKE_INTERNAL_API_KEY")
    )
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise InternalRouteError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "reason": "json_body_required",
            },
        )
    return payload


def _body_field(payload: dict, field: str) -> Any:
    if field not in payload:
        raise InternalRouteError(
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
    return _str_field(value, "body", field)


def _optional_str_field(payload: dict, field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    return _str_field(value, "body", field)


def _path_str_field(value: str, field: str) -> str:
    return _str_field(value, "path", field)


def _str_field(value: Any, location: str, field: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise InternalRouteError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": location,
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value


def _delivery_status(value: str) -> str:
    if value not in {"sent", "delivered", "failed"}:
        raise InternalRouteError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": "status",
                "reason": "unsupported_delivery_status",
            },
        )
    return value


def _timeout_s() -> float:
    raw = request.args.get("timeout_s")
    if raw is None:
        return 30.0
    try:
        value = float(raw)
    except ValueError as error:
        raise InternalRouteError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": "timeout_s",
                "reason": "positive_number_required",
            },
        ) from error
    if value <= 0:
        raise InternalRouteError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": "timeout_s",
                "reason": "positive_number_required",
            },
        )
    return value


def _delivery_callback_body(result) -> dict:
    return {
        "attempt_id": getattr(result, "attempt_id"),
        "provider_type": getattr(result, "provider_type"),
        "provider_idempotency_key": getattr(result, "provider_idempotency_key"),
        "status": getattr(result, "status"),
        "idempotent": getattr(result, "idempotent", True),
    }
