from __future__ import annotations

from datetime import UTC, datetime
from itertools import count

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
    assert second_route.route_key == (
        f"{channel.id}:whatsapp_evolution:whatsapp:+15555550123"
    )
    assert service.get_status(account.id).reachable is True


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
