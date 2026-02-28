# Stripe Subscription Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the manual order-number gate system with Stripe Checkout subscriptions so new users pay via a Stripe-hosted page and access is granted automatically via webhook.

**Architecture:** The current `AccessGate` checks user access, and if denied, sends a static message asking for an order number. We replace that static message with a Stripe Checkout link. A new `/webhook/stripe` route on the existing Flask app receives Stripe events (`checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`) and creates/extends/revokes access automatically. The `OrderDAO` and manual order-binding logic are removed entirely — Stripe is the single source of truth for payment.

**Tech Stack:** `stripe` Python SDK, Flask (existing), MongoDB (existing)

---

## Design Decisions

1. **No migration.** Old `orders` collection is left as-is (we just stop writing to it). `AccessGate` no longer reads from it.

2. **Stripe is the billing system, MongoDB tracks access state.** We store `user.access.stripe_customer_id`, `user.access.stripe_subscription_id`, `user.access.expire_time` on the user doc. The webhook updates these fields.

3. **One Price, one Product.** Created in Stripe Dashboard (not in code). The Price ID goes in config.

4. **User identification flow:** When a new/expired user messages the bot, `AccessGate` creates a Stripe Checkout Session with `metadata.user_id = str(user["_id"])`. The webhook reads this metadata to find the user.

5. **Subscription lifecycle:**
   - `checkout.session.completed` → create access (set `expire_time` from subscription `current_period_end`)
   - `invoice.paid` → extend access (renewal)
   - `customer.subscription.deleted` → revoke access (set `expire_time` to now)

6. **Gate messages change:**
   - `gate_denied` → Brief intro + checkout link
   - `gate_expired` → Renewal message + checkout link

---

## Config Changes

```json
// conf/config.json
"access_control": {
    "enabled": true,
    "platforms": {
        "wechat": true
    },
    "stripe": {
        "price_id": "${STRIPE_PRICE_ID}",
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel"
    },
    "deny_message": "Hi! I'm Qiaoyun. To start chatting with me, please subscribe:\n{checkout_url}",
    "expire_message": "Your subscription has expired. Renew here:\n{checkout_url}",
    "success_message": "[System] Subscription active until {expire_time}"
}
```

**New .env variables:**
```
STRIPE_API_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
```

---

## Task 1: Add `stripe` dependency

**Files:**
- Modify: `requirements.txt`

**Step 1: Add stripe to requirements.txt**

Add this line to `requirements.txt` (after the `redis` line):

```
stripe>=8.0.0
```

**Step 2: Install**

Run: `pip install stripe>=8.0.0`

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat(stripe): add stripe python SDK dependency"
```

---

## Task 2: Add Stripe config to `config.json` and `.env`

**Files:**
- Modify: `conf/config.json`

**Step 1: Update config.json**

Replace the `access_control` section:

```json
"access_control": {
    "enabled": false,
    "platforms": {
        "wechat": false
    },
    "stripe": {
        "price_id": "${STRIPE_PRICE_ID}",
        "success_url": "${STRIPE_SUCCESS_URL}",
        "cancel_url": "${STRIPE_CANCEL_URL}"
    },
    "deny_message": "Hi! I'd love to chat with you. Subscribe here to get started:\n{checkout_url}",
    "expire_message": "Your subscription has expired. Renew here to keep chatting:\n{checkout_url}",
    "success_message": "[System] Subscription active until {expire_time}"
}
```

**Step 2: Commit**

```bash
git add conf/config.json
git commit -m "feat(stripe): add stripe config to access_control"
```

---

## Task 3: Rewrite `AccessGate` to create Stripe Checkout Sessions

This is the core change. The gate no longer looks for order numbers in messages. Instead, when a user is denied or expired, it creates a Stripe Checkout Session and returns the URL in the message.

**Files:**
- Modify: `agent/runner/access_gate.py`
- Test: `tests/unit/runner/test_access_gate.py`

**Step 1: Write the failing tests**

Replace `tests/unit/runner/test_access_gate.py` entirely:

```python
# -*- coding: utf-8 -*-
"""Unit tests for AccessGate with Stripe integration"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


STRIPE_CONFIG = {
    "enabled": True,
    "platforms": {"wechat": True},
    "stripe": {
        "price_id": "price_test123",
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel",
    },
    "deny_message": "Subscribe here:\n{checkout_url}",
    "expire_message": "Expired. Renew:\n{checkout_url}",
    "success_message": "Active until {expire_time}",
}


class TestAccessGate:
    """Tests for AccessGate with Stripe"""

    @pytest.fixture
    def mock_user_dao(self):
        return MagicMock()

    @pytest.fixture
    def access_gate(self, mock_user_dao):
        with patch(
            "agent.runner.access_gate.CONF",
            {"access_control": STRIPE_CONFIG, "admin_user_id": "admin123"},
        ):
            from agent.runner.access_gate import AccessGate

            gate = AccessGate()
            gate.user_dao = mock_user_dao
            return gate

    @pytest.mark.unit
    def test_check_returns_none_when_disabled(self):
        """Should return None when access control is disabled"""
        config = {**STRIPE_CONFIG, "enabled": False}
        with patch(
            "agent.runner.access_gate.CONF",
            {"access_control": config, "admin_user_id": ""},
        ):
            from agent.runner.access_gate import AccessGate

            gate = AccessGate()
            result = gate.check(
                platform="wechat",
                user={"_id": ObjectId()},
                message="hello",
                admin_user_id="",
            )
            assert result is None

    @pytest.mark.unit
    def test_check_returns_none_for_admin(self, access_gate):
        """Should return None for admin user (exempt)"""
        admin_id = ObjectId()
        result = access_gate.check(
            platform="wechat",
            user={"_id": admin_id},
            message="hello",
            admin_user_id=str(admin_id),
        )
        assert result is None

    @pytest.mark.unit
    def test_check_returns_none_for_valid_access(self, access_gate):
        """Should return None when user has valid access"""
        future_time = datetime.now() + timedelta(days=30)
        user = {
            "_id": ObjectId(),
            "access": {"expire_time": future_time},
        }
        result = access_gate.check(
            platform="wechat",
            user=user,
            message="hello",
            admin_user_id="",
        )
        assert result is None

    @pytest.mark.unit
    def test_check_returns_denied_with_checkout_url(self, access_gate):
        """Should return gate_denied with checkout_url for new user"""
        user = {"_id": ObjectId()}
        with patch("agent.runner.access_gate.stripe") as mock_stripe:
            mock_stripe.checkout.Session.create.return_value = MagicMock(
                url="https://checkout.stripe.com/test"
            )
            result = access_gate.check(
                platform="wechat",
                user=user,
                message="hello",
                admin_user_id="",
            )
            assert result[0] == "gate_denied"
            assert result[1]["checkout_url"] == "https://checkout.stripe.com/test"
            mock_stripe.checkout.Session.create.assert_called_once()

    @pytest.mark.unit
    def test_check_returns_expired_with_checkout_url(self, access_gate):
        """Should return gate_expired with checkout_url for expired user"""
        past_time = datetime.now() - timedelta(days=1)
        user = {
            "_id": ObjectId(),
            "access": {"expire_time": past_time},
        }
        with patch("agent.runner.access_gate.stripe") as mock_stripe:
            mock_stripe.checkout.Session.create.return_value = MagicMock(
                url="https://checkout.stripe.com/renew"
            )
            result = access_gate.check(
                platform="wechat",
                user=user,
                message="hello",
                admin_user_id="",
            )
            assert result[0] == "gate_expired"
            assert result[1]["checkout_url"] == "https://checkout.stripe.com/renew"

    @pytest.mark.unit
    def test_get_message_includes_checkout_url(self, access_gate):
        """Should format message with checkout_url"""
        msg = access_gate.get_message(
            "gate_denied", checkout_url="https://checkout.stripe.com/test"
        )
        assert "https://checkout.stripe.com/test" in msg

    @pytest.mark.unit
    def test_get_message_success_includes_expire_time(self, access_gate):
        """Should format success message with expire_time"""
        expire = datetime(2025, 12, 31, 23, 59)
        msg = access_gate.get_message("gate_success", expire_time=expire)
        assert "2025-12-31" in msg

    @pytest.mark.unit
    def test_checkout_session_includes_user_metadata(self, access_gate):
        """Checkout session should include user_id in metadata"""
        user_id = ObjectId()
        user = {"_id": user_id}
        with patch("agent.runner.access_gate.stripe") as mock_stripe:
            mock_stripe.checkout.Session.create.return_value = MagicMock(
                url="https://checkout.stripe.com/test"
            )
            access_gate.check(
                platform="wechat",
                user=user,
                message="hello",
                admin_user_id="",
            )
            call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
            assert call_kwargs["metadata"]["user_id"] == str(user_id)
            assert call_kwargs["mode"] == "subscription"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/runner/test_access_gate.py -v`
Expected: FAIL (import errors, missing stripe mock, etc.)

**Step 3: Rewrite `access_gate.py`**

Replace `agent/runner/access_gate.py` entirely:

```python
# -*- coding: utf-8 -*-
"""
Access Gate - Stripe subscription-based access control.

New users get a Stripe Checkout link. Webhook grants access on payment.
"""

import os
from datetime import datetime
from typing import Dict, Optional, Tuple

import stripe

from conf.config import CONF
from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)

stripe.api_key = os.getenv("STRIPE_API_KEY", "")


class AccessGate:
    """Subscription-based access gate using Stripe Checkout."""

    def __init__(self):
        self.config = CONF.get("access_control", {})
        self.user_dao = UserDAO()
        self.stripe_config = self.config.get("stripe", {})

    def is_enabled(self, platform: str) -> bool:
        if not self.config.get("enabled", False):
            return False
        return self.config.get("platforms", {}).get(platform, False)

    def check(
        self,
        platform: str,
        user: Dict,
        message: str,
        admin_user_id: str,
    ) -> Optional[Tuple[str, Optional[Dict]]]:
        """
        Check user access.

        Returns:
            None: allow through
            ("gate_denied", {"checkout_url": ...}): new user, needs subscription
            ("gate_expired", {"checkout_url": ...}): expired, needs renewal
        """
        # Admin exempt
        if admin_user_id and str(user["_id"]) == admin_user_id:
            return None

        # Platform not gated
        if not self.is_enabled(platform):
            return None

        # Valid access
        access = user.get("access")
        if access and access.get("expire_time"):
            if access["expire_time"] > datetime.now():
                return None

        # No valid access — create checkout session
        checkout_url = self._create_checkout_url(user)
        if access:
            return ("gate_expired", {"checkout_url": checkout_url})
        else:
            return ("gate_denied", {"checkout_url": checkout_url})

    def _create_checkout_url(self, user: Dict) -> str:
        """Create a Stripe Checkout Session and return its URL."""
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[
                    {"price": self.stripe_config["price_id"], "quantity": 1}
                ],
                success_url=self.stripe_config.get(
                    "success_url", "https://example.com/success"
                ),
                cancel_url=self.stripe_config.get(
                    "cancel_url", "https://example.com/cancel"
                ),
                metadata={"user_id": str(user["_id"])},
            )
            return session.url
        except Exception as e:
            logger.error(f"Failed to create Stripe checkout session: {e}")
            return ""

    def get_message(
        self,
        gate_type: str,
        expire_time: datetime = None,
        checkout_url: str = None,
    ) -> str:
        """Format gate message with checkout URL or expire time."""
        if gate_type == "gate_denied":
            msg = self.config.get(
                "deny_message",
                "Subscribe to start chatting:\n{checkout_url}",
            )
            return msg.format(checkout_url=checkout_url or "")
        elif gate_type == "gate_expired":
            msg = self.config.get(
                "expire_message",
                "Subscription expired. Renew:\n{checkout_url}",
            )
            return msg.format(checkout_url=checkout_url or "")
        elif gate_type == "gate_success":
            msg = self.config.get(
                "success_message",
                "[System] Subscription active until {expire_time}",
            )
            if expire_time:
                return msg.format(
                    expire_time=expire_time.strftime("%Y-%m-%d %H:%M")
                )
            return msg
        return ""

    def close(self):
        self.user_dao.close()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/runner/test_access_gate.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add agent/runner/access_gate.py tests/unit/runner/test_access_gate.py
git commit -m "feat(stripe): rewrite AccessGate to use Stripe Checkout Sessions"
```

---

## Task 4: Update `agent_handler.py` gate dispatch to pass `checkout_url`

The handler currently calls `get_message("gate_denied")` without a checkout URL. We need to pass the checkout URL from the dispatch result.

**Files:**
- Modify: `agent/runner/agent_handler.py` (lines 717-751)

**Step 1: Write the change**

In `agent_handler.py`, update the `gate_denied` and `gate_expired` branches to extract `checkout_url` from `dispatch_data`:

Change the `gate_denied` block (around line 717):

```python
            elif dispatch_type == "gate_denied":
                checkout_url = (
                    dispatch_data.get("checkout_url") if dispatch_data else ""
                )
                send_message_via_context(
                    msg_ctx.context,
                    message=dispatcher.access_gate.get_message(
                        "gate_denied", checkout_url=checkout_url
                    ),
                    message_type="text",
                    expect_output_timestamp=int(time.time()),
                )
                finalizer.finalize_blocked(msg_ctx)
```

Change the `gate_expired` block (around line 727):

```python
            elif dispatch_type == "gate_expired":
                checkout_url = (
                    dispatch_data.get("checkout_url") if dispatch_data else ""
                )
                send_message_via_context(
                    msg_ctx.context,
                    message=dispatcher.access_gate.get_message(
                        "gate_expired", checkout_url=checkout_url
                    ),
                    message_type="text",
                    expect_output_timestamp=int(time.time()),
                )
                finalizer.finalize_blocked(msg_ctx)
```

The `gate_success` block stays the same (it's now only triggered by the webhook path, not the chat path).

**Step 2: Run existing tests**

Run: `pytest tests/unit/runner/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add agent/runner/agent_handler.py
git commit -m "feat(stripe): pass checkout_url through gate dispatch to messages"
```

---

## Task 5: Add Stripe webhook route to Flask app

This is where Stripe tells us about payments. We add a `/webhook/stripe` POST route to `ecloud_input.py`.

**Files:**
- Modify: `connector/ecloud/ecloud_input.py`
- Create: `tests/unit/connector/test_stripe_webhook.py`

**Step 1: Write the failing tests**

Create `tests/unit/connector/test_stripe_webhook.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for Stripe webhook handler"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


@pytest.fixture
def mock_stripe():
    with patch("connector.ecloud.ecloud_input.stripe") as m:
        yield m


@pytest.fixture
def mock_user_dao():
    with patch("connector.ecloud.ecloud_input.user_dao") as m:
        yield m


@pytest.fixture
def flask_client():
    with patch.dict(
        "os.environ",
        {"STRIPE_WEBHOOK_SECRET": "whsec_test", "STRIPE_API_KEY": "sk_test"},
    ):
        # Must import after env is patched
        from connector.ecloud.ecloud_input import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client


class TestStripeWebhook:
    """Tests for /webhook/stripe endpoint"""

    @pytest.mark.unit
    def test_missing_signature_returns_400(self, flask_client):
        """Should reject requests without Stripe signature"""
        resp = flask_client.post(
            "/webhook/stripe",
            data=b"{}",
            content_type="application/json",
        )
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_invalid_signature_returns_400(self, flask_client, mock_stripe):
        """Should reject requests with invalid signature"""
        mock_stripe.Webhook.construct_event.side_effect = (
            mock_stripe.error.SignatureVerificationError(
                "bad sig", "sig_header"
            )
        )
        resp = flask_client.post(
            "/webhook/stripe",
            data=b"{}",
            content_type="application/json",
            headers={"Stripe-Signature": "bad"},
        )
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_checkout_completed_grants_access(
        self, flask_client, mock_stripe, mock_user_dao
    ):
        """checkout.session.completed should grant user access"""
        user_id = str(ObjectId())
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"user_id": user_id},
                    "customer": "cus_test123",
                    "subscription": "sub_test123",
                }
            },
        }
        mock_stripe.Webhook.construct_event.return_value = event
        mock_stripe.Subscription.retrieve.return_value = MagicMock(
            current_period_end=1735689600  # 2025-01-01
        )
        mock_user_dao.update_access_stripe.return_value = True

        resp = flask_client.post(
            "/webhook/stripe",
            data=json.dumps(event),
            content_type="application/json",
            headers={"Stripe-Signature": "valid"},
        )
        assert resp.status_code == 200
        mock_user_dao.update_access_stripe.assert_called_once()

    @pytest.mark.unit
    def test_invoice_paid_extends_access(
        self, flask_client, mock_stripe, mock_user_dao
    ):
        """invoice.paid should extend user access on renewal"""
        user_id = str(ObjectId())
        event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "subscription": "sub_test123",
                    "customer": "cus_test123",
                }
            },
        }
        mock_stripe.Webhook.construct_event.return_value = event
        mock_stripe.Subscription.retrieve.return_value = MagicMock(
            current_period_end=1735689600,
            metadata={"user_id": user_id},
        )
        mock_user_dao.update_access_stripe.return_value = True

        resp = flask_client.post(
            "/webhook/stripe",
            data=json.dumps(event),
            content_type="application/json",
            headers={"Stripe-Signature": "valid"},
        )
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_subscription_deleted_revokes_access(
        self, flask_client, mock_stripe, mock_user_dao
    ):
        """customer.subscription.deleted should revoke access"""
        user_id = str(ObjectId())
        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "metadata": {"user_id": user_id},
                    "id": "sub_test123",
                }
            },
        }
        mock_stripe.Webhook.construct_event.return_value = event
        mock_user_dao.revoke_access.return_value = True

        resp = flask_client.post(
            "/webhook/stripe",
            data=json.dumps(event),
            content_type="application/json",
            headers={"Stripe-Signature": "valid"},
        )
        assert resp.status_code == 200
        mock_user_dao.revoke_access.assert_called_once_with(user_id)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/connector/test_stripe_webhook.py -v`
Expected: FAIL

**Step 3: Add the webhook route to `ecloud_input.py`**

Add these imports at the top of `ecloud_input.py` (after the existing imports):

```python
import os
import stripe

stripe.api_key = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
```

Add this route before `if __name__ == "__main__":`:

```python
@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events for subscription management."""
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    if not sig_header:
        return jsonify({"error": "Missing signature"}), 400

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook: invalid signature")
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data_object)
    elif event_type == "invoice.paid":
        _handle_invoice_paid(data_object)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data_object)
    else:
        logger.info(f"Stripe webhook: unhandled event type {event_type}")

    return jsonify({"status": "ok"}), 200


def _handle_checkout_completed(session: dict):
    """Grant access after initial checkout."""
    user_id = session.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Stripe checkout.session.completed: missing user_id in metadata")
        return

    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    sub = stripe.Subscription.retrieve(subscription_id)
    expire_time = datetime.fromtimestamp(sub.current_period_end)

    user_dao.update_access_stripe(
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(
        f"Stripe: granted access to user {user_id}, expires {expire_time}"
    )


def _handle_invoice_paid(invoice: dict):
    """Extend access on subscription renewal."""
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    sub = stripe.Subscription.retrieve(subscription_id)
    user_id = sub.metadata.get("user_id")
    if not user_id:
        logger.warning("Stripe invoice.paid: missing user_id in subscription metadata")
        return

    expire_time = datetime.fromtimestamp(sub.current_period_end)
    user_dao.update_access_stripe(
        user_id=user_id,
        stripe_customer_id=invoice.get("customer"),
        stripe_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(
        f"Stripe: extended access for user {user_id}, expires {expire_time}"
    )


def _handle_subscription_deleted(subscription: dict):
    """Revoke access when subscription is cancelled."""
    user_id = subscription.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning(
            "Stripe subscription.deleted: missing user_id in metadata"
        )
        return

    user_dao.revoke_access(user_id)
    logger.info(f"Stripe: revoked access for user {user_id}")
```

Also add `from datetime import datetime` to the imports at the top if not already present.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/connector/test_stripe_webhook.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add connector/ecloud/ecloud_input.py tests/unit/connector/test_stripe_webhook.py
git commit -m "feat(stripe): add /webhook/stripe route for subscription events"
```

---

## Task 6: Add `update_access_stripe` and `revoke_access` to `UserDAO`

The webhook needs two new methods on `UserDAO`.

**Files:**
- Modify: `dao/user_dao.py`
- Create: `tests/unit/dao/test_user_dao_stripe.py`

**Step 1: Write the failing tests**

Create `tests/unit/dao/test_user_dao_stripe.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for UserDAO Stripe access methods"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestUserDAOStripe:
    """Tests for Stripe-related UserDAO methods"""

    @pytest.fixture
    def user_dao(self):
        with patch("dao.user_dao.CONF", {
            "mongodb": {"mongodb_ip": "127.0.0.1", "mongodb_port": "27017", "mongodb_name": "test"}
        }), patch("dao.user_dao.MongoClient") as mock_client:
            from dao.user_dao import UserDAO

            dao = UserDAO()
            dao.collection = MagicMock()
            return dao

    @pytest.mark.unit
    def test_update_access_stripe(self, user_dao):
        """Should update user access with Stripe fields"""
        user_dao.collection.update_one.return_value = MagicMock(modified_count=1)
        user_id = str(ObjectId())
        expire = datetime.now() + timedelta(days=30)

        result = user_dao.update_access_stripe(
            user_id=user_id,
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_456",
            expire_time=expire,
        )

        assert result is True
        call_args = user_dao.collection.update_one.call_args
        update_set = call_args[0][1]["$set"]
        assert update_set["access.stripe_customer_id"] == "cus_123"
        assert update_set["access.stripe_subscription_id"] == "sub_456"
        assert update_set["access.expire_time"] == expire

    @pytest.mark.unit
    def test_revoke_access(self, user_dao):
        """Should set expire_time to now to revoke access"""
        user_dao.collection.update_one.return_value = MagicMock(modified_count=1)
        user_id = str(ObjectId())

        result = user_dao.revoke_access(user_id)

        assert result is True
        call_args = user_dao.collection.update_one.call_args
        update_set = call_args[0][1]["$set"]
        # expire_time should be approximately now
        assert "access.expire_time" in update_set
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/dao/test_user_dao_stripe.py -v`
Expected: FAIL (methods don't exist)

**Step 3: Add methods to `UserDAO`**

Add these methods to `dao/user_dao.py` (before the `close` method):

```python
    def update_access_stripe(
        self,
        user_id: str,
        stripe_customer_id: str,
        stripe_subscription_id: str,
        expire_time: datetime,
    ) -> bool:
        """Update user access with Stripe subscription info."""
        try:
            object_id = ObjectId(user_id)
        except (TypeError, ValueError):
            return False

        result = self.collection.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "access.stripe_customer_id": stripe_customer_id,
                    "access.stripe_subscription_id": stripe_subscription_id,
                    "access.expire_time": expire_time,
                    "access.granted_at": datetime.now(),
                }
            },
        )
        return result.modified_count > 0

    def revoke_access(self, user_id: str) -> bool:
        """Revoke user access by setting expire_time to now."""
        try:
            object_id = ObjectId(user_id)
        except (TypeError, ValueError):
            return False

        result = self.collection.update_one(
            {"_id": object_id},
            {"$set": {"access.expire_time": datetime.now()}},
        )
        return result.modified_count > 0
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/dao/test_user_dao_stripe.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add dao/user_dao.py tests/unit/dao/test_user_dao_stripe.py
git commit -m "feat(stripe): add update_access_stripe and revoke_access to UserDAO"
```

---

## Task 7: Update dispatcher gate tests

The dispatcher tests need to reflect the new return shape (checkout_url instead of None in data).

**Files:**
- Modify: `tests/unit/runner/test_message_dispatcher_gate.py`

**Step 1: Update the tests**

Replace `tests/unit/runner/test_message_dispatcher_gate.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for MessageDispatcher access gate integration"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestMessageDispatcherGate:
    """Tests for MessageDispatcher with access gate"""

    @pytest.fixture
    def mock_access_gate(self):
        return MagicMock()

    @pytest.fixture
    def msg_ctx(self):
        ctx = MagicMock()
        ctx.context = {
            "user": {"_id": ObjectId()},
            "platform": "wechat",
            "relation": {
                "relationship": {"dislike": 0},
                "character_info": {"status": "空闲"},
            },
        }
        ctx.input_messages = [{"message": "hello"}]
        return ctx

    @pytest.mark.unit
    def test_dispatch_calls_access_gate(self, msg_ctx, mock_access_gate):
        mock_access_gate.check.return_value = None
        with patch(
            "agent.runner.message_processor.AccessGate",
            return_value=mock_access_gate,
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate
            result = dispatcher.dispatch(msg_ctx)
            mock_access_gate.check.assert_called_once()
            assert result == ("normal", None)

    @pytest.mark.unit
    def test_dispatch_returns_gate_denied_with_checkout_url(
        self, msg_ctx, mock_access_gate
    ):
        mock_access_gate.check.return_value = (
            "gate_denied",
            {"checkout_url": "https://checkout.stripe.com/test"},
        )
        with patch(
            "agent.runner.message_processor.AccessGate",
            return_value=mock_access_gate,
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate
            result = dispatcher.dispatch(msg_ctx)
            assert result[0] == "gate_denied"
            assert "checkout_url" in result[1]

    @pytest.mark.unit
    def test_dispatch_blocked_takes_priority(self, msg_ctx, mock_access_gate):
        msg_ctx.context["relation"]["relationship"]["dislike"] = 100
        mock_access_gate.check.return_value = None
        with patch(
            "agent.runner.message_processor.AccessGate",
            return_value=mock_access_gate,
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate
            result = dispatcher.dispatch(msg_ctx)
            assert result == ("blocked", None)
            mock_access_gate.check.assert_not_called()
```

**Step 2: Run tests**

Run: `pytest tests/unit/runner/test_message_dispatcher_gate.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/unit/runner/test_message_dispatcher_gate.py
git commit -m "test(stripe): update dispatcher gate tests for checkout_url"
```

---

## Task 8: Remove dead `OrderDAO` usage from `AccessGate`

The `AccessGate` no longer uses `OrderDAO`. Verify no other code imports `OrderDAO` for gate purposes. The `OrderDAO` class itself can stay (it's not hurting anyone), but the import in `access_gate.py` is already gone from Task 3.

**Files:**
- Verify: `agent/runner/access_gate.py` (should have no OrderDAO import)

**Step 1: Verify**

Run: `grep -r "OrderDAO" agent/runner/`
Expected: No results (OrderDAO is no longer used in the runner layer)

Run: `grep -r "order_dao" agent/runner/`
Expected: No results

**Step 2: Run full test suite**

Run: `pytest -m "not integration" -v`
Expected: All PASS

**Step 3: Commit (if any cleanup needed)**

```bash
git commit -m "chore(stripe): verify OrderDAO removed from access gate"
```

---

## Task 9: Full integration verification

**Step 1: Run all non-integration tests**

Run: `pytest -m "not integration" -v --tb=short`
Expected: All PASS

**Step 2: Verify config loads correctly**

Run: `python -c "from conf.config import CONF; print(CONF['access_control'])"`
Expected: Should show the updated access_control config with stripe section

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(stripe): complete Stripe subscription integration for access gate"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `requirements.txt` | Add `stripe>=8.0.0` |
| `conf/config.json` | Add `stripe` section to `access_control` |
| `agent/runner/access_gate.py` | Rewrite: remove OrderDAO, add Stripe Checkout Session creation |
| `agent/runner/agent_handler.py` | Pass `checkout_url` from dispatch_data to `get_message()` |
| `connector/ecloud/ecloud_input.py` | Add `/webhook/stripe` route with 3 event handlers |
| `dao/user_dao.py` | Add `update_access_stripe()` and `revoke_access()` methods |
| `tests/unit/runner/test_access_gate.py` | Rewrite for Stripe |
| `tests/unit/runner/test_message_dispatcher_gate.py` | Update for checkout_url |
| `tests/unit/connector/test_stripe_webhook.py` | New: webhook handler tests |
| `tests/unit/dao/test_user_dao_stripe.py` | New: UserDAO Stripe method tests |

**What stays untouched:**
- `OrderDAO` class (left as-is, just unused by gate)
- `orders` MongoDB collection (left as-is)
- All workflow/agent code
- All other connector code
