from __future__ import annotations

from collections.abc import Callable

from flask import Blueprint, jsonify, request

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
)
from coke.infra.tracing import ensure_traceparent


def create_provider_webhook_blueprint(
    reachability_service,
    providers,
    *,
    conversation_runtime_service=None,
    commit_callback: Callable[[], None] | None = None,
) -> Blueprint:
    blueprint = Blueprint("provider_webhooks", __name__)

    @blueprint.errorhandler(ChannelReachabilityError)
    def handle_channel_error(error: ChannelReachabilityError):
        return jsonify(_error_body(error.code, error.fact)), 400

    @blueprint.post("/webhooks/whatsapp/evolution")
    def whatsapp_evolution_inbound():
        return _handle_inbound("whatsapp_evolution")

    @blueprint.post("/webhooks/wechat/personal")
    def wechat_personal_inbound():
        return _handle_inbound("wechat_personal")

    @blueprint.post("/webhooks/wechat/ecloud")
    def wechat_ecloud_inbound():
        return _handle_inbound("wechat_ecloud")

    @blueprint.post("/webhooks/linq")
    def linq_inbound():
        return _handle_inbound("linq")

    def _handle_inbound(provider_type: str):
        adapter = providers.get(provider_type)
        if adapter is None:
            raise ChannelReachabilityError("unsupported_provider")
        if provider_type not in PRODUCT_CHANNEL_PROVIDER_TYPES:
            raise ChannelReachabilityError(
                "unsupported_product_channel",
                fact={
                    "type": "unsupported_product_channel",
                    "provider_type": provider_type,
                    "supported_provider_types": sorted(PRODUCT_CHANNEL_PROVIDER_TYPES),
                },
            )
        inbound_event = adapter.normalize_inbound(_json_payload())
        accepted = reachability_service.accept_provider_inbound(inbound_event)
        if conversation_runtime_service is not None:
            conversation_runtime_service.record_inbound(
                account_id=accepted.account_id,
                channel_identity_id=accepted.channel_identity_id,
                causal_inbound_event_id=accepted.raw_event_id,
                text=inbound_event.text,
                payload=dict(inbound_event.payload or {}),
                traceparent=_request_traceparent(),
            )
            if commit_callback is not None:
                commit_callback()
        return (
            jsonify(
                {
                    "accepted": accepted.accepted,
                    "provider_type": accepted.provider_type,
                    "provider_subject": accepted.provider_subject,
                    "account_id": accepted.account_id,
                    "channel_identity_id": accepted.channel_identity_id,
                    "channel_id": accepted.channel_id,
                    "created_account": accepted.created_account,
                    "raw_event_id": accepted.raw_event_id,
                }
            ),
            202,
        )

    return blueprint


def _request_traceparent() -> str:
    try:
        return ensure_traceparent(request.headers.get("traceparent"))
    except ValueError as error:
        raise ChannelReachabilityError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "location": "traceparent",
                "reason": "invalid_traceparent",
            },
        ) from error


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


def _error_body(code: str, fact: dict | None = None) -> dict:
    body = {"error": {"code": code}}
    if fact is not None:
        body["error"]["fact"] = fact
    return body
