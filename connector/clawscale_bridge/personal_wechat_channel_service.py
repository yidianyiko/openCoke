from __future__ import annotations


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

    def create_or_reuse_channel(self, account_id: str):
        return self._normalize_state(
            self.gateway_client.create_or_reuse_channel(account_id=account_id)
        )

    def start_connect(self, account_id: str):
        return self._normalize_state(
            self.gateway_client.connect_channel(account_id=account_id)
        )

    def get_status(self, account_id: str):
        return self._normalize_state(self.gateway_client.get_status(account_id=account_id))

    def disconnect_channel(self, account_id: str):
        return self._normalize_state(
            self.gateway_client.disconnect_channel(account_id=account_id)
        )

    def archive_channel(self, account_id: str):
        return self._normalize_state(
            self.gateway_client.archive_channel(account_id=account_id)
        )
