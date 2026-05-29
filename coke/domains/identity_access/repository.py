from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

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

    def get_channel_identity_by_provider(
        self,
        provider_type: str,
        provider_subject: str,
    ) -> ChannelIdentity | None: ...

    def get_channel_identity(self, channel_identity_id: str) -> ChannelIdentity | None: ...

    def list_channel_identities(self, account_id: str) -> list[ChannelIdentity]: ...

    def add_artifact(self, artifact: AuthArtifact) -> None: ...

    def get_artifact_by_code(self, code: str) -> AuthArtifact | None: ...

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

    def get_channel_identity_by_provider(
        self,
        provider_type: str,
        provider_subject: str,
    ) -> ChannelIdentity | None:
        return self.channel_identities_by_provider.get((provider_type, provider_subject))

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

    def save_artifact(self, artifact: AuthArtifact) -> None:
        if artifact.code not in self.artifacts_by_code:
            raise ValueError("artifact_not_found")
        self.artifacts_by_code[artifact.code] = artifact

    def mark_usable_channel(self, account_id: str) -> None:
        self.usable_channel_accounts.add(account_id)

    def has_usable_channel(self, account_id: str) -> bool:
        return account_id in self.usable_channel_accounts
