from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol, TypeVar
from uuid import uuid4

from coke.domains.channel_reachability.models import (
    Channel,
    ChannelReachabilityError,
    ChannelStatus,
    DeliveryAttempt,
    DeliveryRoute,
    NormalizedInbound,
    PRODUCT_CHANNEL_PROVIDER_TYPES,
    ProviderWebhookAcceptance,
)
from coke.domains.channel_reachability.repository import (
    ChannelReachabilityRepository,
)
from coke.domains.identity_access.models import (
    AccessDecision,
    AccountActivation,
    ArtifactIssueResult,
    ChannelIdentity,
    ChannelIdentityResolution,
    IdentityAccessError,
)
from coke.providers.base import ProviderAdapter

IdentityCallResult = TypeVar("IdentityCallResult")


class IdentityAccessPort(Protocol):
    def check_access_for_action(
        self, account_id: str, action: str
    ) -> AccessDecision: ...

    def get_activation(self, account_id: str) -> AccountActivation: ...

    def observe_usable_channel(self, account_id: str) -> AccountActivation: ...

    def mark_first_inbound_received(self, account_id: str) -> AccountActivation: ...

    def can_remove_channel_identity(
        self, account_id: str, channel_identity_id: str
    ) -> bool: ...

    def get_owned_channel_identity(
        self, account_id: str, channel_identity_id: str
    ) -> ChannelIdentity: ...

    def preview_pairing_code_account(self, pairing_code: str) -> str: ...

    def get_pending_pairing_code(
        self, account_id: str
    ) -> ArtifactIssueResult | None: ...

    def ensure_pairing_code(self, account_id: str) -> ArtifactIssueResult: ...

    def resolve_or_create_channel_identity(
        self,
        provider_type: str,
        provider_subject: str,
        pairing_code: str | None = None,
    ) -> ChannelIdentityResolution: ...

    def bind_channel_identity_to_account(
        self,
        account_id: str,
        provider_type: str,
        provider_subject: str,
        is_account_anchor: bool = False,
    ) -> ChannelIdentityResolution: ...


class ChannelReachabilityService:
    def __init__(
        self,
        repository: ChannelReachabilityRepository,
        identity_access: IdentityAccessPort,
        providers: Mapping[str, ProviderAdapter],
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.identity_access = identity_access
        self.providers = dict(providers)
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda prefix: uuid4().hex)

    def get_status(self, account_id: str) -> ChannelStatus:
        channel = self.repository.get_active_channel(account_id)
        if channel is None:
            return ChannelStatus(
                account_id=account_id,
                channel_id=None,
                provider_type=None,
                connection_state="not_connected",
                reachable=False,
            )
        return ChannelStatus(
            account_id=account_id,
            channel_id=channel.id,
            provider_type=channel.provider_type,
            connection_state=channel.connection_state,
            reachable=channel.connection_state == "connected",
        )

    def start_wechat_personal_connection(self, account_id: str) -> ChannelStatus:
        adapter = self._require_provider("wechat_personal")
        self._require_product_channel("wechat_personal")
        self._require_access(account_id)
        active = self.repository.get_active_channel(account_id)
        if active is not None:
            return self.get_status(account_id)
        if not hasattr(adapter, "start_login"):
            raise ChannelReachabilityError("provider_login_not_supported")
        login = adapter.start_login(account_id=account_id)
        return ChannelStatus(
            account_id=account_id,
            channel_id=None,
            provider_type="wechat_personal",
            connection_state="connecting",
            reachable=False,
            session_id=_optional_response_str(login, "session_id"),
            qrcode_id=_optional_response_str(login, "qrcode_id"),
            qrcode_image=_optional_response_str(login, "qrcode_image_data_url")
            or _optional_response_str(login, "qrcode_image"),
            connector_status=_optional_response_str(login, "status"),
            instructions="scan this QR code with this user's own WeChat account",
        )

    def poll_wechat_personal_login(
        self, account_id: str, session_id: str
    ) -> ChannelStatus:
        adapter = self._require_provider("wechat_personal")
        self._require_product_channel("wechat_personal")
        self._require_access(account_id)
        if not hasattr(adapter, "poll_login_status"):
            raise ChannelReachabilityError("provider_login_not_supported")
        status = adapter.poll_login_status(account_id=account_id, session_id=session_id)
        connector_status = _optional_response_str(status, "status")
        if connector_status == "connected":
            wxid = _required_response_str(status, "ilink_user_id")
            resolution = self._identity_call(
                lambda: self.identity_access.bind_channel_identity_to_account(
                    account_id=account_id,
                    provider_type="wechat_personal",
                    provider_subject=wxid,
                    is_account_anchor=False,
                )
            )
            channel = self.repository.get_active_channel(account_id)
            if channel is None:
                channel = self.create_channel(
                    account_id=account_id,
                    provider_type="wechat_personal",
                    channel_identity_id=resolution.channel_identity.id,
                    removable=True,
                )
            elif channel.channel_identity_id != resolution.channel_identity.id:
                raise ChannelReachabilityError("active_channel_exists")
            if channel.connection_state != "connected":
                channel = self.mark_connected(account_id, channel.id)
            return ChannelStatus(
                account_id=account_id,
                channel_id=channel.id,
                provider_type="wechat_personal",
                connection_state="connected",
                reachable=True,
                session_id=session_id,
                connector_status=connector_status,
                masked_identity=_mask_identity(wxid),
            )
        return ChannelStatus(
            account_id=account_id,
            channel_id=None,
            provider_type="wechat_personal",
            connection_state=(
                "connection_failed" if connector_status == "expired" else "connecting"
            ),
            reachable=False,
            session_id=session_id,
            qrcode_id=_optional_response_str(status, "qrcode_id"),
            qrcode_image=_optional_response_str(status, "qrcode_image_data_url")
            or _optional_response_str(status, "qrcode_image"),
            connector_status=connector_status,
            instructions="scan this QR code with this user's own WeChat account",
        )

    def create_channel(
        self,
        account_id: str,
        provider_type: str,
        channel_identity_id: str,
        removable: bool,
    ) -> Channel:
        self._require_provider(provider_type)
        self._require_product_channel(provider_type)
        self._require_access(account_id)
        identity = self._require_owned_identity(account_id, channel_identity_id)
        if identity.provider_type != provider_type:
            raise ChannelReachabilityError("provider_identity_mismatch")
        if self.repository.get_active_channel(account_id) is not None:
            raise ChannelReachabilityError("active_channel_exists")
        now = self._now()
        channel = Channel(
            id=self._id_factory("channel"),
            account_id=account_id,
            channel_identity_id=channel_identity_id,
            provider_type=provider_type,
            lifecycle="active",
            connection_state="not_connected",
            removable=removable,
            connected_at=None,
            removed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_channel(channel)
        return channel

    def connect_channel(self, account_id: str, channel_id: str) -> Channel:
        self._require_access(account_id)
        channel = self._require_channel(account_id, channel_id)
        return self._save_state(channel, "connecting")

    def poll_channel(self, account_id: str, channel_id: str) -> Channel:
        return self._require_channel(account_id, channel_id)

    def mark_connected(self, account_id: str, channel_id: str) -> Channel:
        self._require_access(account_id)
        channel = self._require_channel(account_id, channel_id)
        self._identity_call(lambda: self.identity_access.get_activation(account_id))
        self._resolve_route_for_channel(channel)
        now = self._now()
        updated = replace(
            channel,
            connection_state="connected",
            connected_at=now,
            updated_at=now,
        )
        self.repository.save_channel(updated)
        self._identity_call(
            lambda: self.identity_access.observe_usable_channel(account_id)
        )
        return updated

    def mark_connection_failed(
        self, account_id: str, channel_id: str, reason: str
    ) -> Channel:
        channel = self._require_channel(account_id, channel_id)
        return self._save_state(channel, "connection_failed")

    def mark_reconnection_required(
        self, account_id: str, channel_id: str, reason: str
    ) -> Channel:
        channel = self._require_channel(account_id, channel_id)
        return self._save_state(channel, "reconnection_required")

    def retry_connection(self, account_id: str, channel_id: str) -> Channel:
        self._require_access(account_id)
        channel = self._require_channel(account_id, channel_id)
        if channel.connection_state not in {
            "connection_failed",
            "reconnection_required",
        }:
            raise ChannelReachabilityError("channel_retry_not_allowed")
        return self._save_state(channel, "connecting")

    def remove_channel(self, account_id: str, channel_id: str) -> Channel:
        channel = self._require_channel(account_id, channel_id)
        if not self._identity_call(
            lambda: self.identity_access.can_remove_channel_identity(
                account_id, channel.channel_identity_id
            )
        ):
            raise ChannelReachabilityError("channel_identity_not_removable")
        if not channel.removable:
            raise ChannelReachabilityError("channel_not_removable")
        now = self._now()
        updated = replace(
            channel,
            lifecycle="removed",
            connection_state="removed",
            removed_at=now,
            updated_at=now,
        )
        self.repository.save_channel(updated)
        self.repository.retire_routes_for_channel(channel.id, retired_at=now)
        return updated

    def resolve_route(self, account_id: str) -> DeliveryRoute:
        channel = self.repository.get_active_channel(account_id)
        if channel is None or channel.connection_state != "connected":
            raise ChannelReachabilityError("no_connected_channel")
        return self._resolve_route_for_channel(channel)

    def _resolve_route_for_channel(self, channel: Channel) -> DeliveryRoute:
        identity = self._require_owned_identity(
            channel.account_id, channel.channel_identity_id
        )
        now = self._now()
        route_key = _delivery_route_key(
            channel.id,
            channel.provider_type,
            identity.provider_subject,
        )
        route = DeliveryRoute(
            id=self._id_factory("delivery_route"),
            account_id=channel.account_id,
            channel_id=channel.id,
            provider_type=channel.provider_type,
            provider_address=identity.provider_subject,
            route_key=route_key,
            lifecycle="active",
            created_at=now,
            updated_at=now,
        )
        return self.repository.upsert_route(route)

    def send_text(
        self,
        account_id: str,
        text: str,
        idempotency_key: str,
        turn_id: str | None = None,
        message_id: str | None = None,
        context_token: str | None = None,
    ) -> DeliveryAttempt:
        route = self.resolve_route(account_id)
        existing = self.repository.get_attempt_by_provider_idempotency(
            route.provider_type,
            idempotency_key,
        )
        if existing is not None:
            existing_route = self.repository.get_route(existing.route_id)
            if (
                existing.route_id != route.id
                or existing_route is None
                or existing_route.account_id != account_id
            ):
                raise ChannelReachabilityError(
                    "provider_idempotency_conflict",
                    fact={
                        "type": "provider_idempotency_conflict",
                        "provider_type": route.provider_type,
                        "provider_idempotency_key": idempotency_key,
                        "existing_account_id": (
                            existing_route.account_id
                            if existing_route is not None
                            else None
                        ),
                        "current_account_id": account_id,
                        "existing_route_id": existing.route_id,
                        "current_route_id": route.id,
                    },
                )
            return existing
        adapter = self._require_provider(route.provider_type)
        if route.provider_type == "wechat_personal":
            result = adapter.send_text(
                route=route,
                text=text,
                idempotency_key=idempotency_key,
                context_token=context_token,
            )
        else:
            result = adapter.send_text(
                route=route,
                text=text,
                idempotency_key=idempotency_key,
            )
        now = self._now()
        if (
            route.provider_type == "wechat_personal"
            and result.status == "failed"
            and _is_session_expired_error(result.error_code)
        ):
            channel = self.repository.get_channel(route.channel_id)
            if (
                channel is not None
                and channel.connection_state != "reconnection_required"
            ):
                self.repository.save_channel(
                    replace(
                        channel,
                        connection_state="reconnection_required",
                        updated_at=now,
                    )
                )
        attempt = DeliveryAttempt(
            id=self._id_factory("delivery_attempt"),
            route_id=route.id,
            provider_type=route.provider_type,
            provider_idempotency_key=idempotency_key,
            status=result.status,
            provider_message_id=result.provider_message_id,
            error_code=result.error_code,
            attempted_at=now,
            delivered_at=result.delivered_at if result.status == "delivered" else None,
            created_at=now,
            updated_at=now,
            turn_id=turn_id,
            message_id=message_id,
        )
        self.repository.save_attempt(attempt)
        return attempt

    def accept_provider_inbound(
        self, inbound: NormalizedInbound
    ) -> ProviderWebhookAcceptance:
        self._require_provider(inbound.provider_type)
        self._require_product_channel(inbound.provider_type)
        if (
            inbound.provider_type == "wechat_personal"
            and inbound.account_id is not None
        ):
            active = self.repository.get_active_channel(inbound.account_id)
            if active is not None:
                identity = self._identity_call(
                    lambda: self.identity_access.bind_channel_identity_to_account(
                        account_id=inbound.account_id,
                        provider_type=inbound.provider_type,
                        provider_subject=inbound.provider_subject,
                        is_account_anchor=False,
                    )
                ).channel_identity
                if active.channel_identity_id != identity.id:
                    raise ChannelReachabilityError("active_channel_exists")
            resolution = self._identity_call(
                lambda: self.identity_access.bind_channel_identity_to_account(
                    account_id=inbound.account_id,
                    provider_type=inbound.provider_type,
                    provider_subject=inbound.provider_subject,
                    is_account_anchor=False,
                )
            )
            account_id = resolution.account.id
            self._require_access(account_id)
            channel = self.repository.get_active_channel(account_id)
            if channel is None:
                channel = self.create_channel(
                    account_id=account_id,
                    provider_type=inbound.provider_type,
                    channel_identity_id=resolution.channel_identity.id,
                    removable=True,
                )
            if channel.connection_state != "connected":
                channel = self.mark_connected(
                    account_id=account_id, channel_id=channel.id
                )
            self._identity_call(
                lambda: self.identity_access.mark_first_inbound_received(account_id)
            )
            return ProviderWebhookAcceptance(
                accepted=True,
                provider_type=inbound.provider_type,
                provider_subject=inbound.provider_subject,
                account_id=account_id,
                channel_identity_id=resolution.channel_identity.id,
                channel_id=channel.id,
                created_account=False,
                raw_event_id=inbound.raw_event_id,
            )
        if inbound.provider_type == "wechat_personal":
            raise ChannelReachabilityError("identity_pairing_required")
        if inbound.pairing_code is not None:
            target_account_id = self._identity_call(
                lambda: self.identity_access.preview_pairing_code_account(
                    inbound.pairing_code
                )
            )
            active = self.repository.get_active_channel(target_account_id)
            if active is not None:
                raise ChannelReachabilityError(
                    "active_channel_exists",
                    fact={
                        "type": "active_channel_exists",
                        "account_id": target_account_id,
                    },
                )
        resolution = self._identity_call(
            lambda: self.identity_access.resolve_or_create_channel_identity(
                provider_type=inbound.provider_type,
                provider_subject=inbound.provider_subject,
                pairing_code=inbound.pairing_code,
                sender_display_name=inbound.sender_display_name,
            )
        )
        account_id = resolution.account.id
        self._require_access(account_id)
        channel = self.repository.get_active_channel(account_id)
        if channel is None:
            channel = self.create_channel(
                account_id=account_id,
                provider_type=inbound.provider_type,
                channel_identity_id=resolution.channel_identity.id,
                removable=not resolution.channel_identity.is_account_anchor,
            )
        elif channel.channel_identity_id != resolution.channel_identity.id:
            raise ChannelReachabilityError("active_channel_exists")
        if channel.connection_state != "connected":
            channel = self.mark_connected(account_id=account_id, channel_id=channel.id)
        self._identity_call(
            lambda: self.identity_access.mark_first_inbound_received(account_id)
        )
        return ProviderWebhookAcceptance(
            accepted=True,
            provider_type=inbound.provider_type,
            provider_subject=inbound.provider_subject,
            account_id=account_id,
            channel_identity_id=resolution.channel_identity.id,
            channel_id=channel.id,
            created_account=resolution.created_account,
            raw_event_id=inbound.raw_event_id,
        )

    def _require_channel(self, account_id: str, channel_id: str) -> Channel:
        channel = self.repository.get_channel(channel_id)
        if (
            channel is None
            or channel.account_id != account_id
            or channel.lifecycle != "active"
        ):
            raise ChannelReachabilityError("channel_not_found")
        return channel

    def _save_state(self, channel: Channel, state) -> Channel:
        updated = replace(channel, connection_state=state, updated_at=self._now())
        self.repository.save_channel(updated)
        return updated

    def _require_access(self, account_id: str) -> None:
        decision = self._identity_call(
            lambda: self.identity_access.check_access_for_action(
                account_id, "connect_channel"
            )
        )
        if not decision.allowed:
            raise ChannelReachabilityError("access_denied", fact=decision.fact)

    def _require_provider(self, provider_type: str) -> ProviderAdapter:
        try:
            return self.providers[provider_type]
        except KeyError as error:
            raise ChannelReachabilityError("unsupported_provider") from error

    def _require_product_channel(self, provider_type: str) -> None:
        if provider_type not in PRODUCT_CHANNEL_PROVIDER_TYPES:
            raise ChannelReachabilityError(
                "unsupported_product_channel",
                fact={
                    "type": "unsupported_product_channel",
                    "provider_type": provider_type,
                    "supported_provider_types": sorted(PRODUCT_CHANNEL_PROVIDER_TYPES),
                },
            )

    def _require_owned_identity(self, account_id: str, channel_identity_id: str):
        try:
            return self.identity_access.get_owned_channel_identity(
                account_id, channel_identity_id
            )
        except IdentityAccessError as error:
            raise ChannelReachabilityError(error.code, fact=error.fact) from error

    def _identity_call(
        self, callback: Callable[[], IdentityCallResult]
    ) -> IdentityCallResult:
        try:
            return callback()
        except IdentityAccessError as error:
            raise ChannelReachabilityError(error.code, fact=error.fact) from error


def _delivery_route_key(
    channel_id: str,
    provider_type: str,
    provider_subject: str,
) -> str:
    material = f"{channel_id}\0{provider_type}\0{provider_subject}".encode("utf-8")
    return f"delivery-route:{sha256(material).hexdigest()}"


def _optional_response_str(response: object, field: str) -> str | None:
    if not isinstance(response, Mapping):
        return None
    value = response.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _required_response_str(response: object, field: str) -> str:
    value = _optional_response_str(response, field)
    if value is None:
        raise ChannelReachabilityError(
            "invalid_provider_response",
            fact={"type": "invalid_provider_response", "field": field},
        )
    return value


def _is_session_expired_error(error_code: str | None) -> bool:
    if not error_code:
        return False
    normalized = error_code.lower()
    return "errcode_-14" in normalized or normalized in {
        "session_expired",
        "ilink_session_expired",
    }


def _mask_identity(value: str) -> str:
    if len(value) <= 8:
        return value
    return f"{value[:4]}***{value[-4:]}"
