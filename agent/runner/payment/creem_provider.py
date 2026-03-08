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
