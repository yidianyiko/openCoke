from __future__ import annotations

from dataclasses import replace

import pytest

from coke.domains.channel_reachability.models import (
    Channel,
    DeliveryAttempt,
    DeliveryRoute,
)
from coke.domains.channel_reachability.repository import (
    InMemoryChannelReachabilityRepository,
    PostgresChannelReachabilityRepository,
)

from .conftest import ACCOUNT_A, CHANNEL_A, CHANNEL_IDENTITY_A, NOW, seed_channel_identity


def _channel(channel_id: str = CHANNEL_A) -> Channel:
    return Channel(
        channel_id,
        ACCOUNT_A,
        CHANNEL_IDENTITY_A,
        "whatsapp_evolution",
        "active",
        "connected",
        True,
        NOW,
        None,
        NOW,
        NOW,
    )


def _route(route_id: str = "21000000000000000000000000000001") -> DeliveryRoute:
    return DeliveryRoute(
        route_id,
        ACCOUNT_A,
        CHANNEL_A,
        "whatsapp_evolution",
        "whatsapp:+15555550123",
        "route:channel-a",
        "active",
        NOW,
        NOW,
    )


def _attempt(attempt_id: str = "22000000000000000000000000000001") -> DeliveryAttempt:
    return DeliveryAttempt(
        id=attempt_id,
        route_id="21000000000000000000000000000001",
        provider_type="whatsapp_evolution",
        provider_idempotency_key="provider-key-1",
        status="sent",
        provider_message_id="provider-message-1",
        error_code=None,
        attempted_at=NOW,
        delivered_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture(params=["memory", "postgres"])
def repository(request, postgres_session):
    if request.param == "memory":
        return InMemoryChannelReachabilityRepository()
    seed_channel_identity(postgres_session)
    return PostgresChannelReachabilityRepository(postgres_session)


def test_channel_route_and_attempt_round_trip(repository) -> None:
    channel = _channel()
    repository.add_channel(channel)
    route = repository.upsert_route(_route())
    attempt = _attempt()
    repository.save_attempt(attempt)

    assert repository.get_channel(channel.id) == channel
    assert repository.get_active_channel(ACCOUNT_A) == channel
    assert repository.list_channels(ACCOUNT_A) == [channel]
    assert repository.get_route(route.id) == route
    assert repository.get_active_route_for_channel(channel.id) == route
    assert (
        repository.get_attempt_by_provider_idempotency(
            "whatsapp_evolution", "provider-key-1"
        )
        == attempt
    )


def test_channel_invariants_match_in_memory(repository) -> None:
    repository.add_channel(_channel())

    with pytest.raises(ValueError, match="duplicate_active_channel"):
        repository.add_channel(
            replace(_channel(), id="20000000000000000000000000000002")
        )

    route = repository.upsert_route(_route())
    assert repository.upsert_route(replace(route, updated_at=NOW)) == route

    with pytest.raises(ValueError, match="delivery_route_identity_mismatch"):
        repository.upsert_route(
            replace(
                _route("21000000000000000000000000000002"),
                provider_address="whatsapp:+15555550999",
            )
        )

    repository.save_attempt(_attempt())
    with pytest.raises(ValueError, match="duplicate_provider_idempotency_key"):
        repository.save_attempt(_attempt("22000000000000000000000000000002"))


def test_retire_routes_for_channel(repository) -> None:
    repository.add_channel(_channel())
    route = repository.upsert_route(_route())

    repository.retire_routes_for_channel(CHANNEL_A, retired_at=NOW)

    retired = repository.get_route(route.id)
    assert retired.lifecycle == "removed"
    assert repository.get_active_route_for_channel(CHANNEL_A) is None
