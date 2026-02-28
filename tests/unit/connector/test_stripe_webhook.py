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
            current_period_end=1735689600
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
