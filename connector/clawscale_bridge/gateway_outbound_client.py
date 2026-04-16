from __future__ import annotations

from datetime import datetime, timezone

import requests

from connector.clawscale_bridge.customer_ids import resolve_customer_id


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
        customer_id: str | None = None,
        account_id: str | None = None,
        business_conversation_key: str,
        text: str,
        message_type: str,
        delivery_mode: str,
        expect_output_timestamp,
        idempotency_key: str,
        trace_id: str,
        causal_inbound_event_id: str | None = None,
    ):
        if isinstance(expect_output_timestamp, str):
            normalized_expect_output_timestamp = expect_output_timestamp
        else:
            normalized_expect_output_timestamp = (
                datetime.fromtimestamp(expect_output_timestamp, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
        normalized_customer_id = resolve_customer_id(
            customer_id=customer_id,
            account_id=account_id,
        )
        payload = {
            "output_id": output_id,
            "customer_id": normalized_customer_id,
            "business_conversation_key": business_conversation_key,
            "text": text,
            "message_type": message_type,
            "delivery_mode": delivery_mode,
            "expect_output_timestamp": normalized_expect_output_timestamp,
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
