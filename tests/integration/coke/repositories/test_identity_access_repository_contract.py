from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from coke.domains.identity_access.models import (
    Account,
    AccountAccess,
    AccountActivation,
    AuthArtifact,
    ChannelIdentity,
    Credential,
    Session,
)
from coke.domains.identity_access.repository import (
    InMemoryIdentityAccessRepository,
    PostgresIdentityAccessRepository,
)

from .conftest import ACCOUNT_A, ACCOUNT_B, CHANNEL_IDENTITY_A, NOW


def _account(account_id: str = ACCOUNT_A) -> Account:
    return Account(account_id, "web_first", "UTC", "active", NOW, NOW)


def _activation(account_id: str = ACCOUNT_A) -> AccountActivation:
    return AccountActivation(
        "90000000000000000000000000000001",
        account_id,
        None,
        None,
        None,
        NOW,
        NOW,
    )


def _access(account_id: str = ACCOUNT_A) -> AccountAccess:
    return AccountAccess(
        "90000000000000000000000000000002",
        account_id,
        "verified",
        "active",
        "active",
        True,
        None,
        NOW,
        NOW,
    )


def _credential(account_id: str = ACCOUNT_A) -> Credential:
    return Credential(
        "90000000000000000000000000000003",
        account_id,
        "user@example.com",
        "hash",
        None,
        False,
        NOW,
        NOW,
    )


def _session(account_id: str = ACCOUNT_A) -> Session:
    return Session(
        "90000000000000000000000000000004",
        account_id,
        "token-hash",
        NOW + timedelta(days=1),
        None,
        NOW,
        NOW,
    )


def _channel_identity(account_id: str = ACCOUNT_A) -> ChannelIdentity:
    return ChannelIdentity(
        CHANNEL_IDENTITY_A,
        account_id,
        "whatsapp_evolution",
        "whatsapp:+15555550123",
        "active",
        True,
        NOW,
        NOW,
    )


def _artifact(account_id: str = ACCOUNT_A) -> AuthArtifact:
    return AuthArtifact(
        id="90000000000000000000000000000005",
        account_id=account_id,
        target_account_id=None,
        type="email_verification",
        purpose="verify_email",
        delivery="email",
        code="artifact-code-hash",
        browser_session=None,
        continuation={"next": "settings"},
        expires_at=NOW + timedelta(hours=1),
        consumed_at=None,
        delivery_state="pending",
        resend_count=0,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture(params=["memory", "postgres"])
def repository(request, postgres_session):
    if request.param == "memory":
        return InMemoryIdentityAccessRepository()
    return PostgresIdentityAccessRepository(postgres_session)


def test_identity_records_round_trip(repository) -> None:
    account = _account()
    activation = _activation()
    access = _access()
    credential = _credential()
    session = _session()
    identity = _channel_identity()
    artifact = _artifact()

    repository.add_account(account)
    repository.add_activation(activation)
    repository.add_access(access)
    repository.add_credential(credential)
    repository.add_session(session)
    repository.add_channel_identity(identity)
    repository.add_artifact(artifact)

    assert repository.count_accounts() == 1
    assert repository.get_account(account.id) == account
    assert repository.get_activation(account.id) == activation
    assert repository.get_access(account.id) == access
    assert repository.get_credential_by_email("user@example.com") == credential
    assert repository.get_credential_by_account(account.id) == credential
    assert repository.get_session_by_token(session.token) == session
    assert repository.get_channel_identity(identity.id) == identity
    assert (
        repository.get_channel_identity_by_provider(
            "whatsapp_evolution", "whatsapp:+15555550123"
        )
        == identity
    )
    assert repository.list_channel_identities(account.id) == [identity]
    assert repository.get_artifact_by_code(artifact.code) == artifact


def test_identity_uniqueness_errors_match_in_memory(repository) -> None:
    account = _account()
    repository.add_account(account)
    repository.add_credential(_credential())
    repository.add_session(_session())
    repository.add_channel_identity(_channel_identity())
    repository.add_artifact(_artifact())

    with pytest.raises(ValueError, match="duplicate_credential_email"):
        repository.add_credential(
            replace(
                _credential(ACCOUNT_B),
                id="90000000000000000000000000000006",
                email="user@example.com",
            )
        )

    with pytest.raises(ValueError, match="duplicate_session_token"):
        repository.add_session(
            replace(_session(), id="90000000000000000000000000000007")
        )

    with pytest.raises(ValueError, match="duplicate_channel_identity_provider"):
        repository.add_channel_identity(
            replace(
                _channel_identity(),
                id="90000000000000000000000000000008",
            )
        )

    with pytest.raises(ValueError, match="duplicate_artifact_code"):
        repository.add_artifact(
            replace(_artifact(), id="90000000000000000000000000000009")
        )


def test_identity_save_methods_require_existing_records(repository) -> None:
    with pytest.raises(ValueError, match="activation_not_found"):
        repository.save_activation(_activation())
    with pytest.raises(ValueError, match="access_not_found"):
        repository.save_access(_access())
    with pytest.raises(ValueError, match="credential_not_found"):
        repository.save_credential(_credential())
    with pytest.raises(ValueError, match="artifact_not_found"):
        repository.save_artifact(_artifact())

    repository.add_account(_account())
    repository.add_activation(_activation())
    updated_activation = replace(_activation(), first_inbound_received_at=NOW)
    repository.save_activation(updated_activation)
    assert repository.get_activation(ACCOUNT_A) == updated_activation
