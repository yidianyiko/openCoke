from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from uuid import UUID

import pytest

from coke.domains.channel_reachability.models import (
    ChannelReachabilityError,
    DeliveryAttemptResult,
    DeliveryRoute,
    NormalizedInbound,
)
from coke.domains.channel_reachability.repository import (
    InMemoryChannelReachabilityRepository,
)
from coke.domains.channel_reachability.service import ChannelReachabilityService
from coke.domains.identity_access.repository import InMemoryIdentityAccessRepository
from coke.domains.identity_access.service import IdentityAccessService
from coke.domains.social_scheduling.availability import ReminderAvailabilityPort
from coke.domains.social_scheduling.repository import InMemorySocialSchedulingRepository
from coke.domains.social_scheduling.service import SocialSchedulingService

NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


class RecordingAdapter:
    provider_type = "whatsapp_evolution"

    def __init__(self, status: str = "sent") -> None:
        self.status = status
        self.calls: list[tuple[str, str, str]] = []

    def normalize_inbound(self, payload):
        raise AssertionError("not used by these tests")

    def send_text(self, route, text, idempotency_key):
        self.calls.append((route.id, text, idempotency_key))
        if self.status == "failed":
            return DeliveryAttemptResult(
                status="failed",
                provider_message_id=None,
                error_code="provider_down",
                delivered_at=None,
            )
        return DeliveryAttemptResult(
            status="sent",
            provider_message_id=f"provider:{idempotency_key}",
            error_code=None,
            delivered_at=None,
        )


class PassiveAdapter(RecordingAdapter):
    def __init__(self, provider_type: str) -> None:
        super().__init__()
        self.provider_type = provider_type
        self.start_calls = []
        self.status_calls = []

    def start_login(self, *, account_id: str):
        self.start_calls.append({"account_id": account_id})
        return {
            "session_id": f"session-{account_id}",
            "qrcode_id": f"qr-{account_id}",
            "qrcode_image": f"data:image/png;base64,{account_id}",
            "status": "waiting_for_scan",
        }

    def poll_login_status(self, *, account_id: str, session_id: str):
        self.status_calls.append({"account_id": account_id, "session_id": session_id})
        return {
            "session_id": session_id,
            "status": "connected",
            "ilink_user_id": "wxid_lizihao",
        }


class FakeDeferredFriendLinkCompletion:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_pending_for_account(self, account_id: str) -> None:
        self.calls.append(account_id)


class IdentityReachability:
    def __init__(self, identity_access: IdentityAccessService) -> None:
        self.identity_access = identity_access

    def has_usable_channel(self, account_id: str) -> bool:
        return self.identity_access.repository.has_usable_channel(account_id)


class EmptyReminderAvailability(ReminderAvailabilityPort):
    def personal_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
        requester_timezone: str,
    ) -> list:
        return []


class DeferredFriendLinkAdapter:
    def __init__(
        self,
        identity_access: IdentityAccessService,
        social_scheduling: SocialSchedulingService,
    ) -> None:
        self.identity_access = identity_access
        self.social_scheduling = social_scheduling

    def complete_pending_for_account(self, account_id: str) -> None:
        for (
            friend_link_id
        ) in self.identity_access.consume_deferred_friend_link_continuations(
            account_id
        ):
            self.social_scheduling.complete_deferred_friend_link(
                joiner_account_id=account_id,
                friend_link_id=friend_link_id,
            )


@pytest.fixture
def identity_service() -> IdentityAccessService:
    return IdentityAccessService(
        repository=InMemoryIdentityAccessRepository(now=lambda: NOW),
        now=lambda: NOW,
        token_factory=sequence_factory("token"),
        id_factory=sequence_factory("id"),
        checkout_url_factory=lambda account_id: f"https://checkout.example/{account_id}",
    )


@pytest.fixture
def reachability(identity_service):
    adapter = RecordingAdapter()
    wechat_personal = PassiveAdapter("wechat_personal")
    wechat_ecloud = PassiveAdapter("wechat_ecloud")
    linq = PassiveAdapter("linq")
    service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={
            adapter.provider_type: adapter,
            wechat_personal.provider_type: wechat_personal,
            wechat_ecloud.provider_type: wechat_ecloud,
            linq.provider_type: linq,
        },
        now=lambda: NOW,
        id_factory=sequence_factory("channel"),
    )
    return service, adapter


def verified_web_account(identity_service):
    registered = identity_service.register_web_account("a@example.com", "hash_1")
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(registered.account.id)
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        pairing_code=pairing.code,
    )
    return registered.account, resolved.channel_identity


def messaging_first_account(identity_service):
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550999",
    )
    return resolved.account, resolved.channel_identity


def paired_identity(identity_service, account_id, provider_type, provider_subject):
    pairing = identity_service.issue_pairing_code(account_id)
    return identity_service.resolve_or_create_channel_identity(
        provider_type=provider_type,
        provider_subject=provider_subject,
        pairing_code=pairing.code,
    ).channel_identity


def test_default_channel_reachability_ids_are_schema_uuid_strings(identity_service):
    adapter = RecordingAdapter()
    service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={adapter.provider_type: adapter},
        now=lambda: NOW,
    )
    account, identity = verified_web_account(identity_service)

    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)
    route = service.resolve_route(account.id)
    attempt = service.send_text(account.id, "hello", "idem_uuid")

    for value in [channel.id, route.id, attempt.id]:
        assert UUID(value).hex == value


def test_single_active_channel_requires_remove_before_switch(
    identity_service, reachability
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    first = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )

    with pytest.raises(ChannelReachabilityError, match="active_channel_exists"):
        service.create_channel(
            account_id=account.id,
            provider_type="whatsapp_evolution",
            channel_identity_id=identity.id,
            removable=True,
        )

    removed = service.remove_channel(account_id=account.id, channel_id=first.id)
    second = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )

    assert removed.connection_state == "removed"
    assert removed.lifecycle == "removed"
    assert second.id != first.id
    assert service.get_status(account.id).channel_id == second.id


def test_connecting_is_not_reachable_and_connected_is_reachable(
    identity_service, reachability
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )
    connecting = service.connect_channel(account_id=account.id, channel_id=channel.id)

    assert connecting.connection_state == "connecting"
    assert service.get_status(account.id).reachable is False

    connected = service.mark_connected(account_id=account.id, channel_id=channel.id)

    assert connected.connection_state == "connected"
    assert service.get_status(account.id).reachable is True


def test_mark_connected_triggers_deferred_friend_link_self_completion(identity_service):
    account, identity = verified_web_account(identity_service)
    completion = FakeDeferredFriendLinkCompletion()
    service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={"whatsapp_evolution": RecordingAdapter()},
        deferred_friend_link_completion=completion,
        now=lambda: NOW,
        id_factory=sequence_factory("deferred"),
    )
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )

    service.mark_connected(account.id, channel.id)

    assert completion.calls == [account.id]


def test_deferred_friend_link_completion_is_idempotently_triggered_on_reconnect(
    identity_service,
):
    account, identity = verified_web_account(identity_service)
    completion = FakeDeferredFriendLinkCompletion()
    service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={"whatsapp_evolution": RecordingAdapter()},
        deferred_friend_link_completion=completion,
        now=lambda: NOW,
        id_factory=sequence_factory("deferred"),
    )
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )

    service.mark_connected(account.id, channel.id)
    service.mark_connected(account.id, channel.id)

    assert completion.calls == [account.id, account.id]


def test_inbound_channel_provisioning_triggers_deferred_friend_link_completion(
    identity_service,
):
    completion = FakeDeferredFriendLinkCompletion()
    service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={"whatsapp_evolution": RecordingAdapter()},
        deferred_friend_link_completion=completion,
        now=lambda: NOW,
        id_factory=sequence_factory("deferred"),
    )

    accepted = service.accept_provider_inbound(
        NormalizedInbound(
            provider_type="whatsapp_evolution",
            provider_subject="15555550123",
            text="hello",
            raw_event_id="wa_msg_first_contact",
            received_at=NOW,
        )
    )

    assert completion.calls == [accepted.account_id]


def test_claimed_friend_link_self_completes_when_joiner_connects_channel(
    identity_service,
):
    social_repository = InMemorySocialSchedulingRepository()
    social = SocialSchedulingService(
        repository=social_repository,
        reachability=IdentityReachability(identity_service),
        reminder_availability=EmptyReminderAvailability(),
        now=lambda: NOW,
        id_factory=sequence_factory("social"),
        token_factory=sequence_factory("social_token"),
        display_name_resolver=identity_service.get_display_name,
    )
    channel_service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={"whatsapp_evolution": RecordingAdapter()},
        deferred_friend_link_completion=DeferredFriendLinkAdapter(
            identity_service, social
        ),
        now=lambda: NOW,
        id_factory=sequence_factory("channel"),
    )
    owner, owner_identity = verified_web_account(identity_service)
    owner_channel = channel_service.create_channel(
        account_id=owner.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=owner_identity.id,
        removable=True,
    )
    channel_service.mark_connected(owner.id, owner_channel.id)
    link = social.get_or_create_friend_link(owner.id)
    joiner = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550999",
    )

    created = social.establish_friendship_from_token(
        joiner_account_id=joiner.account.id,
        public_token=link.public_token,
    )
    claim = identity_service.issue_web_claim_code(
        browser_session="browser_1",
        continuation=created.continuation,
    )
    identity_service.redeem_claim_code_from_channel(
        code=claim.code,
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550999",
    )
    identity_service.complete_web_claim_from_browser(
        code=claim.code,
        browser_session="browser_1",
    )
    joiner_channel = channel_service.create_channel(
        account_id=joiner.account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=joiner.channel_identity.id,
        removable=False,
    )

    channel_service.mark_connected(joiner.account.id, joiner_channel.id)
    channel_service.mark_connected(joiner.account.id, joiner_channel.id)

    assert created.status == "created"
    assert social_repository.list_active_friends(owner.id) == [joiner.account.id]
    assert len(social_repository.friendships_by_id) == 1
    assert (
        identity_service.consume_deferred_friend_link_continuations(joiner.account.id)
        == []
    )


def test_wechat_personal_connect_starts_ilink_login_and_status_stays_unconnected(
    identity_service, reachability
):
    registered = identity_service.register_web_account("wechat@example.com", "hash_1")
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    service, _adapter = reachability
    adapter = service.providers["wechat_personal"]

    pending = service.start_wechat_personal_connection(registered.account.id)
    status = service.get_status(registered.account.id)

    assert adapter.start_calls == [{"account_id": registered.account.id}]
    assert pending.account_id == registered.account.id
    assert pending.channel_id is None
    assert pending.provider_type == "wechat_personal"
    assert pending.connection_state == "connecting"
    assert pending.reachable is False
    assert pending.session_id == f"session-{registered.account.id}"
    assert pending.qrcode_id == f"qr-{registered.account.id}"
    assert pending.qrcode_image == f"data:image/png;base64,{registered.account.id}"
    assert pending.pairing_code is None
    assert status.connection_state == "not_connected"
    assert service.repository.list_channels(registered.account.id) == []


def test_wechat_personal_inbound_with_account_binding_connects_without_pairing(
    identity_service, reachability
):
    registered = identity_service.register_web_account("wxbind@example.com", "hash_1")
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    service, _adapter = reachability

    accepted = service.accept_provider_inbound(
        NormalizedInbound(
            provider_type="wechat_personal",
            provider_subject="wxid_lizihao",
            text="hello",
            raw_event_id="wx_msg_pairing",
            received_at=NOW,
            account_id=registered.account.id,
            connector_session_id="session-1",
            context_token="ctx-1",
        )
    )

    identity = identity_service.repository.get_channel_identity_by_provider(
        "wechat_personal",
        "wxid_lizihao",
    )
    channel = service.repository.get_active_channel(registered.account.id)
    assert identity is not None
    assert identity.account_id == registered.account.id
    assert channel is not None
    assert channel.channel_identity_id == identity.id
    assert channel.connection_state == "connected"
    assert accepted.account_id == registered.account.id
    assert accepted.channel_id == channel.id
    assert accepted.created_account is False


def test_messaging_first_first_contact_preserves_sender_display_name(
    identity_service, reachability
):
    service, _adapter = reachability

    accepted = service.accept_provider_inbound(
        NormalizedInbound(
            provider_type="whatsapp_evolution",
            provider_subject="15555550123",
            text="hello",
            raw_event_id="wa_msg_first_contact",
            received_at=NOW,
            sender_display_name="Alice Push",
        )
    )

    assert accepted.created_account is True
    assert identity_service.get_display_name(accepted.account_id) == "Alice Push"


def test_unpaired_wechat_personal_inbound_fails_closed_without_auto_provision(
    identity_service, reachability
):
    service, _adapter = reachability

    with pytest.raises(ChannelReachabilityError, match="identity_pairing_required"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="wechat_personal",
                provider_subject="wxid_unbound",
                text="hello",
                raw_event_id="wx_msg_unbound",
                received_at=NOW,
            )
        )

    assert (
        identity_service.repository.get_channel_identity_by_provider(
            "wechat_personal",
            "wxid_unbound",
        )
        is None
    )


def test_wechat_personal_inbound_pairing_code_fails_closed_without_session_account(
    identity_service, reachability
):
    registered = identity_service.register_web_account("wxpair@example.com", "hash_1")
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(registered.account.id)
    service, _adapter = reachability

    with pytest.raises(ChannelReachabilityError, match="identity_pairing_required"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="wechat_personal",
                provider_subject="wxid_pairing_attempt",
                text=pairing.code,
                raw_event_id="wx_msg_pairing_attempt",
                received_at=NOW,
                pairing_code=pairing.code,
            )
        )

    assert (
        identity_service.repository.get_channel_identity_by_provider(
            "wechat_personal",
            "wxid_pairing_attempt",
        )
        is None
    )


def test_revoked_access_blocks_existing_channel_completion_from_webhook(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )
    identity_service.set_access_state(
        account_id=account.id,
        email_verification_state="verified",
        subscription_state="inactive",
        suspension_state="active",
    )
    before_identities = dict(identity_service.repository.channel_identities_by_id)
    before_accounts = dict(identity_service.repository.accounts)

    with pytest.raises(ChannelReachabilityError, match="access_denied") as exc_info:
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="whatsapp_evolution",
                provider_subject="whatsapp:+15555550123",
                text="connection callback",
                raw_event_id="wa_msg_after_revocation",
                received_at=NOW,
            )
        )

    assert exc_info.value.fact == {
        "type": "account_access_denied",
        "account_id": account.id,
        "denial_reason": "subscription_inactive",
        "checkout_url": None,
    }
    saved = service.repository.get_channel(channel.id)
    assert saved.connection_state == "not_connected"
    assert service.repository.get_active_route_for_channel(channel.id) is None
    assert identity_service.repository.channel_identities_by_id == before_identities
    assert identity_service.repository.accounts == before_accounts
    assert service.get_status(account.id).reachable is False


def test_revoked_access_blocks_already_connected_channel_inbound(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=True,
    )
    service.mark_connected(account.id, channel.id)
    before_activation = identity_service.get_activation(account.id)
    identity_service.set_access_state(
        account_id=account.id,
        email_verification_state="verified",
        subscription_state="inactive",
        suspension_state="active",
    )

    with pytest.raises(ChannelReachabilityError, match="access_denied") as exc_info:
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="whatsapp_evolution",
                provider_subject="whatsapp:+15555550123",
                text="already connected callback",
                raw_event_id="wa_msg_connected_revoked",
                received_at=NOW,
            )
        )

    assert exc_info.value.fact == {
        "type": "account_access_denied",
        "account_id": account.id,
        "denial_reason": "subscription_inactive",
        "checkout_url": None,
    }
    assert service.get_status(account.id).reachable is True
    assert (
        identity_service.get_activation(account.id).first_inbound_received_at
        == before_activation.first_inbound_received_at
    )


def test_missing_account_access_error_maps_to_channel_error(
    identity_service,
    reachability,
):
    service, _adapter = reachability

    with pytest.raises(ChannelReachabilityError, match="account_not_found"):
        service.create_channel(
            account_id="missing_account",
            provider_type="whatsapp_evolution",
            channel_identity_id="missing_identity",
            removable=True,
        )

    assert service.repository.list_channels("missing_account") == []


def test_account_access_gate_blocks_channel_creation(identity_service):
    registered = identity_service.register_web_account("a@example.com", "hash_1")
    repository = InMemoryChannelReachabilityRepository()
    adapter = RecordingAdapter()
    service = ChannelReachabilityService(
        repository=repository,
        identity_access=identity_service,
        providers={adapter.provider_type: adapter},
        now=lambda: NOW,
        id_factory=sequence_factory("blocked"),
    )

    with pytest.raises(ChannelReachabilityError, match="access_denied") as exc_info:
        service.create_channel(
            account_id=registered.account.id,
            provider_type="whatsapp_evolution",
            channel_identity_id="channel_identity_missing",
            removable=True,
        )

    assert exc_info.value.fact == {
        "type": "account_access_denied",
        "account_id": registered.account.id,
        "denial_reason": "email_verification_required",
        "checkout_url": None,
    }
    assert repository.list_channels(registered.account.id) == []


def test_unsupported_provider_inbound_fails_before_identity_access_writes(
    identity_service,
    reachability,
):
    service, _adapter = reachability
    before_identities = dict(identity_service.repository.channel_identities_by_id)
    before_accounts = dict(identity_service.repository.accounts)

    with pytest.raises(ChannelReachabilityError, match="unsupported_provider"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="unknown_provider",
                provider_subject="unknown_subject",
                text="hello",
                raw_event_id="unknown_event_1",
                received_at=NOW,
            )
        )

    assert identity_service.repository.channel_identities_by_id == before_identities
    assert identity_service.repository.accounts == before_accounts


@pytest.mark.parametrize("provider_type", ["wechat_ecloud", "linq"])
def test_retained_non_product_adapters_cannot_be_connected_as_personal_channels(
    identity_service,
    reachability,
    provider_type,
):
    account, _identity = verified_web_account(identity_service)
    provider_subject = (
        "gewe_alice" if provider_type == "wechat_ecloud" else "+15555550125"
    )
    retained_identity = paired_identity(
        identity_service,
        account.id,
        provider_type,
        provider_subject,
    )
    service, _adapter = reachability

    with pytest.raises(ChannelReachabilityError, match="unsupported_product_channel"):
        service.create_channel(
            account_id=account.id,
            provider_type=provider_type,
            channel_identity_id=retained_identity.id,
            removable=True,
        )

    assert service.get_status(account.id).reachable is False
    assert service.repository.list_channels(account.id) == []


@pytest.mark.parametrize(
    ("provider_type", "provider_subject"),
    [
        ("wechat_ecloud", "gewe_alice"),
        ("linq", "+15555550125"),
    ],
)
def test_retained_non_product_inbound_cannot_auto_bind_personal_channel(
    identity_service,
    reachability,
    provider_type,
    provider_subject,
):
    service, _adapter = reachability
    before_identities = dict(identity_service.repository.channel_identities_by_id)
    before_accounts = dict(identity_service.repository.accounts)

    with pytest.raises(ChannelReachabilityError, match="unsupported_product_channel"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type=provider_type,
                provider_subject=provider_subject,
                text="hello",
                raw_event_id=f"{provider_type}_event_1",
                received_at=NOW,
            )
        )

    assert identity_service.repository.channel_identities_by_id == before_identities
    assert identity_service.repository.accounts == before_accounts
    assert service.repository.list_attempts() == []


def test_pairing_webhook_active_channel_conflict_does_not_consume_or_bind_identity(
    identity_service,
    reachability,
):
    account, first_identity = verified_web_account(identity_service)
    service, _adapter = reachability
    first = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=first_identity.id,
        removable=True,
    )
    pairing = identity_service.issue_pairing_code(account.id)

    with pytest.raises(ChannelReachabilityError, match="active_channel_exists"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="whatsapp_evolution",
                provider_subject="whatsapp:+15555550124",
                text="pairing callback",
                raw_event_id="wa_pair_conflict",
                received_at=NOW,
                pairing_code=pairing.code,
            )
        )

    assert service.repository.get_active_channel(account.id).id == first.id
    assert (
        identity_service.repository.get_artifact_by_code(pairing.code).consumed_at
        is None
    )
    assert (
        identity_service.repository.get_channel_identity_by_provider(
            "whatsapp_evolution",
            "whatsapp:+15555550124",
        )
        is None
    )


def test_non_removable_messaging_anchor_cannot_be_removed(
    identity_service, reachability
):
    account, identity = messaging_first_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account_id=account.id,
        provider_type="whatsapp_evolution",
        channel_identity_id=identity.id,
        removable=False,
    )

    with pytest.raises(
        ChannelReachabilityError, match="channel_identity_not_removable"
    ):
        service.remove_channel(account_id=account.id, channel_id=channel.id)

    assert service.get_status(account.id).channel_id == channel.id


def test_remove_missing_identity_maps_identity_error_to_channel_error(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    identity_service.repository.channel_identities_by_id.pop(identity.id)

    with pytest.raises(ChannelReachabilityError, match="channel_identity_not_found"):
        service.remove_channel(account_id=account.id, channel_id=channel.id)

    assert service.repository.get_channel(channel.id).lifecycle == "active"


def test_removable_web_first_channel_removal_keeps_account_and_stops_reachability(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account_id=account.id, channel_id=channel.id)

    removed = service.remove_channel(account_id=account.id, channel_id=channel.id)

    assert identity_service.repository.get_account(account.id) is not None
    assert removed.connection_state == "removed"
    assert service.get_status(account.id).reachable is False
    assert service.get_status(account.id).channel_id is None


def test_retry_from_failure_and_reconnection_required_returns_connecting(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )

    failed = service.mark_connection_failed(account.id, channel.id, "scan_expired")
    retrying = service.retry_connection(account.id, failed.id)
    required = service.mark_reconnection_required(
        account.id, retrying.id, "provider_session_lost"
    )
    retrying_again = service.retry_connection(account.id, required.id)

    assert failed.connection_state == "connection_failed"
    assert retrying.connection_state == "connecting"
    assert required.connection_state == "reconnection_required"
    assert retrying_again.connection_state == "connecting"


def test_reconnect_reuses_route_key_safely(identity_service, reachability):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)
    first_route = service.resolve_route(account.id)
    service.mark_reconnection_required(account.id, channel.id, "provider_session_lost")
    service.retry_connection(account.id, channel.id)
    service.mark_connected(account.id, channel.id)
    second_route = service.resolve_route(account.id)

    assert second_route.id == first_route.id
    assert second_route.route_key == first_route.route_key
    assert second_route.route_key.startswith("delivery-route:")
    assert len(second_route.route_key) <= 255
    assert "whatsapp:+15555550123" not in second_route.route_key
    assert service.get_status(account.id).reachable is True


def test_route_key_is_bounded_for_max_schema_provider_subject(
    identity_service, reachability
):
    registration = identity_service.register_web_account("long@example.com", "hash_1")
    identity_service.set_access_state(
        account_id=registration.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    provider_subject = "w" * 255
    identity = paired_identity(
        identity_service,
        registration.account.id,
        "whatsapp_evolution",
        provider_subject,
    )
    service, _adapter = reachability
    channel = service.create_channel(
        registration.account.id,
        "whatsapp_evolution",
        identity.id,
        removable=True,
    )

    service.mark_connected(registration.account.id, channel.id)
    route = service.resolve_route(registration.account.id)
    service.mark_reconnection_required(
        registration.account.id, channel.id, "provider_session_lost"
    )
    service.retry_connection(registration.account.id, channel.id)
    service.mark_connected(registration.account.id, channel.id)
    second_route = service.resolve_route(registration.account.id)

    assert len(route.route_key) <= 255
    assert route.route_key.startswith("delivery-route:")
    assert provider_subject not in route.route_key
    assert second_route.id == route.id
    assert second_route.route_key == route.route_key


def test_mark_connected_missing_activation_maps_error_without_connection_write(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    identity_service.repository.activations.pop(account.id)

    with pytest.raises(ChannelReachabilityError, match="activation_not_found"):
        service.mark_connected(account.id, channel.id)

    saved = service.repository.get_channel(channel.id)
    assert saved.connection_state == "not_connected"
    assert service.repository.get_active_route_for_channel(channel.id) is None
    assert account.id not in identity_service.repository.usable_channel_accounts


def test_mark_connected_does_not_save_connected_state_when_route_resolution_fails(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    identity_service.repository.channel_identities_by_id.pop(identity.id)

    with pytest.raises(ChannelReachabilityError, match="channel_identity_not_found"):
        service.mark_connected(account.id, channel.id)

    saved = service.repository.get_channel(channel.id)
    assert saved.connection_state == "not_connected"
    assert service.repository.get_active_route_for_channel(channel.id) is None
    assert service.get_status(account.id).reachable is False


def test_repository_refuses_to_reactivate_retired_route_key(
    identity_service, reachability
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)
    route = service.resolve_route(account.id)
    service.repository.retire_routes_for_channel(channel.id, retired_at=NOW)

    with pytest.raises(ValueError, match="retired_route_key"):
        service.repository.upsert_route(route)

    assert service.repository.get_route(route.id).lifecycle == "removed"


def test_repository_rejects_duplicate_route_id_for_different_route_key(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)
    route = service.resolve_route(account.id)
    duplicate_id_route = DeliveryRoute(
        id=route.id,
        account_id=account.id,
        channel_id=channel.id,
        provider_type="whatsapp_evolution",
        provider_address="whatsapp:+15555550124",
        route_key=f"{channel.id}:whatsapp_evolution:whatsapp:+15555550124",
        lifecycle="active",
        created_at=NOW,
        updated_at=NOW,
    )

    with pytest.raises(ValueError, match="duplicate_delivery_route_id"):
        service.repository.upsert_route(duplicate_id_route)

    assert service.repository.get_route(route.id).route_key == route.route_key


def test_repository_rejects_second_active_route_for_same_channel(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)
    existing = service.resolve_route(account.id)
    competing_route = DeliveryRoute(
        id="delivery_route_competing",
        account_id=account.id,
        channel_id=channel.id,
        provider_type="whatsapp_evolution",
        provider_address="whatsapp:+15555550124",
        route_key=f"{channel.id}:whatsapp_evolution:whatsapp:+15555550124",
        lifecycle="active",
        created_at=NOW,
        updated_at=NOW,
    )

    with pytest.raises(ValueError, match="duplicate_active_route_for_channel"):
        service.repository.upsert_route(competing_route)

    assert service.repository.get_active_route_for_channel(channel.id).id == existing.id


def test_repository_rejects_existing_route_key_reassigned_to_another_channel(
    identity_service,
    reachability,
):
    first_account, first_identity = verified_web_account(identity_service)
    second_registration = identity_service.register_web_account(
        "b@example.com", "hash_2"
    )
    identity_service.set_access_state(
        account_id=second_registration.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    second_identity = paired_identity(
        identity_service,
        second_registration.account.id,
        "whatsapp_evolution",
        "whatsapp:+15555550124",
    )
    service, _adapter = reachability
    first_channel = service.create_channel(
        first_account.id, "whatsapp_evolution", first_identity.id, removable=True
    )
    second_channel = service.create_channel(
        second_registration.account.id,
        "whatsapp_evolution",
        second_identity.id,
        removable=True,
    )
    service.mark_connected(first_account.id, first_channel.id)
    service.mark_connected(second_registration.account.id, second_channel.id)
    first_route = service.resolve_route(first_account.id)
    second_route = service.resolve_route(second_registration.account.id)
    reassigned_route = DeliveryRoute(
        id="delivery_route_reassigned",
        account_id=second_registration.account.id,
        channel_id=second_channel.id,
        provider_type=first_route.provider_type,
        provider_address=first_route.provider_address,
        route_key=first_route.route_key,
        lifecycle="active",
        created_at=NOW,
        updated_at=NOW,
    )

    with pytest.raises(ValueError, match="delivery_route_identity_mismatch"):
        service.repository.upsert_route(reassigned_route)

    assert service.repository.get_route(first_route.id).channel_id == first_channel.id
    assert (
        service.repository.get_active_route_for_channel(second_channel.id).id
        == second_route.id
    )


def test_remove_relink_same_address_retires_old_route_and_preserves_attempt_history(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    first = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, first.id)
    first_attempt = service.send_text(account.id, "first", "idem_original")
    first_route = service.repository.get_route(first_attempt.route_id)

    service.remove_channel(account.id, first.id)
    second = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, second.id)
    second_attempt = service.send_text(account.id, "second", "idem_second")
    retired_first_route = service.repository.get_route(first_attempt.route_id)
    second_route = service.repository.get_route(second_attempt.route_id)

    assert first_route.channel_id == first.id
    assert retired_first_route.id == first_route.id
    assert retired_first_route.lifecycle == "removed"
    assert retired_first_route.channel_id == first.id
    assert (
        service.repository.get_route(first_attempt.route_id).id
        == first_attempt.route_id
    )
    assert second_route.id != first_route.id
    assert second_route.lifecycle == "active"
    assert second_route.channel_id == second.id
    assert second_route.provider_address == first_route.provider_address


def test_send_resolves_current_connected_route_at_send_time(
    identity_service, reachability
):
    account, first_identity = verified_web_account(identity_service)
    service, _adapter = reachability
    first = service.create_channel(
        account.id, "whatsapp_evolution", first_identity.id, removable=True
    )
    service.mark_connected(account.id, first.id)
    first_attempt = service.send_text(account.id, "first", "idem_1")
    service.remove_channel(account.id, first.id)
    pairing = identity_service.issue_pairing_code(account.id)
    second_resolution = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550124",
        pairing_code=pairing.code,
    )
    second = service.create_channel(
        account.id,
        "whatsapp_evolution",
        second_resolution.channel_identity.id,
        removable=True,
    )
    service.mark_connected(account.id, second.id)
    second_attempt = service.send_text(account.id, "second", "idem_2")

    first_route = service.repository.get_route(first_attempt.route_id)
    second_route = service.repository.get_route(second_attempt.route_id)
    assert first_route.provider_address == "whatsapp:+15555550123"
    assert second_route.provider_address == "whatsapp:+15555550124"


def test_send_text_persists_delivery_envelope_diagnostics(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id,
        "whatsapp_evolution",
        identity.id,
        removable=True,
    )
    service.mark_connected(account.id, channel.id)

    attempt = service.send_text(
        account.id,
        "still working",
        "turn_1:waiting:1",
        turn_id="turn_1",
        message_id="message_1",
        delivery_source="waiting_timer",
        delivery_intent="turn_1:waiting:1",
        retry_attempt=1,
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        container="worker-1",
        context_token_source="latest_inbound_message",
        context_token_age_seconds=21,
    )

    assert attempt.delivery_source == "waiting_timer"
    assert attempt.delivery_intent == "turn_1:waiting:1"
    assert attempt.retry_attempt == 1
    assert attempt.traceparent == (
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    )
    assert attempt.container == "worker-1"
    assert attempt.context_token_source == "latest_inbound_message"
    assert attempt.context_token_age_seconds == 21
    assert isinstance(attempt.latency_ms, int)
    assert attempt.latency_ms >= 0


def test_provider_edge_idempotency_reuses_attempt_without_second_adapter_call(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)

    first = service.send_text(account.id, "hello", "idem_same")
    second = service.send_text(account.id, "hello again", "idem_same")

    assert second.id == first.id
    assert adapter.calls == [(first.route_id, "hello", "idem_same")]


def test_same_idempotency_key_after_route_switch_is_conflict_not_suppressed(
    identity_service,
    reachability,
):
    account, first_identity = verified_web_account(identity_service)
    service, adapter = reachability
    first = service.create_channel(
        account.id, "whatsapp_evolution", first_identity.id, removable=True
    )
    service.mark_connected(account.id, first.id)
    first_attempt = service.send_text(account.id, "first", "idem_conflict")
    service.remove_channel(account.id, first.id)
    pairing = identity_service.issue_pairing_code(account.id)
    second_identity = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550124",
        pairing_code=pairing.code,
    ).channel_identity
    second = service.create_channel(
        account.id, "whatsapp_evolution", second_identity.id, removable=True
    )
    service.mark_connected(account.id, second.id)

    with pytest.raises(
        ChannelReachabilityError, match="provider_idempotency_conflict"
    ) as exc_info:
        service.send_text(account.id, "second", "idem_conflict")

    assert exc_info.value.fact == {
        "type": "provider_idempotency_conflict",
        "provider_type": "whatsapp_evolution",
        "provider_idempotency_key": "idem_conflict",
        "existing_account_id": account.id,
        "current_account_id": account.id,
        "existing_route_id": first_attempt.route_id,
        "current_route_id": service.resolve_route(account.id).id,
    }
    assert adapter.calls == [(first_attempt.route_id, "first", "idem_conflict")]


def test_same_idempotency_key_for_different_account_is_conflict_not_suppressed(
    identity_service,
    reachability,
):
    first_account, first_identity = verified_web_account(identity_service)
    second_registration = identity_service.register_web_account(
        "b@example.com", "hash_2"
    )
    identity_service.set_access_state(
        account_id=second_registration.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    second_identity = paired_identity(
        identity_service,
        second_registration.account.id,
        "whatsapp_evolution",
        "whatsapp:+15555550126",
    )
    service, adapter = reachability
    first_channel = service.create_channel(
        first_account.id,
        "whatsapp_evolution",
        first_identity.id,
        removable=True,
    )
    second_channel = service.create_channel(
        second_registration.account.id,
        "whatsapp_evolution",
        second_identity.id,
        removable=True,
    )
    service.mark_connected(first_account.id, first_channel.id)
    service.mark_connected(second_registration.account.id, second_channel.id)
    first_attempt = service.send_text(first_account.id, "first", "idem_cross_account")

    with pytest.raises(
        ChannelReachabilityError, match="provider_idempotency_conflict"
    ) as exc_info:
        service.send_text(
            second_registration.account.id, "second", "idem_cross_account"
        )

    assert exc_info.value.fact == {
        "type": "provider_idempotency_conflict",
        "provider_type": "whatsapp_evolution",
        "provider_idempotency_key": "idem_cross_account",
        "existing_account_id": first_account.id,
        "current_account_id": second_registration.account.id,
        "existing_route_id": first_attempt.route_id,
        "current_route_id": service.resolve_route(second_registration.account.id).id,
    }
    assert adapter.calls == [(first_attempt.route_id, "first", "idem_cross_account")]


def test_failed_provider_send_is_never_delivered(identity_service):
    account, identity = verified_web_account(identity_service)
    adapter = RecordingAdapter(status="failed")
    service = ChannelReachabilityService(
        repository=InMemoryChannelReachabilityRepository(),
        identity_access=identity_service,
        providers={adapter.provider_type: adapter},
        now=lambda: NOW,
        id_factory=sequence_factory("failed"),
    )
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)

    attempt = service.send_text(account.id, "hello", "idem_failed")

    assert attempt.status == "failed"
    assert attempt.delivered_at is None
    assert attempt.provider_message_id is None
    assert attempt.error_code == "provider_down"


def test_absent_send_without_connected_channel_is_never_delivered(
    identity_service, reachability
):
    account, identity = verified_web_account(identity_service)
    service, adapter = reachability
    service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )

    with pytest.raises(ChannelReachabilityError, match="no_connected_channel"):
        service.send_text(account.id, "hello", "idem_absent")

    assert adapter.calls == []
    assert service.repository.list_attempts() == []


def test_invalid_pairing_code_maps_identity_error_to_channel_error(
    identity_service,
    reachability,
):
    service, _adapter = reachability

    with pytest.raises(ChannelReachabilityError, match="artifact_not_found"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="whatsapp_evolution",
                provider_subject="whatsapp:+15555550129",
                text="bad pairing",
                raw_event_id="wa_bad_pairing",
                received_at=NOW,
                pairing_code="missing_pairing_code",
            )
        )


def test_inbound_missing_activation_maps_identity_error_to_channel_error(
    identity_service,
    reachability,
):
    account, identity = verified_web_account(identity_service)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)
    identity_service.repository.activations.pop(account.id)

    with pytest.raises(ChannelReachabilityError, match="activation_not_found"):
        service.accept_provider_inbound(
            NormalizedInbound(
                provider_type="whatsapp_evolution",
                provider_subject="whatsapp:+15555550123",
                text="missing activation callback",
                raw_event_id="wa_missing_activation",
                received_at=NOW,
            )
        )

    assert service.repository.get_channel(channel.id).connection_state == "connected"


def test_channel_reachability_does_not_write_channel_identity(
    identity_service, reachability
):
    account, identity = verified_web_account(identity_service)
    before = dict(identity_service.repository.channel_identities_by_id)
    service, _adapter = reachability
    channel = service.create_channel(
        account.id, "whatsapp_evolution", identity.id, removable=True
    )
    service.mark_connected(account.id, channel.id)
    service.send_text(account.id, "hello", "idem_nowrite")
    service.remove_channel(account.id, channel.id)

    assert identity_service.repository.channel_identities_by_id == before
