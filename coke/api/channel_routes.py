from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.api.auth_helpers import require_customer_account_id
from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
)


def create_channel_blueprint(reachability_service, identity_service) -> Blueprint:
    blueprint = Blueprint("channels", __name__, url_prefix="/api/channels")

    @blueprint.errorhandler(ChannelReachabilityError)
    def handle_channel_error(error: ChannelReachabilityError):
        return jsonify(_error_body(error.code, error.fact)), _status_code(error.code)

    @blueprint.get("/status")
    def status():
        result = reachability_service.get_status(
            account_id=_customer_account_id(identity_service)
        )
        return jsonify(_status_body(result))

    @blueprint.post("/wechat-personal/connect")
    def connect_wechat_personal():
        result = reachability_service.start_wechat_personal_connection(
            account_id=_customer_account_id(identity_service)
        )
        return jsonify(_status_body(result))

    @blueprint.get("/wechat-personal/login-status")
    def wechat_personal_login_status():
        result = reachability_service.poll_wechat_personal_login(
            account_id=_customer_account_id(identity_service),
            session_id=_query_str_field("session_id"),
        )
        return jsonify(_status_body(result))

    @blueprint.post("")
    def create():
        account_id = _customer_account_id(identity_service)
        payload = _json_payload()
        provider_type = _body_str_field(payload, "provider_type")
        if provider_type not in PRODUCT_CHANNEL_PROVIDER_TYPES:
            raise ChannelReachabilityError(
                "unsupported_product_channel",
                fact={
                    "type": "unsupported_product_channel",
                    "provider_type": provider_type,
                    "supported_provider_types": sorted(PRODUCT_CHANNEL_PROVIDER_TYPES),
                },
            )
        channel = reachability_service.create_channel(
            account_id=account_id,
            provider_type=provider_type,
            channel_identity_id=_body_str_field(payload, "channel_identity_id"),
            removable=_body_bool_field(payload, "removable"),
        )
        return jsonify(_channel_body(channel)), 201

    @blueprint.post("/<channel_id>/connect")
    def connect(channel_id: str):
        channel = reachability_service.connect_channel(
            account_id=_customer_account_id(identity_service),
            channel_id=_path_str_field(channel_id, "channel_id"),
        )
        return jsonify(_channel_body(channel))

    @blueprint.get("/<channel_id>/poll")
    def poll(channel_id: str):
        channel = reachability_service.poll_channel(
            account_id=_customer_account_id(identity_service),
            channel_id=_path_str_field(channel_id, "channel_id"),
        )
        return jsonify(_channel_body(channel))

    @blueprint.post("/<channel_id>/remove")
    def remove(channel_id: str):
        channel = reachability_service.remove_channel(
            account_id=_customer_account_id(identity_service),
            channel_id=_path_str_field(channel_id, "channel_id"),
        )
        return jsonify(_channel_body(channel))

    @blueprint.post("/<channel_id>/retry")
    def retry(channel_id: str):
        channel = reachability_service.retry_connection(
            account_id=_customer_account_id(identity_service),
            channel_id=_path_str_field(channel_id, "channel_id"),
        )
        return jsonify(_channel_body(channel))

    @blueprint.get("/resolve-route")
    def resolve_route():
        route = reachability_service.resolve_route(
            account_id=_customer_account_id(identity_service)
        )
        return jsonify(
            {
                "route_id": route.id,
                "account_id": route.account_id,
                "channel_id": route.channel_id,
                "provider_type": route.provider_type,
                "provider_address": route.provider_address,
                "route_key": route.route_key,
                "lifecycle": route.lifecycle,
            }
        )

    return blueprint


def _customer_account_id(identity_service) -> str:
    return require_customer_account_id(identity_service, ChannelReachabilityError)


def _channel_body(channel) -> dict:
    return {
        "channel_id": channel.id,
        "account_id": channel.account_id,
        "provider_type": channel.provider_type,
        "channel_identity_id": channel.channel_identity_id,
        "lifecycle": channel.lifecycle,
        "connection_state": channel.connection_state,
        "removable": channel.removable,
    }


def _status_body(status) -> dict:
    body = {
        "account_id": status.account_id,
        "channel_id": status.channel_id,
        "provider_type": status.provider_type,
        "connection_state": status.connection_state,
        "reachable": status.reachable,
    }
    instructions = getattr(status, "instructions", None)
    session_id = getattr(status, "session_id", None)
    qrcode_id = getattr(status, "qrcode_id", None)
    qrcode_image = getattr(status, "qrcode_image", None)
    connector_status = getattr(status, "connector_status", None)
    masked_identity = getattr(status, "masked_identity", None)
    if instructions is not None:
        body["instructions"] = instructions
    if session_id is not None:
        body["session_id"] = session_id
    if qrcode_id is not None:
        body["qrcode_id"] = qrcode_id
    if qrcode_image is not None:
        body["qrcode_image"] = qrcode_image
    if connector_status is not None:
        body["connector_status"] = connector_status
    if masked_identity is not None:
        body["masked_identity"] = masked_identity
    return body


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ChannelReachabilityError(
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
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    return payload[field]


def _body_bool_field(payload: dict, field: str) -> bool:
    value = _body_field(payload, field)
    if not isinstance(value, bool):
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "boolean_field_required",
            },
        )
    return value


def _body_str_field(payload: dict, field: str) -> str:
    value = _body_field(payload, field)
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise ChannelReachabilityError(
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
        raise ChannelReachabilityError(
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
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "required_field_missing",
            },
        )
    if value.strip() == "" or value != value.strip():
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
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


def _status_code(code: str) -> int:
    return 401 if code == "unauthorized" else 400
