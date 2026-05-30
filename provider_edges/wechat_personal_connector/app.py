from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from base64 import b64encode
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from flask import Flask, jsonify, request


DEFAULT_ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_STATE_PATH = "/data/wechat_personal_state.json"


@dataclass(frozen=True)
class ConnectorConfig:
    api_key: str | None = None
    webhook_url: str = ""
    webhook_api_key: str | None = None
    ilink_base_url: str = DEFAULT_ILINK_BASE_URL
    pairing_code_prefix: str = "pairing_"
    poll_interval_seconds: float = 2.0


class ConnectorState:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {"status": "not_started"}
            return json.loads(self.path.read_text())

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current: dict[str, Any]
            if self.path.exists():
                current = json.loads(self.path.read_text())
            else:
                current = {}
            current.update(values)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            temp_path.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")
            temp_path.replace(self.path)
            return current


class IlinkClient:
    def __init__(self) -> None:
        self._client = httpx.Client()

    def get_qr(self, *, ilink_base_url: str) -> dict[str, Any]:
        response = self._client.get(
            f"{ilink_base_url.rstrip('/')}/ilink/bot/get_bot_qrcode",
            params={"bot_type": "3"},
            headers={"iLink-App-ClientVersion": "1"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def get_qr_status(self, *, ilink_base_url: str, qrcode: str) -> dict[str, Any]:
        response = self._client.get(
            f"{ilink_base_url.rstrip('/')}/ilink/bot/get_qrcode_status",
            params={"qrcode": qrcode},
            headers={"iLink-App-ClientVersion": "1"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def send_text(
        self, *, base_url: str, token: str, to_user_id: str, text: str
    ) -> dict[str, Any]:
        client_id = f"coke-{int(time.time() * 1000)}-{uuid.uuid4().hex[:12]}"
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": 2,
                "message_state": 2,
                "context_token": "",
                "item_list": [
                    {
                        "type": 1,
                        "text_item": {"text": text},
                    }
                ],
            },
            "base_info": {"channel_version": "1.0.0"},
        }
        response = self._client.post(
            f"{base_url.rstrip('/')}/ilink/bot/sendmessage",
            headers=_ilink_bot_headers(token),
            json=body,
            timeout=30.0,
        )
        response.raise_for_status()
        return {"message_id": client_id, "provider_response": response.text}

    def get_updates(self, *, base_url: str, token: str, cursor: str) -> dict[str, Any]:
        response = self._client.post(
            f"{base_url.rstrip('/')}/ilink/bot/getupdates",
            headers=_ilink_bot_headers(token),
            json={"get_updates_buf": cursor or ""},
            timeout=40.0,
        )
        response.raise_for_status()
        return response.json()


def _ilink_bot_headers(token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "X-WECHAT-UIN": b64encode(str(random.randrange(0xFFFFFFFF)).encode()).decode(),
    }


def config_from_env() -> ConnectorConfig:
    return ConnectorConfig(
        api_key=os.getenv("WECHAT_CONNECTOR_API_KEY"),
        webhook_url=os.getenv("WECHAT_CONNECTOR_WEBHOOK_URL", ""),
        webhook_api_key=os.getenv("WECHAT_CONNECTOR_WEBHOOK_API_KEY"),
        ilink_base_url=os.getenv("WEIXIN_PERSONAL_BASE_URL", DEFAULT_ILINK_BASE_URL),
        pairing_code_prefix=os.getenv("WECHAT_CONNECTOR_PAIRING_PREFIX", "pairing_"),
        poll_interval_seconds=float(os.getenv("WECHAT_CONNECTOR_POLL_SECONDS", "2.0")),
    )


def create_app(
    config: ConnectorConfig,
    *,
    state: ConnectorState | None = None,
    ilink_client: IlinkClient | None = None,
    webhook_client: httpx.Client | None = None,
) -> Flask:
    app = Flask(__name__)
    connector_state = state or ConnectorState(
        os.getenv("WECHAT_CONNECTOR_STATE_PATH", DEFAULT_STATE_PATH)
    )
    client = ilink_client or IlinkClient()
    webhook = webhook_client or httpx.Client()
    login_lock = threading.Lock()
    poll_lock = threading.Lock()
    login_thread: threading.Thread | None = None
    poll_thread: threading.Thread | None = None

    def start_poll_loop() -> bool:
        nonlocal poll_thread
        with poll_lock:
            if poll_thread and poll_thread.is_alive():
                return False
            poll_thread = threading.Thread(
                target=_run_poll_loop,
                args=(config, connector_state, client, webhook),
                daemon=True,
            )
            poll_thread.start()
            return True

    @app.get("/healthz")
    def healthz():
        snapshot = connector_state.snapshot()
        return jsonify(
            {
                "ok": True,
                "status": snapshot.get("status", "not_started"),
                "connected": bool(snapshot.get("base_url") and snapshot.get("token")),
            }
        )

    @app.post("/send")
    def send():
        if not _authorized(config):
            return jsonify({"error": "unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        to_user_id = str(body.get("to") or "").strip()
        text = str(body.get("text") or "").strip()
        if not to_user_id or not text:
            return jsonify({"error": "invalid_payload"}), 400
        snapshot = connector_state.snapshot()
        base_url = str(snapshot.get("base_url") or "").strip()
        token = str(snapshot.get("token") or "").strip()
        if not base_url or not token:
            return jsonify({"error": "wechat_not_connected"}), 409
        result = client.send_text(
            base_url=base_url,
            token=token,
            to_user_id=to_user_id,
            text=text,
        )
        return (
            jsonify(
                {
                    "message_id": result.get("message_id"),
                    "status": "sent",
                }
            ),
            202,
        )

    @app.get("/login/status")
    def login_status():
        if not _authorized(config):
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(connector_state.snapshot())

    @app.post("/login/start")
    def login_start():
        if not _authorized(config):
            return jsonify({"error": "unauthorized"}), 401
        nonlocal login_thread
        with login_lock:
            if login_thread and login_thread.is_alive():
                return jsonify(connector_state.snapshot()), 202
            connector_state.update({"status": "starting_login"})
            login_thread = threading.Thread(
                target=_run_login_flow,
                args=(config, connector_state, client, start_poll_loop),
                daemon=True,
            )
            login_thread.start()
        return jsonify(connector_state.snapshot()), 202

    @app.post("/poll/once")
    def poll_once_route():
        if not _authorized(config):
            return jsonify({"error": "unauthorized"}), 401
        delivered = poll_once(
            config,
            state=connector_state,
            ilink_client=client,
            webhook_client=webhook,
        )
        return jsonify({"delivered": delivered}), 202

    @app.post("/poll/start")
    def poll_start_route():
        if not _authorized(config):
            return jsonify({"error": "unauthorized"}), 401
        started = start_poll_loop()
        return jsonify({"started": started}), 202

    if os.getenv("WECHAT_CONNECTOR_AUTOSTART_POLL") == "1":
        snapshot = connector_state.snapshot()
        if snapshot.get("base_url") and snapshot.get("token"):
            start_poll_loop()

    return app


def poll_once(
    config: ConnectorConfig,
    *,
    state: ConnectorState,
    ilink_client: IlinkClient,
    webhook_client: httpx.Client,
) -> int:
    if not config.webhook_url:
        raise RuntimeError("WECHAT_CONNECTOR_WEBHOOK_URL is required for polling")
    snapshot = state.snapshot()
    base_url = str(snapshot.get("base_url") or "").strip()
    token = str(snapshot.get("token") or "").strip()
    if not base_url or not token:
        return 0

    updates = ilink_client.get_updates(
        base_url=base_url,
        token=token,
        cursor=str(snapshot.get("cursor") or ""),
    )
    next_cursor = updates.get("get_updates_buf")
    delivered = 0
    for message in updates.get("msgs") or []:
        payload = _clean_webhook_payload(message, config.pairing_code_prefix)
        if not payload:
            continue
        response = webhook_client.post(
            config.webhook_url,
            json=payload,
            headers=_webhook_headers(config),
            timeout=10.0,
        )
        response.raise_for_status()
        delivered += 1
    if next_cursor is not None:
        state.update({"cursor": next_cursor})
    return delivered


def _clean_webhook_payload(
    message: dict[str, Any], pairing_code_prefix: str
) -> dict[str, Any] | None:
    wxid = str(message.get("from_user_id") or "").strip()
    if not wxid:
        return None
    text = _extract_text(message)
    if text is None:
        return None
    message_id = str(message.get("context_token") or "").strip()
    if not message_id:
        message_id = f"{wxid}:{uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(message, sort_keys=True))}"
    payload: dict[str, Any] = {
        "message_id": message_id,
        "wxid": wxid,
        "text": text,
    }
    if text.startswith(pairing_code_prefix):
        payload["pairing_code"] = text
    return payload


def _extract_text(message: dict[str, Any]) -> str | None:
    for item in message.get("item_list") or []:
        item_type = item.get("type")
        if item_type == 1:
            text = str((item.get("text_item") or {}).get("text") or "").strip()
            if text:
                return text
        if item_type == 3:
            text = str((item.get("voice_item") or {}).get("text") or "").strip()
            if text:
                return text
    return ""


def _authorized(config: ConnectorConfig) -> bool:
    if not config.api_key:
        return True
    authorization = request.headers.get("Authorization", "")
    if authorization == f"Bearer {config.api_key}":
        return True
    return request.headers.get("X-API-Key") == config.api_key


def _webhook_headers(config: ConnectorConfig) -> dict[str, str]:
    if not config.webhook_api_key:
        return {}
    return {"X-API-Key": config.webhook_api_key}


def _run_login_flow(
    config: ConnectorConfig,
    state: ConnectorState,
    ilink_client: IlinkClient,
    start_poll_loop: Any,
) -> None:
    try:
        qr = ilink_client.get_qr(ilink_base_url=config.ilink_base_url)
        qrcode = str(qr.get("qrcode") or qr.get("qrcode_id") or "").strip()
        state.update(
            {
                "status": "waiting_for_scan",
                "error": None,
                "last_login_poll_error": None,
                "qrcode": qrcode,
                "qrcode_url": qr.get("qrcode_img_content") or qr.get("qrcode_img_url"),
                "qrcode_image_data_url": _qr_data_url(
                    str(qr.get("qrcode_img_content") or qr.get("qrcode_img_url") or "")
                ),
                "login_response": qr,
            }
        )
        if not qrcode:
            state.update({"status": "login_error", "error": "missing_qrcode"})
            return

        while True:
            try:
                status = ilink_client.get_qr_status(
                    ilink_base_url=config.ilink_base_url,
                    qrcode=qrcode,
                )
            except Exception as exc:
                state.update(
                    {
                        "status": "waiting_for_scan",
                        "last_login_poll_error": repr(exc),
                    }
                )
                time.sleep(config.poll_interval_seconds)
                continue
            status_name = str(status.get("status") or "").strip()
            state.update({"status": status_name or "waiting_for_scan", "login_status": status})
            if status_name == "confirmed":
                token = str(status.get("bot_token") or "").strip()
                base_url = str(status.get("baseurl") or status.get("base_url") or "").strip()
                if not base_url:
                    base_url = config.ilink_base_url
                ilink_bot_id = str(status.get("ilink_bot_id") or "").strip()
                if not token or not base_url:
                    state.update(
                        {
                            "status": "login_error",
                            "error": "confirmed_without_bot_token_or_base_url",
                        }
                    )
                    return
                state.update(
                    {
                        "status": "connected",
                        "token": token,
                        "base_url": base_url,
                        "ilink_bot_id": ilink_bot_id,
                        "cursor": "",
                    }
                )
                start_poll_loop()
                return
            if status_name == "expired":
                state.update({"status": "expired"})
                return
            time.sleep(config.poll_interval_seconds)
    except Exception as exc:  # pragma: no cover - operational state capture
        state.update({"status": "login_error", "error": repr(exc)})


def _run_poll_loop(
    config: ConnectorConfig,
    state: ConnectorState,
    ilink_client: IlinkClient,
    webhook_client: httpx.Client,
) -> None:
    while True:
        try:
            poll_once(
                config,
                state=state,
                ilink_client=ilink_client,
                webhook_client=webhook_client,
            )
        except Exception as exc:  # pragma: no cover - operational state capture
            state.update({"last_poll_error": repr(exc)})
        time.sleep(config.poll_interval_seconds)


def _qr_data_url(content: str) -> str | None:
    if not content:
        return None
    try:
        import qrcode

        image = qrcode.make(content)
        output = BytesIO()
        image.save(output, format="PNG")
        encoded = b64encode(output.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return None


app = create_app(config_from_env())
