from __future__ import annotations

import hmac
from collections.abc import Callable

from flask import Blueprint, current_app, jsonify, request

from coke.domains.channel_reachability.models import (
    PRODUCT_CHANNEL_PROVIDER_TYPES,
    ChannelReachabilityError,
)
from coke.domains.conversation_runtime.models import ConversationRuntimeError
from coke.infra.tracing import ensure_traceparent

# Provider webhooks are at-least-once: a connector may re-deliver an inbound
# event it already delivered. When the inbound was already recorded and
# enqueued, recording it again collides on the `inbound:<event_id>` outbox
# idempotency key. That is an idempotent replay, not a fault — acknowledge it so
# the connector stops re-delivering instead of looping on a 500 forever.
_IDEMPOTENT_INBOUND_REPLAY_CODES = frozenset({"duplicate_outbox_idempotency_key"})


def create_provider_webhook_blueprint(
    reachability_service,
    providers,
    *,
    conversation_runtime_service=None,
    reminder_service=None,
    social_scheduling_service=None,
    commit_callback: Callable[[], None] | None = None,
    webhook_secret: str | None = None,
) -> Blueprint:
    blueprint = Blueprint("provider_webhooks", __name__)

    @blueprint.errorhandler(ChannelReachabilityError)
    def handle_channel_error(error: ChannelReachabilityError):
        return jsonify(_error_body(error.code, error.fact)), _status_code(error.code)

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
        _require_webhook_secret(webhook_secret)
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
            try:
                conversation_runtime_service.record_inbound(
                    account_id=accepted.account_id,
                    channel_identity_id=accepted.channel_identity_id,
                    causal_inbound_event_id=accepted.raw_event_id,
                    text=inbound_event.text,
                    payload=dict(inbound_event.payload or {}),
                    traceparent=_request_traceparent(),
                    media=inbound_event.media,
                )
            except ConversationRuntimeError as error:
                if error.code not in _IDEMPOTENT_INBOUND_REPLAY_CODES:
                    raise
                # Idempotent re-delivery: the event is already recorded and
                # enqueued. Fall through to acknowledge it as accepted.
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


def _require_webhook_secret(webhook_secret: str | None) -> None:
    expected = _configured_webhook_secret(webhook_secret)
    if expected is None:
        return
    for presented in _presented_webhook_secrets():
        if hmac.compare_digest(presented, expected):
            return
    raise ChannelReachabilityError("webhook_unauthorized")


def _configured_webhook_secret(webhook_secret: str | None) -> str | None:
    if webhook_secret is not None:
        stripped = webhook_secret.strip()
        return stripped or None
    settings = current_app.config.get("COKE_SETTINGS")
    value = getattr(settings, "webhook_inbound_secret", None)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _presented_webhook_secrets() -> list[str]:
    values: list[str] = []
    for header in (
        "X-Coke-Webhook-Secret",
        "X-Webhook-Secret",
        "X-Webhook-Token",
        "X-Evolution-Webhook-Secret",
    ):
        value = request.headers.get(header)
        if value:
            values.append(value.strip())
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        values.append(authorization.removeprefix("Bearer ").strip())
    return [value for value in values if value]


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


def _status_code(code: str) -> int:
    return 401 if code in {"unauthorized", "webhook_unauthorized"} else 400
