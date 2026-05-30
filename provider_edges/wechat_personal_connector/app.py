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

    def update_session(self, session_id: str, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self.path.exists():
                current = json.loads(self.path.read_text())
            else:
                current = {}
            sessions = current.setdefault("sessions", {})
            session = sessions.setdefault(session_id, {})
            session.update(values)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            temp_path.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")
            temp_path.replace(self.path)
            return session


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
        self,
        *,
        base_url: str,
        token: str,
        to_user_id: str,
        context_token: str,
        text: str,
    ) -> dict[str, Any]:
        client_id = f"coke-{int(time.time() * 1000)}-{uuid.uuid4().hex[:12]}"
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": 2,
                "message_state": 2,
                "context_token": context_token,
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
        provider_response = _validated_ilink_response(response)
        return {"message_id": client_id, "provider_response": provider_response}

    def get_updates(self, *, base_url: str, token: str, cursor: str) -> dict[str, Any]:
        response = self._client.post(
            f"{base_url.rstrip('/')}/ilink/bot/getupdates",
            headers=_ilink_bot_headers(token),
            json={
                "get_updates_buf": cursor or "",
                "base_info": {"channel_version": "1.0.2"},
            },
            timeout=40.0,
        )
        body = _validated_ilink_response(response)
        return body if isinstance(body, dict) else {}


class IlinkAPIError(RuntimeError):
    def __init__(self, *, operation: str, response: dict[str, Any]) -> None:
        self.operation = operation
        self.response = response
        super().__init__(f"{operation}:{response}")


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
    poll_lock = threading.Lock()
    poll_thread: threading.Thread | None = None
    login_poll_lock = threading.Lock()
    login_poll_threads: dict[str, threading.Thread] = {}

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

    def start_login_poll_loop(session_id: str) -> bool:
        with login_poll_lock:
            existing = login_poll_threads.get(session_id)
            if existing and existing.is_alive():
                return False
            session = _session_by_id(connector_state.snapshot(), session_id)
            if not session or session.get("status") in {
                "connected",
                "expired",
                "login_error",
            }:
                return False
            thread = threading.Thread(
                target=_run_login_status_loop,
                args=(config, connector_state, client, session_id, start_poll_loop),
                daemon=True,
            )
            login_poll_threads[session_id] = thread
            thread.start()
            return True

    @app.get("/healthz")
    def healthz():
        snapshot = connector_state.snapshot()
        connected_sessions = _connected_sessions(snapshot)
        status = (
            "connected" if connected_sessions else snapshot.get("status", "not_started")
        )
        return jsonify(
            {
                "ok": True,
                "status": status,
                "connected": bool(connected_sessions),
                "connected_session_count": len(connected_sessions),
            }
        )

    @app.post("/send")
    def send():
        if not _authorized(config):
            return jsonify({"error": "unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        account_id = str(body.get("account_id") or "").strip()
        to_user_id = str(body.get("to") or "").strip()
        context_token = str(body.get("context_token") or "").strip()
        text = str(body.get("text") or "").strip()
        if not account_id or not to_user_id or not context_token or not text:
            return jsonify({"error": "invalid_payload"}), 400
        session = _connected_session_for_account(connector_state.snapshot(), account_id)
        base_url = str(session.get("base_url") or "").strip()
        token = str(session.get("token") or "").strip()
        if not base_url or not token:
            return jsonify({"error": "wechat_not_connected"}), 409
        try:
            result = client.send_text(
                base_url=base_url,
                token=token,
                to_user_id=to_user_id,
                context_token=context_token,
                text=text,
            )
        except IlinkAPIError as error:
            return (
                jsonify(
                    {
                        "error": "ilink_send_failed",
                        "ilink": error.response,
                    }
                ),
                502,
            )
        provider_failure = _ilink_failure_from_body(result.get("provider_response"))
        if provider_failure is not None:
            return (
                jsonify(
                    {
                        "error": "ilink_send_failed",
                        "ilink": provider_failure,
                    }
                ),
                502,
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
        session_id = str(request.args.get("session_id") or "").strip()
        account_id = str(request.args.get("account_id") or "").strip()
        if not session_id or not account_id:
            return jsonify({"error": "invalid_payload"}), 400
        session = _session_by_id(connector_state.snapshot(), session_id)
        if not session or session.get("account_id") != account_id:
            return jsonify({"error": "session_not_found"}), 404
        if session.get("status") == "connected":
            start_poll_loop()
        elif session.get("status") not in {"expired", "login_error"}:
            start_login_poll_loop(session_id)
        return jsonify(_session_public_view(session_id, session))

    @app.post("/login/start")
    def login_start():
        if not _authorized(config):
            return jsonify({"error": "unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        account_id = str(body.get("account_id") or "").strip()
        if not account_id:
            return jsonify({"error": "invalid_payload"}), 400
        qr = client.get_qr(ilink_base_url=config.ilink_base_url)
        qrcode = str(qr.get("qrcode") or qr.get("qrcode_id") or "").strip()
        qrcode_image = str(
            qr.get("qrcode_img_content") or qr.get("qrcode_img_url") or ""
        ).strip()
        if not qrcode:
            return jsonify({"error": "missing_qrcode"}), 502
        session_id = uuid.uuid4().hex
        session = connector_state.update_session(
            session_id,
            {
                "account_id": account_id,
                "status": "waiting_for_scan",
                "error": None,
                "qrcode": qrcode,
                "qrcode_image": qrcode_image,
                "qrcode_image_data_url": _qr_data_url(qrcode_image),
                "login_response": qr,
                "cursor": "",
                "context_tokens": {},
            },
        )
        start_login_poll_loop(session_id)
        return jsonify(_session_public_view(session_id, session)), 202

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
        if _connected_sessions(snapshot):
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
    delivered = 0
    for session_id, session in _connected_sessions(snapshot).items():
        if _retry_backoff_active(session):
            continue
        try:
            delivered += _poll_session_once(
                config,
                state=state,
                ilink_client=ilink_client,
                webhook_client=webhook_client,
                session_id=session_id,
                session=session,
            )
        except Exception as exc:
            updates: dict[str, Any] = _poll_error_updates(session, exc)
            if _is_session_expired_error(exc):
                updates.update(
                    {
                        "status": "expired",
                        "token": "",
                        "cursor": "",
                        "context_tokens": {},
                    }
                )
            state.update_session(session_id, updates)
    return delivered


def _poll_session_once(
    config: ConnectorConfig,
    *,
    state: ConnectorState,
    ilink_client: IlinkClient,
    webhook_client: httpx.Client,
    session_id: str,
    session: dict[str, Any],
) -> int:
    base_url = str(session.get("base_url") or "").strip()
    token = str(session.get("token") or "").strip()
    if not base_url or not token:
        return 0
    updates = ilink_client.get_updates(
        base_url=base_url,
        token=token,
        cursor=str(session.get("cursor") or ""),
    )
    next_cursor = updates.get("get_updates_buf")
    context_tokens = dict(session.get("context_tokens") or {})
    delivered = 0
    for message in updates.get("msgs") or []:
        payload = _clean_webhook_payload(message, session_id, session)
        if not payload:
            continue
        context_tokens[payload["wxid"]] = payload["context_token"]
        response = webhook_client.post(
            config.webhook_url,
            json=payload,
            headers=_webhook_headers(config),
            timeout=10.0,
        )
        response.raise_for_status()
        delivered += 1
    updates_to_save: dict[str, Any] = {"context_tokens": context_tokens}
    if next_cursor is not None:
        updates_to_save["cursor"] = next_cursor
    if session.get("last_poll_error"):
        updates_to_save["last_poll_error"] = ""
    if session.get("poll_error_count"):
        updates_to_save["poll_error_count"] = 0
        updates_to_save["next_poll_after"] = 0
    state.update_session(session_id, updates_to_save)
    return delivered


def _clean_webhook_payload(
    message: dict[str, Any], session_id: str, session: dict[str, Any]
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
    context_token = str(message.get("context_token") or "").strip()
    if not context_token:
        return None
    return {
        "account_id": str(session.get("account_id") or ""),
        "session_id": session_id,
        "message_id": message_id,
        "wxid": wxid,
        "text": text,
        "context_token": context_token,
    }


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


def _validated_ilink_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        body = {"raw_body": response.text}
    if not response.is_success:
        failure = body if isinstance(body, dict) else {"raw_body": str(body)}
        failure.setdefault("http_status", response.status_code)
        raise IlinkAPIError(operation="http", response=failure)
    failure = _ilink_failure_from_body(body)
    if failure is not None:
        raise IlinkAPIError(operation="business", response=failure)
    return body if isinstance(body, dict) else {}


def _ilink_failure_from_body(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    ret = body.get("ret")
    errcode = body.get("errcode")
    if _nonzero_number(ret) or _nonzero_number(errcode):
        return dict(body)
    return None


def _nonzero_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value != 0


def _is_session_expired_error(error: BaseException) -> bool:
    if not isinstance(error, IlinkAPIError):
        return False
    response = error.response
    return response.get("ret") == -14 or response.get("errcode") == -14


def _retry_backoff_active(session: dict[str, Any]) -> bool:
    try:
        next_poll_after = float(session.get("next_poll_after") or 0)
    except (TypeError, ValueError):
        return False
    return next_poll_after > time.time()


def _poll_error_updates(
    session: dict[str, Any], error: BaseException
) -> dict[str, Any]:
    count = _poll_error_count(session) + 1
    return {
        "last_poll_error": repr(error),
        "poll_error_count": count,
        "next_poll_after": time.time() + _poll_retry_delay_seconds(count),
    }


def _poll_error_count(session: dict[str, Any]) -> int:
    try:
        value = int(session.get("poll_error_count") or 0)
    except (TypeError, ValueError):
        return 0
    return max(value, 0)


def _poll_retry_delay_seconds(error_count: int) -> float:
    exponent = min(max(error_count - 1, 0), 5)
    return min(60.0, 2.0**exponent)


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


def _sessions(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sessions = snapshot.get("sessions")
    if isinstance(sessions, dict):
        return {
            str(session_id): dict(session)
            for session_id, session in sessions.items()
            if isinstance(session, dict)
        }
    return {}


def _connected_sessions(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        session_id: session
        for session_id, session in _sessions(snapshot).items()
        if session.get("status") == "connected"
    }


def _session_by_id(snapshot: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    return _sessions(snapshot).get(session_id)


def _connected_session_for_account(
    snapshot: dict[str, Any], account_id: str
) -> dict[str, Any]:
    for session in _connected_sessions(snapshot).values():
        if session.get("account_id") == account_id:
            return session
    return {}


def _session_public_view(session_id: str, session: dict[str, Any]) -> dict[str, Any]:
    qrcode = str(session.get("qrcode") or "")
    body = {
        "session_id": session_id,
        "account_id": session.get("account_id"),
        "status": session.get("status", "not_started"),
        "qrcode_id": qrcode,
        "qrcode_image": session.get("qrcode_image"),
        "qrcode_image_data_url": session.get("qrcode_image_data_url"),
        "ilink_user_id": session.get("ilink_user_id"),
        "login_status": session.get("login_status"),
        "error": session.get("error"),
    }
    return {key: value for key, value in body.items() if value is not None}


def _poll_login_status_once(
    *,
    config: ConnectorConfig,
    state: ConnectorState,
    ilink_client: IlinkClient,
    session_id: str,
    session: dict[str, Any],
) -> dict[str, Any]:
    qrcode = str(session.get("qrcode") or "").strip()
    if not qrcode:
        return state.update_session(
            session_id, {"status": "login_error", "error": "missing_qrcode"}
        )
    status = ilink_client.get_qr_status(
        ilink_base_url=config.ilink_base_url,
        qrcode=qrcode,
    )
    status_name = str(status.get("status") or "").strip()
    updates: dict[str, Any] = {
        "status": status_name or "waiting_for_scan",
        "login_status": status,
    }
    if status_name == "confirmed":
        token = str(status.get("bot_token") or "").strip()
        base_url = str(status.get("baseurl") or status.get("base_url") or "").strip()
        ilink_user_id = str(status.get("ilink_user_id") or "").strip()
        if not token or not ilink_user_id:
            updates.update(
                {
                    "status": "login_error",
                    "error": "confirmed_without_bot_token_or_user_id",
                }
            )
        else:
            updates.update(
                {
                    "status": "connected",
                    "token": token,
                    "base_url": base_url or config.ilink_base_url,
                    "ilink_bot_id": str(status.get("ilink_bot_id") or "").strip(),
                    "ilink_user_id": ilink_user_id,
                    "cursor": "",
                }
            )
    if status_name == "expired":
        updates["status"] = "expired"
    return state.update_session(session_id, updates)


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


def _run_login_status_loop(
    config: ConnectorConfig,
    state: ConnectorState,
    ilink_client: IlinkClient,
    session_id: str,
    on_connected,
) -> None:
    while True:
        session = _session_by_id(state.snapshot(), session_id)
        if not session:
            return
        if session.get("status") == "connected":
            on_connected()
            return
        if session.get("status") in {"expired", "login_error"}:
            return
        try:
            session = _poll_login_status_once(
                config=config,
                state=state,
                ilink_client=ilink_client,
                session_id=session_id,
                session=session,
            )
        except Exception as exc:  # pragma: no cover - operational state capture
            state.update_session(session_id, {"last_login_poll_error": repr(exc)})
            session = _session_by_id(state.snapshot(), session_id) or {}
        if session.get("status") == "connected":
            on_connected()
            return
        if session.get("status") in {"expired", "login_error"}:
            return
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
