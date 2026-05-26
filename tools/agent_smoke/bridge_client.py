"""POST /bridge/inbound as if we were ClawScale, return the assistant reply.

This is the one helper every turn calls. Keep it boring.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import requests

from tools.agent_smoke import _config

SYNC_REPLY_TIMEOUT_FALLBACK_REPLY = "正在处理中，稍后把结果发给你。"
FINAL_OUTPUT_STATUSES = {"handled", "failed"}


@dataclass
class BridgeReply:
    reply: str
    output_id: str | None
    causal_inbound_event_id: str
    raw: dict
    placeholder_received: bool = False
    late_reply_landed: bool = False
    placeholder_reply: str | None = None
    placeholder_output_id: str | None = None
    polling_seconds_used: float = 0.0


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
    placeholder_received = SYNC_REPLY_TIMEOUT_FALLBACK_REPLY in reply_text
    late_reply_landed = False
    placeholder_reply = reply_text if placeholder_received else None
    placeholder_output_id = output_id if placeholder_received else None
    polling_seconds_used = 0.0

    if placeholder_received:
        poll_start = time.monotonic()
        late_reply_text, late_output_doc = poll_late_reply_text(
            causal_inbound_event_id=event_id,
            coke_account_id=payload["coke_account_id"],
        )
        polling_seconds_used = time.monotonic() - poll_start
        if late_reply_text and late_output_doc:
            reply_text = late_reply_text
            output_id = str(late_output_doc.get("_id")) if late_output_doc.get("_id") else None
            late_reply_landed = True

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
        placeholder_received=placeholder_received,
        late_reply_landed=late_reply_landed,
        placeholder_reply=placeholder_reply,
        placeholder_output_id=placeholder_output_id,
        polling_seconds_used=polling_seconds_used,
    )


def poll_late_reply_text(
    *,
    causal_inbound_event_id: str,
    coke_account_id: str,
    poll_seconds: float = 45.0,
    poll_interval_seconds: float = 1.5,
) -> tuple[str | None, dict | None]:
    """
    After send_as returns the placeholder (sync timeout), poll mongo for
    the late real reply on the same causal_inbound_event_id.
    Returns (reply_text, output_doc) or (None, None) on timeout.
    """
    from pymongo import MongoClient  # local import to keep the basic send path lean

    client = MongoClient(_config.mongo_uri())
    collection = client[_config.mongo_db_name()].outputmessages
    deadline = time.monotonic() + poll_seconds
    query = {
        "$and": [
            {"$or": [{"to_user": coke_account_id}, {"account_id": coke_account_id}]},
            {
                "$or": [
                    {
                        "metadata.business_protocol.causal_inbound_event_id": causal_inbound_event_id
                    },
                    {"metadata.causal_inbound_event_id": causal_inbound_event_id},
                ]
            },
            {"status": {"$in": sorted(FINAL_OUTPUT_STATUSES)}},
            {"message": {"$nin": ["", SYNC_REPLY_TIMEOUT_FALLBACK_REPLY]}},
        ]
    }
    try:
        while time.monotonic() < deadline:
            for doc in collection.find(query).sort("_id", -1):
                if not _is_final_output_doc(doc):
                    continue
                reply_text = _output_reply_text(doc)
                if reply_text and reply_text != SYNC_REPLY_TIMEOUT_FALLBACK_REPLY:
                    return reply_text, doc
            time.sleep(poll_interval_seconds)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    return None, None


def _is_final_output_doc(doc: dict) -> bool:
    return doc.get("status") in FINAL_OUTPUT_STATUSES


def _output_reply_text(doc: dict) -> str:
    for key in ("message", "text", "reply"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


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
