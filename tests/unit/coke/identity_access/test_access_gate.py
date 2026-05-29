from __future__ import annotations

from datetime import UTC, datetime
from itertools import count

import pytest

from coke.domains.identity_access.models import AccessDeniedReason
from coke.domains.identity_access.repository import InMemoryIdentityAccessRepository
from coke.domains.identity_access.service import IdentityAccessService


NOW = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


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


def test_allowed_access_returns_allowed_decision(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )

    decision = identity_service.check_access_for_inbound(account_id=registered.account.id)

    assert decision.allowed is True
    assert decision.turn_trigger is None
    assert decision.fact is None


@pytest.mark.parametrize(
    ("email_state", "subscription_state", "suspension_state", "reason"),
    [
        ("required", "active", "active", AccessDeniedReason.EMAIL_VERIFICATION_REQUIRED),
        ("verified", "inactive", "active", AccessDeniedReason.SUBSCRIPTION_INACTIVE),
        ("verified", "active", "suspended", AccessDeniedReason.SUSPENDED),
    ],
)
def test_denied_access_returns_access_denied_turn_fact(
    identity_service,
    email_state,
    subscription_state,
    suspension_state,
    reason,
):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state=email_state,
        subscription_state=subscription_state,
        suspension_state=suspension_state,
    )

    decision = identity_service.check_access_for_inbound(account_id=registered.account.id)

    assert decision.allowed is False
    assert decision.turn_trigger == "AccessDeniedTurn"
    assert decision.fact == {
        "type": "account_access_denied",
        "account_id": registered.account.id,
        "denial_reason": reason,
        "checkout_url": None,
    }


def test_subscription_inactive_messaging_first_inbound_includes_checkout_url(identity_service):
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    identity_service.set_access_state(
        account_id=resolved.account.id,
        email_verification_state="verified",
        subscription_state="inactive",
        suspension_state="active",
    )

    decision = identity_service.check_access_for_inbound(account_id=resolved.account.id)

    assert decision.allowed is False
    assert decision.fact == {
        "type": "account_access_denied",
        "account_id": resolved.account.id,
        "denial_reason": AccessDeniedReason.SUBSCRIPTION_INACTIVE,
        "checkout_url": f"https://checkout.example/{resolved.account.id}",
    }


def test_access_gate_reusable_for_gated_web_actions(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="inactive",
        suspension_state="active",
    )

    channel_decision = identity_service.check_access_for_action(
        account_id=registered.account.id,
        action="connect_channel",
    )
    calendar_decision = identity_service.check_access_for_action(
        account_id=registered.account.id,
        action="calendar_import",
    )

    assert channel_decision.allowed is False
    assert channel_decision.fact["denial_reason"] == AccessDeniedReason.SUBSCRIPTION_INACTIVE
    assert calendar_decision.allowed is False
    assert calendar_decision.fact["denial_reason"] == AccessDeniedReason.SUBSCRIPTION_INACTIVE
