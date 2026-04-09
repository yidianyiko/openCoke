#!/usr/bin/env python3
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from pymongo import DESCENDING, MongoClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from conf.config import CONF


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=body, method=method, headers=request_headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        data = json.loads(raw) if raw else {}
        return exc.code, data
    except URLError as exc:
        raise RuntimeError(f"http_request_failed:{url}:{exc}") from exc


def wait_until(description: str, predicate, timeout_seconds: float, interval_seconds: float = 1.0):
    deadline = time.time() + timeout_seconds
    last_value = None
    while time.time() < deadline:
        try:
            result = predicate()
        except Exception as exc:
            last_value = f"{type(exc).__name__}:{exc}"
            time.sleep(interval_seconds)
            continue
        last_value = result
        if result:
            return result
        time.sleep(interval_seconds)
    raise RuntimeError(f"timeout_waiting_for_{description}: last_value={last_value}")


def start_fake_provider(provider_python: str, provider_script: Path, host: str, port: int) -> subprocess.Popen:
    process = subprocess.Popen(
        [provider_python, str(provider_script), "--host", host, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return process


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def default_mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


def default_mongo_db_name() -> str:
    return CONF["mongodb"]["mongodb_name"]


def output_platform_fields_present(doc: dict[str, Any] | None) -> bool:
    if not isinstance(doc, dict):
        return False
    top_level_fields = ("platform", "from_user", "to_user", "chatroom_name")
    if any(field in doc for field in top_level_fields):
        return True
    metadata = doc.get("metadata")
    if not isinstance(metadata, dict):
        return False
    forbidden_metadata_fields = (
        "platform",
        "channel_id",
        "end_user_id",
        "external_id",
        "external_end_user_id",
        "clawscale",
    )
    return any(field in metadata for field in forbidden_metadata_fields)


def assert_cutover_invariants(result: dict[str, Any]) -> None:
    first_turn = result["first_turn"]
    steady_state = result["steady_state"]
    proactive = result["proactive"]
    mongo_assertions = result["mongo_assertions"]

    business_key = first_turn["business_conversation_key"]
    assert isinstance(business_key, str) and business_key.startswith("bc_")
    assert isinstance(steady_state["reply_text"], str) and steady_state["reply_text"].strip()
    assert steady_state["business_conversation_key"] == business_key
    assert proactive["delivered_count"] >= 1
    assert mongo_assertions["output_platform_fields_present"] is False


def mongo_collection(uri: str, db_name: str, name: str):
    client = MongoClient(uri)
    return client[db_name][name]


def fetch_latest_business_input(
    mongo_uri: str,
    mongo_db_name: str,
    account_id: str,
    min_input_timestamp: int,
    *,
    require_business_conversation_key: bool = True,
):
    collection = mongo_collection(mongo_uri, mongo_db_name, "inputmessages")
    doc = collection.find_one(
        {
            "metadata.source": "clawscale",
            "from_user": account_id,
            "input_timestamp": {"$gte": min_input_timestamp},
        },
        sort=[("input_timestamp", DESCENDING), ("_id", DESCENDING)],
    )
    if not isinstance(doc, dict):
        return False
    protocol = doc.get("metadata", {}).get("business_protocol", {})
    if not isinstance(protocol, dict):
        return False
    if not require_business_conversation_key:
        return doc
    business_key = protocol.get("business_conversation_key")
    if not isinstance(business_key, str) or not business_key.strip():
        return False
    return doc


def fetch_latest_business_output(
    mongo_uri: str,
    mongo_db_name: str,
    *,
    causal_inbound_event_id: str,
    min_expect_output_timestamp: int,
):
    collection = mongo_collection(mongo_uri, mongo_db_name, "outputmessages")
    doc = collection.find_one(
        {
            "platform": "business",
            "metadata.source": "clawscale",
            "expect_output_timestamp": {"$gte": min_expect_output_timestamp},
            "metadata.business_protocol.causal_inbound_event_id": causal_inbound_event_id,
            "metadata.business_protocol.business_conversation_key": {
                "$exists": True,
                "$ne": "",
            },
        },
        sort=[("expect_output_timestamp", DESCENDING), ("_id", DESCENDING)],
    )
    if not isinstance(doc, dict):
        return False
    return doc


def fetch_conversation_by_business_key(
    mongo_uri: str,
    mongo_db_name: str,
    *,
    business_conversation_key: str,
):
    collection = mongo_collection(mongo_uri, mongo_db_name, "conversations")
    doc = collection.find_one({"business_conversation_key": business_conversation_key})
    if not isinstance(doc, dict):
        return False
    return doc


def insert_proactive_output(
    mongo_uri: str,
    mongo_db_name: str,
    *,
    account_id: str,
    business_conversation_key: str,
    text: str,
    output_id: str,
):
    now_ts = int(time.time())
    collection = mongo_collection(mongo_uri, mongo_db_name, "outputmessages")
    document = {
        "_id": output_id,
        "account_id": account_id,
        "status": "pending",
        "message": text,
        "message_type": "text",
        "expect_output_timestamp": now_ts,
        "metadata": {
            "business_conversation_key": business_conversation_key,
            "delivery_mode": "push",
            "output_id": output_id,
            "idempotency_key": f"idem_{output_id}",
            "trace_id": f"trace_{output_id}",
        },
    }
    collection.insert_one(document)
    return document


def fetch_output_document(
    mongo_uri: str,
    mongo_db_name: str,
    output_id: str,
):
    collection = mongo_collection(mongo_uri, mongo_db_name, "outputmessages")
    return collection.find_one({"_id": output_id})


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local fake-WeChat E2E against the Coke/Clawscale stack.")
    parser.add_argument("--bridge-base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--fake-provider-base-url", default="http://127.0.0.1:19090")
    parser.add_argument("--fake-provider-host", default="127.0.0.1")
    parser.add_argument("--fake-provider-port", type=int, default=19090)
    parser.add_argument("--fake-provider-python", default=sys.executable)
    parser.add_argument("--provider-script", default=str(Path("scripts/fake_wechat_provider.py")))
    parser.add_argument("--display-name", default="WeChat E2E")
    parser.add_argument("--password", default="e2e-password-123")
    parser.add_argument("--email", default=None)
    parser.add_argument("--from-user-id", default="wx_e2e_user")
    parser.add_argument("--message", default="请简单回复一句，证明你收到这条 E2E 消息。")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--keep-provider", action="store_true")
    parser.add_argument("--no-start-provider", action="store_true")
    parser.add_argument("--followup-message", default="请继续用一句话回复这条后续消息。")
    parser.add_argument("--proactive-message", default="这是一次精确路由的主动提醒。")
    parser.add_argument("--mongo-uri", default=default_mongo_uri())
    parser.add_argument("--mongo-db-name", default=default_mongo_db_name())
    args = parser.parse_args()

    timestamp = int(time.time())
    email = args.email or f"wechat-e2e+{timestamp}@example.com"
    provider_process = None

    if not args.no_start_provider:
        provider_process = start_fake_provider(
            provider_python=args.fake_provider_python,
            provider_script=Path(args.provider_script),
            host=args.fake_provider_host,
            port=args.fake_provider_port,
        )

    try:
        wait_until(
            "fake_provider_healthz",
            lambda: http_json("GET", f"{args.fake_provider_base_url}/healthz", timeout=2)[0] == 200,
            timeout_seconds=10,
            interval_seconds=0.5,
        )
        http_json("POST", f"{args.fake_provider_base_url}/__e2e/reset", {})

        status, register_data = http_json(
            "POST",
            f"{args.bridge_base_url}/user/register",
            {
                "display_name": args.display_name,
                "email": email,
                "password": args.password,
            },
        )
        if status != 201 or not register_data.get("ok"):
            raise RuntimeError(f"user_register_failed:{status}:{register_data}")

        auth_data = register_data["data"]
        token = auth_data["token"]
        account_id = auth_data["user"]["id"]

        status, create_data = http_json(
            "POST",
            f"{args.bridge_base_url}/user/wechat-channel",
            headers=bearer(token),
        )
        if status != 200 or not create_data.get("ok"):
            raise RuntimeError(f"create_channel_failed:{status}:{create_data}")

        status, connect_data = http_json(
            "POST",
            f"{args.bridge_base_url}/user/wechat-channel/connect",
            headers=bearer(token),
        )
        if status != 200 or not connect_data.get("ok"):
            raise RuntimeError(f"connect_channel_failed:{status}:{connect_data}")

        channel = connect_data["data"]
        connect_url = channel.get("connect_url") or channel.get("qr_url")
        if not isinstance(connect_url, str) or not connect_url.startswith(args.fake_provider_base_url):
            raise RuntimeError(
                "gateway_not_pointing_to_fake_provider:"
                f"connect_url={connect_url} expected_prefix={args.fake_provider_base_url}. "
                "Restart gateway API with WEIXIN_PERSONAL_BASE_URL set to the fake provider."
            )
        qrcode = urlsplit(connect_url).path.rsplit("/", 1)[-1]
        if not qrcode:
            raise RuntimeError(f"invalid_connect_url:{connect_url}")

        status, confirm_data = http_json(
            "POST",
            f"{args.fake_provider_base_url}/__e2e/confirm",
            {"qrcode": qrcode},
        )
        if status != 200 or not confirm_data.get("ok"):
            raise RuntimeError(f"provider_confirm_failed:{status}:{confirm_data}")
        bot_token = confirm_data["bot_token"]

        connected = wait_until(
            "wechat_channel_connected",
            lambda: _fetch_connected_status(args.bridge_base_url, token),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )

        status, inbound_data = http_json(
            "POST",
            f"{args.fake_provider_base_url}/__e2e/inbound",
            {
                "bot_token": bot_token,
                "from_user_id": args.from_user_id,
                "text": args.message,
                "context_token": f"ctx_{timestamp}",
            },
        )
        if status != 200 or not inbound_data.get("ok"):
            raise RuntimeError(f"fake_inbound_failed:{status}:{inbound_data}")

        sent_messages = wait_until(
            "wechat_reply",
            lambda: _fetch_sent_messages(args.fake_provider_base_url, bot_token),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )

        first_reply = sent_messages[0]
        if not isinstance(first_reply.get("text"), str) or not first_reply["text"].strip():
            raise RuntimeError(f"empty_reply:{first_reply}")

        first_turn_input = wait_until(
            "first_turn_business_key",
            lambda: fetch_latest_business_input(
                args.mongo_uri,
                args.mongo_db_name,
                account_id,
                min_input_timestamp=timestamp,
                require_business_conversation_key=False,
            ),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )
        first_turn_protocol = first_turn_input["metadata"]["business_protocol"]
        causal_inbound_event_id = first_turn_protocol["causal_inbound_event_id"]
        first_turn_output = wait_until(
            "first_turn_business_output",
            lambda: fetch_latest_business_output(
                args.mongo_uri,
                args.mongo_db_name,
                causal_inbound_event_id=causal_inbound_event_id,
                min_expect_output_timestamp=timestamp,
            ),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )
        first_turn_output_protocol = first_turn_output["metadata"]["business_protocol"]
        business_conversation_key = first_turn_output_protocol[
            "business_conversation_key"
        ]
        first_turn_conversation = wait_until(
            "business_conversation_persisted",
            lambda: fetch_conversation_by_business_key(
                args.mongo_uri,
                args.mongo_db_name,
                business_conversation_key=business_conversation_key,
            ),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )

        followup_timestamp = int(time.time())
        status, followup_inbound = http_json(
            "POST",
            f"{args.fake_provider_base_url}/__e2e/inbound",
            {
                "bot_token": bot_token,
                "from_user_id": args.from_user_id,
                "text": args.followup_message,
                "context_token": f"ctx_followup_{timestamp}",
            },
        )
        if status != 200 or not followup_inbound.get("ok"):
            raise RuntimeError(f"fake_followup_inbound_failed:{status}:{followup_inbound}")

        steady_state_messages = wait_until(
            "wechat_steady_state_reply",
            lambda: _fetch_sent_messages(
                args.fake_provider_base_url, bot_token, minimum_count=2
            ),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )
        steady_state_reply = steady_state_messages[-1]
        steady_state_input = wait_until(
            "steady_state_business_key",
            lambda: fetch_latest_business_input(
                args.mongo_uri,
                args.mongo_db_name,
                account_id,
                min_input_timestamp=followup_timestamp,
            ),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )
        steady_state_business_key = steady_state_input["metadata"]["business_protocol"][
            "business_conversation_key"
        ]

        proactive_output_id = f"out_e2e_{timestamp}"
        insert_proactive_output(
            args.mongo_uri,
            args.mongo_db_name,
            account_id=account_id,
            business_conversation_key=business_conversation_key,
            text=args.proactive_message,
            output_id=proactive_output_id,
        )
        proactive_messages = wait_until(
            "wechat_proactive_delivery",
            lambda: _fetch_sent_messages(
                args.fake_provider_base_url, bot_token, minimum_count=3
            ),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )
        proactive_output_doc = wait_until(
            "proactive_output_document",
            lambda: fetch_output_document(
                args.mongo_uri, args.mongo_db_name, proactive_output_id
            ),
            timeout_seconds=args.timeout_seconds,
            interval_seconds=1.0,
        )
        result = {
            "ok": True,
            "account_id": account_id,
            "email": email,
            "channel_id": connected["channel_id"],
            "first_turn": {
                "reply_text": first_reply["text"],
                "business_conversation_key": business_conversation_key,
                "causal_inbound_event_id": causal_inbound_event_id,
                "conversation_id": str(first_turn_conversation["_id"]),
            },
            "steady_state": {
                "reply_text": steady_state_reply["text"],
                "business_conversation_key": steady_state_business_key,
            },
            "proactive": {
                "reply_text": proactive_messages[-1]["text"],
                "delivered_count": max(0, len(proactive_messages) - 2),
                "output_id": proactive_output_id,
            },
            "mongo_assertions": {
                "output_platform_fields_present": output_platform_fields_present(
                    proactive_output_doc
                ),
            },
        }
        assert_cutover_invariants(result)

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if not args.keep_provider:
            stop_process(provider_process)


def _fetch_connected_status(bridge_base_url: str, token: str):
    status, payload = http_json(
        "GET",
        f"{bridge_base_url}/user/wechat-channel/status",
        headers=bearer(token),
    )
    if status != 200 or not payload.get("ok"):
        return False
    data = payload.get("data", {})
    if data.get("status") != "connected":
        return False
    return data


def _fetch_sent_messages(
    fake_provider_base_url: str, bot_token: str, minimum_count: int = 1
):
    query = urlencode({"bot_token": bot_token})
    status, payload = http_json("GET", f"{fake_provider_base_url}/__e2e/sent?{query}")
    if status != 200 or not payload.get("ok"):
        return False
    data = payload.get("data")
    if not isinstance(data, list) or len(data) < minimum_count:
        return False
    return data


if __name__ == "__main__":
    sys.exit(main())
