from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

from coke.domains.identity_access.models import (
    AccessDecision,
    AccessDeniedReason,
    Account,
    AccountAccess,
    AccountActivation,
    ArtifactIssueResult,
    ArtifactRedemption,
    ArtifactType,
    AuthArtifact,
    ChannelClaimRedemption,
    ChannelIdentity,
    ChannelIdentityResolution,
    ClaimCodeStatus,
    Credential,
    IdentityAccessError,
    LoginResult,
    RegistrationResult,
    Session,
)
from coke.domains.identity_access.repository import IdentityAccessRepository


class IdentityAccessService:
    def __init__(
        self,
        repository: IdentityAccessRepository,
        now: Callable[[], datetime] | None = None,
        token_factory: Callable[[str], str] | None = None,
        id_factory: Callable[[str], str] | None = None,
        checkout_url_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self._now = now or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda prefix: f"{prefix}_{token_urlsafe(32)}")
        self._id_factory = id_factory or self._default_id
        self._checkout_url_factory = checkout_url_factory or (
            lambda account_id: f"https://checkout.example/{account_id}"
        )

    def register_web_account(
        self,
        email: str,
        password_hash: str,
        default_timezone: str = "UTC",
    ) -> RegistrationResult:
        if self.repository.get_credential_by_email(email):
            raise IdentityAccessError("email_already_registered")

        account = self._create_account(origin="web_first", default_timezone=default_timezone)
        credential = Credential(
            id=self._id_factory("credential"),
            account_id=account.id,
            email=email,
            password_hash=password_hash,
            email_verified_at=None,
            reset_required=False,
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.add_credential(credential)
        session = self._create_session(account.id)
        email_verification = self._issue_artifact(
            artifact_type=ArtifactType.EMAIL_VERIFICATION,
            purpose="verify_email",
            delivery="email",
            account_id=account.id,
            ttl=timedelta(hours=24),
        ).artifact
        return RegistrationResult(
            account=account,
            credential=credential,
            session=session,
            email_verification=email_verification,
        )

    def login(self, email: str, password_hash: str) -> LoginResult:
        credential = self.repository.get_credential_by_email(email)
        if credential is None or credential.password_hash != password_hash:
            raise IdentityAccessError("invalid_credentials")
        account = self._require_account(credential.account_id)
        return LoginResult(account=account, session=self._create_session(account.id))

    def current_user(self, session_token: str) -> Account:
        session = self.repository.get_session_by_token(session_token)
        if session is None or session.revoked_at is not None or session.expires_at <= self._now():
            raise IdentityAccessError("invalid_session")
        return self._require_account(session.account_id)

    def get_access_status(self, account_id: str) -> AccountAccess:
        return self._require_access(account_id)

    def set_access_state(
        self,
        account_id: str,
        email_verification_state: str,
        subscription_state: str,
        suspension_state: str,
    ) -> AccountAccess:
        self._require_account(account_id)
        denial_reason = self._derive_denial_reason(
            email_verification_state=email_verification_state,
            subscription_state=subscription_state,
            suspension_state=suspension_state,
        )
        current = self._require_access(account_id)
        access = replace(
            current,
            email_verification_state=email_verification_state,
            subscription_state=subscription_state,
            suspension_state=suspension_state,
            access_allowed=denial_reason is None,
            denial_reason=denial_reason,
            updated_at=self._now(),
        )
        self.repository.save_access(access)
        return access

    def check_access_for_inbound(self, account_id: str) -> AccessDecision:
        return self._check_access(account_id=account_id, include_checkout_for_messaging=True)

    def check_access_for_action(self, account_id: str, action: str) -> AccessDecision:
        if action not in {"connect_channel", "calendar_import"}:
            raise IdentityAccessError("unsupported_gated_action")
        return self._check_access(account_id=account_id, include_checkout_for_messaging=False)

    def resolve_or_create_channel_identity(
        self,
        provider_type: str,
        provider_subject: str,
        pairing_code: str | None = None,
    ) -> ChannelIdentityResolution:
        if pairing_code is not None:
            artifact = self._require_unconsumed_artifact(
                pairing_code,
                expected_type=ArtifactType.PAIRING_CODE,
            )
            if artifact.account_id is None:
                raise IdentityAccessError("artifact_missing_account")
            account = self._require_account(artifact.account_id)
            access_decision = self.check_access_for_action(
                account_id=account.id,
                action="connect_channel",
            )
            if not access_decision.allowed:
                raise IdentityAccessError("access_denied", fact=access_decision.fact)
            existing = self.repository.get_channel_identity_by_provider(provider_type, provider_subject)
            if existing is not None:
                raise IdentityAccessError("channel_identity_already_bound")
            consumed = replace(
                artifact,
                consumed_at=self._now(),
                delivery_state="consumed",
                updated_at=self._now(),
            )
            identity = self._build_channel_identity(
                account_id=account.id,
                provider_type=provider_type,
                provider_subject=provider_subject,
                is_account_anchor=False,
            )
            try:
                self.repository.add_channel_identity_and_save_artifact(identity, consumed)
            except ValueError as error:
                raise IdentityAccessError(
                    "channel_identity_write_conflict",
                    fact={
                        "type": "channel_identity_write_conflict",
                        "provider_type": provider_type,
                        "reason": str(error),
                    },
                ) from error
            return ChannelIdentityResolution(
                account=account,
                channel_identity=identity,
                created_account=False,
            )

        existing = self.repository.get_channel_identity_by_provider(provider_type, provider_subject)
        if existing is not None:
            return ChannelIdentityResolution(
                account=self._require_account(existing.account_id),
                channel_identity=existing,
                created_account=False,
            )

        if provider_type != "whatsapp_evolution":
            raise IdentityAccessError("identity_pairing_required")

        account = self._create_account(origin="messaging_first", default_timezone="UTC")
        identity = self._create_channel_identity(
            account_id=account.id,
            provider_type=provider_type,
            provider_subject=provider_subject,
            is_account_anchor=True,
        )
        return ChannelIdentityResolution(
            account=account,
            channel_identity=identity,
            created_account=True,
        )

    def issue_login_url(self, account_id: str) -> ArtifactIssueResult:
        self._require_account(account_id)
        return self._issue_artifact(
            artifact_type=ArtifactType.LOGIN_URL,
            purpose="chat_login",
            delivery="in_conversation",
            account_id=account_id,
            ttl=timedelta(minutes=15),
        )

    def redeem_login_url(self, token: str, browser_session: str) -> ArtifactRedemption:
        artifact = self._consume_artifact(token, expected_type=ArtifactType.LOGIN_URL)
        if artifact.account_id is None:
            raise IdentityAccessError("artifact_missing_account")
        session = self._create_session(artifact.account_id)
        return ArtifactRedemption(
            account_id=artifact.account_id,
            session=session,
            continuation=dict(artifact.continuation),
        )

    def issue_web_claim_code(
        self,
        browser_session: str,
        continuation: dict | None = None,
    ) -> ArtifactIssueResult:
        return self._issue_artifact(
            artifact_type=ArtifactType.CLAIM_CODE,
            purpose="web_claim",
            delivery="web",
            browser_session=browser_session,
            continuation=continuation or {},
            ttl=timedelta(minutes=15),
        )

    def get_claim_code_status(self, code: str, browser_session: str) -> ClaimCodeStatus:
        artifact = self.repository.get_artifact_by_code(code)
        if artifact is None or artifact.type != ArtifactType.CLAIM_CODE:
            return ClaimCodeStatus(
                found=False,
                consumed=False,
                target_account_id=None,
                delivery_state=None,
            )
        if artifact.expires_at <= self._now():
            raise IdentityAccessError("artifact_expired")
        if artifact.browser_session != browser_session:
            raise IdentityAccessError("browser_session_mismatch")
        return ClaimCodeStatus(
            found=True,
            consumed=artifact.consumed_at is not None,
            target_account_id=artifact.target_account_id,
            delivery_state=artifact.delivery_state,
        )

    def redeem_claim_code_from_channel(
        self,
        code: str,
        provider_type: str,
        provider_subject: str,
    ) -> ChannelClaimRedemption:
        identity = self.repository.get_channel_identity_by_provider(provider_type, provider_subject)
        if identity is None:
            raise IdentityAccessError("unknown_channel_identity")

        artifact = self._require_unconsumed_artifact(code, expected_type=ArtifactType.CLAIM_CODE)
        updated = replace(
            artifact,
            consumed_at=self._now(),
            delivery_state="consumed",
            target_account_id=identity.account_id,
            updated_at=self._now(),
        )
        self.repository.save_artifact(updated)
        return ChannelClaimRedemption(
            account_id=identity.account_id,
            continuation=dict(artifact.continuation),
        )

    def complete_web_claim_from_browser(
        self,
        code: str,
        browser_session: str,
    ) -> ArtifactRedemption:
        artifact = self.repository.get_artifact_by_code(code)
        if artifact is None:
            raise IdentityAccessError("artifact_not_found")
        if artifact.type != ArtifactType.CLAIM_CODE:
            raise IdentityAccessError("artifact_wrong_type")
        if artifact.expires_at <= self._now():
            raise IdentityAccessError("artifact_expired")
        if artifact.browser_session != browser_session:
            raise IdentityAccessError("browser_session_mismatch")
        if artifact.consumed_at is None or artifact.target_account_id is None:
            raise IdentityAccessError("claim_not_redeemed")
        if artifact.delivery_state == "completed":
            raise IdentityAccessError("artifact_consumed")
        session = self._create_session(artifact.target_account_id)
        completed = replace(
            artifact,
            delivery_state="completed",
            updated_at=self._now(),
        )
        self.repository.save_artifact(completed)
        return ArtifactRedemption(
            account_id=artifact.target_account_id,
            session=session,
            continuation=dict(artifact.continuation),
        )

    def issue_pairing_code(self, account_id: str) -> ArtifactIssueResult:
        account = self._require_account(account_id)
        if account.origin != "web_first":
            raise IdentityAccessError("pairing_requires_web_first_account")
        access_decision = self.check_access_for_action(
            account_id=account_id,
            action="connect_channel",
        )
        if not access_decision.allowed:
            raise IdentityAccessError("access_denied", fact=access_decision.fact)
        return self._issue_artifact(
            artifact_type=ArtifactType.PAIRING_CODE,
            purpose="channel_pairing",
            delivery="web",
            account_id=account_id,
            ttl=timedelta(minutes=15),
        )

    def issue_password_reset(self, email: str) -> ArtifactIssueResult:
        credential = self.repository.get_credential_by_email(email)
        if credential is None:
            raise IdentityAccessError("unknown_email")
        return self._issue_artifact(
            artifact_type=ArtifactType.PASSWORD_RESET,
            purpose="password_reset",
            delivery="email",
            account_id=credential.account_id,
            ttl=timedelta(hours=1),
        )

    def reset_password(self, token: str, password_hash: str) -> Credential:
        artifact = self._consume_artifact(token, expected_type=ArtifactType.PASSWORD_RESET)
        if artifact.account_id is None:
            raise IdentityAccessError("artifact_missing_account")
        credential = self.repository.get_credential_by_account(artifact.account_id)
        if credential is None:
            raise IdentityAccessError("credential_not_found")
        updated = replace(
            credential,
            password_hash=password_hash,
            reset_required=False,
            updated_at=self._now(),
        )
        self.repository.save_credential(updated)
        return updated

    def verify_email(self, token: str) -> Credential:
        artifact = self._consume_artifact(token, expected_type=ArtifactType.EMAIL_VERIFICATION)
        if artifact.account_id is None:
            raise IdentityAccessError("artifact_missing_account")
        credential = self.repository.get_credential_by_account(artifact.account_id)
        if credential is None:
            raise IdentityAccessError("credential_not_found")
        updated = replace(
            credential,
            email_verified_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.save_credential(updated)
        self.set_access_state(
            account_id=artifact.account_id,
            email_verification_state="verified",
            subscription_state=self._require_access(artifact.account_id).subscription_state,
            suspension_state=self._require_access(artifact.account_id).suspension_state,
        )
        return updated

    def resend_artifact(self, code: str) -> AuthArtifact:
        artifact = self.repository.get_artifact_by_code(code)
        if artifact is None:
            raise IdentityAccessError("artifact_not_found")
        if artifact.type not in {ArtifactType.EMAIL_VERIFICATION, ArtifactType.PASSWORD_RESET}:
            raise IdentityAccessError("artifact_not_resendable")
        if artifact.consumed_at is not None:
            raise IdentityAccessError("artifact_consumed")
        if artifact.expires_at <= self._now():
            raise IdentityAccessError("artifact_expired")
        updated = replace(
            artifact,
            delivery_state="pending",
            resend_count=artifact.resend_count + 1,
            updated_at=self._now(),
        )
        self.repository.save_artifact(updated)
        return updated

    def observe_usable_channel(self, account_id: str) -> AccountActivation:
        self._require_account(account_id)
        self.repository.mark_usable_channel(account_id)
        return self._recompute_activation(account_id)

    def mark_first_inbound_received(self, account_id: str) -> AccountActivation:
        activation = self.get_activation(account_id)
        if activation.first_inbound_received_at is None:
            activation = replace(
                activation,
                first_inbound_received_at=self._now(),
                updated_at=self._now(),
            )
            self.repository.save_activation(activation)
        return self._recompute_activation(account_id)

    def mark_first_guidance_sent(self, account_id: str) -> AccountActivation:
        activation = self.get_activation(account_id)
        if activation.first_guidance_sent_at is not None:
            return activation
        updated = replace(
            activation,
            first_guidance_sent_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.save_activation(updated)
        return updated

    def get_activation(self, account_id: str) -> AccountActivation:
        activation = self.repository.get_activation(account_id)
        if activation is None:
            raise IdentityAccessError("activation_not_found")
        return activation

    def can_remove_channel_identity(self, account_id: str, channel_identity_id: str) -> bool:
        account = self._require_account(account_id)
        identity = self.repository.get_channel_identity(channel_identity_id)
        if identity is None or identity.account_id != account_id:
            raise IdentityAccessError("channel_identity_not_found")
        active_identities = self.repository.list_channel_identities(account_id)
        if account.origin == "messaging_first" and identity.is_account_anchor and len(active_identities) == 1:
            return False
        return True

    def _create_account(self, origin: str, default_timezone: str) -> Account:
        account = Account(
            id=self._id_factory("account"),
            origin=origin,
            default_timezone=default_timezone,
            lifecycle="active",
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.add_account(account)
        self.repository.add_activation(
            AccountActivation(
                id=self._id_factory("activation"),
                account_id=account.id,
                first_inbound_received_at=None,
                activation_completed_at=None,
                first_guidance_sent_at=None,
                created_at=self._now(),
                updated_at=self._now(),
            )
        )
        self.repository.add_access(
            AccountAccess(
                id=self._id_factory("access"),
                account_id=account.id,
                email_verification_state="required" if origin == "web_first" else "verified",
                subscription_state="active",
                suspension_state="active",
                access_allowed=origin == "messaging_first",
                denial_reason=(
                    AccessDeniedReason.EMAIL_VERIFICATION_REQUIRED if origin == "web_first" else None
                ),
                created_at=self._now(),
                updated_at=self._now(),
            )
        )
        return account

    def _create_channel_identity(
        self,
        account_id: str,
        provider_type: str,
        provider_subject: str,
        is_account_anchor: bool,
    ) -> ChannelIdentity:
        identity = self._build_channel_identity(
            account_id=account_id,
            provider_type=provider_type,
            provider_subject=provider_subject,
            is_account_anchor=is_account_anchor,
        )
        self.repository.add_channel_identity(identity)
        return identity

    def _build_channel_identity(
        self,
        account_id: str,
        provider_type: str,
        provider_subject: str,
        is_account_anchor: bool,
    ) -> ChannelIdentity:
        return ChannelIdentity(
            id=self._id_factory("channel_identity"),
            account_id=account_id,
            provider_type=provider_type,
            provider_subject=provider_subject,
            lifecycle="active",
            is_account_anchor=is_account_anchor,
            created_at=self._now(),
            updated_at=self._now(),
        )

    def _create_session(self, account_id: str) -> Session:
        session = Session(
            id=self._id_factory("session"),
            account_id=account_id,
            token=self._token_factory("session"),
            expires_at=self._now() + timedelta(days=30),
            revoked_at=None,
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.add_session(session)
        return session

    def _issue_artifact(
        self,
        artifact_type: str,
        purpose: str,
        delivery: str,
        ttl: timedelta,
        account_id: str | None = None,
        browser_session: str | None = None,
        continuation: dict | None = None,
    ) -> ArtifactIssueResult:
        artifact = AuthArtifact(
            id=self._id_factory("auth_artifact"),
            account_id=account_id,
            target_account_id=None,
            type=artifact_type,
            purpose=purpose,
            delivery=delivery,
            code=self._token_factory(artifact_type),
            browser_session=browser_session,
            continuation=continuation or {},
            expires_at=self._now() + ttl,
            consumed_at=None,
            delivery_state="pending",
            resend_count=0,
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.add_artifact(artifact)
        return ArtifactIssueResult(artifact=artifact, code=artifact.code)

    def _require_unconsumed_artifact(self, code: str, expected_type: str) -> AuthArtifact:
        artifact = self.repository.get_artifact_by_code(code)
        if artifact is None:
            raise IdentityAccessError("artifact_not_found")
        if artifact.type != expected_type:
            raise IdentityAccessError("artifact_wrong_type")
        if artifact.consumed_at is not None:
            raise IdentityAccessError("artifact_consumed")
        if artifact.expires_at <= self._now():
            raise IdentityAccessError("artifact_expired")
        return artifact

    def _consume_artifact(self, code: str, expected_type: str) -> AuthArtifact:
        artifact = self._require_unconsumed_artifact(code, expected_type)
        consumed = replace(
            artifact,
            consumed_at=self._now(),
            delivery_state="consumed",
            updated_at=self._now(),
        )
        self.repository.save_artifact(consumed)
        return consumed

    def _check_access(self, account_id: str, include_checkout_for_messaging: bool) -> AccessDecision:
        account = self._require_account(account_id)
        access = self._require_access(account_id)
        if access.access_allowed:
            return AccessDecision(allowed=True)

        checkout_url = None
        if (
            include_checkout_for_messaging
            and access.denial_reason == AccessDeniedReason.SUBSCRIPTION_INACTIVE
            and account.origin == "messaging_first"
        ):
            checkout_url = self._checkout_url_factory(account_id)

        return AccessDecision(
            allowed=False,
            denial_reason=access.denial_reason,
            turn_trigger="AccessDeniedTurn",
            fact={
                "type": "account_access_denied",
                "account_id": account_id,
                "denial_reason": access.denial_reason,
                "checkout_url": checkout_url,
            },
        )

    def _derive_denial_reason(
        self,
        email_verification_state: str,
        subscription_state: str,
        suspension_state: str,
    ) -> str | None:
        if suspension_state == "suspended":
            return AccessDeniedReason.SUSPENDED
        if email_verification_state != "verified":
            return AccessDeniedReason.EMAIL_VERIFICATION_REQUIRED
        if subscription_state != "active":
            return AccessDeniedReason.SUBSCRIPTION_INACTIVE
        return None

    def _recompute_activation(self, account_id: str) -> AccountActivation:
        account = self._require_account(account_id)
        activation = self.get_activation(account_id)
        has_identity_condition = False
        if account.origin == "web_first":
            has_identity_condition = self.repository.get_credential_by_account(account_id) is not None
        elif account.origin == "messaging_first":
            has_identity_condition = any(
                identity.is_account_anchor for identity in self.repository.list_channel_identities(account_id)
            )

        complete = (
            has_identity_condition
            and self.repository.has_usable_channel(account_id)
            and activation.first_inbound_received_at is not None
        )
        if complete and activation.activation_completed_at is None:
            activation = replace(
                activation,
                activation_completed_at=self._now(),
                updated_at=self._now(),
            )
            self.repository.save_activation(activation)
        return activation

    def _require_account(self, account_id: str) -> Account:
        account = self.repository.get_account(account_id)
        if account is None:
            raise IdentityAccessError("account_not_found")
        return account

    def _require_access(self, account_id: str) -> AccountAccess:
        access = self.repository.get_access(account_id)
        if access is None:
            raise IdentityAccessError("access_not_found")
        return access

    def _default_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"
