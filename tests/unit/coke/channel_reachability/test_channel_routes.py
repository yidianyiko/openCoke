from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from coke.api.channel_routes import create_channel_blueprint
from coke.app import create_app
from coke.config import Settings
from coke.domains.channel_reachability.models import ChannelReachabilityError

DATABASE_URL = "postgresql+psycopg://coke:coke@localhost:5432/coke_test"
REDIS_URL = "redis://localhost:6379/15"


class FakeReachabilityService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_status(self, account_id):
        self.calls.append(("get_status", {"account_id": account_id}))
        return SimpleNamespace(
            account_id=account_id,
            channel_id="channel_1",
            provider_type="whatsapp_evolution",
            connection_state="connected",
            reachable=True,
        )

    def start_wechat_personal_connection(self, account_id):
        self.calls.append(
            ("start_wechat_personal_connection", {"account_id": account_id})
        )
        return SimpleNamespace(
            account_id=account_id,
            channel_id=None,
            provider_type="wechat_personal",
            connection_state="connecting",
            reachable=False,
            session_id="ilink_session_1",
            qrcode_id="qr_1",
            qrcode_image="data:image/png;base64,QR1",
            connector_status="waiting_for_scan",
            instructions="scan this QR code with this user's own WeChat account",
        )

    def poll_wechat_personal_login(self, account_id, session_id):
        self.calls.append(
            (
                "poll_wechat_personal_login",
                {"account_id": account_id, "session_id": session_id},
            )
        )
        return SimpleNamespace(
            account_id=account_id,
            channel_id="channel_1",
            provider_type="wechat_personal",
            connection_state="connected",
            reachable=True,
            session_id=session_id,
            connector_status="connected",
            masked_identity="wxid...lice",
        )

    def create_channel(self, account_id, provider_type, channel_identity_id, removable):
        self.calls.append(
            (
                "create_channel",
                {
                    "account_id": account_id,
                    "provider_type": provider_type,
                    "channel_identity_id": channel_identity_id,
                    "removable": removable,
                },
            )
        )
        return self._channel("not_connected")

    def connect_channel(self, account_id, channel_id):
        self.calls.append(
            ("connect_channel", {"account_id": account_id, "channel_id": channel_id})
        )
        return self._channel("connecting")

    def poll_channel(self, account_id, channel_id):
        self.calls.append(
            ("poll_channel", {"account_id": account_id, "channel_id": channel_id})
        )
        return self._channel("connected")

    def remove_channel(self, account_id, channel_id):
        self.calls.append(
            ("remove_channel", {"account_id": account_id, "channel_id": channel_id})
        )
        return self._channel("removed")

    def retry_connection(self, account_id, channel_id):
        self.calls.append(
            ("retry_connection", {"account_id": account_id, "channel_id": channel_id})
        )
        return self._channel("connecting")

    def resolve_route(self, account_id):
        self.calls.append(("resolve_route", {"account_id": account_id}))
        return SimpleNamespace(
            id="route_1",
            account_id=account_id,
            channel_id="channel_1",
            provider_type="whatsapp_evolution",
            provider_address="whatsapp:+15555550123",
            route_key="whatsapp_evolution:whatsapp:+15555550123",
            lifecycle="active",
        )

    def _channel(self, state):
        return SimpleNamespace(
            id="channel_1",
            account_id="acct_1",
            provider_type="whatsapp_evolution",
            channel_identity_id="ci_1",
            lifecycle="removed" if state == "removed" else "active",
            connection_state=state,
            removable=True,
        )


class ErrorService(FakeReachabilityService):
    def remove_channel(self, account_id, channel_id):
        raise ChannelReachabilityError(
            "channel_identity_not_removable",
            fact={"type": "channel_identity_anchor", "account_id": account_id},
        )


class FakeIdentityService:
    def __init__(self, account_id="acct_1") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.account_id = account_id

    def current_user(self, session_token):
        self.calls.append(("current_user", {"session_token": session_token}))
        if session_token != "session_token":
            raise AssertionError(f"unexpected session token: {session_token}")
        return SimpleNamespace(id=self.account_id, origin="web_first")


class AuthenticatedClient:
    def __init__(self, raw_client) -> None:
        self.raw = raw_client

    def get(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs.setdefault("headers", {"Authorization": "Bearer session_token"})
        return self.raw.post(*args, **kwargs)


def make_client(service=None, identity_service=None):
    service = service or FakeReachabilityService()
    identity_service = identity_service or FakeIdentityService()
    app = Flask(__name__)
    app.register_blueprint(create_channel_blueprint(service, identity_service))
    return AuthenticatedClient(app.test_client()), service, identity_service


def test_status_route_is_thin_service_adapter():
    client, service, identity = make_client()

    response = client.get("/api/channels/status?account_id=spoofed_account")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "channel_id": "channel_1",
        "provider_type": "whatsapp_evolution",
        "connection_state": "connected",
        "reachable": True,
    }
    assert identity.calls == [("current_user", {"session_token": "session_token"})]
    assert service.calls == [("get_status", {"account_id": "acct_1"})]


def test_status_route_rejects_missing_session_before_service_call():
    client, service, identity = make_client()

    response = client.get("/api/channels/status?account_id=acct_1", headers={})

    assert response.status_code == 401
    assert response.get_json() == {
        "error": {
            "code": "unauthorized",
            "fact": {
                "type": "unauthorized",
                "reason": "missing_bearer_token",
            },
        }
    }
    assert identity.calls == []
    assert service.calls == []


def test_status_route_surfaces_pending_wechat_qr_fields():
    class PendingStatusService(FakeReachabilityService):
        def get_status(self, account_id):
            self.calls.append(("get_status", {"account_id": account_id}))
            return SimpleNamespace(
                account_id=account_id,
                channel_id=None,
                provider_type="wechat_personal",
                connection_state="connecting",
                reachable=False,
                session_id="ilink_session_1",
                qrcode_id="qr_1",
                qrcode_image="data:image/png;base64,QR1",
                connector_status="waiting_for_scan",
                instructions="scan this QR code with this user's own WeChat account",
            )

    client, service, _identity = make_client(PendingStatusService())

    response = client.get("/api/channels/status?account_id=acct_1")

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "channel_id": None,
        "provider_type": "wechat_personal",
        "connection_state": "connecting",
        "reachable": False,
        "session_id": "ilink_session_1",
        "qrcode_id": "qr_1",
        "qrcode_image": "data:image/png;base64,QR1",
        "connector_status": "waiting_for_scan",
        "instructions": "scan this QR code with this user's own WeChat account",
    }
    assert service.calls == [("get_status", {"account_id": "acct_1"})]


def test_wechat_personal_connect_route_starts_ilink_qr_login():
    client, service, _identity = make_client()

    response = client.post(
        "/api/channels/wechat-personal/connect",
        json={"account_id": "acct_1"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "channel_id": None,
        "provider_type": "wechat_personal",
        "connection_state": "connecting",
        "reachable": False,
        "session_id": "ilink_session_1",
        "qrcode_id": "qr_1",
        "qrcode_image": "data:image/png;base64,QR1",
        "connector_status": "waiting_for_scan",
        "instructions": "scan this QR code with this user's own WeChat account",
    }
    assert service.calls == [
        ("start_wechat_personal_connection", {"account_id": "acct_1"})
    ]


def test_wechat_personal_login_status_route_polls_connector_session():
    client, service, _identity = make_client()

    response = client.get(
        "/api/channels/wechat-personal/login-status"
        "?account_id=acct_1&session_id=ilink_session_1"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "account_id": "acct_1",
        "channel_id": "channel_1",
        "provider_type": "wechat_personal",
        "connection_state": "connected",
        "reachable": True,
        "session_id": "ilink_session_1",
        "connector_status": "connected",
        "masked_identity": "wxid...lice",
    }
    assert service.calls == [
        (
            "poll_wechat_personal_login",
            {"account_id": "acct_1", "session_id": "ilink_session_1"},
        )
    ]


def test_channel_action_routes_delegate_to_service_methods():
    client, service, _identity = make_client()

    assert (
        client.post(
            "/api/channels",
            json={
                "account_id": "spoofed_account",
                "provider_type": "whatsapp_evolution",
                "channel_identity_id": "ci_1",
                "removable": True,
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/channels/channel_1/connect", json={"account_id": "spoofed_account"}
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/channels/channel_1/poll?account_id=spoofed_account"
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/channels/channel_1/retry", json={"account_id": "spoofed_account"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/channels/channel_1/remove", json={"account_id": "spoofed_account"}
        ).status_code
        == 200
    )
    assert (
        client.get("/api/channels/resolve-route?account_id=spoofed_account").status_code
        == 200
    )

    assert [call[0] for call in service.calls] == [
        "create_channel",
        "connect_channel",
        "poll_channel",
        "retry_connection",
        "remove_channel",
        "resolve_route",
    ]


@pytest.mark.parametrize("provider_type", ["wechat_ecloud", "linq"])
def test_create_route_rejects_retained_non_product_provider_before_service_call(
    provider_type,
):
    client, service, _identity = make_client()

    response = client.post(
        "/api/channels",
        json={
            "account_id": "acct_1",
            "provider_type": provider_type,
            "channel_identity_id": "ci_1",
            "removable": True,
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "unsupported_product_channel",
            "fact": {
                "type": "unsupported_product_channel",
                "provider_type": provider_type,
                "supported_provider_types": [
                    "wechat_personal",
                    "whatsapp_evolution",
                ],
            },
        }
    }
    assert service.calls == []


def test_create_route_requires_boolean_removable_before_service_call():
    client, service, _identity = make_client()

    response = client.post(
        "/api/channels",
        json={
            "account_id": "acct_1",
            "provider_type": "whatsapp_evolution",
            "channel_identity_id": "ci_1",
            "removable": "false",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "field": "removable",
                "reason": "boolean_field_required",
            },
        }
    }
    assert service.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_type", []),
        ("provider_type", ""),
        ("provider_type", " whatsapp_evolution "),
        ("channel_identity_id", {}),
        ("channel_identity_id", " ci_1 "),
    ],
)
def test_create_route_requires_string_body_fields_before_service_call(field, value):
    client, service, _identity = make_client()
    payload = {
        "account_id": "acct_1",
        "provider_type": "whatsapp_evolution",
        "channel_identity_id": "ci_1",
        "removable": True,
    }
    payload[field] = value

    response = client.post("/api/channels", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "body",
                "field": field,
                "reason": "string_field_required",
            },
        }
    }
    assert service.calls == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/channels/%20channel_1%20/connect"),
        ("get", "/api/channels/%20channel_1%20/poll"),
        ("post", "/api/channels/%20channel_1%20/remove"),
        ("post", "/api/channels/%20channel_1%20/retry"),
    ],
)
def test_channel_action_routes_require_string_channel_id_before_service_call(
    method,
    path,
):
    client, service, _identity = make_client()
    request = getattr(client, method)
    kwargs = {"json": {"account_id": "acct_1"}} if method == "post" else {}

    response = request(path, **kwargs)

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "path",
                "field": "channel_id",
                "reason": "string_field_required",
            },
        }
    }
    assert service.calls == []


def test_wechat_personal_login_status_requires_session_id_before_service_call():
    client, service, _identity = make_client()

    response = client.get("/api/channels/wechat-personal/login-status")

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "invalid_request",
            "fact": {
                "type": "invalid_request",
                "location": "query",
                "field": "session_id",
                "reason": "required_field_missing",
            },
        }
    }
    assert service.calls == []


def test_channel_route_errors_are_json():
    client, _service, _identity = make_client(service=ErrorService())

    response = client.post(
        "/api/channels/channel_1/remove",
        json={"account_id": "acct_1"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": {
            "code": "channel_identity_not_removable",
            "fact": {"type": "channel_identity_anchor", "account_id": "acct_1"},
        }
    }


def test_create_app_registers_channel_routes_only_when_service_is_supplied():
    settings = Settings(database_url=DATABASE_URL, redis_url=REDIS_URL, app_env="test")
    bare_app = create_app(settings=settings)
    assert (
        bare_app.test_client().get("/api/channels/status?account_id=acct_1").status_code
        == 404
    )

    service = FakeReachabilityService()
    app = create_app(settings=settings, channel_reachability_service=service)
    assert (
        app.test_client()
        .get(
            "/api/channels/status?account_id=acct_1",
            headers={"Authorization": "Bearer session_token"},
        )
        .status_code
        == 404
    )

    identity_service = FakeIdentityService()
    app = create_app(
        settings=settings,
        identity_access_service=identity_service,
        channel_reachability_service=service,
    )
    response = app.test_client().get("/api/channels/status?account_id=acct_1")

    assert response.status_code == 401
    response = app.test_client().get(
        "/api/channels/status?account_id=acct_1",
        headers={"Authorization": "Bearer session_token"},
    )
    assert response.status_code == 200


def test_create_app_registers_provider_webhooks_when_service_and_adapters_are_supplied():
    class FakeAdapter:
        provider_type = "whatsapp_evolution"

        def normalize_inbound(self, payload):
            return SimpleNamespace(
                provider_type="whatsapp_evolution",
                provider_subject=payload["sender"],
                text=payload.get("text", ""),
                raw_event_id=payload["message_id"],
                pairing_code=payload.get("pairing_code"),
            )

        def send_text(self, route, text, idempotency_key):
            raise AssertionError("webhook ingress must not send")

    service = FakeReachabilityService()

    def accept_provider_inbound(inbound):
        return SimpleNamespace(
            accepted=True,
            provider_type=inbound.provider_type,
            provider_subject=inbound.provider_subject,
            account_id="acct_1",
            channel_identity_id="ci_1",
            channel_id="channel_1",
            created_account=False,
            raw_event_id=inbound.raw_event_id,
        )

    service.accept_provider_inbound = accept_provider_inbound
    app = create_app(
        settings=Settings(
            database_url=DATABASE_URL,
            redis_url=REDIS_URL,
            app_env="test",
        ),
        channel_reachability_service=service,
        provider_adapters={"whatsapp_evolution": FakeAdapter()},
    )

    response = app.test_client().post(
        "/webhooks/whatsapp/evolution",
        json={
            "message_id": "wa_msg_1",
            "sender": "whatsapp:+15555550123",
            "text": "hello",
        },
    )

    assert response.status_code == 202
    assert response.get_json()["account_id"] == "acct_1"
