import requests


class GatewayIdentityClient:
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key

    def bind_identity(
        self,
        tenant_id: str,
        channel_id: str,
        external_id: str,
        coke_account_id: str,
    ):
        response = requests.post(
            url=self.api_url,
            json={
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "external_id": external_id,
                "coke_account_id": coke_account_id,
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("invalid_gateway_identity_response")
        if not payload.get("ok"):
            raise ValueError(payload.get("error", "gateway_identity_bind_failed"))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("invalid_gateway_identity_response")
        return data

    def bind(
        self,
        tenant_id: str,
        channel_id: str,
        external_id: str,
        coke_account_id: str,
    ):
        return self.bind_identity(
            tenant_id=tenant_id,
            channel_id=channel_id,
            external_id=external_id,
            coke_account_id=coke_account_id,
        )
