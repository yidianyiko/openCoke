# Multi-Provider Payment (Stripe + Creem) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 AccessGate 同时支持 Creem 和 Stripe 两种支付 provider，通过 `access_control.provider` 配置切换。

**Architecture:** 在 `agent/runner/payment/` 下引入 provider 抽象层，`AccessGate` 委托给具体 provider 生成 checkout URL；webhook 路由保持独立（`/webhook/creem` 和 `/webhook/stripe`）；DAO 新增 `update_access_stripe()`，其余逻辑不变。

**Tech Stack:** Python 3.12, stripe SDK, requests (Creem), Flask (webhook), pytest

---

### Task 1: 创建 PaymentProvider 抽象基类

**Files:**
- Create: `agent/runner/payment/__init__.py`
- Create: `agent/runner/payment/base.py`
- Test: `tests/unit/runner/payment/test_base.py`

**Step 1: 写失败测试**

新建 `tests/unit/runner/payment/` 目录，创建空 `__init__.py`，然后写：

```python
# tests/unit/runner/payment/test_base.py
import pytest
from agent.runner.payment.base import PaymentProvider


class TestPaymentProviderInterface:
    @pytest.mark.unit
    def test_base_class_cannot_be_instantiated_directly(self):
        """Base class methods must be overridden"""
        class BrokenProvider(PaymentProvider):
            pass  # 不实现任何方法

        p = BrokenProvider()
        with pytest.raises(NotImplementedError):
            p.create_checkout_url({"_id": "user123"})
```

**Step 2: 运行测试确认失败**

```bash
pytest tests/unit/runner/payment/test_base.py -v
```
Expected: `ImportError` 或 `ModuleNotFoundError`

**Step 3: 实现基类**

```python
# agent/runner/payment/__init__.py
# (空文件)
```

```python
# agent/runner/payment/base.py
# -*- coding: utf-8 -*-
"""Abstract base class for payment providers."""

from typing import Dict


class PaymentProvider:
    """Abstract payment provider. Subclasses must implement create_checkout_url."""

    def create_checkout_url(self, user: Dict) -> str:
        """Create a checkout session and return the URL. Returns '' on failure."""
        raise NotImplementedError
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/unit/runner/payment/test_base.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add agent/runner/payment/ tests/unit/runner/payment/
git commit -m "feat(payment): add PaymentProvider abstract base class"
```

---

### Task 2: 实现 CreemProvider（从 access_gate.py 迁移）

**Files:**
- Create: `agent/runner/payment/creem_provider.py`
- Test: `tests/unit/runner/payment/test_creem_provider.py`

**Step 1: 写失败测试**

```python
# tests/unit/runner/payment/test_creem_provider.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, patch
from bson import ObjectId
from agent.runner.payment.creem_provider import CreemProvider


CREEM_CFG = {
    "product_id": "prod_test123",
    "success_url": "https://example.com/success",
}


class TestCreemProvider:
    @pytest.fixture
    def provider(self):
        with patch.dict("os.environ", {"CREEM_API_KEY": "test_key"}):
            return CreemProvider(CREEM_CFG)

    @pytest.mark.unit
    def test_create_checkout_url_returns_url_on_success(self, provider):
        user = {"_id": ObjectId()}
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"checkout_url": "https://checkout.creem.io/abc"}

        with patch("agent.runner.payment.creem_provider.requests.post", return_value=mock_resp):
            url = provider.create_checkout_url(user)

        assert url == "https://checkout.creem.io/abc"

    @pytest.mark.unit
    def test_create_checkout_url_sends_user_id_in_metadata(self, provider):
        user_id = ObjectId()
        user = {"_id": user_id}
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"checkout_url": "https://checkout.creem.io/abc"}

        with patch("agent.runner.payment.creem_provider.requests.post", return_value=mock_resp) as mock_post:
            provider.create_checkout_url(user)

        payload = mock_post.call_args[1]["json"]
        assert payload["metadata"]["user_id"] == str(user_id)
        assert payload["product_id"] == "prod_test123"

    @pytest.mark.unit
    def test_create_checkout_url_returns_empty_on_api_error(self, provider):
        user = {"_id": ObjectId()}
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch("agent.runner.payment.creem_provider.requests.post", return_value=mock_resp):
            url = provider.create_checkout_url(user)

        assert url == ""

    @pytest.mark.unit
    def test_create_checkout_url_returns_empty_on_exception(self, provider):
        user = {"_id": ObjectId()}

        with patch("agent.runner.payment.creem_provider.requests.post", side_effect=Exception("timeout")):
            url = provider.create_checkout_url(user)

        assert url == ""
```

**Step 2: 运行测试确认失败**

```bash
pytest tests/unit/runner/payment/test_creem_provider.py -v
```
Expected: `ImportError`

**Step 3: 实现 CreemProvider**

```python
# agent/runner/payment/creem_provider.py
# -*- coding: utf-8 -*-
"""Creem payment provider."""

import os
from typing import Dict

import requests

from agent.runner.payment.base import PaymentProvider
from util.log_util import get_logger

logger = get_logger(__name__)

CREEM_API_BASE = "https://api.creem.io"


class CreemProvider(PaymentProvider):
    """Payment provider backed by Creem Checkout Sessions."""

    def __init__(self, config: Dict):
        self.product_id = config.get("product_id", "")
        self.success_url = config.get("success_url", "https://example.com/success")
        self.api_key = os.getenv("CREEM_API_KEY", "")

    def create_checkout_url(self, user: Dict) -> str:
        try:
            response = requests.post(
                f"{CREEM_API_BASE}/v1/checkouts",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "product_id": self.product_id,
                    "success_url": self.success_url,
                    "metadata": {"user_id": str(user["_id"])},
                },
            )
            if response.status_code == 201:
                return response.json().get("checkout_url", "")
            logger.error(f"Creem checkout API error: {response.status_code} {response.text}")
            return ""
        except Exception as e:
            logger.error(f"Failed to create Creem checkout session: {e}")
            return ""
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/unit/runner/payment/test_creem_provider.py -v
```
Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add agent/runner/payment/creem_provider.py tests/unit/runner/payment/test_creem_provider.py
git commit -m "feat(payment): add CreemProvider"
```

---

### Task 3: 实现 StripeProvider

**Files:**
- Create: `agent/runner/payment/stripe_provider.py`
- Test: `tests/unit/runner/payment/test_stripe_provider.py`

**背景知识：**
- Stripe Checkout Session 文档：`stripe.checkout.Session.create()`
- 关键参数：`price_id`（对应 Creem 的 `product_id`）、`success_url`、`mode="subscription"`
- 需要 `stripe` SDK：已在 requirements.txt 或需新增（运行前确认 `pip show stripe`）

**Step 1: 确认 stripe 已安装**

```bash
pip show stripe
```

若未安装：
```bash
pip install stripe && echo "stripe" >> requirements.txt
```

**Step 2: 写失败测试**

```python
# tests/unit/runner/payment/test_stripe_provider.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, patch
from bson import ObjectId
from agent.runner.payment.stripe_provider import StripeProvider


STRIPE_CFG = {
    "price_id": "price_test123",
    "success_url": "https://example.com/success",
}


class TestStripeProvider:
    @pytest.fixture
    def provider(self):
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_xxx"}):
            return StripeProvider(STRIPE_CFG)

    @pytest.mark.unit
    def test_create_checkout_url_returns_url_on_success(self, provider):
        user = {"_id": ObjectId()}
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_abc"

        with patch("agent.runner.payment.stripe_provider.stripe.checkout.Session.create", return_value=mock_session):
            url = provider.create_checkout_url(user)

        assert url == "https://checkout.stripe.com/pay/cs_test_abc"

    @pytest.mark.unit
    def test_create_checkout_url_sends_user_id_in_metadata(self, provider):
        user_id = ObjectId()
        user = {"_id": user_id}
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_abc"

        with patch("agent.runner.payment.stripe_provider.stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            provider.create_checkout_url(user)

        kwargs = mock_create.call_args[1]
        assert kwargs["metadata"]["user_id"] == str(user_id)
        assert kwargs["line_items"][0]["price"] == "price_test123"
        assert kwargs["mode"] == "subscription"

    @pytest.mark.unit
    def test_create_checkout_url_returns_empty_on_stripe_error(self, provider):
        import stripe
        user = {"_id": ObjectId()}

        with patch(
            "agent.runner.payment.stripe_provider.stripe.checkout.Session.create",
            side_effect=stripe.StripeError("card declined"),
        ):
            url = provider.create_checkout_url(user)

        assert url == ""

    @pytest.mark.unit
    def test_create_checkout_url_returns_empty_on_exception(self, provider):
        user = {"_id": ObjectId()}

        with patch(
            "agent.runner.payment.stripe_provider.stripe.checkout.Session.create",
            side_effect=Exception("network error"),
        ):
            url = provider.create_checkout_url(user)

        assert url == ""
```

**Step 3: 运行测试确认失败**

```bash
pytest tests/unit/runner/payment/test_stripe_provider.py -v
```
Expected: `ImportError`

**Step 4: 实现 StripeProvider**

```python
# agent/runner/payment/stripe_provider.py
# -*- coding: utf-8 -*-
"""Stripe payment provider."""

import os
from typing import Dict

import stripe

from agent.runner.payment.base import PaymentProvider
from util.log_util import get_logger

logger = get_logger(__name__)


class StripeProvider(PaymentProvider):
    """Payment provider backed by Stripe Checkout Sessions."""

    def __init__(self, config: Dict):
        self.price_id = config.get("price_id", "")
        self.success_url = config.get("success_url", "https://example.com/success")
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

    def create_checkout_url(self, user: Dict) -> str:
        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": self.price_id, "quantity": 1}],
                success_url=self.success_url,
                metadata={"user_id": str(user["_id"])},
            )
            return session.url or ""
        except stripe.StripeError as e:
            logger.error(f"Stripe checkout error: {e}")
            return ""
        except Exception as e:
            logger.error(f"Failed to create Stripe checkout session: {e}")
            return ""
```

**Step 5: 运行测试确认通过**

```bash
pytest tests/unit/runner/payment/test_stripe_provider.py -v
```
Expected: 4 tests PASS

**Step 6: Commit**

```bash
git add agent/runner/payment/stripe_provider.py tests/unit/runner/payment/test_stripe_provider.py requirements.txt
git commit -m "feat(payment): add StripeProvider"
```

---

### Task 4: 重构 AccessGate 使用 provider 抽象

**Files:**
- Modify: `agent/runner/access_gate.py`
- Modify: `tests/unit/runner/test_access_gate.py`

**Step 1: 写失败测试（新增 provider 切换测试）**

在 `tests/unit/runner/test_access_gate.py` 末尾追加：

```python
# 在文件末尾追加（在 class TestAccessGate 之外）

STRIPE_CONFIG = {
    "enabled": True,
    "provider": "stripe",
    "platforms": {"wechat": True},
    "stripe": {
        "price_id": "price_test123",
        "success_url": "https://example.com/success",
    },
    "deny_message": "Subscribe here:\n{checkout_url}",
    "expire_message": "Expired. Renew:\n{checkout_url}",
    "success_message": "Active until {expire_time}",
}


class TestAccessGateProviderSelection:
    """Tests for provider selection based on config."""

    @pytest.mark.unit
    def test_uses_creem_provider_when_configured(self):
        config = {**CREEM_CONFIG, "provider": "creem"}
        with patch("agent.runner.access_gate.CONF", {"access_control": config}):
            from agent.runner.access_gate import AccessGate
            gate = AccessGate()
            from agent.runner.payment.creem_provider import CreemProvider
            assert isinstance(gate.provider, CreemProvider)

    @pytest.mark.unit
    def test_uses_stripe_provider_when_configured(self):
        with patch("agent.runner.access_gate.CONF", {"access_control": STRIPE_CONFIG}):
            from agent.runner.access_gate import AccessGate
            gate = AccessGate()
            from agent.runner.payment.stripe_provider import StripeProvider
            assert isinstance(gate.provider, StripeProvider)

    @pytest.mark.unit
    def test_defaults_to_creem_when_provider_not_set(self):
        config = {k: v for k, v in CREEM_CONFIG.items() if k != "provider"}
        with patch("agent.runner.access_gate.CONF", {"access_control": config}):
            from agent.runner.access_gate import AccessGate
            gate = AccessGate()
            from agent.runner.payment.creem_provider import CreemProvider
            assert isinstance(gate.provider, CreemProvider)

    @pytest.mark.unit
    def test_check_delegates_checkout_url_to_provider(self):
        with patch("agent.runner.access_gate.CONF", {"access_control": CREEM_CONFIG}):
            from agent.runner.access_gate import AccessGate
            gate = AccessGate()
            gate.provider = MagicMock()
            gate.provider.create_checkout_url.return_value = "https://checkout.creem.io/test"

            user = {"_id": ObjectId()}
            result = gate.check(platform="wechat", user=user, admin_user_id="")

            gate.provider.create_checkout_url.assert_called_once_with(user)
            assert result[1]["checkout_url"] == "https://checkout.creem.io/test"
```

**Step 2: 运行测试确认失败**

```bash
pytest tests/unit/runner/test_access_gate.py::TestAccessGateProviderSelection -v
```
Expected: FAIL（`gate` 还没有 `provider` 属性）

**Step 3: 重构 access_gate.py**

将 `agent/runner/access_gate.py` 完整替换为：

```python
# -*- coding: utf-8 -*-
"""
Access Gate - subscription-based access control.

Supports multiple payment providers (creem, stripe) via config.
"""

from datetime import datetime
from typing import Dict, Optional, Tuple

from conf.config import CONF
from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)


class AccessGate:
    """Subscription-based access gate. Provider selected from config."""

    def __init__(self):
        self.config = CONF.get("access_control", {})
        self.user_dao = UserDAO()
        self.provider = self._init_provider()

    def _init_provider(self):
        provider_name = self.config.get("provider", "creem")
        if provider_name == "stripe":
            from agent.runner.payment.stripe_provider import StripeProvider
            return StripeProvider(self.config.get("stripe", {}))
        else:
            from agent.runner.payment.creem_provider import CreemProvider
            return CreemProvider(self.config.get("creem", {}))

    def is_enabled(self, platform: str) -> bool:
        if not self.config.get("enabled", False):
            return False
        return self.config.get("platforms", {}).get(platform, False)

    def check(
        self,
        platform: str,
        user: Dict,
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
        """Delegate to the configured payment provider."""
        return self.provider.create_checkout_url(user)

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

**Step 4: 运行全部 access_gate 测试确认通过**

```bash
pytest tests/unit/runner/test_access_gate.py -v
```
Expected: 全部 PASS（注意：原有的 `test_create_checkout_url_calls_creem_api` 测试需要同步修改，见下一步）

**Step 4b: 修复原有 test_create_checkout_url 测试**

原测试 `test_create_checkout_url_calls_creem_api` 直接 patch `agent.runner.access_gate.requests.post`，但现在 requests 在 creem_provider 模块里。更新该测试：

将 `tests/unit/runner/test_access_gate.py` 中的 `test_create_checkout_url_calls_creem_api` 改为：

```python
@pytest.mark.unit
def test_create_checkout_url_calls_creem_api(self, access_gate):
    """Checkout session should include user_id in metadata"""
    user_id = ObjectId()
    user = {"_id": user_id}
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"checkout_url": "https://checkout.creem.io/test"}

    with patch("agent.runner.payment.creem_provider.requests.post", return_value=mock_response) as mock_post:
        url = access_gate._create_checkout_url(user)
        assert url == "https://checkout.creem.io/test"
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["metadata"]["user_id"] == str(user_id)
        assert payload["product_id"] == "prod_test123"
```

**Step 5: 运行全部 access_gate 测试确认通过**

```bash
pytest tests/unit/runner/test_access_gate.py -v
```
Expected: 全部 PASS

**Step 6: Commit**

```bash
git add agent/runner/access_gate.py tests/unit/runner/test_access_gate.py
git commit -m "refactor(access_gate): delegate checkout URL creation to payment provider"
```

---

### Task 5: 新增 update_access_stripe() DAO 方法

**Files:**
- Modify: `dao/user_dao.py`
- Test: `tests/unit/dao/test_user_dao_stripe.py`

**Step 1: 写失败测试**

```python
# tests/unit/dao/test_user_dao_stripe.py
# -*- coding: utf-8 -*-
"""Unit tests for UserDAO Stripe access methods."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from bson import ObjectId


class TestUserDaoStripe:

    @pytest.fixture
    def dao(self):
        with patch("dao.user_dao.MongoClient"):
            from dao.user_dao import UserDAO
            d = UserDAO()
            d.collection = MagicMock()
            return d

    @pytest.mark.unit
    def test_update_access_stripe_calls_update_one(self, dao):
        user_id = str(ObjectId())
        expire = datetime.now() + timedelta(days=30)
        dao.collection.update_one.return_value = MagicMock(modified_count=1)

        result = dao.update_access_stripe(
            user_id=user_id,
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            expire_time=expire,
        )

        assert result is True
        dao.collection.update_one.assert_called_once()
        call_args = dao.collection.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert update_doc["access.stripe_customer_id"] == "cus_test"
        assert update_doc["access.stripe_subscription_id"] == "sub_test"
        assert update_doc["access.expire_time"] == expire

    @pytest.mark.unit
    def test_update_access_stripe_returns_false_for_invalid_id(self, dao):
        result = dao.update_access_stripe(
            user_id="not-an-objectid",
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            expire_time=datetime.now(),
        )
        assert result is False
        dao.collection.update_one.assert_not_called()

    @pytest.mark.unit
    def test_update_access_stripe_returns_false_when_not_found(self, dao):
        user_id = str(ObjectId())
        dao.collection.update_one.return_value = MagicMock(modified_count=0)
        result = dao.update_access_stripe(
            user_id=user_id,
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            expire_time=datetime.now(),
        )
        assert result is False
```

**Step 2: 运行测试确认失败**

```bash
pytest tests/unit/dao/test_user_dao_stripe.py -v
```
Expected: `AttributeError: 'UserDAO' object has no attribute 'update_access_stripe'`

**Step 3: 在 user_dao.py 中新增方法**

在 `update_access_creem()` 方法之后（约第 484 行），新增：

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
    except (TypeError, ValueError, InvalidId):
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
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/unit/dao/test_user_dao_stripe.py -v
```
Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add dao/user_dao.py tests/unit/dao/test_user_dao_stripe.py
git commit -m "feat(dao): add update_access_stripe method"
```

---

### Task 6: 新增 /webhook/stripe 路由到 Flask app

**Files:**
- Modify: `connector/ecloud/ecloud_input.py`
- Test: `tests/unit/connector/test_stripe_webhook.py`

**背景知识：**
- Stripe webhook 验签：`stripe.Webhook.construct_event(payload, sig_header, secret)`
- 签名 header：`Stripe-Signature`
- 关键事件：
  - `checkout.session.completed`：首次购买，`session.metadata.user_id`
  - `invoice.paid`：续费，需通过 `subscription` 找到 `metadata.user_id`（需调用 `stripe.Subscription.retrieve()`）
  - `customer.subscription.deleted`：取消/过期，同上

**Step 1: 写失败测试**

```python
# tests/unit/connector/test_stripe_webhook.py
# -*- coding: utf-8 -*-
"""Unit tests for Stripe webhook handler in ecloud_input."""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


def make_app():
    with patch.dict("os.environ", {
        "STRIPE_WEBHOOK_SECRET": "whsec_test",
        "CREEM_WEBHOOK_SECRET": "whsec_creem",
    }):
        import importlib
        import connector.ecloud.ecloud_input as m
        importlib.reload(m)
        return m.app


class TestStripeWebhook:

    @pytest.fixture
    def client(self):
        app = make_app()
        app.config["TESTING"] = True
        return app.test_client()

    @pytest.fixture
    def mock_user_dao(self):
        with patch("connector.ecloud.ecloud_input.user_dao") as mock:
            yield mock

    @pytest.mark.unit
    def test_missing_signature_returns_400(self, client, mock_user_dao):
        resp = client.post("/webhook/stripe", data=b"{}", content_type="application/json")
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_invalid_signature_returns_400(self, client, mock_user_dao):
        import stripe
        with patch("connector.ecloud.ecloud_input.stripe.Webhook.construct_event",
                   side_effect=stripe.SignatureVerificationError("bad sig", "sig_header")):
            resp = client.post(
                "/webhook/stripe",
                data=b'{"type":"checkout.session.completed"}',
                content_type="application/json",
                headers={"Stripe-Signature": "bad_sig"},
            )
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_checkout_session_completed_grants_access(self, client, mock_user_dao):
        import stripe
        user_id = "64f0000000000000000000ab"
        event = MagicMock()
        event.type = "checkout.session.completed"
        event.data.object = {
            "metadata": {"user_id": user_id},
            "customer": "cus_test",
            "subscription": "sub_test",
        }
        mock_sub = MagicMock()
        mock_sub.current_period_end = 1999999999

        with patch("connector.ecloud.ecloud_input.stripe.Webhook.construct_event", return_value=event):
            with patch("connector.ecloud.ecloud_input.stripe.Subscription.retrieve", return_value=mock_sub):
                resp = client.post(
                    "/webhook/stripe",
                    data=b"{}",
                    content_type="application/json",
                    headers={"Stripe-Signature": "t=1,v1=abc"},
                )

        assert resp.status_code == 200
        mock_user_dao.update_access_stripe.assert_called_once()
        call_kwargs = mock_user_dao.update_access_stripe.call_args[1]
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["stripe_customer_id"] == "cus_test"
        assert call_kwargs["stripe_subscription_id"] == "sub_test"

    @pytest.mark.unit
    def test_subscription_deleted_revokes_access(self, client, mock_user_dao):
        import stripe
        user_id = "64f0000000000000000000ab"
        event = MagicMock()
        event.type = "customer.subscription.deleted"
        event.data.object = {
            "id": "sub_test",
            "metadata": {"user_id": user_id},
        }

        with patch("connector.ecloud.ecloud_input.stripe.Webhook.construct_event", return_value=event):
            resp = client.post(
                "/webhook/stripe",
                data=b"{}",
                content_type="application/json",
                headers={"Stripe-Signature": "t=1,v1=abc"},
            )

        assert resp.status_code == 200
        mock_user_dao.revoke_access.assert_called_once_with(user_id)

    @pytest.mark.unit
    def test_unknown_event_returns_200(self, client, mock_user_dao):
        import stripe
        event = MagicMock()
        event.type = "payment_intent.created"

        with patch("connector.ecloud.ecloud_input.stripe.Webhook.construct_event", return_value=event):
            resp = client.post(
                "/webhook/stripe",
                data=b"{}",
                content_type="application/json",
                headers={"Stripe-Signature": "t=1,v1=abc"},
            )

        assert resp.status_code == 200
```

**Step 2: 运行测试确认失败**

```bash
pytest tests/unit/connector/test_stripe_webhook.py -v
```
Expected: `404` on `/webhook/stripe` 或 `ImportError`

**Step 3: 修改 ecloud_input.py**

在文件顶部的 import/env 区域新增（紧接着 `CREEM_WEBHOOK_SECRET` 那行之后）：

```python
import stripe

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
```

然后在 `/webhook/creem` 路由之后追加：

```python
@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events for subscription management."""
    payload = request.get_data(as_text=False)
    sig_header = request.headers.get("Stripe-Signature")

    if not sig_header:
        return jsonify({"error": "Missing signature"}), 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        logger.warning("Stripe webhook: invalid signature")
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event.type

    if event_type == "checkout.session.completed":
        _handle_stripe_checkout_completed(event.data.object)
    elif event_type == "invoice.paid":
        _handle_stripe_invoice_paid(event.data.object)
    elif event_type == "customer.subscription.deleted":
        _handle_stripe_subscription_deleted(event.data.object)
    else:
        logger.info(f"Stripe webhook: unhandled event type {event_type}")

    return jsonify({"status": "ok"}), 200


def _handle_stripe_checkout_completed(session: dict):
    """Grant access after initial Stripe checkout."""
    user_id = session.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Stripe checkout.session.completed: missing user_id in metadata")
        return

    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    expire_time = _get_stripe_subscription_expire(subscription_id)

    user_dao.update_access_stripe(
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Stripe: granted access to user {user_id}, expires {expire_time}")


def _handle_stripe_invoice_paid(invoice: dict):
    """Extend access on Stripe subscription renewal."""
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    sub = stripe.Subscription.retrieve(subscription_id)
    user_id = sub.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Stripe invoice.paid: missing user_id in subscription metadata")
        return

    customer_id = invoice.get("customer")
    expire_time = _get_stripe_subscription_expire(subscription_id)

    user_dao.update_access_stripe(
        user_id=user_id,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        expire_time=expire_time,
    )
    logger.info(f"Stripe: extended access for user {user_id}, expires {expire_time}")


def _handle_stripe_subscription_deleted(subscription: dict):
    """Revoke access when Stripe subscription is cancelled."""
    user_id = subscription.get("metadata", {}).get("user_id")
    if not user_id:
        logger.warning("Stripe subscription.deleted: missing user_id in metadata")
        return

    user_dao.revoke_access(user_id)
    logger.info(f"Stripe: revoked access for user {user_id}")


def _get_stripe_subscription_expire(subscription_id: str) -> datetime:
    """Fetch subscription period end from Stripe and convert to datetime."""
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        ts = sub.current_period_end
        return datetime.utcfromtimestamp(ts)
    except Exception as e:
        logger.warning(f"Stripe: could not fetch subscription {subscription_id}: {e}")
        return datetime.now()
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/unit/connector/test_stripe_webhook.py -v
```
Expected: 5 tests PASS

**Step 5: Commit**

```bash
git add connector/ecloud/ecloud_input.py tests/unit/connector/test_stripe_webhook.py
git commit -m "feat(stripe): add /webhook/stripe route to Flask app"
```

---

### Task 7: 更新配置文件

**Files:**
- Modify: `conf/config.json`

**Step 1: 修改 access_control 配置块**

将 `conf/config.json` 中的 `access_control` 块替换为：

```json
"access_control": {
    "enabled": false,
    "provider": "creem",
    "platforms": {
        "wechat": false
    },
    "creem": {
        "product_id": "${CREEM_PRODUCT_ID}",
        "success_url": "${CREEM_SUCCESS_URL}"
    },
    "stripe": {
        "price_id": "${STRIPE_PRICE_ID}",
        "success_url": "${STRIPE_SUCCESS_URL}"
    },
    "deny_message": "Hi! I'd love to chat with you. Subscribe here to get started:\n{checkout_url}",
    "expire_message": "Your subscription has expired. Renew here to keep chatting:\n{checkout_url}",
    "success_message": "[System] Subscription active until {expire_time}"
},
```

**Step 2: 更新 CLAUDE.md 配置文档**

在 `CLAUDE.md` 的 Access Control (Gate System) 节中，将配置示例更新，新增 `provider` 字段说明。

**Step 3: Commit**

```bash
git add conf/config.json CLAUDE.md
git commit -m "config: add provider field and stripe config to access_control"
```

---

### Task 8: 全量测试 & 收尾

**Step 1: 运行全部单元测试**

```bash
pytest -m "not integration" -v
```
Expected: 全部 PASS，无新失败

**Step 2: 运行覆盖率检查**

```bash
pytest -m "not integration" --cov=agent/runner/payment --cov=agent/runner/access_gate --cov=connector/ecloud/ecloud_input --cov=dao/user_dao --cov-report=term-missing
```
Expected: payment/ 模块覆盖率 > 90%

**Step 3: 格式化代码**

```bash
black agent/runner/payment/ connector/ecloud/ecloud_input.py dao/user_dao.py && isort agent/runner/payment/ connector/ecloud/ecloud_input.py dao/user_dao.py
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "style: format payment provider files"
```

---

## 环境变量汇总

| 变量 | Provider | 说明 |
|------|----------|------|
| `CREEM_API_KEY` | creem | Creem REST API key |
| `CREEM_WEBHOOK_SECRET` | creem | Webhook 签名密钥 |
| `CREEM_PRODUCT_ID` | creem | Creem 产品 ID |
| `CREEM_SUCCESS_URL` | creem | 支付成功跳转 URL |
| `STRIPE_SECRET_KEY` | stripe | Stripe secret key (sk_live_... / sk_test_...) |
| `STRIPE_WEBHOOK_SECRET` | stripe | Webhook 签名密钥 (whsec_...) |
| `STRIPE_PRICE_ID` | stripe | Stripe Price ID (price_...) |
| `STRIPE_SUCCESS_URL` | stripe | 支付成功跳转 URL |

## 切换 Provider

只需修改 `conf/config.json`：

```json
"access_control": {
    "provider": "stripe"   // 或 "creem"
}
```
