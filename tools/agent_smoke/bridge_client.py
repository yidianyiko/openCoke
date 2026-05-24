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
    tenant_id: str | None = None,
    clawscale_user_id: str | None = None,
    channel_id: str | None = None,
    platform: str = "wechat_personal",
    external_id: str | None = None,
    end_user_id: str | None = None,
    channel_scope: str = "personal",
    inbound_event_id: str | None = None,
    timestamp: int | None = None,
    request_timeout: float = 180.0,
) -> BridgeReply:
    """Send one message as `coke_account_id` and wait for the assistant reply.

    The bridge waits for the worker to produce a reply, so this is synchronous
    from the caller's view. `request_timeout` is the HTTP-level timeout — it
    must exceed the bridge's `reply_timeout_seconds`.

    `tenant_id` / `clawscale_user_id` come from `account_factory.provision_account`
    and may be `None` when provisioning was skipped — we synthesize deterministic
    placeholders so the bridge's required-context check passes (it only checks
    non-empty strings, not DB existence).
    """
    label = coke_account_id.replace("ck_smoke_", "").replace("ck_", "")
    payload = {
        "customer_id": coke_account_id,
        "coke_account_id": coke_account_id,
        "tenant_id": tenant_id or f"tnt_smoke_{label}",
        "clawscale_user_id": clawscale_user_id or f"csu_smoke_{label}",
        "channel_id": channel_id or f"chn_smoke_{label}",
        "platform": platform,
        "external_id": external_id or f"ext_smoke_{label}",
        "end_user_id": end_user_id or f"eu_smoke_{label}",
        "channel_scope": channel_scope,
        "input": text,
        "text": text,
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

    reply_text = body.get("reply") or ""
    output_id = body.get("output_id")
    event_id = body.get("causal_inbound_event_id") or payload["inbound_event_id"]

    # Bridge's reply_timeout_seconds (default 25) is short for shared dev where
    # workers may be contended. If the bridge returned ok but no reply yet, poll
    # mongo for the assistant's output. First try the causal_inbound_event_id
    # (production-correct match); fall back to recipient + timestamp because the
    # worker batches a user message with a concurrently-injected product
    # notification and propagates the FIRST batched message's causal id onto
    # the output, orphaning our user message's id. (See bug F in
    # docs/issues/2026-05-24-agent-shared-reminder-smoke.md.)
    if not reply_text:
        reply_text, output_id = _poll_for_reply(
            event_id,
            request_timeout,
            recipient_account_id=payload["coke_account_id"],
            since_ts=payload["timestamp"],
        )

    return BridgeReply(
        reply=reply_text,
        output_id=output_id,
        causal_inbound_event_id=event_id,
        raw=body,
    )


def _poll_for_reply(
    event_id: str,
    deadline_seconds: float,
    *,
    recipient_account_id: str,
    since_ts: int,
) -> tuple[str, str | None]:
    from pymongo import MongoClient  # local import to keep the basic send path lean

    client = MongoClient(_config.mongo_uri())
    collection = client[_config.mongo_db_name()].outputmessages
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        cursor = collection.find(
            {"metadata.business_protocol.causal_inbound_event_id": event_id}
        ).sort("input_timestamp", 1)
        messages = list(cursor)
        if messages:
            text = "\n".join(m.get("message", "") for m in messages if m.get("message"))
            return text, str(messages[0].get("_id")) if messages else None
        # Fallback: causal_id may be hijacked by a concurrent product
        # notification batched into the same worker turn. Match by recipient
        # + timestamp window — pick the most recent pending output sent to
        # this account after we sent the inbound.
        if recipient_account_id and since_ts:
            recent = collection.find_one(
                {
                    "to_user": recipient_account_id,
                    "input_timestamp": {"$gte": since_ts - 5},
                },
                sort=[("input_timestamp", -1)],
            )
            if recent and recent.get("message"):
                return recent.get("message", ""), str(recent.get("_id"))
        time.sleep(1.5)
    return "", None
