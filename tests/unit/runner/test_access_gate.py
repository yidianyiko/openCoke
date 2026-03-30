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

        with patch("agent.runner.payment.creem_provider.requests.post", return_value=mock_response) as mock_post:
            url = access_gate._create_checkout_url(user)
            assert url == "https://checkout.creem.io/test"
            call_kwargs = mock_post.call_args
            payload = call_kwargs[1]["json"]
            assert payload["metadata"]["user_id"] == str(user_id)
            assert payload["product_id"] == "prod_test123"


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
