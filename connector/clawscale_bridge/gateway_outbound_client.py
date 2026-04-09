from __future__ import annotations

import requests


class GatewayOutboundClient:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        session=None,
        timeout_seconds: int = 15,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def post_output(
        self,
        *,
        output_id: str,
        account_id: str,
        business_conversation_key: str,
        text: str,
        message_type: str,
        delivery_mode: str,
        idempotency_key: str,
        trace_id: str,
        causal_inbound_event_id: str | None = None,
    ):
        payload = {
            "output_id": output_id,
            "account_id": account_id,
            "business_conversation_key": business_conversation_key,
            "text": text,
            "message_type": message_type,
            "delivery_mode": delivery_mode,
            "idempotency_key": idempotency_key,
            "trace_id": trace_id,
        }
        if causal_inbound_event_id is not None:
            payload["causal_inbound_event_id"] = causal_inbound_event_id

        return self.session.post(
            self.api_url,
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout_seconds,
        )
