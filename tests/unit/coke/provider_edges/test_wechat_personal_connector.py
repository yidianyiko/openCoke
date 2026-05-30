from __future__ import annotations

import json
from pathlib import Path

import pytest

from provider_edges.wechat_personal_connector.app import (
    ConnectorConfig,
    ConnectorState,
    create_app,
    poll_once,
)


class FakeIlinkClient:
    def __init__(self, updates=None) -> None:
        self.sent = []
        self.updates = updates or {"msgs": [], "get_updates_buf": ""}

    def send_text(self, *, base_url: str, token: str, to_user_id: str, text: str):
        self.sent.append(
            {
                "base_url": base_url,
                "token": token,
                "to_user_id": to_user_id,
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
            "status": "connected",
            "base_url": "https://bot.example",
            "token": "bot-token",
            "cursor": "cursor-0",
        }
    )
    return state


def test_send_endpoint_maps_clean_contract_to_ilink_sendmessage(state):
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
        json={"to": "wxid_alice", "text": "hello"},
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
        json={"to": "wxid_alice", "text": "hello"},
    )

    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}


def test_poll_once_posts_clean_wechat_webhook_payload_and_pairing_token(state):
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
                "message_id": "ctx-1",
                "wxid": "wxid_alice",
                "text": "pairing_abc123",
                "pairing_code": "pairing_abc123",
            },
            "headers": {"X-API-Key": "clean-webhook-key"},
            "timeout": 10.0,
        }
    ]
    assert json.loads(state.path.read_text())["cursor"] == "cursor-1"


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
        "message_id": "ctx-2",
        "wxid": "wxid_alice",
        "text": "hello",
    }
