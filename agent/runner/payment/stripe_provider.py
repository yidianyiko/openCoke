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
