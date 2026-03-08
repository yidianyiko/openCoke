# -*- coding: utf-8 -*-
"""Abstract base class for payment providers."""

from typing import Dict


class PaymentProvider:
    """Abstract payment provider. Subclasses must implement create_checkout_url."""

    def create_checkout_url(self, user: Dict) -> str:
        """Create a checkout session and return the URL. Returns '' on failure."""
        raise NotImplementedError
