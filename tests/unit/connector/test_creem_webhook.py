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
                "subscription": {
                    "id": "sub_test123",
                    "current_period_end": "2026-01-01T00:00:00Z",
                },
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
