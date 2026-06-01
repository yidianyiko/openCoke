from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import yaml

from provider_edges.wechat_personal_connector.app import (
    ConnectorConfig,
    ConnectorState,
    _poll_login_status_once,
    config_from_env,
    create_app,
    poll_once,
)

ROOT = Path(__file__).resolve().parents[4]
CONNECTOR_COMPOSE = (
    ROOT / "provider_edges" / "wechat_personal_connector" / "docker-compose.yml"
)


class FakeIlinkClient:
    def __init__(self, updates=None) -> None:
        self.sent = []
        self.qr_calls = []
        self.status_calls = []
        self.update_calls = []
        self.updates = updates or {"msgs": [], "get_updates_buf": ""}
        self.updates_by_token = {}
        self.fail_tokens = {}
        self.send_response = None
        self.send_responses = []

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
        if self.send_responses:
            return self.send_responses.pop(0)
        if self.send_response is not None:
            return self.send_response
        return {"message_id": "client-id-1", "provider_response": "ok"}

    def get_updates(self, *, base_url: str, token: str, cursor: str):
        self.update_calls.append(
            {"base_url": base_url, "token": token, "cursor": cursor}
        )
        if token in self.fail_tokens:
            raise self.fail_tokens[token]
        if self.updates_by_token:
            return self.updates_by_token[token]
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


def test_healthz_reports_connected_status_from_persisted_sessions(state):
    state.update({"status": "expired"})
    app = create_app(
        ConnectorConfig(api_key="connector-key"),
        state=state,
        ilink_client=FakeIlinkClient(),
        webhook_client=FakeWebhookClient(),
    )

    response = app.test_client().get("/healthz")

    assert response.status_code == 200
    assert response.get_json()["connected"] is True
    assert response.get_json()["connected_session_count"] == 1
    assert response.get_json()["status"] == "connected"


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


def test_send_endpoint_maps_ilink_business_failure_to_clear_error(state):
    ilink = FakeIlinkClient()
    ilink.send_response = {
        "message_id": "client-id-1",
        "provider_response": {"ret": -2, "errmsg": "invalid context_token"},
    }
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
            "context_token": "ctx-bad",
            "text": "hello",
        },
        headers={"Authorization": "Bearer connector-key"},
    )

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "ilink_send_failed",
        "ilink": {"ret": -2, "errmsg": "invalid context_token"},
    }


def test_send_endpoint_retries_transient_ret_minus_two_and_logs_body(state, caplog):
    ilink = FakeIlinkClient()
    ilink.send_responses = [
        {
            "message_id": "client-id-1",
            "provider_response": {"ret": -2, "errmsg": "invalid context_token"},
        },
        {
            "message_id": "client-id-2",
            "provider_response": {"ret": 0},
        },
    ]
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
        headers={"Authorization": "Bearer connector-key"},
    )

    assert response.status_code == 202
    assert response.get_json() == {"message_id": "client-id-2", "status": "sent"}
    assert len(ilink.sent) == 2
    assert "ilink sendmessage failed" in caplog.text
    assert '"ret": -2' in caplog.text


def test_send_expires_session_on_session_timeout(state):
    ilink = FakeIlinkClient()
    ilink.send_response = {
        "message_id": "client-id-1",
        "provider_response": {"errcode": -14, "errmsg": "session timeout"},
    }
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
        headers={"Authorization": "Bearer connector-key"},
    )

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "ilink_send_failed",
        "ilink": {"errcode": -14, "errmsg": "session timeout"},
    }
    session = state.snapshot()["sessions"]["session-1"]
    assert session["status"] == "expired"
    assert session["token"] == ""
    assert session["cursor"] == ""
    assert session["context_tokens"] == {}
    health = app.test_client().get("/healthz")
    assert health.status_code == 200
    assert health.get_json()["connected"] is False
    assert health.get_json()["connected_session_count"] == 0


def test_send_does_not_expire_session_on_ret_minus_two(state):
    ilink = FakeIlinkClient()
    ilink.send_response = {
        "message_id": "client-id-1",
        "provider_response": {"ret": -2, "errmsg": "invalid context_token"},
    }
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
            "context_token": "ctx-bad",
            "text": "hello",
        },
        headers={"Authorization": "Bearer connector-key"},
    )

    assert response.status_code == 502
    session = state.snapshot()["sessions"]["session-1"]
    assert session["status"] == "connected"
    assert session["token"] == "bot-token"
    assert session["cursor"] == "cursor-0"
    assert session["context_tokens"] == {"wxid_alice": "ctx-0"}


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
        json={
            "account_id": "acct_1",
            "to": "wxid_alice",
            "context_token": "ctx-1",
            "text": "hello",
        },
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
            webhook_inbound_secret="clean-webhook-secret",
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
            "headers": {
                "X-API-Key": "clean-webhook-key",
                "X-Coke-Webhook-Secret": "clean-webhook-secret",
            },
            "timeout": 10.0,
        }
    ]
    session = json.loads(state.path.read_text())["sessions"]["session-1"]
    assert session["cursor"] == "cursor-1"
    assert session["context_tokens"] == {"wxid_alice": "ctx-1"}


def test_poll_once_posts_image_media_payload_with_blank_text(state):
    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-1",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-image-1",
                    "item_list": [
                        {
                            "type": 2,
                            "image_item": {
                                "data_uri": "data:image/jpeg;base64,/9j/2w==",
                                "mime": "image/jpeg",
                            },
                        }
                    ],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    delivered = poll_once(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
            webhook_api_key="clean-webhook-key",
            webhook_inbound_secret="clean-webhook-secret",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert delivered == 1
    assert webhook.posts[0]["json"] == {
        "account_id": "acct_1",
        "session_id": "session-1",
        "message_id": "ctx-image-1",
        "wxid": "wxid_alice",
        "text": "",
        "context_token": "ctx-image-1",
        "media": [
            {
                "media_type": "image",
                "storage_uri": "data:image/jpeg;base64,/9j/2w==",
                "mime": "image/jpeg",
                "agent_label": "image",
            }
        ],
    }


def test_poll_once_posts_voice_native_transcript_as_text_without_media(state):
    # Voice primary path: WeChat's native transcript becomes the message text;
    # the SILK audio is not forwarded this iteration, so no media is attached.
    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-1",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-voice-1",
                    "item_list": [
                        {
                            "type": 3,
                            "voice_item": {
                                "text": "remind me at nine",
                                "media": {
                                    "full_url": "https://cdn.example/voice",
                                    "aes_key": "MDEyMzQ1Njc4OWFiY2RlZg==",
                                },
                            },
                        }
                    ],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    delivered = poll_once(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
            webhook_api_key="clean-webhook-key",
            webhook_inbound_secret="clean-webhook-secret",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert delivered == 1
    assert webhook.posts[0]["json"] == {
        "account_id": "acct_1",
        "session_id": "session-1",
        "message_id": "ctx-voice-1",
        "wxid": "wxid_alice",
        "text": "remind me at nine",
        "context_token": "ctx-voice-1",
    }


def test_poll_once_downloads_and_decrypts_cdn_image_into_data_uri(state, monkeypatch):
    from base64 import b64encode

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7

    from provider_edges.wechat_personal_connector import app as connector_app

    plaintext = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    key = b"0123456789abcdef"  # 16 raw bytes
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    class FakeCdnResponse:
        content = ciphertext

        def raise_for_status(self):
            return None

    captured = {}

    def fake_get(url, timeout=60.0):
        captured["url"] = url
        return FakeCdnResponse()

    monkeypatch.setattr(connector_app._CDN_HTTP, "get", fake_get)

    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-1",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-image-cdn",
                    "item_list": [
                        {
                            "type": 2,
                            "image_item": {
                                "mime": "image/jpeg",
                                "media": {
                                    "full_url": "https://cdn.example/img?q=1",
                                    "aes_key": b64encode(key).decode("ascii"),
                                },
                            },
                        }
                    ],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    delivered = poll_once(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert delivered == 1
    assert captured["url"] == "https://cdn.example/img?q=1"
    expected_uri = f"data:image/jpeg;base64,{b64encode(plaintext).decode('ascii')}"
    assert webhook.posts[0]["json"]["text"] == ""
    assert webhook.posts[0]["json"]["media"] == [
        {
            "media_type": "image",
            "storage_uri": expected_uri,
            "mime": "image/jpeg",
            "agent_label": "image",
        }
    ]


def test_poll_once_skips_malformed_image_without_readable_media(state):
    ilink = FakeIlinkClient(
        updates={
            "get_updates_buf": "cursor-1",
            "msgs": [
                {
                    "from_user_id": "wxid_alice",
                    "context_token": "ctx-image-bad",
                    "item_list": [
                        {
                            "type": 2,
                            "image_item": {"cdn_url": "https://cdn.invalid/image"},
                        }
                    ],
                }
            ],
        }
    )
    webhook = FakeWebhookClient()

    delivered = poll_once(
        ConnectorConfig(
            api_key="connector-key",
            webhook_url="http://coke-api/webhooks/wechat/personal",
        ),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    assert delivered == 0
    assert webhook.posts == []


def test_config_from_env_reads_webhook_inbound_secret(monkeypatch):
    monkeypatch.setenv("WECHAT_CONNECTOR_API_KEY", "connector-key")
    monkeypatch.setenv(
        "WECHAT_CONNECTOR_WEBHOOK_URL", "http://coke-api/webhooks/wechat/personal"
    )
    monkeypatch.setenv("WECHAT_CONNECTOR_WEBHOOK_API_KEY", "legacy-webhook-key")
    monkeypatch.setenv("COKE_WEBHOOK_INBOUND_SECRET", "clean-webhook-secret")

    config = config_from_env()

    assert config.api_key == "connector-key"
    assert config.webhook_url == "http://coke-api/webhooks/wechat/personal"
    assert config.webhook_api_key == "legacy-webhook-key"
    assert config.webhook_inbound_secret == "clean-webhook-secret"


def test_poll_once_records_session_error_and_continues_other_sessions(tmp_path):
    state = ConnectorState(tmp_path / "state.json")
    state.update(
        {
            "sessions": {
                "session-bad": {
                    "account_id": "acct_bad",
                    "status": "connected",
                    "base_url": "https://bot.example",
                    "token": "bad-token",
                    "cursor": "cursor-bad",
                    "ilink_user_id": "wxid_bad",
                    "context_tokens": {},
                },
                "session-good": {
                    "account_id": "acct_good",
                    "status": "connected",
                    "base_url": "https://bot.example",
                    "token": "good-token",
                    "cursor": "cursor-good",
                    "ilink_user_id": "wxid_good",
                    "context_tokens": {},
                },
            }
        }
    )
    ilink = FakeIlinkClient()
    ilink.fail_tokens = {"bad-token": RuntimeError("temporary network")}
    ilink.updates_by_token = {
        "good-token": {
            "get_updates_buf": "cursor-good-next",
            "msgs": [
                {
                    "from_user_id": "wxid_good",
                    "context_token": "ctx-good",
                    "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
                }
            ],
        }
    }
    webhook = FakeWebhookClient()

    delivered = poll_once(
        ConnectorConfig(webhook_url="http://coke-api/webhooks/wechat/personal"),
        state=state,
        ilink_client=ilink,
        webhook_client=webhook,
    )

    snapshot = state.snapshot()["sessions"]
    assert delivered == 1
    assert "temporary network" in snapshot["session-bad"]["last_poll_error"]
    assert "last_poll_error" not in snapshot["session-good"]
    assert snapshot["session-good"]["cursor"] == "cursor-good-next"
    assert snapshot["session-good"]["context_tokens"] == {"wxid_good": "ctx-good"}
    assert webhook.posts[0]["json"]["account_id"] == "acct_good"


def test_poll_once_sets_retry_backoff_for_retryable_session_error(state):
    ilink = FakeIlinkClient()
    ilink.fail_tokens = {"bot-token": RuntimeError("temporary network")}
    before = time.time()

    delivered = poll_once(
        ConnectorConfig(webhook_url="http://coke-api/webhooks/wechat/personal"),
        state=state,
        ilink_client=ilink,
        webhook_client=FakeWebhookClient(),
    )

    session = state.snapshot()["sessions"]["session-1"]
    assert delivered == 0
    assert session["poll_error_count"] == 1
    assert session["next_poll_after"] > before
    assert "temporary network" in session["last_poll_error"]


def test_poll_once_skips_session_until_retry_backoff_elapses(state):
    state.update_session(
        "session-1",
        {"poll_error_count": 1, "next_poll_after": time.time() + 60},
    )
    ilink = FakeIlinkClient()

    delivered = poll_once(
        ConnectorConfig(webhook_url="http://coke-api/webhooks/wechat/personal"),
        state=state,
        ilink_client=ilink,
        webhook_client=FakeWebhookClient(),
    )

    assert delivered == 0
    assert ilink.update_calls == []


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


def test_connector_compose_joins_clean_runtime_network_for_webhooks():
    compose = yaml.safe_load(CONNECTOR_COMPOSE.read_text())
    service = compose["services"]["wechat-personal-connector"]

    assert service["networks"] == ["default", "coke_clean"]
    assert compose["networks"]["coke_clean"] == {
        "external": True,
        "name": "${WECHAT_CONNECTOR_COKE_NETWORK:-coke-clean_default}",
    }


def test_compose_provides_inbound_defaults():
    compose = yaml.safe_load(CONNECTOR_COMPOSE.read_text())
    service = compose["services"]["wechat-personal-connector"]

    assert service["environment"] == {
        "WECHAT_CONNECTOR_WEBHOOK_URL": "${WECHAT_CONNECTOR_WEBHOOK_URL:-http://coke-api:8000/webhooks/wechat/personal}",
        "WECHAT_CONNECTOR_AUTOSTART_POLL": "${WECHAT_CONNECTOR_AUTOSTART_POLL:-1}",
    }
