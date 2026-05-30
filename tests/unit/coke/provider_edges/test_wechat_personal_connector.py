from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from provider_edges.wechat_personal_connector.app import (
    ConnectorConfig,
    ConnectorState,
    create_app,
    poll_once,
    _poll_login_status_once,
)


class FakeIlinkClient:
    def __init__(self, updates=None) -> None:
        self.sent = []
        self.qr_calls = []
        self.status_calls = []
        self.updates = updates or {"msgs": [], "get_updates_buf": ""}

    def get_qr(self, *, ilink_base_url: str):
        self.qr_calls.append({"ilink_base_url": ilink_base_url})
        return {
            "qrcode": f"qr-{len(self.qr_calls)}",
            "qrcode_img_content": f"https://weixin.qq.com/x/{len(self.qr_calls)}",
        }

    def get_qr_status(self, *, ilink_base_url: str, qrcode: str):
        self.status_calls.append({"ilink_base_url": ilink_base_url, "qrcode": qrcode})
        return {
            "status": "confirmed",
            "bot_token": f"bot-token-{qrcode}",
            "baseurl": "https://bot.example",
            "ilink_bot_id": f"bot-{qrcode}@im.bot",
            "ilink_user_id": f"user-{qrcode}@im.wechat",
        }

    def send_text(
        self,
        *,
        base_url: str,
        token: str,
        to_user_id: str,
        context_token: str,
        text: str,
    ):
        self.sent.append(
            {
                "base_url": base_url,
                "token": token,
                "to_user_id": to_user_id,
                "context_token": context_token,
                "text": text,
            }
        )
        return {"message_id": "client-id-1", "provider_response": "ok"}

    def get_updates(self, *, base_url: str, token: str, cursor: str):
        assert base_url == "https://bot.example"
        assert token == "bot-token"
        assert cursor == "cursor-0"
        return self.updates


class FakeWebhookClient:
    def __init__(self) -> None:
        self.posts = []

    def post(self, url, *, json, headers=None, timeout=None):
        self.posts.append(
            {
                "url": url,
                "json": json,
                "headers": headers or {},
                "timeout": timeout,
            }
        )
        return FakeResponse(202, {"accepted": True})


class FakeResponse:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self._body = body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP {self.status_code}")

    def json(self):
        return self._body


@pytest.fixture
def state(tmp_path: Path) -> ConnectorState:
    state = ConnectorState(tmp_path / "state.json")
    state.update(
        {
            "sessions": {
                "session-1": {
                    "account_id": "acct_1",
                    "status": "connected",
                    "base_url": "https://bot.example",
                    "token": "bot-token",
                    "cursor": "cursor-0",
                    "ilink_user_id": "wxid_alice",
                    "context_tokens": {"wxid_alice": "ctx-0"},
                }
            }
        }
    )
    return state


def test_start_login_creates_distinct_account_sessions_with_qr_payload(tmp_path):
    state = ConnectorState(tmp_path / "state.json")
    ilink = FakeIlinkClient()
    app = create_app(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=FakeWebhookClient(),
    )

    client = app.test_client()
    first = client.post(
        "/login/start",
        json={"account_id": "acct_1"},
        headers={"Authorization": "Bearer connector-key"},
    )
    second = client.post(
        "/login/start",
        json={"account_id": "acct_2"},
        headers={"Authorization": "Bearer connector-key"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    first_body = first.get_json()
    second_body = second.get_json()
    assert first_body["account_id"] == "acct_1"
    assert second_body["account_id"] == "acct_2"
    assert first_body["session_id"] != second_body["session_id"]
    assert first_body["qrcode_id"] == "qr-1"
    assert second_body["qrcode_id"] == "qr-2"
    assert first_body["qrcode_image"] == "https://weixin.qq.com/x/1"
    assert second_body["qrcode_image"] == "https://weixin.qq.com/x/2"


def test_login_status_confirmation_persists_account_bot_token_and_cursor(tmp_path):
    state = ConnectorState(tmp_path / "state.json")
    ilink = FakeIlinkClient()
    app = create_app(
        ConnectorConfig(api_key="connector-key"),
        state=state,
        ilink_client=ilink,
        webhook_client=FakeWebhookClient(),
    )
    client = app.test_client()
    started = client.post(
        "/login/start",
        json={"account_id": "acct_1"},
        headers={"Authorization": "Bearer connector-key"},
    ).get_json()

    session = _poll_login_status_once(
        config=ConnectorConfig(api_key="connector-key"),
        state=state,
        ilink_client=ilink,
        session_id=started["session_id"],
        session=state.snapshot()["sessions"][started["session_id"]],
    )

    assert session | {"login_status": session["login_status"]} == {
        **session,
        "status": "connected",
        "account_id": "acct_1",
        "ilink_user_id": "user-qr-1@im.wechat",
    }
    snapshot = state.snapshot()["sessions"][started["session_id"]]
    assert snapshot["token"] == "bot-token-qr-1"
    assert snapshot["cursor"] == ""


def test_login_status_returns_cached_waiting_state_without_inline_ilink_poll(tmp_path):
    state = ConnectorState(tmp_path / "state.json")
    state.update_session(
        "session-1",
        {
            "account_id": "acct_1",
            "status": "waiting_for_scan",
            "qrcode": "qr-1",
            "qrcode_image": "https://weixin.qq.com/x/1",
            "qrcode_image_data_url": "data:image/png;base64,qr",
        },
    )
    ilink = FakeIlinkClient()
    app = create_app(
        ConnectorConfig(api_key="connector-key"),
        state=state,
        ilink_client=ilink,
        webhook_client=FakeWebhookClient(),
    )

    response = app.test_client().get(
        "/login/status?account_id=acct_1&session_id=session-1",
        headers={"Authorization": "Bearer connector-key"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "waiting_for_scan"
    assert response.get_json()["qrcode_id"] == "qr-1"
    assert ilink.status_calls == []


def test_login_start_background_poll_confirms_session(tmp_path):
    state = ConnectorState(tmp_path / "state.json")
    ilink = FakeIlinkClient()
    app = create_app(
        ConnectorConfig(api_key="connector-key", poll_interval_seconds=0.01),
        state=state,
        ilink_client=ilink,
        webhook_client=FakeWebhookClient(),
    )

    started = app.test_client().post(
        "/login/start",
        json={"account_id": "acct_1"},
        headers={"Authorization": "Bearer connector-key"},
    )

    assert started.status_code == 202
    session_id = started.get_json()["session_id"]
    deadline = time.monotonic() + 1.0
    session = state.snapshot()["sessions"][session_id]
    while session.get("status") != "connected" and time.monotonic() < deadline:
        time.sleep(0.01)
        session = state.snapshot()["sessions"][session_id]

    assert session["status"] == "connected"
    assert session["ilink_user_id"] == "user-qr-1@im.wechat"
    assert ilink.status_calls == [
        {"ilink_base_url": "https://ilinkai.weixin.qq.com", "qrcode": "qr-1"}
    ]


def test_send_endpoint_maps_clean_contract_to_account_ilink_sendmessage(state):
    ilink = FakeIlinkClient()
    app = create_app(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=FakeWebhookClient(),
    )

    response = app.test_client().post(
        "/send",
        json={
            "account_id": "acct_1",
            "to": "wxid_alice",
            "context_token": "ctx-1",
            "text": "hello",
        },
        headers={
            "Authorization": "Bearer connector-key",
            "Idempotency-Key": "idem-1",
        },
    )

    assert response.status_code == 202
    assert response.get_json() == {"message_id": "client-id-1", "status": "sent"}
    assert ilink.sent == [
        {
                "base_url": "https://bot.example",
                "token": "bot-token",
                "to_user_id": "wxid_alice",
                "context_token": "ctx-1",
                "text": "hello",
            }
        ]


def test_send_endpoint_requires_configured_api_key(state):
    app = create_app(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
        ),
        state=state,
        ilink_client=FakeIlinkClient(),
        webhook_client=FakeWebhookClient(),
    )

    response = app.test_client().post(
        "/send",
        json={"account_id": "acct_1", "to": "wxid_alice", "context_token": "ctx-1", "text": "hello"},
    )

    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}


def test_poll_once_posts_account_bound_payload_and_context_token(state):
    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-1",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-1",
                    "item_list": [
                        {
                            "type": 1,
                            "text_item": {"text": "pairing_abc123"},
                        }
                    ],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    poll_once(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
            webhook_api_key="clean-webhook-key",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert webhook.posts == [
        {
            "url": "http://coke-api/webhooks/wechat/personal",
            "json": {
                "account_id": "acct_1",
                "session_id": "session-1",
                "message_id": "ctx-1",
                "wxid": "wxid_alice",
                "text": "pairing_abc123",
                "context_token": "ctx-1",
            },
            "headers": {"X-API-Key": "clean-webhook-key"},
            "timeout": 10.0,
        }
    ]
    session = json.loads(state.path.read_text())["sessions"]["session-1"]
    assert session["cursor"] == "cursor-1"
    assert session["context_tokens"] == {"wxid_alice": "ctx-1"}


def test_poll_once_does_not_mark_normal_text_as_pairing_code(state):
    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-2",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-2",
                    "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    poll_once(
        ConnectorConfig(webhook_url="http://coke-api/webhooks/wechat/personal"),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert webhook.posts[0]["json"] == {
        "account_id": "acct_1",
        "session_id": "session-1",
        "message_id": "ctx-2",
        "wxid": "wxid_alice",
        "text": "hello",
        "context_token": "ctx-2",
    }
