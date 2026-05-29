from __future__ import annotations

from datetime import datetime
from typing import Protocol

from coke.domains.channel_reachability.models import (
    Channel,
    DeliveryAttempt,
    DeliveryRoute,
)


class ChannelReachabilityRepository(Protocol):
    def add_channel(self, channel: Channel) -> None: ...

    def save_channel(self, channel: Channel) -> None: ...

    def get_channel(self, channel_id: str) -> Channel | None: ...

    def get_active_channel(self, account_id: str) -> Channel | None: ...

    def list_channels(self, account_id: str) -> list[Channel]: ...

    def upsert_route(self, route: DeliveryRoute) -> DeliveryRoute: ...

    def get_route(self, route_id: str) -> DeliveryRoute | None: ...

    def get_active_route_for_channel(self, channel_id: str) -> DeliveryRoute | None: ...

    def retire_routes_for_channel(
        self, channel_id: str, retired_at: datetime
    ) -> None: ...

    def save_attempt(self, attempt: DeliveryAttempt) -> None: ...

    def get_attempt_by_provider_idempotency(
        self,
        provider_type: str,
        provider_idempotency_key: str,
    ) -> DeliveryAttempt | None: ...


class InMemoryChannelReachabilityRepository:
    def __init__(self) -> None:
        self.channels_by_id: dict[str, Channel] = {}
        self.routes_by_id: dict[str, DeliveryRoute] = {}
        self.routes_by_key: dict[str, DeliveryRoute] = {}
        self.attempts_by_id: dict[str, DeliveryAttempt] = {}
        self.attempts_by_provider_idempotency: dict[
            tuple[str, str], DeliveryAttempt
        ] = {}

    def add_channel(self, channel: Channel) -> None:
        if channel.id in self.channels_by_id:
            raise ValueError("duplicate_channel_id")
        if (
            channel.lifecycle == "active"
            and self.get_active_channel(channel.account_id) is not None
        ):
            raise ValueError("duplicate_active_channel")
        self.channels_by_id[channel.id] = channel

    def save_channel(self, channel: Channel) -> None:
        if channel.id not in self.channels_by_id:
            raise ValueError("channel_not_found")
        if channel.lifecycle == "active":
            active = self.get_active_channel(channel.account_id)
            if active is not None and active.id != channel.id:
                raise ValueError("duplicate_active_channel")
        self.channels_by_id[channel.id] = channel

    def get_channel(self, channel_id: str) -> Channel | None:
        return self.channels_by_id.get(channel_id)

    def get_active_channel(self, account_id: str) -> Channel | None:
        for channel in self.channels_by_id.values():
            if channel.account_id == account_id and channel.lifecycle == "active":
                return channel
        return None

    def list_channels(self, account_id: str) -> list[Channel]:
        return [
            channel
            for channel in self.channels_by_id.values()
            if channel.account_id == account_id
        ]

    def upsert_route(self, route: DeliveryRoute) -> DeliveryRoute:
        existing = self.routes_by_key.get(route.route_key)
        if existing is not None:
            if existing.lifecycle != "active":
                raise ValueError("retired_route_key")
            existing_by_id = self.routes_by_id.get(route.id)
            if existing_by_id is not None and existing_by_id.id != existing.id:
                raise ValueError("duplicate_delivery_route_id")
            updated = DeliveryRoute(
                id=existing.id,
                account_id=route.account_id,
                channel_id=route.channel_id,
                provider_type=route.provider_type,
                provider_address=route.provider_address,
                route_key=route.route_key,
                lifecycle="active",
                created_at=existing.created_at,
                updated_at=route.updated_at,
            )
            self.routes_by_id[updated.id] = updated
            self.routes_by_key[updated.route_key] = updated
            return updated
        if route.id in self.routes_by_id:
            raise ValueError("duplicate_delivery_route_id")
        active_for_channel = self.get_active_route_for_channel(route.channel_id)
        if active_for_channel is not None:
            raise ValueError("duplicate_active_route_for_channel")
        self.routes_by_id[route.id] = route
        self.routes_by_key[route.route_key] = route
        return route

    def get_route(self, route_id: str) -> DeliveryRoute | None:
        return self.routes_by_id.get(route_id)

    def get_active_route_for_channel(self, channel_id: str) -> DeliveryRoute | None:
        for route in self.routes_by_id.values():
            if route.channel_id == channel_id and route.lifecycle == "active":
                return route
        return None

    def retire_routes_for_channel(self, channel_id: str, retired_at: datetime) -> None:
        for route in list(self.routes_by_id.values()):
            if route.channel_id == channel_id and route.lifecycle == "active":
                retired = DeliveryRoute(
                    id=route.id,
                    account_id=route.account_id,
                    channel_id=route.channel_id,
                    provider_type=route.provider_type,
                    provider_address=route.provider_address,
                    route_key=route.route_key,
                    lifecycle="removed",
                    created_at=route.created_at,
                    updated_at=retired_at,
                )
                self.routes_by_id[retired.id] = retired
                self.routes_by_key[retired.route_key] = retired

    def save_attempt(self, attempt: DeliveryAttempt) -> None:
        key = (attempt.provider_type, attempt.provider_idempotency_key)
        if attempt.id in self.attempts_by_id:
            raise ValueError("duplicate_delivery_attempt_id")
        if key in self.attempts_by_provider_idempotency:
            raise ValueError("duplicate_provider_idempotency_key")
        self.attempts_by_id[attempt.id] = attempt
        self.attempts_by_provider_idempotency[key] = attempt

    def get_attempt_by_provider_idempotency(
        self,
        provider_type: str,
        provider_idempotency_key: str,
    ) -> DeliveryAttempt | None:
        return self.attempts_by_provider_idempotency.get(
            (provider_type, provider_idempotency_key)
        )

    def list_attempts(self) -> list[DeliveryAttempt]:
        return list(self.attempts_by_id.values())
