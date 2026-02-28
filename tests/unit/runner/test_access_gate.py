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
        with patch("agent.runner.access_gate.stripe") as mock_stripe:
            mock_stripe.checkout.Session.create.return_value = MagicMock(
                url="https://checkout.stripe.com/test"
            )
            result = access_gate.check(
                platform="wechat",
                user=user,
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
                admin_user_id="",
            )
            call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
            assert call_kwargs["metadata"]["user_id"] == str(user_id)
            assert call_kwargs["mode"] == "subscription"
            assert call_kwargs["subscription_data"]["metadata"]["user_id"] == str(user_id)
