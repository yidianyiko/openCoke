from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
)


def create_channel_blueprint(reachability_service) -> Blueprint:
    blueprint = Blueprint("channels", __name__, url_prefix="/api/channels")

    @blueprint.errorhandler(ChannelReachabilityError)
    def handle_channel_error(error: ChannelReachabilityError):
        return jsonify(_error_body(error.code, error.fact)), 400

    @blueprint.get("/status")
    def status():
        result = reachability_service.get_status(
            account_id=_query_str_field("account_id")
        )
        return jsonify(
            {
                "account_id": result.account_id,
                "channel_id": result.channel_id,
                "provider_type": result.provider_type,
                "connection_state": result.connection_state,
                "reachable": result.reachable,
            }
        )

    @blueprint.post("")
    def create():
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
            account_id=_body_str_field(payload, "account_id"),
            provider_type=provider_type,
            channel_identity_id=_body_str_field(payload, "channel_identity_id"),
            removable=_body_bool_field(payload, "removable"),
        )
        return jsonify(_channel_body(channel)), 201

    @blueprint.post("/<channel_id>/connect")
    def connect(channel_id: str):
        payload = _json_payload()
        channel = reachability_service.connect_channel(
            account_id=_body_str_field(payload, "account_id"),
            channel_id=channel_id,
        )
        return jsonify(_channel_body(channel))

    @blueprint.get("/<channel_id>/poll")
    def poll(channel_id: str):
        channel = reachability_service.poll_channel(
            account_id=_query_str_field("account_id"),
            channel_id=channel_id,
        )
        return jsonify(_channel_body(channel))

    @blueprint.post("/<channel_id>/remove")
    def remove(channel_id: str):
        payload = _json_payload()
        channel = reachability_service.remove_channel(
            account_id=_body_str_field(payload, "account_id"),
            channel_id=channel_id,
        )
        return jsonify(_channel_body(channel))

    @blueprint.post("/<channel_id>/retry")
    def retry(channel_id: str):
        payload = _json_payload()
        channel = reachability_service.retry_connection(
            account_id=_body_str_field(payload, "account_id"),
            channel_id=channel_id,
        )
        return jsonify(_channel_body(channel))

    @blueprint.get("/resolve-route")
    def resolve_route():
        route = reachability_service.resolve_route(
            account_id=_query_str_field("account_id")
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
    if not isinstance(value, str) or value.strip() == "":
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value.strip()


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
    if value.strip() == "":
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "query",
                "field": field,
                "reason": "string_field_required",
            },
        )
    return value.strip()


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body
