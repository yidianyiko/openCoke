from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from coke import schema
from coke.domains._pg import db_id, insert_row, many, one_or_none, update_row
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
            if (
                route.account_id != existing.account_id
                or route.channel_id != existing.channel_id
                or route.provider_type != existing.provider_type
                or route.provider_address != existing.provider_address
            ):
                raise ValueError("delivery_route_identity_mismatch")
            updated = DeliveryRoute(
                id=existing.id,
                account_id=existing.account_id,
                channel_id=existing.channel_id,
                provider_type=existing.provider_type,
                provider_address=existing.provider_address,
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
            if _same_route_identity(route, active_for_channel):
                updated = DeliveryRoute(
                    id=active_for_channel.id,
                    account_id=active_for_channel.account_id,
                    channel_id=active_for_channel.channel_id,
                    provider_type=active_for_channel.provider_type,
                    provider_address=active_for_channel.provider_address,
                    route_key=route.route_key,
                    lifecycle="active",
                    created_at=active_for_channel.created_at,
                    updated_at=route.updated_at,
                )
                self.routes_by_key.pop(active_for_channel.route_key, None)
                self.routes_by_id[updated.id] = updated
                self.routes_by_key[updated.route_key] = updated
                return updated
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


class PostgresChannelReachabilityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_channel(self, channel: Channel) -> None:
        insert_row(
            self.session,
            schema.channel,
            _channel_values(channel),
            {
                "pk_channel": "duplicate_channel_id",
                "uq_channel_one_active_per_account": "duplicate_active_channel",
            },
            default_error="duplicate_active_channel",
        )

    def save_channel(self, channel: Channel) -> None:
        if self.get_channel(channel.id) is None:
            raise ValueError("channel_not_found")
        if (
            update_row(
                self.session,
                schema.channel,
                _channel_values(channel),
                {"uq_channel_one_active_per_account": "duplicate_active_channel"},
                default_error="duplicate_active_channel",
            )
            == 0
        ):
            raise ValueError("channel_not_found")

    def get_channel(self, channel_id: str) -> Channel | None:
        row = one_or_none(
            self.session, schema.channel, schema.channel.c.id == channel_id
        )
        return _channel(row) if row else None

    def get_active_channel(self, account_id: str) -> Channel | None:
        row = one_or_none(
            self.session,
            schema.channel,
            schema.channel.c.account_id == account_id,
            schema.channel.c.lifecycle == "active",
        )
        return _channel(row) if row else None

    def list_channels(self, account_id: str) -> list[Channel]:
        return [
            _channel(row)
            for row in many(
                self.session,
                schema.channel,
                schema.channel.c.account_id == account_id,
                order_by=(schema.channel.c.created_at, schema.channel.c.id),
            )
        ]

    def upsert_route(self, route: DeliveryRoute) -> DeliveryRoute:
        existing = self._get_route_by_key(route.route_key)
        if existing is not None:
            if existing.lifecycle != "active":
                raise ValueError("retired_route_key")
            existing_by_id = self.get_route(route.id)
            if existing_by_id is not None and existing_by_id.id != existing.id:
                raise ValueError("duplicate_delivery_route_id")
            if (
                route.account_id != existing.account_id
                or route.channel_id != existing.channel_id
                or route.provider_type != existing.provider_type
                or route.provider_address != existing.provider_address
            ):
                raise ValueError("delivery_route_identity_mismatch")
            updated = replace(existing, updated_at=route.updated_at)
            self._save_route(updated)
            return updated
        if self.get_route(route.id) is not None:
            raise ValueError("duplicate_delivery_route_id")
        active = self.get_active_route_for_channel(route.channel_id)
        if active is not None:
            if _same_route_identity(route, active):
                updated = replace(
                    active, route_key=route.route_key, updated_at=route.updated_at
                )
                self._save_route(updated)
                return updated
            raise ValueError("duplicate_active_route_for_channel")
        insert_row(
            self.session,
            schema.delivery_route,
            _route_values(route),
            {
                "pk_delivery_route": "duplicate_delivery_route_id",
                "uq_delivery_route_route_key": "retired_route_key",
            },
            default_error="retired_route_key",
        )
        return route

    def get_route(self, route_id: str) -> DeliveryRoute | None:
        row = one_or_none(
            self.session, schema.delivery_route, schema.delivery_route.c.id == route_id
        )
        return _route(row) if row else None

    def get_active_route_for_channel(self, channel_id: str) -> DeliveryRoute | None:
        row = one_or_none(
            self.session,
            schema.delivery_route,
            schema.delivery_route.c.channel_id == channel_id,
            schema.delivery_route.c.lifecycle == "active",
        )
        return _route(row) if row else None

    def retire_routes_for_channel(self, channel_id: str, retired_at: datetime) -> None:
        self.session.execute(
            schema.delivery_route.update()
            .where(
                schema.delivery_route.c.channel_id == channel_id,
                schema.delivery_route.c.lifecycle == "active",
            )
            .values(lifecycle="removed", updated_at=retired_at)
        )

    def save_attempt(self, attempt: DeliveryAttempt) -> None:
        insert_row(
            self.session,
            schema.delivery_attempt,
            _attempt_values(attempt),
            {
                "pk_delivery_attempt": "duplicate_delivery_attempt_id",
                "uq_delivery_attempt_provider_idempotency": "duplicate_provider_idempotency_key",
            },
            default_error="duplicate_provider_idempotency_key",
        )

    def get_attempt_by_provider_idempotency(
        self,
        provider_type: str,
        provider_idempotency_key: str,
    ) -> DeliveryAttempt | None:
        row = one_or_none(
            self.session,
            schema.delivery_attempt,
            schema.delivery_attempt.c.provider_type == provider_type,
            schema.delivery_attempt.c.provider_idempotency_key
            == provider_idempotency_key,
        )
        return _attempt(row) if row else None

    def list_attempts(self) -> list[DeliveryAttempt]:
        return [
            _attempt(row)
            for row in many(
                self.session,
                schema.delivery_attempt,
                order_by=(
                    schema.delivery_attempt.c.attempted_at,
                    schema.delivery_attempt.c.id,
                ),
            )
        ]

    def _get_route_by_key(self, route_key: str) -> DeliveryRoute | None:
        row = one_or_none(
            self.session,
            schema.delivery_route,
            schema.delivery_route.c.route_key == route_key,
        )
        return _route(row) if row else None

    def _save_route(self, route: DeliveryRoute) -> None:
        update_row(
            self.session,
            schema.delivery_route,
            _route_values(route),
            {"uq_delivery_route_route_key": "retired_route_key"},
            default_error="retired_route_key",
        )


def _channel_values(channel: Channel) -> dict:
    return {
        "id": channel.id,
        "account_id": channel.account_id,
        "channel_identity_id": channel.channel_identity_id,
        "provider_type": channel.provider_type,
        "lifecycle": channel.lifecycle,
        "connection_state": channel.connection_state,
        "removable": channel.removable,
        "connected_at": channel.connected_at,
        "removed_at": channel.removed_at,
        "created_at": channel.created_at,
        "updated_at": channel.updated_at,
    }


def _channel(row: Mapping) -> Channel:
    return Channel(
        db_id(row["id"]),
        db_id(row["account_id"]),
        db_id(row["channel_identity_id"]),
        row["provider_type"],
        row["lifecycle"],
        row["connection_state"],
        row["removable"],
        row["connected_at"],
        row["removed_at"],
        row["created_at"],
        row["updated_at"],
    )


def _route_values(route: DeliveryRoute) -> dict:
    return {
        "id": route.id,
        "account_id": route.account_id,
        "channel_id": route.channel_id,
        "provider_type": route.provider_type,
        "provider_address": route.provider_address,
        "route_key": route.route_key,
        "lifecycle": route.lifecycle,
        "created_at": route.created_at,
        "updated_at": route.updated_at,
    }


def _route(row: Mapping) -> DeliveryRoute:
    return DeliveryRoute(
        db_id(row["id"]),
        db_id(row["account_id"]),
        db_id(row["channel_id"]),
        row["provider_type"],
        row["provider_address"],
        row["route_key"],
        row["lifecycle"],
        row["created_at"],
        row["updated_at"],
    )


def _same_route_identity(left: DeliveryRoute, right: DeliveryRoute) -> bool:
    return (
        _same_identifier(left.account_id, right.account_id)
        and _same_identifier(left.channel_id, right.channel_id)
        and left.provider_type == right.provider_type
        and left.provider_address == right.provider_address
    )


def _same_identifier(left: str, right: str) -> bool:
    try:
        return UUID(str(left)).hex == UUID(str(right)).hex
    except ValueError:
        return str(left) == str(right)


def _attempt_values(attempt: DeliveryAttempt) -> dict:
    return {
        "id": attempt.id,
        "route_id": attempt.route_id,
        "turn_id": attempt.turn_id,
        "message_id": attempt.message_id,
        "provider_type": attempt.provider_type,
        "provider_message_id": attempt.provider_message_id,
        "provider_idempotency_key": attempt.provider_idempotency_key,
        "status": attempt.status,
        "error_code": attempt.error_code,
        "delivery_source": attempt.delivery_source,
        "delivery_intent": attempt.delivery_intent,
        "retry_attempt": attempt.retry_attempt,
        "traceparent": attempt.traceparent,
        "container": attempt.container,
        "context_token_source": attempt.context_token_source,
        "context_token_age_seconds": attempt.context_token_age_seconds,
        "latency_ms": attempt.latency_ms,
        "attempted_at": attempt.attempted_at,
        "delivered_at": attempt.delivered_at,
        "created_at": attempt.created_at,
        "updated_at": attempt.updated_at,
    }


def _attempt(row: Mapping) -> DeliveryAttempt:
    return DeliveryAttempt(
        id=db_id(row["id"]),
        route_id=db_id(row["route_id"]),
        turn_id=db_id(row["turn_id"]) if row["turn_id"] is not None else None,
        message_id=db_id(row["message_id"]) if row["message_id"] is not None else None,
        provider_type=row["provider_type"],
        provider_message_id=row["provider_message_id"],
        provider_idempotency_key=row["provider_idempotency_key"],
        status=row["status"],
        error_code=row["error_code"],
        delivery_source=row["delivery_source"],
        delivery_intent=row["delivery_intent"],
        retry_attempt=row["retry_attempt"],
        traceparent=row["traceparent"],
        container=row["container"],
        context_token_source=row["context_token_source"],
        context_token_age_seconds=row["context_token_age_seconds"],
        latency_ms=row["latency_ms"],
        attempted_at=row["attempted_at"],
        delivered_at=row["delivered_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
