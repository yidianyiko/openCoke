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
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
      last_value = predicate()
      if last_value:
          return last_value
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local fake-WeChat E2E against the Coke/Clawscale stack.")
    parser.add_argument("--bridge-base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--fake-provider-base-url", default="http://127.0.0.1:19090")
    parser.add_argument("--fake-provider-host", default="127.0.0.1")
    parser.add_argument("--fake-provider-port", type=int, default=19090)
    parser.add_argument("--fake-provider-python", default=str(Path(".venv/bin/python")))
    parser.add_argument("--provider-script", default=str(Path("scripts/fake_wechat_provider.py")))
    parser.add_argument("--display-name", default="WeChat E2E")
    parser.add_argument("--password", default="e2e-password-123")
    parser.add_argument("--email", default=None)
    parser.add_argument("--from-user-id", default="wx_e2e_user")
    parser.add_argument("--message", default="请简单回复一句，证明你收到这条 E2E 消息。")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--keep-provider", action="store_true")
    parser.add_argument("--no-start-provider", action="store_true")
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

        status, confirm_data = http_json("POST", f"{args.fake_provider_base_url}/__e2e/confirm", {})
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

        print(
            json.dumps(
                {
                    "ok": True,
                    "account_id": account_id,
                    "email": email,
                    "channel_id": connected["channel_id"],
                    "reply_text": first_reply["text"],
                    "sent_count": len(sent_messages),
                },
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


def _fetch_sent_messages(fake_provider_base_url: str, bot_token: str):
    query = urlencode({"bot_token": bot_token})
    status, payload = http_json("GET", f"{fake_provider_base_url}/__e2e/sent?{query}")
    if status != 200 or not payload.get("ok"):
        return False
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return False
    return data


if __name__ == "__main__":
    sys.exit(main())
