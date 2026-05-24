"""POST /bridge/inbound as if we were ClawScale, return the assistant reply.

This is the one helper every turn calls. Keep it boring.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import requests

from tools.agent_smoke import _config


@dataclass
class BridgeReply:
    reply: str
    output_id: str | None
    causal_inbound_event_id: str
    raw: dict


class BridgeError(RuntimeError):
    def __init__(self, status: int, body: dict | str):
        super().__init__(f"bridge_error status={status} body={body!r}")
        self.status = status
        self.body = body


def send_as(
    coke_account_id: str,
    text: str,
    *,
    display_name: str | None = None,
    inbound_event_id: str | None = None,
    timestamp: int | None = None,
    request_timeout: float = 180.0,
) -> BridgeReply:
    """Send one message as `coke_account_id` and wait for the assistant reply.

    The bridge waits for the worker to produce a reply, so this is synchronous
    from the caller's view. `request_timeout` is the HTTP-level timeout — it
    must exceed the bridge's `reply_timeout_seconds`.
    """
    payload = {
        "customer_id": coke_account_id,
        "coke_account_id": coke_account_id,
        "message": text,
        "message_type": "text",
        "timestamp": int(timestamp or time.time()),
        "inbound_event_id": inbound_event_id or f"smoke_evt_{uuid.uuid4().hex}",
    }
    if display_name:
        payload["coke_account_display_name"] = display_name

    url = _config.bridge_base_url() + "/bridge/inbound"
    headers = {
        "Authorization": f"Bearer {_config.bridge_api_key()}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=request_timeout)
    try:
        body = response.json()
    except ValueError:
        body = response.text
    if response.status_code != 200 or not isinstance(body, dict) or not body.get("ok"):
        raise BridgeError(response.status_code, body)

    return BridgeReply(
        reply=body.get("reply") or "",
        output_id=body.get("output_id"),
        causal_inbound_event_id=body.get("causal_inbound_event_id") or payload["inbound_event_id"],
        raw=body,
    )
