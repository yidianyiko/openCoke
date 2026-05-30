from __future__ import annotations

from datetime import UTC, datetime
from itertools import count

from coke.domains.channel_reachability.models import (
    DeliveryAttemptResult,
    NormalizedInbound,
)
from coke.domains.channel_reachability.repository import (
    InMemoryChannelReachabilityRepository,
)
from coke.domains.channel_reachability.service import ChannelReachabilityService
from coke.domains.identity_access.repository import InMemoryIdentityAccessRepository
from coke.domains.identity_access.service import IdentityAccessService
from coke.composition import ChannelReachabilityOutboundDelivery
from coke.turn.runner import DeliveryRequest

NOW = datetime(2026, 5, 30, 9, 0, tzinfo=UTC)


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


class IlinkAdapter:
    provider_type = "wechat_personal"

    def __init__(self) -> None:
        self.start_calls = []
        self.status_calls = []
        self.send_calls = []

    def start_login(self, *, account_id: str):
        self.start_calls.append({"account_id": account_id})
        return {
            "session_id": f"session-{account_id}",
            "qrcode_id": f"qr-{account_id}",
            "qrcode_image": f"raw-qr-image-{account_id}",
            "qrcode_image_data_url": f"data:image/png;base64,{account_id}",
            "status": "waiting_for_scan",
        }

    def poll_login_status(self, *, account_id: str, session_id: str):
        self.status_calls.append({"account_id": account_id, "session_id": session_id})
        return {
            "session_id": session_id,
            "status": "connected",
            "ilink_user_id": "wxid_alice",
        }

    def normalize_inbound(self, payload):
        return NormalizedInbound(
            provider_type="wechat_personal",
            provider_subject=payload["wxid"],
            text=payload["text"],
            raw_event_id=payload["message_id"],
            received_at=NOW,
            account_id=payload["account_id"],
            connector_session_id=payload["session_id"],
            context_token=payload["context_token"],
            payload=payload,
        )

    def send_text(self, route, text, idempotency_key, context_token=None):
        self.send_calls.append(
            {
                "account_id": route.account_id,
                "to": route.provider_address,
                "text": text,
                "idempotency_key": idempotency_key,
                "context_token": context_token,
            }
        )
        return DeliveryAttemptResult(
            status="sent",
            provider_message_id="sent-1",
            error_code=None,
            delivered_at=None,
        )


def make_services():
    identity = IdentityAccessService(
        repository=InMemoryIdentityAccessRepository(now=lambda: NOW),
        now=lambda: NOW,
        token_factory=sequence_factory("token"),
        id_factory=sequence_factory("id"),
    )
    registered = identity.register_web_account("alice@example.com", "hash_1")
    identity.set_access_state(
        registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    adapter = IlinkAdapter()
    reachability = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity,
        providers={"wechat_personal": adapter},
        now=lambda: NOW,
        id_factory=sequence_factory("channel"),
    )
    return identity, reachability, adapter, registered.account.id


def test_wechat_personal_connect_starts_per_account_ilink_login():
    _identity, reachability, adapter, account_id = make_services()

    status = reachability.start_wechat_personal_connection(account_id)

    assert adapter.start_calls == [{"account_id": account_id}]
    assert status.account_id == account_id
    assert status.provider_type == "wechat_personal"
    assert status.connection_state == "connecting"
    assert status.session_id == f"session-{account_id}"
    assert status.qrcode_id == f"qr-{account_id}"
    assert status.qrcode_image == f"data:image/png;base64,{account_id}"
    assert status.pairing_code is None


def test_wechat_personal_status_confirmation_binds_wxid_to_account_and_connects():
    identity, reachability, adapter, account_id = make_services()
    pending = reachability.start_wechat_personal_connection(account_id)

    status = reachability.poll_wechat_personal_login(
        account_id=account_id,
        session_id=pending.session_id,
    )

    assert adapter.status_calls == [
        {"account_id": account_id, "session_id": pending.session_id}
    ]
    channel = reachability.repository.get_active_channel(account_id)
    identity_row = identity.repository.get_channel_identity_by_provider(
        "wechat_personal",
        "wxid_alice",
    )
    assert status.connection_state == "connected"
    assert status.reachable is True
    assert identity_row is not None
    assert channel is not None
    assert channel.channel_identity_id == identity_row.id


def test_account_bound_wechat_webhook_binds_without_pairing_and_preserves_context():
    identity, reachability, adapter, account_id = make_services()
    inbound = adapter.normalize_inbound(
        {
            "account_id": account_id,
            "session_id": "session-1",
            "message_id": "wx_msg_1",
            "wxid": "wxid_alice",
            "text": "hello",
            "context_token": "ctx-1",
        }
    )

    accepted = reachability.accept_provider_inbound(inbound)

    identity_row = identity.repository.get_channel_identity_by_provider(
        "wechat_personal",
        "wxid_alice",
    )
    assert identity_row is not None
    assert identity_row.account_id == account_id
    assert accepted.account_id == account_id
    assert accepted.provider_subject == "wxid_alice"


def test_wechat_personal_outbound_uses_context_token():
    _identity, reachability, adapter, account_id = make_services()
    pending = reachability.start_wechat_personal_connection(account_id)
    reachability.poll_wechat_personal_login(account_id, pending.session_id)

    attempt = reachability.send_text(
        account_id,
        "hello back",
        "idem-1",
        context_token="ctx-1",
    )

    assert attempt.status == "sent"
    assert adapter.send_calls == [
        {
            "account_id": account_id,
            "to": "wxid_alice",
            "text": "hello back",
            "idempotency_key": "idem-1",
            "context_token": "ctx-1",
        }
    ]


def test_outbound_delivery_uses_request_context_token_before_latest_fallback():
    conversation = type(
        "ConversationContext",
        (),
        {"latest_context_token": lambda self, conversation_id: "ctx-latest"},
    )()
    _identity, reachability, adapter, account_id = make_services()
    pending = reachability.start_wechat_personal_connection(account_id)
    reachability.poll_wechat_personal_login(account_id, pending.session_id)
    delivery = ChannelReachabilityOutboundDelivery(
        reachability,
        conversation_runtime=conversation,
    )

    delivery.deliver(
        DeliveryRequest(
            account_id=account_id,
            conversation_id="conversation_1",
            turn_id="turn_1",
            message_type="reply",
            visible_text="hello back",
            idempotency_key="idem-reply-1",
            context_token="ctx-trigger",
        )
    )

    assert adapter.send_calls[-1] == {
        "account_id": account_id,
        "to": "wxid_alice",
        "text": "hello back",
        "idempotency_key": "idem-reply-1",
        "context_token": "ctx-trigger",
    }


def test_outbound_delivery_uses_latest_context_token_for_render_without_trigger_token():
    conversation = type(
        "ConversationContext",
        (),
        {"latest_context_token": lambda self, conversation_id: "ctx-latest"},
    )()
    _identity, reachability, adapter, account_id = make_services()
    pending = reachability.start_wechat_personal_connection(account_id)
    reachability.poll_wechat_personal_login(account_id, pending.session_id)
    delivery = ChannelReachabilityOutboundDelivery(
        reachability,
        conversation_runtime=conversation,
    )

    delivery.deliver(
        DeliveryRequest(
            account_id=account_id,
            conversation_id="conversation_1",
            turn_id="turn_1",
            message_type="notification",
            visible_text="nightly summary",
            idempotency_key="idem-render-1",
        )
    )

    assert adapter.send_calls[-1]["context_token"] == "ctx-latest"
