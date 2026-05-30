from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.orm import Session as SqlAlchemySession

from coke import schema
from coke.domains._pg import (
    db_id,
    insert_row,
    many,
    one_or_none,
    update_row,
    write_with_integrity,
)
from coke.domains.identity_access.models import (
    Account,
    AccountAccess,
    AccountActivation,
    AuthArtifact,
    ChannelIdentity,
    Credential,
    Session,
)


class IdentityAccessRepository(Protocol):
    def count_accounts(self) -> int: ...

    def add_account(self, account: Account) -> None: ...

    def get_account(self, account_id: str) -> Account | None: ...

    def add_activation(self, activation: AccountActivation) -> None: ...

    def get_activation(self, account_id: str) -> AccountActivation | None: ...

    def save_activation(self, activation: AccountActivation) -> None: ...

    def add_access(self, access: AccountAccess) -> None: ...

    def get_access(self, account_id: str) -> AccountAccess | None: ...

    def save_access(self, access: AccountAccess) -> None: ...

    def add_credential(self, credential: Credential) -> None: ...

    def get_credential_by_email(self, email: str) -> Credential | None: ...

    def get_credential_by_account(self, account_id: str) -> Credential | None: ...

    def save_credential(self, credential: Credential) -> None: ...

    def add_session(self, session: Session) -> None: ...

    def get_session_by_token(self, token: str) -> Session | None: ...

    def add_channel_identity(self, channel_identity: ChannelIdentity) -> None: ...

    def add_channel_identity_and_save_artifact(
        self,
        channel_identity: ChannelIdentity,
        artifact: AuthArtifact,
    ) -> None: ...

    def get_channel_identity_by_provider(
        self,
        provider_type: str,
        provider_subject: str,
    ) -> ChannelIdentity | None: ...

    def get_channel_identity(
        self, channel_identity_id: str
    ) -> ChannelIdentity | None: ...

    def list_channel_identities(self, account_id: str) -> list[ChannelIdentity]: ...

    def add_artifact(self, artifact: AuthArtifact) -> None: ...

    def get_artifact_by_code(self, code: str) -> AuthArtifact | None: ...

    def get_latest_unconsumed_artifact(
        self,
        *,
        account_id: str,
        artifact_type: str,
        purpose: str,
    ) -> AuthArtifact | None: ...

    def save_artifact(self, artifact: AuthArtifact) -> None: ...

    def mark_usable_channel(self, account_id: str) -> None: ...

    def has_usable_channel(self, account_id: str) -> bool: ...


class InMemoryIdentityAccessRepository:
    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self.accounts: dict[str, Account] = {}
        self.activations: dict[str, AccountActivation] = {}
        self.access: dict[str, AccountAccess] = {}
        self.credentials_by_account: dict[str, Credential] = {}
        self.credentials_by_email: dict[str, Credential] = {}
        self.sessions_by_token: dict[str, Session] = {}
        self.channel_identities_by_id: dict[str, ChannelIdentity] = {}
        self.channel_identities_by_provider: dict[tuple[str, str], ChannelIdentity] = {}
        self.artifacts_by_code: dict[str, AuthArtifact] = {}
        self.usable_channel_accounts: set[str] = set()

    def count_accounts(self) -> int:
        return len(self.accounts)

    def add_account(self, account: Account) -> None:
        if account.id in self.accounts:
            raise ValueError("duplicate_account_id")
        self.accounts[account.id] = account

    def get_account(self, account_id: str) -> Account | None:
        return self.accounts.get(account_id)

    def add_activation(self, activation: AccountActivation) -> None:
        if activation.account_id in self.activations:
            raise ValueError("duplicate_activation_account")
        self.activations[activation.account_id] = activation

    def get_activation(self, account_id: str) -> AccountActivation | None:
        return self.activations.get(account_id)

    def save_activation(self, activation: AccountActivation) -> None:
        if activation.account_id not in self.activations:
            raise ValueError("activation_not_found")
        self.activations[activation.account_id] = activation

    def add_access(self, access: AccountAccess) -> None:
        if access.account_id in self.access:
            raise ValueError("duplicate_access_account")
        self.access[access.account_id] = access

    def get_access(self, account_id: str) -> AccountAccess | None:
        return self.access.get(account_id)

    def save_access(self, access: AccountAccess) -> None:
        if access.account_id not in self.access:
            raise ValueError("access_not_found")
        self.access[access.account_id] = access

    def add_credential(self, credential: Credential) -> None:
        email_key = credential.email.lower()
        if credential.account_id in self.credentials_by_account:
            raise ValueError("duplicate_credential_account")
        if email_key in self.credentials_by_email:
            raise ValueError("duplicate_credential_email")
        self.credentials_by_account[credential.account_id] = credential
        self.credentials_by_email[email_key] = credential

    def get_credential_by_email(self, email: str) -> Credential | None:
        return self.credentials_by_email.get(email.lower())

    def get_credential_by_account(self, account_id: str) -> Credential | None:
        return self.credentials_by_account.get(account_id)

    def save_credential(self, credential: Credential) -> None:
        existing = self.credentials_by_account.get(credential.account_id)
        if existing is None:
            raise ValueError("credential_not_found")
        email_key = credential.email.lower()
        email_owner = self.credentials_by_email.get(email_key)
        if email_owner is not None and email_owner.account_id != credential.account_id:
            raise ValueError("duplicate_credential_email")
        old_email_key = existing.email.lower()
        if old_email_key != email_key:
            self.credentials_by_email.pop(old_email_key, None)
        self.credentials_by_account[credential.account_id] = credential
        self.credentials_by_email[email_key] = credential

    def add_session(self, session: Session) -> None:
        if session.token in self.sessions_by_token:
            raise ValueError("duplicate_session_token")
        self.sessions_by_token[session.token] = session

    def get_session_by_token(self, token: str) -> Session | None:
        return self.sessions_by_token.get(token)

    def add_channel_identity(self, channel_identity: ChannelIdentity) -> None:
        key = (channel_identity.provider_type, channel_identity.provider_subject)
        if channel_identity.id in self.channel_identities_by_id:
            raise ValueError("duplicate_channel_identity_id")
        if key in self.channel_identities_by_provider:
            raise ValueError("duplicate_channel_identity_provider")
        self.channel_identities_by_id[channel_identity.id] = channel_identity
        self.channel_identities_by_provider[key] = channel_identity

    def add_channel_identity_and_save_artifact(
        self,
        channel_identity: ChannelIdentity,
        artifact: AuthArtifact,
    ) -> None:
        key = (channel_identity.provider_type, channel_identity.provider_subject)
        if channel_identity.id in self.channel_identities_by_id:
            raise ValueError("duplicate_channel_identity_id")
        if key in self.channel_identities_by_provider:
            raise ValueError("duplicate_channel_identity_provider")
        if artifact.code not in self.artifacts_by_code:
            raise ValueError("artifact_not_found")
        self.channel_identities_by_id[channel_identity.id] = channel_identity
        self.channel_identities_by_provider[key] = channel_identity
        self.artifacts_by_code[artifact.code] = artifact

    def get_channel_identity_by_provider(
        self,
        provider_type: str,
        provider_subject: str,
    ) -> ChannelIdentity | None:
        return self.channel_identities_by_provider.get(
            (provider_type, provider_subject)
        )

    def get_channel_identity(self, channel_identity_id: str) -> ChannelIdentity | None:
        return self.channel_identities_by_id.get(channel_identity_id)

    def list_channel_identities(self, account_id: str) -> list[ChannelIdentity]:
        return [
            identity
            for identity in self.channel_identities_by_id.values()
            if identity.account_id == account_id and identity.lifecycle == "active"
        ]

    def add_artifact(self, artifact: AuthArtifact) -> None:
        if artifact.code in self.artifacts_by_code:
            raise ValueError("duplicate_artifact_code")
        self.artifacts_by_code[artifact.code] = artifact

    def get_artifact_by_code(self, code: str) -> AuthArtifact | None:
        return self.artifacts_by_code.get(code)

    def get_latest_unconsumed_artifact(
        self,
        *,
        account_id: str,
        artifact_type: str,
        purpose: str,
    ) -> AuthArtifact | None:
        artifacts = [
            artifact
            for artifact in self.artifacts_by_code.values()
            if artifact.account_id == account_id
            and artifact.type == artifact_type
            and artifact.purpose == purpose
            and artifact.consumed_at is None
        ]
        if not artifacts:
            return None
        return max(artifacts, key=lambda artifact: (artifact.created_at, artifact.id))

    def save_artifact(self, artifact: AuthArtifact) -> None:
        if artifact.code not in self.artifacts_by_code:
            raise ValueError("artifact_not_found")
        self.artifacts_by_code[artifact.code] = artifact

    def mark_usable_channel(self, account_id: str) -> None:
        self.usable_channel_accounts.add(account_id)

    def has_usable_channel(self, account_id: str) -> bool:
        return account_id in self.usable_channel_accounts


class PostgresIdentityAccessRepository:
    def __init__(self, session: SqlAlchemySession) -> None:
        self.session = session

    def count_accounts(self) -> int:
        return int(
            self.session.scalar(sa.select(sa.func.count()).select_from(schema.account))
            or 0
        )

    def add_account(self, account: Account) -> None:
        insert_row(
            self.session,
            schema.account,
            _account_values(account),
            {"pk_account": "duplicate_account_id"},
            default_error="duplicate_account_id",
        )

    def get_account(self, account_id: str) -> Account | None:
        row = one_or_none(
            self.session, schema.account, schema.account.c.id == account_id
        )
        return _account(row) if row else None

    def add_activation(self, activation: AccountActivation) -> None:
        insert_row(
            self.session,
            schema.account_activation,
            _activation_values(activation),
            {
                "pk_account_activation": "duplicate_activation_id",
                "uq_account_activation_account": "duplicate_activation_account",
            },
            default_error="duplicate_activation_account",
        )

    def get_activation(self, account_id: str) -> AccountActivation | None:
        row = one_or_none(
            self.session,
            schema.account_activation,
            schema.account_activation.c.account_id == account_id,
        )
        return _activation(row) if row else None

    def save_activation(self, activation: AccountActivation) -> None:
        if (
            update_row(
                self.session,
                schema.account_activation,
                _activation_values(activation),
                {"uq_account_activation_account": "duplicate_activation_account"},
                default_error="duplicate_activation_account",
            )
            == 0
        ):
            raise ValueError("activation_not_found")

    def add_access(self, access: AccountAccess) -> None:
        insert_row(
            self.session,
            schema.account_access,
            _access_values(access),
            {
                "pk_account_access": "duplicate_access_id",
                "uq_account_access_account": "duplicate_access_account",
            },
            default_error="duplicate_access_account",
        )

    def get_access(self, account_id: str) -> AccountAccess | None:
        row = one_or_none(
            self.session,
            schema.account_access,
            schema.account_access.c.account_id == account_id,
        )
        return _access(row) if row else None

    def save_access(self, access: AccountAccess) -> None:
        if (
            update_row(
                self.session,
                schema.account_access,
                _access_values(access),
                {"uq_account_access_account": "duplicate_access_account"},
                default_error="duplicate_access_account",
            )
            == 0
        ):
            raise ValueError("access_not_found")

    def add_credential(self, credential: Credential) -> None:
        insert_row(
            self.session,
            schema.credential,
            _credential_values(credential),
            {
                "pk_credential": "duplicate_credential_id",
                "uq_credential_account": "duplicate_credential_account",
                "uq_credential_email": "duplicate_credential_email",
            },
            default_error="duplicate_credential_email",
        )

    def get_credential_by_email(self, email: str) -> Credential | None:
        row = one_or_none(
            self.session,
            schema.credential,
            sa.func.lower(schema.credential.c.email) == email.lower(),
        )
        return _credential(row) if row else None

    def get_credential_by_account(self, account_id: str) -> Credential | None:
        row = one_or_none(
            self.session,
            schema.credential,
            schema.credential.c.account_id == account_id,
        )
        return _credential(row) if row else None

    def save_credential(self, credential: Credential) -> None:
        existing = self.get_credential_by_account(credential.account_id)
        if existing is None:
            raise ValueError("credential_not_found")
        owner = self.get_credential_by_email(credential.email)
        if owner is not None and owner.account_id != credential.account_id:
            raise ValueError("duplicate_credential_email")
        if (
            update_row(
                self.session,
                schema.credential,
                _credential_values(credential),
                {"uq_credential_email": "duplicate_credential_email"},
                default_error="duplicate_credential_email",
            )
            == 0
        ):
            raise ValueError("credential_not_found")

    def add_session(self, session: Session) -> None:
        insert_row(
            self.session,
            schema.session,
            _session_values(session),
            {
                "pk_session": "duplicate_session_id",
                "uq_session_token_hash": "duplicate_session_token",
            },
            default_error="duplicate_session_token",
        )

    def get_session_by_token(self, token: str) -> Session | None:
        row = one_or_none(
            self.session,
            schema.session,
            schema.session.c.token_hash == token,
        )
        return _session(row) if row else None

    def add_channel_identity(self, channel_identity: ChannelIdentity) -> None:
        insert_row(
            self.session,
            schema.channel_identity,
            _channel_identity_values(channel_identity),
            {
                "pk_channel_identity": "duplicate_channel_identity_id",
                "uq_channel_identity_provider_subject": "duplicate_channel_identity_provider",
            },
            default_error="duplicate_channel_identity_provider",
        )

    def add_channel_identity_and_save_artifact(
        self,
        channel_identity: ChannelIdentity,
        artifact: AuthArtifact,
    ) -> None:
        if self.get_artifact_by_code(artifact.code) is None:
            raise ValueError("artifact_not_found")

        def _write() -> None:
            self.session.execute(
                schema.channel_identity.insert().values(
                    **_channel_identity_values(channel_identity)
                )
            )
            self.session.execute(
                schema.auth_artifact.update()
                .where(schema.auth_artifact.c.token_hash == artifact.code)
                .values(**_artifact_values(artifact))
            )

        write_with_integrity(
            self.session,
            _write,
            {
                "pk_channel_identity": "duplicate_channel_identity_id",
                "uq_channel_identity_provider_subject": "duplicate_channel_identity_provider",
            },
            default_error="duplicate_channel_identity_provider",
        )

    def get_channel_identity_by_provider(
        self,
        provider_type: str,
        provider_subject: str,
    ) -> ChannelIdentity | None:
        row = one_or_none(
            self.session,
            schema.channel_identity,
            schema.channel_identity.c.provider_type == provider_type,
            schema.channel_identity.c.provider_subject == provider_subject,
        )
        return _channel_identity(row) if row else None

    def get_channel_identity(self, channel_identity_id: str) -> ChannelIdentity | None:
        row = one_or_none(
            self.session,
            schema.channel_identity,
            schema.channel_identity.c.id == channel_identity_id,
        )
        return _channel_identity(row) if row else None

    def list_channel_identities(self, account_id: str) -> list[ChannelIdentity]:
        return [
            _channel_identity(row)
            for row in many(
                self.session,
                schema.channel_identity,
                schema.channel_identity.c.account_id == account_id,
                schema.channel_identity.c.lifecycle == "active",
                order_by=(
                    schema.channel_identity.c.created_at,
                    schema.channel_identity.c.id,
                ),
            )
        ]

    def add_artifact(self, artifact: AuthArtifact) -> None:
        insert_row(
            self.session,
            schema.auth_artifact,
            _artifact_values(artifact),
            {
                "pk_auth_artifact": "duplicate_artifact_id",
                "uq_auth_artifact_token_hash": "duplicate_artifact_code",
            },
            default_error="duplicate_artifact_code",
        )

    def get_artifact_by_code(self, code: str) -> AuthArtifact | None:
        row = one_or_none(
            self.session,
            schema.auth_artifact,
            schema.auth_artifact.c.token_hash == code,
        )
        return _artifact(row) if row else None

    def get_latest_unconsumed_artifact(
        self,
        *,
        account_id: str,
        artifact_type: str,
        purpose: str,
    ) -> AuthArtifact | None:
        row = (
            self.session.execute(
                sa.select(schema.auth_artifact)
                .where(
                    schema.auth_artifact.c.account_id == account_id,
                    schema.auth_artifact.c.type == artifact_type,
                    schema.auth_artifact.c.purpose == purpose,
                    schema.auth_artifact.c.consumed_at.is_(None),
                )
                .order_by(
                    schema.auth_artifact.c.created_at.desc(),
                    schema.auth_artifact.c.id.desc(),
                )
                .limit(1)
            )
            .mappings()
            .first()
        )
        return _artifact(row) if row else None

    def save_artifact(self, artifact: AuthArtifact) -> None:
        existing = self.get_artifact_by_code(artifact.code)
        if existing is None:
            raise ValueError("artifact_not_found")
        if (
            update_row(
                self.session,
                schema.auth_artifact,
                _artifact_values(artifact),
                {"uq_auth_artifact_token_hash": "duplicate_artifact_code"},
                default_error="duplicate_artifact_code",
            )
            == 0
        ):
            raise ValueError("artifact_not_found")

    def mark_usable_channel(self, account_id: str) -> None:
        return None

    def has_usable_channel(self, account_id: str) -> bool:
        row = one_or_none(
            self.session,
            schema.channel,
            schema.channel.c.account_id == account_id,
            schema.channel.c.lifecycle == "active",
            schema.channel.c.connection_state == "connected",
        )
        return row is not None


def _account_values(account: Account) -> dict:
    return {
        "id": account.id,
        "origin": account.origin,
        "default_timezone": account.default_timezone,
        "lifecycle": account.lifecycle,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


def _account(row: Mapping) -> Account:
    return Account(
        db_id(row["id"]),
        row["origin"],
        row["default_timezone"],
        row["lifecycle"],
        row["created_at"],
        row["updated_at"],
    )


def _activation_values(activation: AccountActivation) -> dict:
    return {
        "id": activation.id,
        "account_id": activation.account_id,
        "first_inbound_received_at": activation.first_inbound_received_at,
        "activation_completed_at": activation.activation_completed_at,
        "first_guidance_sent_at": activation.first_guidance_sent_at,
        "created_at": activation.created_at,
        "updated_at": activation.updated_at,
    }


def _activation(row: Mapping) -> AccountActivation:
    return AccountActivation(
        db_id(row["id"]),
        db_id(row["account_id"]),
        row["first_inbound_received_at"],
        row["activation_completed_at"],
        row["first_guidance_sent_at"],
        row["created_at"],
        row["updated_at"],
    )


def _access_values(access: AccountAccess) -> dict:
    return {
        "id": access.id,
        "account_id": access.account_id,
        "email_verification_state": access.email_verification_state,
        "subscription_state": access.subscription_state,
        "suspension_state": access.suspension_state,
        "access_allowed": access.access_allowed,
        "denial_reason": access.denial_reason,
        "created_at": access.created_at,
        "updated_at": access.updated_at,
    }


def _access(row: Mapping) -> AccountAccess:
    return AccountAccess(
        db_id(row["id"]),
        db_id(row["account_id"]),
        row["email_verification_state"],
        row["subscription_state"],
        row["suspension_state"],
        row["access_allowed"],
        row["denial_reason"],
        row["created_at"],
        row["updated_at"],
    )


def _credential_values(credential: Credential) -> dict:
    return {
        "id": credential.id,
        "account_id": credential.account_id,
        "email": credential.email.lower(),
        "password_hash": credential.password_hash,
        "email_verified_at": credential.email_verified_at,
        "reset_required": credential.reset_required,
        "created_at": credential.created_at,
        "updated_at": credential.updated_at,
    }


def _credential(row: Mapping) -> Credential:
    return Credential(
        db_id(row["id"]),
        db_id(row["account_id"]),
        row["email"],
        row["password_hash"],
        row["email_verified_at"],
        row["reset_required"],
        row["created_at"],
        row["updated_at"],
    )


def _session_values(session: Session) -> dict:
    return {
        "id": session.id,
        "account_id": session.account_id,
        "token_hash": session.token,
        "expires_at": session.expires_at,
        "revoked_at": session.revoked_at,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _session(row: Mapping) -> Session:
    return Session(
        db_id(row["id"]),
        db_id(row["account_id"]),
        row["token_hash"],
        row["expires_at"],
        row["revoked_at"],
        row["created_at"],
        row["updated_at"],
    )


def _channel_identity_values(identity: ChannelIdentity) -> dict:
    return {
        "id": identity.id,
        "account_id": identity.account_id,
        "provider_type": identity.provider_type,
        "provider_subject": identity.provider_subject,
        "lifecycle": identity.lifecycle,
        "is_account_anchor": identity.is_account_anchor,
        "created_at": identity.created_at,
        "updated_at": identity.updated_at,
    }


def _channel_identity(row: Mapping) -> ChannelIdentity:
    return ChannelIdentity(
        db_id(row["id"]),
        db_id(row["account_id"]),
        row["provider_type"],
        row["provider_subject"],
        row["lifecycle"],
        row["is_account_anchor"],
        row["created_at"],
        row["updated_at"],
    )


def _artifact_values(artifact: AuthArtifact) -> dict:
    return {
        "id": artifact.id,
        "account_id": artifact.account_id,
        "target_account_id": artifact.target_account_id,
        "type": artifact.type,
        "purpose": artifact.purpose,
        "delivery": artifact.delivery,
        "token_hash": artifact.code,
        "browser_session": artifact.browser_session,
        "continuation": dict(artifact.continuation),
        "expires_at": artifact.expires_at,
        "consumed_at": artifact.consumed_at,
        "delivery_state": artifact.delivery_state,
        "resend_count": artifact.resend_count,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


def _artifact(row: Mapping) -> AuthArtifact:
    return AuthArtifact(
        id=db_id(row["id"]),
        account_id=db_id(row["account_id"]) if row["account_id"] is not None else None,
        target_account_id=(
            db_id(row["target_account_id"])
            if row["target_account_id"] is not None
            else None
        ),
        type=row["type"],
        purpose=row["purpose"],
        delivery=row["delivery"],
        code=row["token_hash"],
        browser_session=row["browser_session"],
        continuation=dict(row["continuation"]),
        expires_at=row["expires_at"],
        consumed_at=row["consumed_at"],
        delivery_state=row["delivery_state"],
        resend_count=row["resend_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
