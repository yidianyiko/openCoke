from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


AccountOrigin = Literal["web_first", "messaging_first"]
AccountLifecycle = Literal["active", "disabled"]
ChannelIdentityLifecycle = Literal["active", "removed"]


class AccessDeniedReason:
    EMAIL_VERIFICATION_REQUIRED = "email_verification_required"
    SUBSCRIPTION_INACTIVE = "subscription_inactive"
    SUSPENDED = "suspended"


class ArtifactType:
    LOGIN_URL = "login_url"
    CLAIM_CODE = "claim_code"
    PAIRING_CODE = "pairing_code"
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


class IdentityAccessError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        fact: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.fact = fact
        super().__init__(message or code)


@dataclass(slots=True)
class Account:
    id: str
    origin: AccountOrigin
    default_timezone: str
    lifecycle: AccountLifecycle
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AccountActivation:
    id: str
    account_id: str
    first_inbound_received_at: datetime | None
    activation_completed_at: datetime | None
    first_guidance_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AccountAccess:
    id: str
    account_id: str
    email_verification_state: str
    subscription_state: str
    suspension_state: str
    access_allowed: bool
    denial_reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Credential:
    id: str
    account_id: str
    email: str
    password_hash: str
    email_verified_at: datetime | None
    reset_required: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Session:
    id: str
    account_id: str
    token: str
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ChannelIdentity:
    id: str
    account_id: str
    provider_type: str
    provider_subject: str
    lifecycle: ChannelIdentityLifecycle
    is_account_anchor: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AuthArtifact:
    id: str
    type: str
    purpose: str
    delivery: str
    code: str
    expires_at: datetime
    consumed_at: datetime | None
    delivery_state: str
    resend_count: int
    created_at: datetime
    updated_at: datetime
    account_id: str | None = None
    target_account_id: str | None = None
    browser_session: str | None = None
    continuation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    account: Account
    credential: Credential
    session: Session
    email_verification: AuthArtifact


@dataclass(frozen=True, slots=True)
class LoginResult:
    account: Account
    session: Session


@dataclass(frozen=True, slots=True)
class ChannelIdentityResolution:
    account: Account
    channel_identity: ChannelIdentity
    created_account: bool


@dataclass(frozen=True, slots=True)
class ArtifactIssueResult:
    artifact: AuthArtifact
    code: str


@dataclass(frozen=True, slots=True)
class ArtifactRedemption:
    account_id: str
    session: Session
    continuation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChannelClaimRedemption:
    account_id: str
    continuation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ClaimCodeStatus:
    found: bool
    consumed: bool
    target_account_id: str | None
    delivery_state: str | None


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    denial_reason: str | None = None
    turn_trigger: str | None = None
    fact: dict[str, Any] | None = None
