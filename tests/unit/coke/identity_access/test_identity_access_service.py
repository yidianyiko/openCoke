from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import UUID

import pytest

from coke.domains.identity_access.models import (
    ArtifactType,
    IdentityAccessError,
)
from coke.domains.identity_access.repository import InMemoryIdentityAccessRepository
from coke.domains.identity_access.service import IdentityAccessService

NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


class FakeEmailSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def send_verification(self, to: str, token: str, email: str) -> None:
        self.calls.append(
            ("verification", {"to": to, "token": token, "email": email})
        )

    def send_password_reset(self, to: str, token: str) -> None:
        self.calls.append(("password_reset", {"to": to, "token": token}))

    def send_claim(self, to: str, token: str) -> None:
        self.calls.append(("claim", {"to": to, "token": token}))


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


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
def email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def identity_service_with_email_sender(
    email_sender: FakeEmailSender,
) -> IdentityAccessService:
    return IdentityAccessService(
        repository=InMemoryIdentityAccessRepository(now=lambda: NOW),
        now=lambda: NOW,
        token_factory=sequence_factory("token"),
        id_factory=sequence_factory("id"),
        checkout_url_factory=lambda account_id: f"https://checkout.example/{account_id}",
        email_sender=email_sender,
    )


def test_register_web_account_creates_credential_session_and_verification_artifact(
    identity_service,
):
    result = identity_service.register_web_account(
        email="a@example.com",
        password="correct horse battery staple",
        display_name="Alice A",
        default_timezone="Asia/Tokyo",
    )

    assert result.account.origin == "web_first"
    assert result.account.default_timezone == "Asia/Tokyo"
    assert result.user_profile.account_id == result.account.id
    assert result.user_profile.nickname == "Alice A"
    assert result.credential.email == "a@example.com"
    assert result.credential.password_hash != "correct horse battery staple"
    assert result.credential.password_hash.startswith("$argon2")
    assert result.session.account_id == result.account.id
    assert result.email_verification.type == ArtifactType.EMAIL_VERIFICATION
    assert result.email_verification.account_id == result.account.id
    assert result.email_verification.delivery == "email"


def test_register_web_account_sends_verification_email_with_round_trip_token(
    identity_service_with_email_sender,
    email_sender,
):
    result = identity_service_with_email_sender.register_web_account(
        email="a@example.com",
        password="correct horse battery staple",
        display_name="Alice A",
    )

    assert email_sender.calls == [
        (
            "verification",
            {
                "to": "a@example.com",
                "token": result.email_verification.code,
                "email": "a@example.com",
            },
        )
    ]

    verified = identity_service_with_email_sender.verify_email(
        token=result.email_verification.code
    )

    assert verified.account_id == result.account.id
    assert verified.email == "a@example.com"


def test_register_web_account_rejects_blank_display_name(identity_service):
    with pytest.raises(IdentityAccessError, match="display_name_required"):
        identity_service.register_web_account(
            email="blank@example.com",
            password="correct horse battery staple",
            display_name="  ",
        )

    assert identity_service.repository.count_accounts() == 0


def test_login_reuses_existing_web_account_and_creates_session(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com", password="hash_1", display_name="Alice"
    )

    logged_in = identity_service.login(email="a@example.com", password="hash_1")

    assert logged_in.account.id == registered.account.id
    assert logged_in.session.account_id == registered.account.id


def test_real_service_creates_distinct_account_ids_session_tokens_and_artifact_codes(
    identity_service,
):
    first = identity_service.register_web_account(
        email="a@example.com", password="hash_1", display_name="Alice"
    )
    second = identity_service.register_web_account(
        email="b@example.com", password="hash_2", display_name="Bob"
    )
    login = identity_service.login(email="a@example.com", password="hash_1")
    first_reset = identity_service.issue_password_reset(email="a@example.com")
    second_reset = identity_service.issue_password_reset(email="a@example.com")

    assert first.account.id != second.account.id
    assert first.session.token != second.session.token
    assert login.session.token not in {first.session.token, second.session.token}
    assert first.email_verification.id != second.email_verification.id
    assert first.email_verification.code != second.email_verification.code
    assert first_reset.artifact.id != second_reset.artifact.id
    assert first_reset.code != second_reset.code


def test_issue_password_reset_sends_reset_email(
    identity_service_with_email_sender,
    email_sender,
):
    identity_service_with_email_sender.register_web_account(
        email="a@example.com", password="hash_1", display_name="Alice"
    )
    email_sender.calls.clear()

    reset = identity_service_with_email_sender.issue_password_reset(
        email="a@example.com"
    )

    assert email_sender.calls == [
        (
            "password_reset",
            {"to": "a@example.com", "token": reset.code},
        )
    ]


def test_resend_artifact_sends_email_matching_artifact_type(
    identity_service_with_email_sender,
    email_sender,
):
    registered = identity_service_with_email_sender.register_web_account(
        email="a@example.com", password="hash_1", display_name="Alice"
    )
    reset = identity_service_with_email_sender.issue_password_reset(
        email="a@example.com"
    )
    email_sender.calls.clear()

    resent_verification = identity_service_with_email_sender.resend_artifact(
        registered.email_verification.code
    )
    resent_reset = identity_service_with_email_sender.resend_artifact(reset.code)

    assert email_sender.calls == [
        (
            "verification",
            {
                "to": "a@example.com",
                "token": resent_verification.code,
                "email": "a@example.com",
            },
        ),
        (
            "password_reset",
            {"to": "a@example.com", "token": resent_reset.code},
        ),
    ]


def test_resend_email_verification_reuses_active_artifact_or_issues_fresh_one(
    identity_service_with_email_sender,
    email_sender,
):
    registered = identity_service_with_email_sender.register_web_account(
        email="a@example.com", password="hash_1", display_name="Alice"
    )
    email_sender.calls.clear()

    active = identity_service_with_email_sender.resend_email_verification(
        email="a@example.com"
    )

    assert active.code == registered.email_verification.code
    assert active.artifact.resend_count == 1
    assert email_sender.calls == [
        (
            "verification",
            {
                "to": "a@example.com",
                "token": registered.email_verification.code,
                "email": "a@example.com",
            },
        )
    ]

    identity_service_with_email_sender.verify_email(
        token=registered.email_verification.code
    )
    email_sender.calls.clear()

    fresh = identity_service_with_email_sender.resend_email_verification(
        email="a@example.com"
    )

    assert fresh.code != registered.email_verification.code
    assert fresh.artifact.resend_count == 0
    assert email_sender.calls == [
        (
            "verification",
            {
                "to": "a@example.com",
                "token": fresh.code,
                "email": "a@example.com",
            },
        )
    ]


def test_default_identity_access_ids_are_schema_uuid_strings():
    repository = InMemoryIdentityAccessRepository(now=lambda: NOW)
    service = IdentityAccessService(
        repository=repository,
        now=lambda: NOW,
        token_factory=sequence_factory("token"),
        checkout_url_factory=lambda account_id: f"https://checkout.example/{account_id}",
    )

    registered = service.register_web_account(
        email="uuid@example.com", password="hash_1", display_name="Uuid User"
    )
    resolved = service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    ids = [
        registered.account.id,
        registered.credential.id,
        registered.session.id,
        registered.email_verification.id,
        repository.get_activation(registered.account.id).id,
        repository.get_access(registered.account.id).id,
        repository.get_user_profile(registered.account.id).id,
        resolved.account.id,
        resolved.channel_identity.id,
        repository.get_activation(resolved.account.id).id,
        repository.get_access(resolved.account.id).id,
        repository.get_user_profile(resolved.account.id).id,
    ]
    for value in ids:
        assert UUID(value).hex == value


def test_repository_duplicate_guards_reject_silent_overwrites(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com", password="hash_1", display_name="Alice"
    )
    sender = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    with pytest.raises(ValueError, match="duplicate_account_id"):
        identity_service.repository.add_account(registered.account)

    with pytest.raises(ValueError, match="duplicate_session_token"):
        identity_service.repository.add_session(registered.session)

    with pytest.raises(ValueError, match="duplicate_artifact_code"):
        identity_service.repository.add_artifact(registered.email_verification)

    duplicate_provider_tuple = replace(
        sender.channel_identity,
        id="channel_identity_duplicate_provider",
    )
    with pytest.raises(ValueError, match="duplicate_channel_identity_provider"):
        identity_service.repository.add_channel_identity(duplicate_provider_tuple)

    assert identity_service.repository.count_accounts() == 2
    assert (
        identity_service.repository.get_session_by_token(registered.session.token)
        == registered.session
    )
    assert (
        identity_service.repository.get_artifact_by_code(
            registered.email_verification.code
        )
        == registered.email_verification
    )
    assert (
        identity_service.repository.get_channel_identity_by_provider(
            "whatsapp_evolution",
            "whatsapp:+15555550123",
        )
        == sender.channel_identity
    )


def test_login_rejects_unknown_or_wrong_password(identity_service):
    identity_service.register_web_account(
        email="a@example.com", password="hash_1", display_name="Alice"
    )

    with pytest.raises(IdentityAccessError, match="invalid_credentials"):
        identity_service.login(email="a@example.com", password="hash_2")

    with pytest.raises(IdentityAccessError, match="invalid_credentials"):
        identity_service.login(email="missing@example.com", password="hash_1")


def test_shared_whatsapp_first_seen_auto_provisions_one_messaging_account(
    identity_service,
):
    first = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        sender_display_name="Alice WhatsApp",
    )
    second = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    assert first.account.origin == "messaging_first"
    assert first.channel_identity.is_account_anchor is True
    assert identity_service.get_display_name(first.account.id) == "Alice WhatsApp"
    assert second.account.id == first.account.id
    assert second.channel_identity.id == first.channel_identity.id
    assert identity_service.repository.count_accounts() == 1


def test_shared_whatsapp_first_seen_uses_non_empty_fallback_display_name(
    identity_service,
):
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="wxid_lizihao",
        sender_display_name="  ",
    )

    display_name = identity_service.get_display_name(resolved.account.id)

    assert display_name
    assert display_name == "wxid_lizihao"


def test_non_whatsapp_first_seen_identity_fails_closed(identity_service):
    with pytest.raises(IdentityAccessError, match="identity_pairing_required"):
        identity_service.resolve_or_create_channel_identity(
            provider_type="wechat_personal",
            provider_subject="wxid_1",
        )

    assert identity_service.repository.count_accounts() == 0


def test_pairing_code_binds_first_seen_provider_identity_to_web_account(
    identity_service,
):
    registered = identity_service.register_web_account(
        email="a@example.com", password="hash_1", display_name="Alice"
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)

    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        pairing_code=pairing.code,
    )

    assert resolved.account.id == registered.account.id
    assert resolved.account.origin == "web_first"
    assert resolved.channel_identity.account_id == registered.account.id
    assert resolved.channel_identity.is_account_anchor is False
    assert identity_service.repository.count_accounts() == 1


def test_messaging_first_account_cannot_issue_pairing_code(identity_service):
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    with pytest.raises(IdentityAccessError, match="pairing_requires_web_first_account"):
        identity_service.issue_pairing_code(account_id=resolved.account.id)


@pytest.mark.parametrize(
    ("email_state", "subscription_state", "suspension_state", "reason"),
    [
        ("required", "active", "active", "email_verification_required"),
        ("verified", "inactive", "active", "subscription_inactive"),
        ("verified", "active", "suspended", "suspended"),
    ],
)
def test_pairing_code_issuance_requires_allowed_channel_connection_access(
    identity_service,
    email_state,
    subscription_state,
    suspension_state,
    reason,
):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state=email_state,
        subscription_state=subscription_state,
        suspension_state=suspension_state,
    )

    with pytest.raises(IdentityAccessError, match="access_denied") as exc_info:
        identity_service.issue_pairing_code(account_id=registered.account.id)

    assert exc_info.value.fact == {
        "type": "account_access_denied",
        "account_id": registered.account.id,
        "denial_reason": reason,
        "checkout_url": None,
    }


@pytest.mark.parametrize(
    ("email_state", "subscription_state", "suspension_state", "reason"),
    [
        ("required", "active", "active", "email_verification_required"),
        ("verified", "inactive", "active", "subscription_inactive"),
        ("verified", "active", "suspended", "suspended"),
    ],
)
def test_pairing_code_redemption_requires_allowed_channel_connection_access_before_consuming_artifact(
    identity_service,
    email_state,
    subscription_state,
    suspension_state,
    reason,
):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state=email_state,
        subscription_state=subscription_state,
        suspension_state=suspension_state,
    )

    with pytest.raises(IdentityAccessError, match="access_denied") as exc_info:
        identity_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
            pairing_code=pairing.code,
        )

    assert exc_info.value.fact == {
        "type": "account_access_denied",
        "account_id": registered.account.id,
        "denial_reason": reason,
        "checkout_url": None,
    }
    assert (
        identity_service.repository.get_channel_identity_by_provider(
            "whatsapp_evolution",
            "whatsapp:+15555550123",
        )
        is None
    )
    assert (
        identity_service.repository.get_artifact_by_code(pairing.code).consumed_at
        is None
    )

    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        pairing_code=pairing.code,
    )

    assert resolved.account.id == registered.account.id
    assert resolved.channel_identity.account_id == registered.account.id
    assert (
        identity_service.repository.get_artifact_by_code(pairing.code).consumed_at
        is not None
    )


def test_pairing_code_is_single_use(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)
    identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        pairing_code=pairing.code,
    )

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550124",
            pairing_code=pairing.code,
        )


def test_known_provider_identity_with_expired_pairing_code_fails_closed(
    identity_service,
):
    existing = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=2),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
            pairing_code=pairing.code,
        )

    identity = identity_service.repository.get_channel_identity_by_provider(
        "whatsapp_evolution",
        "whatsapp:+15555550123",
    )
    assert identity == existing.channel_identity
    assert identity.account_id == existing.account.id
    assert identity.account_id != registered.account.id
    assert (
        identity_service.repository.get_artifact_by_code(pairing.code).consumed_at
        is None
    )


def test_known_provider_identity_with_wrong_type_pairing_code_fails_closed(
    identity_service,
):
    existing = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    login_url = identity_service.issue_login_url(account_id=registered.account.id)

    with pytest.raises(IdentityAccessError, match="artifact_wrong_type"):
        identity_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
            pairing_code=login_url.code,
        )

    identity = identity_service.repository.get_channel_identity_by_provider(
        "whatsapp_evolution",
        "whatsapp:+15555550123",
    )
    assert identity == existing.channel_identity
    assert identity.account_id == existing.account.id
    assert identity.account_id != registered.account.id
    assert (
        identity_service.repository.get_artifact_by_code(login_url.code).consumed_at
        is None
    )


def test_known_provider_identity_with_consumed_pairing_code_fails_closed(
    identity_service,
):
    existing = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)
    identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550124",
        pairing_code=pairing.code,
    )

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
            pairing_code=pairing.code,
        )

    identity = identity_service.repository.get_channel_identity_by_provider(
        "whatsapp_evolution",
        "whatsapp:+15555550123",
    )
    assert identity == existing.channel_identity
    assert identity.account_id == existing.account.id
    assert identity.account_id != registered.account.id


def test_known_provider_identity_with_access_denied_pairing_code_fails_closed(
    identity_service,
):
    existing = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="inactive",
        suspension_state="active",
    )

    with pytest.raises(IdentityAccessError, match="access_denied") as exc_info:
        identity_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
            pairing_code=pairing.code,
        )

    assert exc_info.value.fact == {
        "type": "account_access_denied",
        "account_id": registered.account.id,
        "denial_reason": "subscription_inactive",
        "checkout_url": None,
    }
    identity = identity_service.repository.get_channel_identity_by_provider(
        "whatsapp_evolution",
        "whatsapp:+15555550123",
    )
    assert identity == existing.channel_identity
    assert identity.account_id == existing.account.id
    assert identity.account_id != registered.account.id
    assert (
        identity_service.repository.get_artifact_by_code(pairing.code).consumed_at
        is None
    )


def test_known_provider_identity_cannot_be_rebound_with_valid_pairing_code(
    identity_service,
):
    existing = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)

    with pytest.raises(IdentityAccessError, match="channel_identity_already_bound"):
        identity_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
            pairing_code=pairing.code,
        )

    identity = identity_service.repository.get_channel_identity_by_provider(
        "whatsapp_evolution",
        "whatsapp:+15555550123",
    )
    assert identity == existing.channel_identity
    assert identity.account_id == existing.account.id
    assert identity.account_id != registered.account.id
    assert (
        identity_service.repository.get_artifact_by_code(pairing.code).consumed_at
        is None
    )


def test_login_url_authenticates_bound_account_once(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    login_url = identity_service.issue_login_url(account_id=registered.account.id)

    redeemed = identity_service.redeem_login_url(
        token=login_url.code,
        browser_session="browser_1",
    )

    assert redeemed.account_id == registered.account.id
    assert redeemed.session.account_id == registered.account.id
    assert redeemed.continuation == {}

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.redeem_login_url(
            token=login_url.code,
            browser_session="browser_1",
        )


def test_web_claim_code_resolves_target_account_at_redemption(identity_service):
    sender = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    claim = identity_service.issue_web_claim_code(
        browser_session="browser_1",
        continuation={"friend_link_id": "fl_1"},
    )

    channel_redemption = identity_service.redeem_claim_code_from_channel(
        code=claim.code,
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    assert channel_redemption.account_id == sender.account.id
    assert channel_redemption.continuation == {"friend_link_id": "fl_1"}
    saved_artifact = identity_service.repository.get_artifact_by_code(claim.code)
    assert saved_artifact is not None
    assert saved_artifact.target_account_id == sender.account.id
    assert saved_artifact.consumed_at == NOW
    assert saved_artifact.delivery_state == "consumed"
    browser_completion = identity_service.complete_web_claim_from_browser(
        code=claim.code,
        browser_session="browser_1",
    )
    assert browser_completion.account_id == sender.account.id
    assert browser_completion.session.account_id == sender.account.id
    assert browser_completion.continuation == {"friend_link_id": "fl_1"}


def test_send_claim_email_delivers_existing_login_url_without_consuming_it(
    identity_service_with_email_sender,
    email_sender,
):
    resolved = identity_service_with_email_sender.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    login_url = identity_service_with_email_sender.issue_login_url(
        account_id=resolved.account.id
    )
    email_sender.calls.clear()

    claim = identity_service_with_email_sender.send_claim_email(
        token=login_url.code,
        email="claimant@example.com",
    )

    assert claim.code == login_url.code
    assert email_sender.calls == [
        (
            "claim",
            {"to": "claimant@example.com", "token": login_url.code},
        )
    ]
    redeemed = identity_service_with_email_sender.redeem_login_url(
        token=login_url.code,
        browser_session="browser_1",
    )
    assert redeemed.account_id == resolved.account.id


def test_send_claim_email_rejects_existing_web_account_email(
    identity_service_with_email_sender,
    email_sender,
):
    identity_service_with_email_sender.register_web_account(
        email="a@example.com",
        password="hash_1",
        display_name="Alice",
    )
    resolved = identity_service_with_email_sender.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    login_url = identity_service_with_email_sender.issue_login_url(
        account_id=resolved.account.id
    )
    email_sender.calls.clear()

    with pytest.raises(IdentityAccessError, match="email_already_registered"):
        identity_service_with_email_sender.send_claim_email(
            token=login_url.code,
            email="a@example.com",
        )

    assert email_sender.calls == []


def test_web_claim_code_does_not_send_email_for_channel_only_claim_flow(
    identity_service_with_email_sender,
    email_sender,
):
    claim = identity_service_with_email_sender.issue_web_claim_code(
        browser_session="browser_1",
        continuation={"friend_link_id": "fl_1"},
    )

    assert claim.code
    assert email_sender.calls == []


def test_deferred_friend_link_continuation_is_consumed_once_after_claim_completion(
    identity_service,
):
    sender = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    claim = identity_service.issue_web_claim_code(
        browser_session="browser_1",
        continuation={"friend_link_id": "fl_1", "next": "/channels"},
    )
    identity_service.redeem_claim_code_from_channel(
        code=claim.code,
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    identity_service.complete_web_claim_from_browser(
        code=claim.code,
        browser_session="browser_1",
    )

    first = identity_service.consume_deferred_friend_link_continuations(
        sender.account.id
    )
    second = identity_service.consume_deferred_friend_link_continuations(
        sender.account.id
    )

    assert first == ["fl_1"]
    assert second == []
    saved = identity_service.repository.get_artifact_by_code(claim.code)
    assert saved.continuation == {"next": "/channels"}


def test_claim_code_status_requires_original_browser_session(identity_service):
    claim = identity_service.issue_web_claim_code(browser_session="browser_1")

    with pytest.raises(IdentityAccessError, match="browser_session_mismatch"):
        identity_service.get_claim_code_status(
            code=claim.code,
            browser_session="browser_2",
        )


def test_claim_code_browser_completion_requires_original_browser_session(
    identity_service,
):
    identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    claim = identity_service.issue_web_claim_code(browser_session="browser_1")
    identity_service.redeem_claim_code_from_channel(
        code=claim.code,
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    with pytest.raises(IdentityAccessError, match="browser_session_mismatch"):
        identity_service.get_claim_code_status(
            code=claim.code,
            browser_session="browser_2",
        )

    with pytest.raises(IdentityAccessError, match="browser_session_mismatch"):
        identity_service.complete_web_claim_from_browser(
            code=claim.code,
            browser_session="browser_2",
        )

    completed = identity_service.complete_web_claim_from_browser(
        code=claim.code,
        browser_session="browser_1",
    )
    identity = identity_service.repository.get_channel_identity_by_provider(
        "whatsapp_evolution",
        "whatsapp:+15555550123",
    )

    assert identity is not None
    assert completed.account_id == identity.account_id


def test_claim_code_browser_completion_requires_channel_redemption(identity_service):
    claim = identity_service.issue_web_claim_code(browser_session="browser_1")

    with pytest.raises(IdentityAccessError, match="claim_not_redeemed"):
        identity_service.complete_web_claim_from_browser(
            code=claim.code,
            browser_session="browser_1",
        )


def test_claim_code_browser_completion_is_single_use(identity_service):
    identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    claim = identity_service.issue_web_claim_code(browser_session="browser_1")
    identity_service.redeem_claim_code_from_channel(
        code=claim.code,
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    identity_service.complete_web_claim_from_browser(
        code=claim.code,
        browser_session="browser_1",
    )

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.complete_web_claim_from_browser(
            code=claim.code,
            browser_session="browser_1",
        )


def test_claim_code_channel_redemption_is_single_use(identity_service):
    identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    claim = identity_service.issue_web_claim_code(browser_session="browser_1")
    identity_service.redeem_claim_code_from_channel(
        code=claim.code,
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.redeem_claim_code_from_channel(
            code=claim.code,
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
        )


def test_claim_code_wrong_type_and_expired_fail_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)

    with pytest.raises(IdentityAccessError, match="artifact_wrong_type"):
        identity_service.complete_web_claim_from_browser(
            code=pairing.code,
            browser_session="browser_1",
        )

    identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    claim = identity_service.issue_web_claim_code(browser_session="browser_1")
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=2),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.redeem_claim_code_from_channel(
            code=claim.code,
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
        )


def test_claim_code_requires_known_sender_identity_at_redemption(identity_service):
    claim = identity_service.issue_web_claim_code(browser_session="browser_1")

    with pytest.raises(IdentityAccessError, match="unknown_channel_identity"):
        identity_service.redeem_claim_code_from_channel(
            code=claim.code,
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
        )

    assert identity_service.repository.count_accounts() == 0


def test_wrong_type_and_expired_artifacts_fail_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)

    with pytest.raises(IdentityAccessError, match="artifact_wrong_type"):
        identity_service.redeem_login_url(
            token=pairing.code, browser_session="browser_1"
        )

    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=2),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550123",
            pairing_code=pairing.code,
        )


def test_verify_email_updates_credential_and_access_state(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )

    credential = identity_service.verify_email(token=registered.email_verification.code)
    access = identity_service.get_access_status(account_id=registered.account.id)

    assert credential.email_verified_at == NOW
    assert access.email_verification_state == "verified"
    assert access.access_allowed is True
    assert access.denial_reason is None


def test_verify_email_is_single_use(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )

    identity_service.verify_email(token=registered.email_verification.code)

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.verify_email(token=registered.email_verification.code)


def test_expired_email_verification_fails_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=25),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.verify_email(token=registered.email_verification.code)

    credential = identity_service.repository.get_credential_by_account(
        registered.account.id
    )
    assert credential.email_verified_at is None


def test_password_reset_hashes_new_password_and_login_uses_it(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="old-password",
    )
    reset = identity_service.issue_password_reset(email="a@example.com")

    credential = identity_service.reset_password(
        token=reset.code,
        password="new-password",
    )

    assert credential.account_id == registered.account.id
    assert credential.password_hash != "new-password"
    assert credential.password_hash.startswith("$argon2")
    assert credential.reset_required is False
    with pytest.raises(IdentityAccessError, match="invalid_credentials"):
        identity_service.login(email="a@example.com", password="old-password")
    logged_in = identity_service.login(email="a@example.com", password="new-password")
    assert logged_in.account.id == registered.account.id


def test_password_reset_is_single_use(identity_service):
    identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    reset = identity_service.issue_password_reset(email="a@example.com")

    identity_service.reset_password(token=reset.code, password="new-password")

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.reset_password(token=reset.code, password="newer-password")


def test_expired_password_reset_fails_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    reset = identity_service.issue_password_reset(email="a@example.com")
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=2),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.reset_password(token=reset.code, password="new-password")

    credential = identity_service.repository.get_credential_by_account(
        registered.account.id
    )
    assert credential.password_hash != "hash_1"
    assert credential.password_hash.startswith("$argon2")


def test_resend_artifact_increments_count_and_sets_pending(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    failed = replace(
        registered.email_verification,
        delivery_state="failed",
        resend_count=2,
    )
    identity_service.repository.save_artifact(failed)

    resent = identity_service.resend_artifact(code=registered.email_verification.code)

    assert resent.resend_count == 3
    assert resent.delivery_state == "pending"
    assert resent.updated_at == NOW


def test_resend_consumed_artifact_fails_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.verify_email(token=registered.email_verification.code)

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.resend_artifact(code=registered.email_verification.code)


def test_resend_expired_artifact_fails_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=25),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.resend_artifact(code=registered.email_verification.code)

    assert (
        identity_service.repository.get_artifact_by_code(
            registered.email_verification.code
        ).resend_count
        == 0
    )


def test_resend_non_resendable_artifact_type_fails_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    login_url = identity_service.issue_login_url(account_id=registered.account.id)

    with pytest.raises(IdentityAccessError, match="artifact_not_resendable"):
        identity_service.resend_artifact(code=login_url.code)

    assert (
        identity_service.repository.get_artifact_by_code(login_url.code).resend_count
        == 0
    )


def test_pairing_identity_collision_does_not_consume_artifact():
    channel_identity_ids = count(1)
    fallback_ids = count(1)

    def colliding_identity_id_factory(prefix: str) -> str:
        if prefix == "channel_identity":
            return f"channel_identity_collision_{next(channel_identity_ids) % 1}"
        return f"{prefix}_id_{next(fallback_ids)}"

    service = IdentityAccessService(
        repository=InMemoryIdentityAccessRepository(now=lambda: NOW),
        now=lambda: NOW,
        token_factory=sequence_factory("token"),
        id_factory=colliding_identity_id_factory,
        checkout_url_factory=lambda account_id: f"https://checkout.example/{account_id}",
    )
    service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    registered = service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = service.issue_pairing_code(account_id=registered.account.id)

    with pytest.raises(
        IdentityAccessError, match="channel_identity_write_conflict"
    ) as exc_info:
        service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="whatsapp:+15555550124",
            pairing_code=pairing.code,
        )

    assert exc_info.value.fact == {
        "type": "channel_identity_write_conflict",
        "provider_type": "whatsapp_evolution",
        "reason": "write_conflict",
    }
    assert service.repository.get_artifact_by_code(pairing.code).consumed_at is None
    assert (
        service.repository.get_channel_identity_by_provider(
            "whatsapp_evolution",
            "whatsapp:+15555550124",
        )
        is None
    )


def test_activation_web_first_requires_registration_channel_and_first_inbound(
    identity_service,
):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )

    assert (
        identity_service.get_activation(registered.account.id).activation_completed_at
        is None
    )

    identity_service.observe_usable_channel(account_id=registered.account.id)
    assert (
        identity_service.get_activation(registered.account.id).activation_completed_at
        is None
    )

    identity_service.mark_first_inbound_received(account_id=registered.account.id)

    activation = identity_service.get_activation(registered.account.id)
    assert activation.first_inbound_received_at == NOW
    assert activation.activation_completed_at == NOW


def test_activation_messaging_first_requires_anchor_channel_and_first_inbound(
    identity_service,
):
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    assert (
        identity_service.get_activation(resolved.account.id).activation_completed_at
        is None
    )

    identity_service.mark_first_inbound_received(account_id=resolved.account.id)
    assert (
        identity_service.get_activation(resolved.account.id).activation_completed_at
        is None
    )

    identity_service.observe_usable_channel(account_id=resolved.account.id)

    activation = identity_service.get_activation(resolved.account.id)
    assert activation.activation_completed_at == NOW


def test_first_guidance_is_marked_once(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )

    first = identity_service.mark_first_guidance_sent(account_id=registered.account.id)
    second = identity_service.mark_first_guidance_sent(account_id=registered.account.id)

    assert first.first_guidance_sent_at == NOW
    assert second.first_guidance_sent_at == NOW


def test_anchor_identity_cannot_be_removed_when_it_is_messaging_first_only_identity(
    identity_service,
):
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    assert (
        identity_service.can_remove_channel_identity(
            account_id=resolved.account.id,
            channel_identity_id=resolved.channel_identity.id,
        )
        is False
    )


def test_web_first_bound_identity_can_be_removed_by_channel_reachability(
    identity_service,
):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        pairing_code=pairing.code,
    )

    assert (
        identity_service.can_remove_channel_identity(
            account_id=registered.account.id,
            channel_identity_id=resolved.channel_identity.id,
        )
        is True
    )


def test_preview_pairing_code_account_returns_account_without_consuming(
    identity_service,
):
    registered = identity_service.register_web_account(
        email="preview@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)

    account_id = identity_service.preview_pairing_code_account(pairing.code)

    assert account_id == registered.account.id
    assert (
        identity_service.repository.get_artifact_by_code(pairing.code).consumed_at
        is None
    )


def test_preview_pairing_code_account_rejects_wrong_expired_or_consumed_artifact(
    identity_service,
):
    registered = identity_service.register_web_account(
        email="preview@example.com",
        password="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    login_url = identity_service.issue_login_url(account_id=registered.account.id)
    consumed = identity_service.issue_pairing_code(account_id=registered.account.id)
    identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
        pairing_code=consumed.code,
    )
    expiring = identity_service.issue_pairing_code(account_id=registered.account.id)
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=2),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_wrong_type"):
        identity_service.preview_pairing_code_account(login_url.code)

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.preview_pairing_code_account(consumed.code)

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.preview_pairing_code_account(expiring.code)
