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
