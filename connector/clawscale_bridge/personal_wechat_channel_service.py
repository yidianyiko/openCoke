from __future__ import annotations

from connector.clawscale_bridge.customer_ids import resolve_customer_id


class PersonalWechatChannelService:
    def __init__(self, gateway_client):
        self.gateway_client = gateway_client

    def _normalize_state(self, state: dict) -> dict:
        normalized = dict(state)
        if "qr" in normalized and "qr_code" not in normalized:
            normalized["qr_code"] = normalized["qr"]
        if "qr_url" in normalized and "qr_code_url" not in normalized:
            normalized["qr_code_url"] = normalized["qr_url"]
        if normalized.get("status") == "pending":
            connect_url = (
                normalized.get("connect_url")
                or normalized.get("qr_url")
                or normalized.get("qr_code_url")
            )
            if connect_url:
                normalized["connect_url"] = connect_url
        return normalized

    def create_or_reuse_channel(
        self,
        customer_id: str | None = None,
        account_id: str | None = None,
    ):
        normalized_customer_id = resolve_customer_id(
            customer_id=customer_id,
            account_id=account_id,
        )
        return self._normalize_state(
            self.gateway_client.create_or_reuse_channel(
                customer_id=normalized_customer_id
            )
        )

    def start_connect(
        self,
        customer_id: str | None = None,
        account_id: str | None = None,
    ):
        normalized_customer_id = resolve_customer_id(
            customer_id=customer_id,
            account_id=account_id,
        )
        return self._normalize_state(
            self.gateway_client.connect_channel(customer_id=normalized_customer_id)
        )

    def get_status(
        self,
        customer_id: str | None = None,
        account_id: str | None = None,
    ):
        normalized_customer_id = resolve_customer_id(
            customer_id=customer_id,
            account_id=account_id,
        )
        return self._normalize_state(
            self.gateway_client.get_status(customer_id=normalized_customer_id)
        )

    def disconnect_channel(
        self,
        customer_id: str | None = None,
        account_id: str | None = None,
    ):
        normalized_customer_id = resolve_customer_id(
            customer_id=customer_id,
            account_id=account_id,
        )
        return self._normalize_state(
            self.gateway_client.disconnect_channel(customer_id=normalized_customer_id)
        )

    def archive_channel(
        self,
        customer_id: str | None = None,
        account_id: str | None = None,
    ):
        normalized_customer_id = resolve_customer_id(
            customer_id=customer_id,
            account_id=account_id,
        )
        return self._normalize_state(
            self.gateway_client.archive_channel(customer_id=normalized_customer_id)
        )
