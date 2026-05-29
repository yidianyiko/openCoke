# Coke Clean Rebuild IdentityAccess Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the clean-rebuild IdentityAccess domain contract for accounts, access gating, activation, channel identity ownership, auth artifacts, and lightweight auth/claim API routes without implementing provider, channel lifecycle, worker, or web behavior.

**Architecture:** IdentityAccess is an in-process Python domain module backed first by dataclasses and a protocol-friendly in-memory repository, so the domain contract can be tested before SQLAlchemy persistence is wired. Flask routes are thin adapters that call service methods and return JSON facts; they never write tables directly. ChannelReachability remains responsible for `channel`, `delivery_route`, and `delivery_attempt`; this slice only stores reusable reachability signals needed to compute activation and expose anchor-removal checks.

**Tech Stack:** Python 3.12, Flask blueprints, dataclasses, pytest, existing `coke` backend package, existing clean schema tables in `coke/schema.py`.

---

**Plan Status:** ready for execution
**Status Date:** 2026-05-29
**Parent Plan:** `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md`, Task 4: IdentityAccess, Access Gate, Activation, And Web Claim

**Source Specs:**
- `docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`
- `docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`

**Freshness Check:** Before executing, compare this plan against current `main`, `docs/ARCHITECTURE.md`, `docs/design-docs/interface-contract.md`, `docs/product-specs/FEATURE_TREE.md`, and `coke/schema.py`.

## Scope

In scope:

- Account origin contract: `web_first` and `messaging_first`.
- Minimal web-first credential and session service behavior.
- Shared WhatsApp first-seen sender auto-provisioning through `whatsapp_evolution` only.
- Known provider identity resolution without duplicate accounts.
- Pairing-code binding of a first-seen provider identity to an existing web-first account.
- Fail-closed access gate for inbound turns and gated web actions.
- Pairing-code issuance and redemption gated by `check_access_for_action(account_id, "connect_channel")`.
- `AccessDeniedTurn` structured facts with denial reasons `email_verification_required`, `subscription_inactive`, and `suspended`.
- Activation projection fields: `first_inbound_received_at`, `activation_completed_at`, `first_guidance_sent_at`.
- Auth artifact domain contract for `login_url`, `claim_code`, `pairing_code`, `email_verification`, and `password_reset`.
- One-time, time-limited, single-use artifact behavior with delivery state and resend count.
- Web-initiated `claim_code` split flow: browser issuance, channel-side account resolution, and original-browser-only session completion.
- Channel identity ownership and anchor protection checks.
- Thin Flask blueprints under `/api/auth/*` and `/api/claim/*`.

Out of scope:

- SQLAlchemy persistence implementation for IdentityAccess.
- Password hashing infrastructure beyond injected stable password hash strings used by tests.
- Email provider delivery.
- Provider adapters.
- `channel`, `delivery_route`, and `delivery_attempt` lifecycle behavior.
- ConversationRuntime, The Turn renderer, normal assistant intent execution, worker code, scheduler code, Redis work queues, and web UI.
- Account merging, account unlinking, display-name matching, profile similarity matching, and legacy compatibility routes.

## File Structure

- Create `coke/domains/__init__.py`: marks Python domain package.
- Create `coke/domains/identity_access/__init__.py`: exports public IdentityAccess service/model classes.
- Create `coke/domains/identity_access/models.py`: dataclasses, literal constants, result objects, and domain exceptions.
- Create `coke/domains/identity_access/repository.py`: protocol-style repository boundary plus in-memory repository used by unit tests.
- Create `coke/domains/identity_access/service.py`: IdentityAccess application/domain service methods.
- Create `coke/api/__init__.py`: marks Python API package.
- Create `coke/api/auth_routes.py`: auth/access Flask blueprint factory that depends on a service object.
- Create `coke/api/claim_routes.py`: web-claim and pairing Flask blueprint factory that depends on a service object.
- Modify `coke/app.py`: register auth and claim blueprints only when an `identity_access_service` is passed to `create_app`.
- Create `tests/unit/coke/identity_access/test_identity_access_service.py`: account, identity, artifact, activation, and anchor contract tests.
- Create `tests/unit/coke/identity_access/test_access_gate.py`: fail-closed gate contract tests.
- Create `tests/unit/coke/identity_access/test_auth_routes.py`: fake-service route adapter tests.

## Execution Preflight

- [ ] **Step 1: Enter the requested worktree**

Run:

```bash
cd /data/projects/coke/.worktrees/clean-rebuild-exec
git status --short
```

Expected: no output, or only changes you intentionally own for this task. If unrelated changes exist, leave them in place and avoid editing those files.

- [ ] **Step 2: Select the Python command**

Run:

```bash
python_cmd=".venv/bin/python"
if [[ ! -x "$python_cmd" ]]; then
  python_cmd="python3"
fi
printf '%s\n' "$python_cmd"
```

Expected: prints `.venv/bin/python` when the virtualenv exists, otherwise `python3`.

- [ ] **Step 3: Verify the current backend surface before edits**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/test_backend_foundation.py tests/unit/coke/test_clean_schema_contract.py -v
```

Expected: all selected tests pass before IdentityAccess files are added.

## Task 1: IdentityAccess Service Contract Tests

**Files:**
- Create: `tests/unit/coke/identity_access/test_identity_access_service.py`

- [ ] **Step 1: Create the failing service tests**

Create `tests/unit/coke/identity_access/test_identity_access_service.py`:

```python
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from coke.domains.identity_access.models import (
    ArtifactType,
    IdentityAccessError,
)
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


def test_register_web_account_creates_credential_session_and_verification_artifact(identity_service):
    result = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
        default_timezone="Asia/Tokyo",
    )

    assert result.account.origin == "web_first"
    assert result.account.default_timezone == "Asia/Tokyo"
    assert result.credential.email == "a@example.com"
    assert result.credential.password_hash == "hash_1"
    assert result.session.account_id == result.account.id
    assert result.email_verification.type == ArtifactType.EMAIL_VERIFICATION
    assert result.email_verification.account_id == result.account.id
    assert result.email_verification.delivery == "email"


def test_login_reuses_existing_web_account_and_creates_session(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )

    logged_in = identity_service.login(email="a@example.com", password_hash="hash_1")

    assert logged_in.account.id == registered.account.id
    assert logged_in.session.account_id == registered.account.id


def test_real_service_creates_distinct_account_ids_session_tokens_and_artifact_codes(identity_service):
    first = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )
    second = identity_service.register_web_account(
        email="b@example.com",
        password_hash="hash_2",
    )
    login = identity_service.login(email="a@example.com", password_hash="hash_1")
    first_reset = identity_service.issue_password_reset(email="a@example.com")
    second_reset = identity_service.issue_password_reset(email="a@example.com")

    assert first.account.id != second.account.id
    assert first.session.token != second.session.token
    assert login.session.token not in {first.session.token, second.session.token}
    assert first.email_verification.id != second.email_verification.id
    assert first.email_verification.code != second.email_verification.code
    assert first_reset.artifact.id != second_reset.artifact.id
    assert first_reset.code != second_reset.code


def test_login_rejects_unknown_or_wrong_password(identity_service):
    identity_service.register_web_account(email="a@example.com", password_hash="hash_1")

    with pytest.raises(IdentityAccessError, match="invalid_credentials"):
        identity_service.login(email="a@example.com", password_hash="hash_2")

    with pytest.raises(IdentityAccessError, match="invalid_credentials"):
        identity_service.login(email="missing@example.com", password_hash="hash_1")


def test_shared_whatsapp_first_seen_auto_provisions_one_messaging_account(identity_service):
    first = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )
    second = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    assert first.account.origin == "messaging_first"
    assert first.channel_identity.is_account_anchor is True
    assert second.account.id == first.account.id
    assert second.channel_identity.id == first.channel_identity.id
    assert identity_service.repository.count_accounts() == 1


def test_non_whatsapp_first_seen_identity_fails_closed(identity_service):
    with pytest.raises(IdentityAccessError, match="identity_pairing_required"):
        identity_service.resolve_or_create_channel_identity(
            provider_type="wechat_personal",
            provider_subject="wxid_1",
        )

    assert identity_service.repository.count_accounts() == 0


def test_pairing_code_binds_first_seen_provider_identity_to_web_account(identity_service):
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
        password_hash="hash_1",
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
        password_hash="hash_1",
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
    assert identity_service.repository.get_artifact_by_code(pairing.code).consumed_at is None

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
    assert identity_service.repository.get_artifact_by_code(pairing.code).consumed_at is not None


def test_pairing_code_is_single_use(identity_service):
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


def test_login_url_authenticates_bound_account_once(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
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


def test_claim_code_status_requires_original_browser_session(identity_service):
    claim = identity_service.issue_web_claim_code(browser_session="browser_1")

    with pytest.raises(IdentityAccessError, match="browser_session_mismatch"):
        identity_service.get_claim_code_status(
            code=claim.code,
            browser_session="browser_2",
        )


def test_claim_code_browser_completion_requires_original_browser_session(identity_service):
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
        password_hash="hash_1",
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
        password_hash="hash_1",
    )
    identity_service.set_access_state(
        account_id=registered.account.id,
        email_verification_state="verified",
        subscription_state="active",
        suspension_state="active",
    )
    pairing = identity_service.issue_pairing_code(account_id=registered.account.id)

    with pytest.raises(IdentityAccessError, match="artifact_wrong_type"):
        identity_service.redeem_login_url(token=pairing.code, browser_session="browser_1")

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
        password_hash="hash_1",
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
        password_hash="hash_1",
    )

    identity_service.verify_email(token=registered.email_verification.code)

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.verify_email(token=registered.email_verification.code)


def test_expired_email_verification_fails_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=25),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.verify_email(token=registered.email_verification.code)

    credential = identity_service.repository.get_credential_by_account(registered.account.id)
    assert credential.email_verified_at is None


def test_password_reset_updates_password_hash(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )
    reset = identity_service.issue_password_reset(email="a@example.com")

    credential = identity_service.reset_password(
        token=reset.code,
        password_hash="hash_2",
    )

    assert credential.account_id == registered.account.id
    assert credential.password_hash == "hash_2"
    assert credential.reset_required is False


def test_password_reset_is_single_use(identity_service):
    identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )
    reset = identity_service.issue_password_reset(email="a@example.com")

    identity_service.reset_password(token=reset.code, password_hash="hash_2")

    with pytest.raises(IdentityAccessError, match="artifact_consumed"):
        identity_service.reset_password(token=reset.code, password_hash="hash_3")


def test_expired_password_reset_fails_closed(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )
    reset = identity_service.issue_password_reset(email="a@example.com")
    expired_service = IdentityAccessService(
        repository=identity_service.repository,
        now=lambda: NOW + timedelta(hours=2),
        token_factory=sequence_factory("late_token"),
        id_factory=sequence_factory("late_id"),
    )

    with pytest.raises(IdentityAccessError, match="artifact_expired"):
        expired_service.reset_password(token=reset.code, password_hash="hash_2")

    credential = identity_service.repository.get_credential_by_account(registered.account.id)
    assert credential.password_hash == "hash_1"


def test_resend_artifact_increments_count_and_sets_pending(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
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


def test_activation_web_first_requires_registration_channel_and_first_inbound(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )

    assert identity_service.get_activation(registered.account.id).activation_completed_at is None

    identity_service.observe_usable_channel(account_id=registered.account.id)
    assert identity_service.get_activation(registered.account.id).activation_completed_at is None

    identity_service.mark_first_inbound_received(account_id=registered.account.id)

    activation = identity_service.get_activation(registered.account.id)
    assert activation.first_inbound_received_at == NOW
    assert activation.activation_completed_at == NOW


def test_activation_messaging_first_requires_anchor_channel_and_first_inbound(identity_service):
    resolved = identity_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="whatsapp:+15555550123",
    )

    assert identity_service.get_activation(resolved.account.id).activation_completed_at is None

    identity_service.mark_first_inbound_received(account_id=resolved.account.id)
    assert identity_service.get_activation(resolved.account.id).activation_completed_at is None

    identity_service.observe_usable_channel(account_id=resolved.account.id)

    activation = identity_service.get_activation(resolved.account.id)
    assert activation.activation_completed_at == NOW


def test_first_guidance_is_marked_once(identity_service):
    registered = identity_service.register_web_account(
        email="a@example.com",
        password_hash="hash_1",
    )

    first = identity_service.mark_first_guidance_sent(account_id=registered.account.id)
    second = identity_service.mark_first_guidance_sent(account_id=registered.account.id)

    assert first.first_guidance_sent_at == NOW
    assert second.first_guidance_sent_at == NOW


def test_anchor_identity_cannot_be_removed_when_it_is_messaging_first_only_identity(identity_service):
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


def test_web_first_bound_identity_can_be_removed_by_channel_reachability(identity_service):
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
```

- [ ] **Step 2: Run the service tests and verify they fail**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_identity_access_service.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'coke.domains'`.

## Task 2: Access Gate Tests

**Files:**
- Create: `tests/unit/coke/identity_access/test_access_gate.py`

- [ ] **Step 1: Create the failing access-gate tests**

Create `tests/unit/coke/identity_access/test_access_gate.py`:

```python
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
```

- [ ] **Step 2: Run the access-gate tests and verify they fail**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_access_gate.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'coke.domains'`.

## Task 3: IdentityAccess Models

**Files:**
- Create: `coke/domains/__init__.py`
- Create: `coke/domains/identity_access/__init__.py`
- Create: `coke/domains/identity_access/models.py`

- [ ] **Step 1: Create the domain package files**

Create `coke/domains/__init__.py`:

```python
"""Coke bounded domain modules."""
```

Create `coke/domains/identity_access/__init__.py`:

```python
from coke.domains.identity_access.models import (
    AccessDecision,
    AccessDeniedReason,
    Account,
    AccountAccess,
    AccountActivation,
    ArtifactType,
    AuthArtifact,
    ChannelClaimRedemption,
    ChannelIdentity,
    ClaimCodeStatus,
    Credential,
    IdentityAccessError,
    Session,
)
from coke.domains.identity_access.repository import (
    IdentityAccessRepository,
    InMemoryIdentityAccessRepository,
)
from coke.domains.identity_access.service import IdentityAccessService

__all__ = [
    "AccessDecision",
    "AccessDeniedReason",
    "Account",
    "AccountAccess",
    "AccountActivation",
    "ArtifactType",
    "AuthArtifact",
    "ChannelIdentity",
    "ChannelClaimRedemption",
    "ClaimCodeStatus",
    "Credential",
    "IdentityAccessError",
    "IdentityAccessRepository",
    "InMemoryIdentityAccessRepository",
    "Session",
    "IdentityAccessService",
]
```

Create `coke/domains/identity_access/models.py`:

```python
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
```

- [ ] **Step 2: Run the existing failing tests**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_identity_access_service.py tests/unit/coke/identity_access/test_access_gate.py -v
```

Expected: FAIL because `coke.domains.identity_access.repository` does not exist.

## Task 4: Repository Protocol And In-Memory Boundary

**Files:**
- Create: `coke/domains/identity_access/repository.py`

- [ ] **Step 1: Create the repository implementation**

Create `coke/domains/identity_access/repository.py`:

```python
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
```

- [ ] **Step 2: Run the tests and verify the next failure**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_identity_access_service.py tests/unit/coke/identity_access/test_access_gate.py -v
```

Expected: FAIL because `coke.domains.identity_access.service` does not exist.

## Task 5: IdentityAccess Service

**Files:**
- Create: `coke/domains/identity_access/service.py`

- [ ] **Step 1: Create the service implementation**

Create `coke/domains/identity_access/service.py`:

```python
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
        self._checkout_url_factory = checkout_url_factory or (lambda account_id: f"https://checkout.example/{account_id}")

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
        existing = self.repository.get_channel_identity_by_provider(provider_type, provider_subject)
        if existing is not None:
            return ChannelIdentityResolution(
                account=self._require_account(existing.account_id),
                channel_identity=existing,
                created_account=False,
            )

        if pairing_code is not None:
            artifact = self._require_unconsumed_artifact(pairing_code, expected_type=ArtifactType.PAIRING_CODE)
            if artifact.account_id is None:
                raise IdentityAccessError("artifact_missing_account")
            account = self._require_account(artifact.account_id)
            access_decision = self.check_access_for_action(
                account_id=account.id,
                action="connect_channel",
            )
            if not access_decision.allowed:
                raise IdentityAccessError("access_denied", fact=access_decision.fact)
            self._consume_artifact(pairing_code, expected_type=ArtifactType.PAIRING_CODE)
            identity = self._create_channel_identity(
                account_id=account.id,
                provider_type=provider_type,
                provider_subject=provider_subject,
                is_account_anchor=False,
            )
            return ChannelIdentityResolution(
                account=account,
                channel_identity=identity,
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
                denial_reason=AccessDeniedReason.EMAIL_VERIFICATION_REQUIRED if origin == "web_first" else None,
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
        identity = ChannelIdentity(
            id=self._id_factory("channel_identity"),
            account_id=account_id,
            provider_type=provider_type,
            provider_subject=provider_subject,
            lifecycle="active",
            is_account_anchor=is_account_anchor,
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.add_channel_identity(identity)
        return identity

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
```

- [ ] **Step 2: Run the domain tests**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_identity_access_service.py tests/unit/coke/identity_access/test_access_gate.py -v
```

Expected: PASS for both test files.

- [ ] **Step 3: Commit the domain-service slice**

Run:

```bash
git add coke/domains tests/unit/coke/identity_access/test_identity_access_service.py tests/unit/coke/identity_access/test_access_gate.py
git commit -m "feat: add identity access domain service"
```

Expected: commit succeeds with only IdentityAccess domain package files and domain/access-gate tests.

## Task 6: Auth And Claim Route Adapter Tests

**Files:**
- Create: `tests/unit/coke/identity_access/test_auth_routes.py`

- [ ] **Step 1: Create route tests with a fake service**

Create `tests/unit/coke/identity_access/test_auth_routes.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from coke.app import create_app
from coke.api.auth_routes import create_auth_blueprint
from coke.api.claim_routes import create_claim_blueprint
from coke.config import Settings
from coke.domains.identity_access.models import IdentityAccessError


class FakeObject(SimpleNamespace):
    pass


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.account = FakeObject(id="acct_1", origin="web_first")
        self.session = FakeObject(id="sess_1", account_id="acct_1", token="session_token")

    def register_web_account(self, email, password_hash, default_timezone="UTC"):
        self.calls.append(
            (
                "register_web_account",
                {
                    "email": email,
                    "password_hash": password_hash,
                    "default_timezone": default_timezone,
                },
            )
        )
        return FakeObject(
            id="registration_result",
            account=self.account,
            session=self.session,
            email_verification=FakeObject(id="artifact_1"),
        )

    def login(self, email, password_hash):
        self.calls.append(("login", {"email": email, "password_hash": password_hash}))
        return FakeObject(id="login_result", account=self.account, session=self.session)

    def verify_email(self, token):
        self.calls.append(("verify_email", {"token": token}))
        return FakeObject(id="credential_1", account_id="acct_1", email="a@example.com")

    def issue_password_reset(self, email):
        self.calls.append(("issue_password_reset", {"email": email}))
        return FakeObject(code="reset_token", artifact=FakeObject(id="artifact_2"))

    def reset_password(self, token, password_hash):
        self.calls.append(
            (
                "reset_password",
                {
                    "token": token,
                    "password_hash": password_hash,
                },
            )
        )
        return FakeObject(id="credential_1", account_id="acct_1", email="a@example.com")

    def current_user(self, session_token):
        self.calls.append(("current_user", {"session_token": session_token}))
        return self.account

    def get_access_status(self, account_id):
        self.calls.append(("get_access_status", {"account_id": account_id}))
        return FakeObject(
            id="access_1",
            account_id=account_id,
            access_allowed=True,
            denial_reason=None,
        )

    def redeem_login_url(self, token, browser_session):
        self.calls.append(
            (
                "redeem_login_url",
                {
                    "token": token,
                    "browser_session": browser_session,
                },
            )
        )
        return FakeObject(account_id="acct_1", session=self.session, continuation={"next": "/channels"})

    def issue_web_claim_code(self, browser_session, continuation=None):
        self.calls.append(
            (
                "issue_web_claim_code",
                {
                    "browser_session": browser_session,
                    "continuation": continuation or {},
                },
            )
        )
        return FakeObject(code="claim_code", artifact=FakeObject(id="artifact_3"))

    def get_claim_code_status(self, code, browser_session):
        self.calls.append(
            (
                "get_claim_code_status",
                {
                    "code": code,
                    "browser_session": browser_session,
                },
            )
        )
        return FakeObject(
            found=True,
            consumed=False,
            target_account_id=None,
            delivery_state="pending",
        )

    def redeem_claim_code_from_channel(self, code, provider_type, provider_subject):
        self.calls.append(
            (
                "redeem_claim_code_from_channel",
                {
                    "code": code,
                    "provider_type": provider_type,
                    "provider_subject": provider_subject,
                },
            )
        )
        return FakeObject(account_id="acct_1", continuation={"friend_link_id": "fl_1"})

    def complete_web_claim_from_browser(self, code, browser_session):
        self.calls.append(
            (
                "complete_web_claim_from_browser",
                {
                    "code": code,
                    "browser_session": browser_session,
                },
            )
        )
        return FakeObject(account_id="acct_1", session=self.session, continuation={"friend_link_id": "fl_1"})

    def issue_pairing_code(self, account_id):
        self.calls.append(("issue_pairing_code", {"account_id": account_id}))
        return FakeObject(code="pairing_code", artifact=FakeObject(id="artifact_4"))

    def resolve_or_create_channel_identity(self, provider_type, provider_subject, pairing_code=None):
        self.calls.append(
            (
                "resolve_or_create_channel_identity",
                {
                    "provider_type": provider_type,
                    "provider_subject": provider_subject,
                    "pairing_code": pairing_code,
                },
            )
        )
        return FakeObject(account=self.account, channel_identity=FakeObject(id="ci_1", account_id="acct_1"))


class ErrorService(FakeService):
    def login(self, email, password_hash):
        raise IdentityAccessError("invalid_credentials")

    def redeem_claim_code_from_channel(self, code, provider_type, provider_subject):
        raise IdentityAccessError("unknown_channel_identity")

    def issue_pairing_code(self, account_id):
        raise IdentityAccessError("pairing_requires_web_first_account")


class AccessDeniedService(FakeService):
    def issue_pairing_code(self, account_id):
        raise IdentityAccessError(
            "access_denied",
            fact={
                "type": "account_access_denied",
                "account_id": account_id,
                "denial_reason": "email_verification_required",
                "checkout_url": None,
            },
        )


class PairingRedemptionAccessDeniedService(FakeService):
    def resolve_or_create_channel_identity(self, provider_type, provider_subject, pairing_code=None):
        raise IdentityAccessError(
            "access_denied",
            fact={
                "type": "account_access_denied",
                "account_id": "acct_1",
                "denial_reason": "subscription_inactive",
                "checkout_url": None,
            },
        )


def make_client(service=None):
    service = service or FakeService()
    app = Flask(__name__)
    app.register_blueprint(create_auth_blueprint(service))
    app.register_blueprint(create_claim_blueprint(service))
    return app.test_client(), service


def make_factory_client(service=None):
    service = service or FakeService()
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            app_env="test",
        ),
        identity_access_service=service,
    )
    return app.test_client(), service


def test_create_app_registers_auth_and_claim_routes_with_identity_service():
    client, service = make_factory_client()

    auth_response = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password_hash": "hash_1"},
    )
    claim_response = client.post(
        "/api/claim/code",
        json={"browser_session": "browser_1", "continuation": {"next": "/channels"}},
    )

    assert auth_response.status_code == 200
    assert auth_response.get_json() == {"account_id": "acct_1", "session_token": "session_token"}
    assert claim_response.status_code == 201
    assert claim_response.get_json() == {"code": "claim_code", "artifact_id": "artifact_3"}
    assert service.calls == [
        ("login", {"email": "a@example.com", "password_hash": "hash_1"}),
        (
            "issue_web_claim_code",
            {
                "browser_session": "browser_1",
                "continuation": {"next": "/channels"},
            },
        ),
    ]


def test_register_route_calls_service_and_returns_json():
    client, service = make_client()

    response = client.post(
        "/api/auth/register",
        json={
            "email": "a@example.com",
            "password_hash": "hash_1",
            "default_timezone": "Asia/Tokyo",
        },
    )

    assert response.status_code == 201
    assert response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
        "email_verification_artifact_id": "artifact_1",
    }
    assert service.calls[-1] == (
        "register_web_account",
        {
            "email": "a@example.com",
            "password_hash": "hash_1",
            "default_timezone": "Asia/Tokyo",
        },
    )


def test_login_and_current_user_routes_call_service():
    client, service = make_client()

    login_response = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password_hash": "hash_1"},
    )
    current_response = client.get(
        "/api/auth/current-user",
        headers={"Authorization": "Bearer session_token"},
    )

    assert login_response.status_code == 200
    assert login_response.get_json() == {"account_id": "acct_1", "session_token": "session_token"}
    assert current_response.status_code == 200
    assert current_response.get_json() == {"account_id": "acct_1", "origin": "web_first"}
    assert service.calls[-1] == ("current_user", {"session_token": "session_token"})


def test_access_status_route_calls_service():
    client, service = make_client()

    response = client.get("/api/auth/access-status?account_id=acct_1")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "access_allowed": True,
        "denial_reason": None,
    }
    assert service.calls[-1] == ("get_access_status", {"account_id": "acct_1"})


def test_verification_and_password_reset_routes_call_service():
    client, service = make_client()

    verify_response = client.post("/api/auth/email-verification/verify", json={"token": "verify_token"})
    request_response = client.post("/api/auth/password-reset/request", json={"email": "a@example.com"})
    complete_response = client.post(
        "/api/auth/password-reset/complete",
        json={"token": "reset_token", "password_hash": "hash_2"},
    )

    assert verify_response.status_code == 200
    assert request_response.status_code == 202
    assert complete_response.status_code == 200
    assert service.calls[-3:] == [
        ("verify_email", {"token": "verify_token"}),
        ("issue_password_reset", {"email": "a@example.com"}),
        ("reset_password", {"token": "reset_token", "password_hash": "hash_2"}),
    ]


def test_login_url_landing_calls_service():
    client, service = make_client()

    response = client.post(
        "/api/auth/login-url/redeem",
        json={"token": "login_token", "browser_session": "browser_1"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
        "continuation": {"next": "/channels"},
    }
    assert service.calls[-1] == (
        "redeem_login_url",
        {
            "token": "login_token",
            "browser_session": "browser_1",
        },
    )


def test_claim_code_issue_and_redeem_routes_call_service():
    client, service = make_client()

    issue_response = client.post(
        "/api/claim/code",
        json={"browser_session": "browser_1", "continuation": {"friend_link_id": "fl_1"}},
    )
    redeem_response = client.post(
        "/api/claim/code/redeem",
        json={
            "code": "claim_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert issue_response.status_code == 201
    assert issue_response.get_json() == {"code": "claim_code", "artifact_id": "artifact_3"}
    assert redeem_response.status_code == 200
    assert redeem_response.get_json() == {
        "account_id": "acct_1",
        "continuation": {"friend_link_id": "fl_1"},
    }
    assert "session_token" not in redeem_response.get_json()


def test_claim_code_poll_route_calls_service():
    client, service = make_client()

    response = client.get("/api/claim/code/claim_code/status?browser_session=browser_1")

    assert response.status_code == 200
    assert response.get_json() == {
        "found": True,
        "consumed": False,
        "target_account_id": None,
        "delivery_state": "pending",
    }
    assert service.calls[-1] == (
        "get_claim_code_status",
        {
            "code": "claim_code",
            "browser_session": "browser_1",
        },
    )


def test_claim_code_browser_complete_route_returns_session_to_original_browser():
    client, service = make_client()

    response = client.post(
        "/api/claim/code/complete",
        json={"code": "claim_code", "browser_session": "browser_1"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "session_token": "session_token",
        "continuation": {"friend_link_id": "fl_1"},
    }
    assert service.calls[-1] == (
        "complete_web_claim_from_browser",
        {
            "code": "claim_code",
            "browser_session": "browser_1",
        },
    )


def test_auth_route_errors_are_json_facts():
    client, _service = make_client(ErrorService())

    response = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password_hash": "wrong"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": {"code": "invalid_credentials"}}


def test_claim_route_errors_are_json_facts():
    client, _service = make_client(ErrorService())

    response = client.post(
        "/api/claim/code/redeem",
        json={
            "code": "claim_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": {"code": "unknown_channel_identity"}}


def test_pairing_code_issue_route_returns_json_error_when_service_rejects_origin():
    client, _service = make_client(ErrorService())

    response = client.post("/api/claim/pairing-code", json={"account_id": "acct_msg"})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {"code": "pairing_requires_web_first_account"}
    }


def test_pairing_code_issue_route_returns_access_denied_fact():
    client, _service = make_client(AccessDeniedService())

    response = client.post("/api/claim/pairing-code", json={"account_id": "acct_1"})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "access_denied",
            "fact": {
                "type": "account_access_denied",
                "account_id": "acct_1",
                "denial_reason": "email_verification_required",
                "checkout_url": None,
            },
        }
    }


def test_pairing_code_redeem_route_returns_access_denied_fact():
    client, _service = make_client(PairingRedemptionAccessDeniedService())

    response = client.post(
        "/api/claim/pairing-code/redeem",
        json={
            "pairing_code": "pairing_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "access_denied",
            "fact": {
                "type": "account_access_denied",
                "account_id": "acct_1",
                "denial_reason": "subscription_inactive",
                "checkout_url": None,
            },
        }
    }


def test_pairing_code_issue_and_redeem_routes_call_service():
    client, service = make_client()

    issue_response = client.post("/api/claim/pairing-code", json={"account_id": "acct_1"})
    redeem_response = client.post(
        "/api/claim/pairing-code/redeem",
        json={
            "pairing_code": "pairing_code",
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
        },
    )

    assert issue_response.status_code == 201
    assert issue_response.get_json() == {"code": "pairing_code", "artifact_id": "artifact_4"}
    assert redeem_response.status_code == 200
    assert redeem_response.get_json() == {"account_id": "acct_1", "channel_identity_id": "ci_1"}
    assert service.calls[-1] == (
        "resolve_or_create_channel_identity",
        {
            "provider_type": "whatsapp_evolution",
            "provider_subject": "whatsapp:+15555550123",
            "pairing_code": "pairing_code",
        },
    )
```

- [ ] **Step 2: Run the route tests and verify they fail**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_auth_routes.py -v
```

Expected: FAIL because `coke.api.auth_routes` does not exist.

## Task 7: Auth And Claim Route Adapters

**Files:**
- Create: `coke/api/__init__.py`
- Create: `coke/api/auth_routes.py`
- Create: `coke/api/claim_routes.py`
- Modify: `coke/app.py`

- [ ] **Step 1: Create the API package marker**

Create `coke/api/__init__.py`:

```python
"""Flask route adapters for Coke domain services."""
```

- [ ] **Step 2: Create auth routes**

Create `coke/api/auth_routes.py`:

```python
from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.domains.identity_access.models import IdentityAccessError


def create_auth_blueprint(identity_service) -> Blueprint:
    blueprint = Blueprint("auth", __name__, url_prefix="/api/auth")

    @blueprint.errorhandler(IdentityAccessError)
    def handle_identity_access_error(error: IdentityAccessError):
        body = {"error": {"code": error.code}}
        if error.fact is not None:
            body["error"]["fact"] = error.fact
        return jsonify(body), 400

    @blueprint.post("/register")
    def register():
        payload = request.get_json(silent=True) or {}
        result = identity_service.register_web_account(
            email=payload["email"],
            password_hash=payload["password_hash"],
            default_timezone=payload.get("default_timezone", "UTC"),
        )
        return (
            jsonify(
                {
                    "account_id": result.account.id,
                    "session_token": result.session.token,
                    "email_verification_artifact_id": result.email_verification.id,
                }
            ),
            201,
        )

    @blueprint.post("/login")
    def login():
        payload = request.get_json(silent=True) or {}
        result = identity_service.login(
            email=payload["email"],
            password_hash=payload["password_hash"],
        )
        return jsonify({"account_id": result.account.id, "session_token": result.session.token})

    @blueprint.post("/email-verification/verify")
    def verify_email():
        payload = request.get_json(silent=True) or {}
        credential = identity_service.verify_email(token=payload["token"])
        return jsonify({"account_id": credential.account_id, "email": credential.email})

    @blueprint.post("/password-reset/request")
    def request_password_reset():
        payload = request.get_json(silent=True) or {}
        identity_service.issue_password_reset(email=payload["email"])
        return jsonify({"accepted": True}), 202

    @blueprint.post("/password-reset/complete")
    def complete_password_reset():
        payload = request.get_json(silent=True) or {}
        credential = identity_service.reset_password(
            token=payload["token"],
            password_hash=payload["password_hash"],
        )
        return jsonify({"account_id": credential.account_id, "email": credential.email})

    @blueprint.get("/current-user")
    def current_user():
        session_token = _bearer_token()
        account = identity_service.current_user(session_token=session_token)
        return jsonify({"account_id": account.id, "origin": account.origin})

    @blueprint.get("/access-status")
    def access_status():
        account_id = request.args["account_id"]
        access = identity_service.get_access_status(account_id=account_id)
        return jsonify(
            {
                "account_id": access.account_id,
                "access_allowed": access.access_allowed,
                "denial_reason": access.denial_reason,
            }
        )

    @blueprint.post("/login-url/redeem")
    def redeem_login_url():
        payload = request.get_json(silent=True) or {}
        redeemed = identity_service.redeem_login_url(
            token=payload["token"],
            browser_session=payload["browser_session"],
        )
        return jsonify(
            {
                "account_id": redeemed.account_id,
                "session_token": redeemed.session.token,
                "continuation": redeemed.continuation,
            }
        )

    return blueprint


def _bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return ""
    return header[len(prefix) :]
```

- [ ] **Step 3: Create claim routes**

Create `coke/api/claim_routes.py`:

```python
from __future__ import annotations

from flask import Blueprint, jsonify, request

from coke.domains.identity_access.models import IdentityAccessError


def create_claim_blueprint(identity_service) -> Blueprint:
    blueprint = Blueprint("claim", __name__, url_prefix="/api/claim")

    @blueprint.errorhandler(IdentityAccessError)
    def handle_identity_access_error(error: IdentityAccessError):
        body = {"error": {"code": error.code}}
        if error.fact is not None:
            body["error"]["fact"] = error.fact
        return jsonify(body), 400

    @blueprint.post("/code")
    def issue_claim_code():
        payload = request.get_json(silent=True) or {}
        result = identity_service.issue_web_claim_code(
            browser_session=payload["browser_session"],
            continuation=payload.get("continuation", {}),
        )
        return jsonify({"code": result.code, "artifact_id": result.artifact.id}), 201

    @blueprint.get("/code/<code>/status")
    def poll_claim_code(code: str):
        status = identity_service.get_claim_code_status(
            code=code,
            browser_session=request.args["browser_session"],
        )
        if not status.found:
            return (
                jsonify(
                    {
                        "found": False,
                        "consumed": False,
                        "target_account_id": None,
                        "delivery_state": None,
                    }
                ),
                404,
            )
        return jsonify(
            {
                "found": True,
                "consumed": status.consumed,
                "target_account_id": status.target_account_id,
                "delivery_state": status.delivery_state,
            }
        )

    @blueprint.post("/code/redeem")
    def redeem_claim_code():
        payload = request.get_json(silent=True) or {}
        redeemed = identity_service.redeem_claim_code_from_channel(
            code=payload["code"],
            provider_type=payload["provider_type"],
            provider_subject=payload["provider_subject"],
        )
        return jsonify(
            {
                "account_id": redeemed.account_id,
                "continuation": redeemed.continuation,
            }
        )

    @blueprint.post("/code/complete")
    def complete_claim_code():
        payload = request.get_json(silent=True) or {}
        redeemed = identity_service.complete_web_claim_from_browser(
            code=payload["code"],
            browser_session=payload["browser_session"],
        )
        return jsonify(
            {
                "account_id": redeemed.account_id,
                "session_token": redeemed.session.token,
                "continuation": redeemed.continuation,
            }
        )

    @blueprint.post("/pairing-code")
    def issue_pairing_code():
        payload = request.get_json(silent=True) or {}
        result = identity_service.issue_pairing_code(account_id=payload["account_id"])
        return jsonify({"code": result.code, "artifact_id": result.artifact.id}), 201

    @blueprint.post("/pairing-code/redeem")
    def redeem_pairing_code():
        payload = request.get_json(silent=True) or {}
        resolved = identity_service.resolve_or_create_channel_identity(
            provider_type=payload["provider_type"],
            provider_subject=payload["provider_subject"],
            pairing_code=payload["pairing_code"],
        )
        return jsonify(
            {
                "account_id": resolved.account.id,
                "channel_identity_id": resolved.channel_identity.id,
            }
        )

    return blueprint
```

- [ ] **Step 4: Register blueprints from the app factory when a service is supplied**

Modify `coke/app.py` to exactly:

```python
from __future__ import annotations

from flask import Flask, jsonify

from coke.config import Settings


def create_app(settings: Settings, identity_access_service=None) -> Flask:
    app = Flask(__name__)
    app.config["COKE_SETTINGS"] = settings
    app.config["APP_ENV"] = settings.app_env

    if identity_access_service is not None:
        from coke.api.auth_routes import create_auth_blueprint
        from coke.api.claim_routes import create_claim_blueprint

        app.register_blueprint(create_auth_blueprint(identity_access_service))
        app.register_blueprint(create_claim_blueprint(identity_access_service))

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app
```

- [ ] **Step 5: Run route tests**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access/test_auth_routes.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the route/app slice**

Run:

```bash
git add coke/api coke/app.py tests/unit/coke/identity_access/test_auth_routes.py
git commit -m "feat: add identity access auth and claim routes"
```

Expected: commit succeeds with only API route files, app blueprint registration, and fake-service route tests.

## Task 8: IdentityAccess Surface Verification

**Files:**
- Verify: `coke/domains/identity_access/*.py`
- Verify: `coke/api/*.py`
- Verify: `tests/unit/coke/identity_access/*.py`

- [ ] **Step 1: Run all IdentityAccess unit tests**

Run:

```bash
$python_cmd -m pytest tests/unit/coke/identity_access -v
```

Expected: all IdentityAccess tests pass.

- [ ] **Step 2: Run backend clean-rebuild surface tests**

Run:

```bash
zsh scripts/verify-surface clean-rebuild-backend
```

Expected: command exits 0 and runs all `tests/unit/coke -v`.

- [ ] **Step 3: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: `suggest-verification` includes `clean-rebuild-backend`; `review-trigger` exits 0 and reports risk without blocking completion.

- [ ] **Step 4: Run repository checks**

Run:

```bash
zsh scripts/check
git diff --check
```

Expected: both commands exit 0.

## Task 9: Commit Audit

**Files:**
- Add: `coke/domains/__init__.py`
- Add: `coke/domains/identity_access/__init__.py`
- Add: `coke/domains/identity_access/models.py`
- Add: `coke/domains/identity_access/repository.py`
- Add: `coke/domains/identity_access/service.py`
- Add: `coke/api/__init__.py`
- Add: `coke/api/auth_routes.py`
- Add: `coke/api/claim_routes.py`
- Modify: `coke/app.py`
- Add: `tests/unit/coke/identity_access/test_identity_access_service.py`
- Add: `tests/unit/coke/identity_access/test_access_gate.py`
- Add: `tests/unit/coke/identity_access/test_auth_routes.py`

- [ ] **Step 1: Review the committed IdentityAccess change range**

Run:

```bash
git show --stat --oneline --no-renames HEAD~2..HEAD
```

Expected: the two-commit range contains only IdentityAccess domain files, API adapter files, app blueprint registration, and IdentityAccess tests.

- [ ] **Step 2: Confirm the planned split commits exist**

Run:

```bash
git log --oneline -2
```

Expected: the two newest commits are `feat: add identity access auth and claim routes` and `feat: add identity access domain service`.

- [ ] **Step 3: Confirm the worktree is clean after split commits**

Run:

```bash
git status --short
```

Expected: no output.

## Self-Review Checklist

Before handoff, confirm each item:

- [ ] The implementation does not write SQLAlchemy IdentityAccess persistence; the repository remains protocol-friendly and in-memory for this slice.
- [ ] `IdentityAccessService` depends on `IdentityAccessRepository` protocol, not the concrete in-memory implementation.
- [ ] Unit-test fixtures use monotonic deterministic factories, while production defaults use `uuid4()` for IDs and `secrets.token_urlsafe()` for tokens/codes.
- [ ] The in-memory repository rejects duplicate account IDs, activation/access rows per account, credential account/email keys, session tokens, channel identity IDs/provider tuples, and artifact codes.
- [ ] Routes call IdentityAccess service methods only and do not write repository dictionaries or schema tables directly.
- [ ] `create_app(Settings(...), identity_access_service=fake)` registers at least one auth route and one claim route in route tests.
- [ ] Shared WhatsApp auto-provisioning is limited to `whatsapp_evolution`.
- [ ] Known provider identity lookup returns the existing account and channel identity without duplicates.
- [ ] Non-WhatsApp first-seen identities fail closed unless a valid pairing code is supplied.
- [ ] The service contains no account merge, unlink, display-name matching, or profile matching behavior.
- [ ] Denied inbound access returns an `AccessDeniedTurn` fact and does not expose normal intent execution.
- [ ] Denial reasons are limited to `email_verification_required`, `subscription_inactive`, and `suspended`.
- [ ] Messaging-first subscription inactive inbound access includes the checkout URL fact.
- [ ] Web-first activation requires credential/session origin, usable channel signal, and first inbound.
- [ ] Messaging-first activation requires sender identity binding, usable messaging channel signal, and first inbound.
- [ ] First guidance stamping is idempotent.
- [ ] `login_url`, `claim_code`, `pairing_code`, `email_verification`, and `password_reset` artifacts are one-time, time-limited, single-use, and wrong-type failures are closed.
- [ ] Real-service tests cover email verification success, single-use verification, expired verification, password reset success, single-use reset, expired reset, and resend state updates.
- [ ] `claim_code` target account is resolved from `channel_identity` at redemption, not issuance.
- [ ] `claim_code` channel redemption writes `consumed_at`, `delivery_state`, `target_account_id`, and `updated_at` in one repository save.
- [ ] Channel-side `claim_code` redemption never returns a web session token; only the original browser session can complete the claim and receive the authenticated web session.
- [ ] Wrong-browser, unknown-sender, expired, consumed, and wrong-type claim artifacts fail closed with `IdentityAccessError`.
- [ ] Wrong-browser claim polling and completion attempts do not consume or complete the artifact before the original browser finishes.
- [ ] `pairing_code` issuance is allowed only for `web_first` accounts.
- [ ] `pairing_code` issuance calls `check_access_for_action(account_id, "connect_channel")` and fails closed with an access-denied fact when email verification, subscription, or suspension blocks channel connection.
- [ ] `pairing_code` redemption validates the artifact without consuming it, calls `check_access_for_action(account_id, "connect_channel")`, and fails closed before `channel_identity` creation when access is denied.
- [ ] `pairing_code` binds the sender identity to the issuing web-first account instead of auto-provisioning.
- [ ] Auth and claim route adapters map `IdentityAccessError` to JSON error facts and do not render prose.
- [ ] Channel identity anchor protection is exposed for ChannelReachability and no `channel`, `delivery_route`, or `delivery_attempt` lifecycle behavior is implemented.
- [ ] The implementation is split into a domain-service commit and a route/app commit before final verification.
- [ ] `zsh scripts/verify-surface clean-rebuild-backend`, `zsh scripts/check`, and `git diff --check` passed with fresh output.
