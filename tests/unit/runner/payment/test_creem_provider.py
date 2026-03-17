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
