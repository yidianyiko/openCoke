# Creem Subscription Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the manual order-number gate system with Creem Checkout subscriptions so new users pay via a Creem-hosted page and access is granted automatically via webhook.

**Architecture:** The current `AccessGate` checks user access, and if denied, sends a static message asking for an order number. We replace that static message with a Creem Checkout link. A new `/webhook/creem` route on the existing Flask app receives Creem events (`checkout.completed`, `subscription.paid`, `subscription.canceled`, `subscription.expired`) and creates/extends/revokes access automatically. The `OrderDAO` and manual order-binding logic are removed entirely — Creem is the single source of truth for payment.

**Tech Stack:** `requests` (stdlib, for Creem REST API calls), `hmac`/`hashlib` (stdlib, for webhook signature verification), Flask (existing), MongoDB (existing)

---

## Design Decisions

1. **No migration.** Old `orders` collection is left as-is (we just stop writing to it). `AccessGate` no longer reads from it.

2. **Creem is the billing system, MongoDB tracks access state.** We store `user.access.creem_customer_id`, `user.access.creem_subscription_id`, `user.access.expire_time` on the user doc. The webhook updates these fields.

3. **One Product.** Created in Creem Dashboard (not in code). The Product ID goes in config.

4. **User identification flow:** When a new/expired user messages the bot, `AccessGate` creates a Creem Checkout Session via REST API with `metadata.user_id = str(user["_id"])`. The webhook reads this metadata (`object.metadata.user_id`) to find the user.

5. **Subscription lifecycle:**
   - `checkout.completed` → create access (set `expire_time` from subscription period end)
   - `subscription.paid` → extend access (renewal)
   - `subscription.canceled` / `subscription.expired` → revoke access (set `expire_time` to now)

6. **Webhook signature verification:** Creem signs requests with HMAC-SHA256 using the raw payload and `CREEM_WEBHOOK_SECRET`. Header is `creem-signature`. Verified in Python with `hmac.compare_digest`.

7. **Gate messages change:**
   - `gate_denied` → Brief intro + checkout link
   - `gate_expired` → Renewal message + checkout link

8. **No Creem Python SDK.** Creem has no official Python SDK; we call the REST API directly with `requests`.

---

## Config Changes

```json
// conf/config.json
"access_control": {
    "enabled": true,
    "platforms": {
        "wechat": true
    },
    "creem": {
        "product_id": "${CREEM_PRODUCT_ID}",
        "success_url": "https://example.com/success"
    },
    "deny_message": "Hi! I'm Qiaoyun. To start chatting with me, please subscribe:\n{checkout_url}",
    "expire_message": "Your subscription has expired. Renew here:\n{checkout_url}",
    "success_message": "[System] Subscription active until {expire_time}"
}
```

**New .env variables:**
```
CREEM_API_KEY=creem_...
CREEM_WEBHOOK_SECRET=whsec_...
CREEM_PRODUCT_ID=prod_...
```

---

## Task 1: Add Creem config to `config.json` and `.env`

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
    "creem": {
        "product_id": "${CREEM_PRODUCT_ID}",
        "success_url": "${CREEM_SUCCESS_URL}"
    },
    "deny_message": "Hi! I'd love to chat with you. Subscribe here to get started:\n{checkout_url}",
    "expire_message": "Your subscription has expired. Renew here to keep chatting:\n{checkout_url}",
    "success_message": "[System] Subscription active until {expire_time}"
}
```

**Step 2: Commit**

```bash
git add conf/config.json
git commit -m "feat(creem): add creem config to access_control"
```

---

## Task 2: Rewrite `AccessGate` to create Creem Checkout Sessions

This is the core change. The gate no longer looks for order numbers in messages. Instead, when a user is denied or expired, it calls the Creem REST API to create a Checkout Session and returns the URL in the message.

**Files:**
- Modify: `agent/runner/access_gate.py`
- Test: `tests/unit/runner/test_access_gate.py`

**Step 1: Write the failing tests**

Replace `tests/unit/runner/test_access_gate.py` entirely:

```python
# -*- coding: utf-8 -*-
"""Unit tests for AccessGate with Creem integration"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


CREEM_CONFIG = {
    "enabled": True,
    "platforms": {"wechat": True},
    "creem": {
        "product_id": "prod_test123",
        "success_url": "https://example.com/success",
    },
    "deny_message": "Subscribe here:\n{checkout_url}",
    "expire_message": "Expired. Renew:\n{checkout_url}",
    "success_message": "Active until {expire_time}",
}


class TestAccessGate:
    """Tests for AccessGate with Creem"""

    @pytest.fixture
    def mock_user_dao(self):
        return MagicMock()

    @pytest.fixture
    def access_gate(self, mock_user_dao):
        with patch(
            "agent.runner.access_gate.CONF",
            {"access_control": CREEM_CONFIG, "admin_user_id": "admin123"},
        ):
            from agent.runner.access_gate import AccessGate

            gate = AccessGate()
            gate.user_dao = mock_user_dao
            return gate

    @pytest.mark.unit
    def test_check_returns_none_when_disabled(self):
        """Should return None when access control is disabled"""
        config = {**CREEM_CONFIG, "enabled": False}
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
        with patch.object(
            access_gate, "_create_checkout_url", return_value="https://checkout.creem.io/test"
        ):
            result = access_gate.check(
                platform="wechat",
                user=user,
                message="hello",
                admin_user_id="",
            )
            assert result[0] == "gate_denied"
            assert result[1]["checkout_url"] == "https://checkout.creem.io/test"

    @pytest.mark.unit
    def test_check_returns_expired_with_checkout_url(self, access_gate):
        """Should return gate_expired with checkout_url for expired user"""
        past_time = datetime.now() - timedelta(days=1)
        user = {
            "_id": ObjectId(),
            "access": {"expire_time": past_time},
        }
        with patch.object(
            access_gate, "_create_checkout_url", return_value="https://checkout.creem.io/renew"
        ):
            result = access_gate.check(
                platform="wechat",
                user=user,
                message="hello",
                admin_user_id="",
            )
            assert result[0] == "gate_expired"
            assert result[1]["checkout_url"] == "https://checkout.creem.io/renew"

    @pytest.mark.unit
    def test_get_message_includes_checkout_url(self, access_gate):
        """Should format message with checkout_url"""
        msg = access_gate.get_message(
            "gate_denied", checkout_url="https://checkout.creem.io/test"
        )
        assert "https://checkout.creem.io/test" in msg

    @pytest.mark.unit
    def test_get_message_success_includes_expire_time(self, access_gate):
        """Should format success message with expire_time"""
        expire = datetime(2025, 12, 31, 23, 59)
        msg = access_gate.get_message("gate_success", expire_time=expire)
        assert "2025-12-31" in msg

    @pytest.mark.unit
    def test_create_checkout_url_calls_creem_api(self, access_gate):
        """Checkout session should include user_id in metadata"""
        user_id = ObjectId()
        user = {"_id": user_id}
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"checkout_url": "https://checkout.creem.io/test"}

        with patch("agent.runner.access_gate.requests.post", return_value=mock_response) as mock_post:
            url = access_gate._create_checkout_url(user)
            assert url == "https://checkout.creem.io/test"
            call_kwargs = mock_post.call_args
            payload = call_kwargs[1]["json"]
            assert payload["metadata"]["user_id"] == str(user_id)
            assert payload["product_id"] == "prod_test123"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/runner/test_access_gate.py -v`
Expected: FAIL (import errors, missing creem integration, etc.)

**Step 3: Rewrite `access_gate.py`**

Replace `agent/runner/access_gate.py` entirely:

```python
# -*- coding: utf-8 -*-
"""
Access Gate - Creem subscription-based access control.

New users get a Creem Checkout link. Webhook grants access on payment.
"""

import hmac
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

import requests

from conf.config import CONF
from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)

CREEM_API_BASE = "https://api.creem.io"
CREEM_API_KEY = os.getenv("CREEM_API_KEY", "")


class AccessGate:
    """Subscription-based access gate using Creem Checkout."""

    def __init__(self):
        self.config = CONF.get("access_control", {})
        self.user_dao = UserDAO()
        self.creem_config = self.config.get("creem", {})

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
        """Create a Creem Checkout Session via REST API and return its URL."""
        try:
            response = requests.post(
                f"{CREEM_API_BASE}/v1/checkouts",
                headers={
                    "Authorization": f"Bearer {CREEM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "product_id": self.creem_config["product_id"],
                    "success_url": self.creem_config.get(
                        "success_url", "https://example.com/success"
                    ),
                    "metadata": {"user_id": str(user["_id"])},
                },
            )
            if response.status_code == 201:
                return response.json().get("checkout_url", "")
            logger.error(
                f"Creem checkout API error: {response.status_code} {response.text}"
            )
            return ""
        except Exception as e:
            logger.error(f"Failed to create Creem checkout session: {e}")
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
git commit -m "feat(creem): rewrite AccessGate to use Creem Checkout Sessions"
```

---

## Task 3: Update `agent_handler.py` gate dispatch to pass `checkout_url`

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
git commit -m "feat(creem): pass checkout_url through gate dispatch to messages"
```

---

## Task 4: Add Creem webhook route to Flask app

This is where Creem tells us about payments. We add a `/webhook/creem` POST route to `ecloud_input.py`.

Creem webhook signature: `creem-signature` header, verified via HMAC-SHA256 of raw body with `CREEM_WEBHOOK_SECRET`.

Event structure:
```json
{
  "eventType": "checkout.completed",
  "object": { ... }
}
```

**Files:**
- Modify: `connector/ecloud/ecloud_input.py`
- Create: `tests/unit/connector/test_creem_webhook.py`

**Step 1: Write the failing tests**

Create `tests/unit/connector/test_creem_webhook.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for Creem webhook handler"""

import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


def make_signature(payload: str, secret: str) -> str:
    return hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


WEBHOOK_SECRET = "whsec_test"


@pytest.fixture
def mock_user_dao():
    with patch("connector.ecloud.ecloud_input.user_dao") as m:
        yield m


@pytest.fixture
def flask_client():
    with patch.dict(
        "os.environ",
        {"CREEM_WEBHOOK_SECRET": WEBHOOK_SECRET, "CREEM_API_KEY": "creem_test"},
    ):
        from connector.ecloud.ecloud_input import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client


class TestCreemWebhook:
    """Tests for /webhook/creem endpoint"""

    @pytest.mark.unit
    def test_missing_signature_returns_400(self, flask_client):
        """Should reject requests without Creem signature"""
        resp = flask_client.post(
            "/webhook/creem",
            data=b"{}",
            content_type="application/json",
        )
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_invalid_signature_returns_400(self, flask_client):
        """Should reject requests with invalid signature"""
        resp = flask_client.post(
            "/webhook/creem",
            data=b"{}",
            content_type="application/json",
            headers={"creem-signature": "badsig"},
        )
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_checkout_completed_grants_access(self, flask_client, mock_user_dao):
        """checkout.completed should grant user access"""
        user_id = str(ObjectId())
        event = {
            "eventType": "checkout.completed",
            "object": {
                "metadata": {"user_id": user_id},
                "customer": {"id": "cust_test123"},
                "subscription": {"id": "sub_test123", "current_period_end": "2026-01-01T00:00:00Z"},
            },
        }
        payload = json.dumps(event)
        sig = make_signature(payload, WEBHOOK_SECRET)
        mock_user_dao.update_access_creem.return_value = True

        resp = flask_client.post(
            "/webhook/creem",
            data=payload,
            content_type="application/json",
            headers={"creem-signature": sig},
        )
        assert resp.status_code == 200
        mock_user_dao.update_access_creem.assert_called_once()

    @pytest.mark.unit
    def test_subscription_paid_extends_access(self, flask_client, mock_user_dao):
        """subscription.paid should extend user access on renewal"""
        user_id = str(ObjectId())
        event = {
            "eventType": "subscription.paid",
            "object": {
                "metadata": {"user_id": user_id},
                "customer": {"id": "cust_test123"},
                "id": "sub_test123",
                "current_period_end": "2026-02-01T00:00:00Z",
            },
        }
        payload = json.dumps(event)
        sig = make_signature(payload, WEBHOOK_SECRET)
        mock_user_dao.update_access_creem.return_value = True

        resp = flask_client.post(
            "/webhook/creem",
            data=payload,
            content_type="application/json",
            headers={"creem-signature": sig},
        )
        assert resp.status_code == 200
        mock_user_dao.update_access_creem.assert_called_once()

    @pytest.mark.unit
    def test_subscription_canceled_revokes_access(self, flask_client, mock_user_dao):
        """subscription.canceled should revoke access"""
        user_id = str(ObjectId())
        event = {
            "eventType": "subscription.canceled",
            "object": {
                "metadata": {"user_id": user_id},
                "id": "sub_test123",
            },
        }
        payload = json.dumps(event)
        sig = make_signature(payload, WEBHOOK_SECRET)
        mock_user_dao.revoke_access.return_value = True

        resp = flask_client.post(
            "/webhook/creem",
            data=payload,
            content_type="application/json",
            headers={"creem-signature": sig},
        )
        assert resp.status_code == 200
        mock_user_dao.revoke_access.assert_called_once_with(user_id)

    @pytest.mark.unit
    def test_subscription_expired_revokes_access(self, flask_client, mock_user_dao):
        """subscription.expired should revoke access"""
        user_id = str(ObjectId())
        event = {
            "eventType": "subscription.expired",
            "object": {
                "metadata": {"user_id": user_id},
                "id": "sub_test123",
            },
        }
        payload = json.dumps(event)
        sig = make_signature(payload, WEBHOOK_SECRET)
        mock_user_dao.revoke_access.return_value = True

        resp = flask_client.post(
            "/webhook/creem",
            data=payload,
            content_type="application/json",
            headers={"creem-signature": sig},
        )
        assert resp.status_code == 200
        mock_user_dao.revoke_access.assert_called_once_with(user_id)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/connector/test_creem_webhook.py -v`
Expected: FAIL

**Step 3: Add the webhook route to `ecloud_input.py`**

Add these imports at the top of `ecloud_input.py` (after the existing imports):

```python
import hashlib
import hmac
import os

CREEM_WEBHOOK_SECRET = os.getenv("CREEM_WEBHOOK_SECRET", "")
```

Add this route before `if __name__ == "__main__":`:

```python
@app.route("/webhook/creem", methods=["POST"])
def creem_webhook():
    """Handle Creem webhook events for subscription management."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("creem-signature")

    if not sig_header:
        return jsonify({"error": "Missing signature"}), 400

    # Verify HMAC-SHA256 signature
    computed = hmac.new(
        CREEM_WEBHOOK_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed, sig_header):
        logger.warning("Creem webhook: invalid signature")
        return jsonify({"error": "Invalid signature"}), 400

    event = request.get_json(force=True)
    event_type = event.get("eventType", "")
    obj = event.get("object", {})

    if event_type == "checkout.completed":
        _handle_creem_checkout_completed(obj)
    elif event_type == "subscription.paid":
        _handle_creem_subscription_paid(obj)
    elif event_type in ("subscription.canceled", "subscription.expired"):
        _handle_creem_subscription_revoked(obj)
    else:
        logger.info(f"Creem webhook: unhandled event type {event_type}")

    return jsonify({"status": "ok"}), 200


def _handle_creem_checkout_completed(obj: dict):
    """Grant access after initial checkout."""
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem checkout.completed: missing user_id in metadata")
        return

    customer_id = obj.get("customer", {}).get("id")
    subscription = obj.get("subscription", {})
    subscription_id = subscription.get("id")
    period_end_str = subscription.get("current_period_end")
    expire_time = _parse_creem_datetime(period_end_str)

    user_dao.update_access_creem(
        user_id=user_id,
        creem_customer_id=customer_id,
        creem_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Creem: granted access to user {user_id}, expires {expire_time}")


def _handle_creem_subscription_paid(obj: dict):
    """Extend access on subscription renewal."""
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem subscription.paid: missing user_id in metadata")
        return

    customer_id = obj.get("customer", {}).get("id")
    subscription_id = obj.get("id")
    period_end_str = obj.get("current_period_end")
    expire_time = _parse_creem_datetime(period_end_str)

    user_dao.update_access_creem(
        user_id=user_id,
        creem_customer_id=customer_id,
        creem_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Creem: extended access for user {user_id}, expires {expire_time}")


def _handle_creem_subscription_revoked(obj: dict):
    """Revoke access when subscription is cancelled or expired."""
    user_id = obj.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Creem subscription revoked: missing user_id in metadata")
        return

    user_dao.revoke_access(user_id)
    logger.info(f"Creem: revoked access for user {user_id}")


def _parse_creem_datetime(dt_str: str) -> datetime:
    """Parse ISO 8601 datetime string from Creem API."""
    if not dt_str:
        return datetime.now()
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        logger.warning(f"Creem: could not parse datetime {dt_str!r}, using now")
        return datetime.now()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/connector/test_creem_webhook.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add connector/ecloud/ecloud_input.py tests/unit/connector/test_creem_webhook.py
git commit -m "feat(creem): add /webhook/creem route for subscription events"
```

---

## Task 5: Add `update_access_creem` and `revoke_access` to `UserDAO`

The webhook needs two new methods on `UserDAO`.

**Files:**
- Modify: `dao/user_dao.py`
- Create: `tests/unit/dao/test_user_dao_creem.py`

**Step 1: Write the failing tests**

Create `tests/unit/dao/test_user_dao_creem.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for UserDAO Creem access methods"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestUserDAOCreem:
    """Tests for Creem-related UserDAO methods"""

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
    def test_update_access_creem(self, user_dao):
        """Should update user access with Creem fields"""
        user_dao.collection.update_one.return_value = MagicMock(modified_count=1)
        user_id = str(ObjectId())
        expire = datetime.now() + timedelta(days=30)

        result = user_dao.update_access_creem(
            user_id=user_id,
            creem_customer_id="cust_123",
            creem_subscription_id="sub_456",
            expire_time=expire,
        )

        assert result is True
        call_args = user_dao.collection.update_one.call_args
        update_set = call_args[0][1]["$set"]
        assert update_set["access.creem_customer_id"] == "cust_123"
        assert update_set["access.creem_subscription_id"] == "sub_456"
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
        assert "access.expire_time" in update_set
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/dao/test_user_dao_creem.py -v`
Expected: FAIL (methods don't exist)

**Step 3: Add methods to `UserDAO`**

Add these methods to `dao/user_dao.py` (before the `close` method):

```python
    def update_access_creem(
        self,
        user_id: str,
        creem_customer_id: str,
        creem_subscription_id: str,
        expire_time: datetime,
    ) -> bool:
        """Update user access with Creem subscription info."""
        try:
            object_id = ObjectId(user_id)
        except (TypeError, ValueError):
            return False

        result = self.collection.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "access.creem_customer_id": creem_customer_id,
                    "access.creem_subscription_id": creem_subscription_id,
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

Run: `pytest tests/unit/dao/test_user_dao_creem.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add dao/user_dao.py tests/unit/dao/test_user_dao_creem.py
git commit -m "feat(creem): add update_access_creem and revoke_access to UserDAO"
```

---

## Task 6: Update dispatcher gate tests

The dispatcher tests need to reflect the new return shape (checkout_url in data).

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
            {"checkout_url": "https://checkout.creem.io/test"},
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
git commit -m "test(creem): update dispatcher gate tests for checkout_url shape"
```

---

## Task 7: Remove dead `OrderDAO` usage from `AccessGate`

The `AccessGate` no longer uses `OrderDAO`. Verify no other code imports `OrderDAO` for gate purposes.

**Files:**
- Verify: `agent/runner/access_gate.py` (should have no OrderDAO import)

**Step 1: Verify**

Run: `grep -r "OrderDAO" agent/runner/`
Expected: No results

Run: `grep -r "order_dao" agent/runner/`
Expected: No results

**Step 2: Run full test suite**

Run: `pytest -m "not integration" -v`
Expected: All PASS

**Step 3: Commit (if any cleanup needed)**

```bash
git commit -m "chore(creem): verify OrderDAO removed from access gate"
```

---

## Task 8: Full integration verification

**Step 1: Run all non-integration tests**

Run: `pytest -m "not integration" -v --tb=short`
Expected: All PASS

**Step 2: Verify config loads correctly**

Run: `python -c "from conf.config import CONF; print(CONF['access_control'])"`
Expected: Should show the updated access_control config with creem section

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(creem): complete Creem subscription integration for access gate"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `conf/config.json` | Replace `stripe` section with `creem` section in `access_control` |
| `agent/runner/access_gate.py` | Rewrite: remove Stripe SDK, call Creem REST API for checkout sessions |
| `agent/runner/agent_handler.py` | Pass `checkout_url` from dispatch_data to `get_message()` |
| `connector/ecloud/ecloud_input.py` | Add `/webhook/creem` route with 4 event handlers, HMAC-SHA256 verification |
| `dao/user_dao.py` | Add `update_access_creem()` and `revoke_access()` methods |
| `tests/unit/runner/test_access_gate.py` | Rewrite for Creem |
| `tests/unit/runner/test_message_dispatcher_gate.py` | Update for checkout_url |
| `tests/unit/connector/test_creem_webhook.py` | New: webhook handler tests (replaces test_stripe_webhook.py) |
| `tests/unit/dao/test_user_dao_creem.py` | New: UserDAO Creem method tests (replaces test_user_dao_stripe.py) |

**Key differences from Stripe plan:**
- No Python SDK needed — Creem uses plain REST API calls via `requests`
- No `stripe` dependency in `requirements.txt`
- Webhook signature: `creem-signature` header, HMAC-SHA256 with raw body (stdlib `hmac`/`hashlib`)
- Event names: `checkout.completed`, `subscription.paid`, `subscription.canceled`, `subscription.expired` (vs Stripe's `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`)
- Event payload structure: `{ "eventType": "...", "object": { ... } }` (vs Stripe's `{ "type": "...", "data": { "object": { ... } } }`)
- User metadata key: `metadata.user_id` (same concept, same field name)
- MongoDB fields: `creem_customer_id`, `creem_subscription_id` (vs `stripe_customer_id`, `stripe_subscription_id`)
- Webhook route: `/webhook/creem` (vs `/webhook/stripe`)

**What stays untouched:**
- `OrderDAO` class (left as-is, just unused by gate)
- `orders` MongoDB collection (left as-is)
- All workflow/agent code
- All other connector code
