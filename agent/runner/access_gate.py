# -*- coding: utf-8 -*-
"""
Access Gate - Creem subscription-based access control.

New users get a Creem Checkout link. Webhook grants access on payment.
"""

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
                    "x-api-key": CREEM_API_KEY,
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
