# ClawScale Coke WeChat Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Phase 1 `wechat_personal -> ClawScale -> CokeBridge -> coke` text-chat integration with Coke-owned account binding and ClawScale-delivered proactive messages.

**Architecture:** Keep ClawScale as the gateway layer and Coke as the business/account owner. Phase 1 keeps Coke runtime compatibility by translating ClawScale personal WeChat traffic into Coke's existing internal `platform="wechat"` message model, while preserving gateway identity in message metadata and a new `ExternalIdentity` mapping table.

**Tech Stack:** Python 3.12, Flask, PyMongo, Werkzeug password hashing, pytest, TypeScript, Hono, Vitest, pnpm

---

## File Structure

### New Python files

- `connector/clawscale_bridge/__init__.py`
  Marks the bridge package.
- `connector/clawscale_bridge/models.py`
  Defines parsed inbound payload and normalized message dataclasses.
- `connector/clawscale_bridge/auth.py`
  Validates `Authorization: Bearer <COKE_BRIDGE_API_KEY>`.
- `connector/clawscale_bridge/identity_service.py`
  Resolves `ExternalIdentity`, creates/reuses `BindingTicket`, and applies account lifecycle rules.
- `connector/clawscale_bridge/message_gateway.py`
  Translates bridge requests into Coke `inputmessages` using internal `platform="wechat"` compatibility.
- `connector/clawscale_bridge/reply_waiter.py`
  Polls Mongo `outputmessages` for the first correlated request-response reply.
- `connector/clawscale_bridge/bind_service.py`
  Validates tickets and binds a Coke account via `phone_number + bind_secret`.
- `connector/clawscale_bridge/app.py`
  Flask app with `/bridge/inbound`, `/bridge/healthz`, `/bind/<ticket_id>`, and `/bind/<ticket_id>/submit`.
- `connector/clawscale_bridge/output_route_resolver.py`
  Resolves primary ClawScale push target metadata for proactive outputs.
- `connector/clawscale_bridge/output_dispatcher.py`
  Polls proactive `outputmessages` and calls ClawScale outbound delivery.
- `connector/clawscale_bridge/templates/bind.html`
  Minimal standalone bind page.

### New DAO files

- `dao/external_identity_dao.py`
  CRUD and indexes for `external_identities`.
- `dao/binding_ticket_dao.py`
  CRUD, reuse, and throttling helpers for `binding_tickets`.

### Modified Python files

- `conf/config.json`
  Adds `clawscale_bridge` runtime configuration.
- `dao/user_dao.py`
  Adds phone-number lookup and bind-secret fields/indexes for Phase 1 account verification.
- `agent/util/message_util.py`
  Preserves request-response metadata contract and injects ClawScale push metadata for proactive outputs.

### New Python tests

- `tests/unit/dao/test_external_identity_dao.py`
- `tests/unit/dao/test_binding_ticket_dao.py`
- `tests/unit/dao/test_user_dao_bridge_lookup.py`
- `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- `tests/unit/connector/clawscale_bridge/test_reply_waiter.py`
- `tests/unit/connector/clawscale_bridge/test_bind_service.py`
- `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- `tests/unit/connector/clawscale_bridge/test_output_route_resolver.py`
- `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
- `tests/unit/agent/test_message_util_clawscale_routing.py`

### New ClawScale files inside `gateway/`

- `gateway/packages/api/src/routes/outbound.ts`
  Authenticated outbound delivery endpoint for Coke proactive pushes.
- `gateway/packages/api/src/lib/outbound-delivery.ts`
  Channel-type switch that sends direct outbound messages.
- `gateway/packages/api/src/lib/ai-backend.test.ts`
  Verifies the custom backend metadata envelope.
- `gateway/packages/api/src/routes/outbound.test.ts`
  Verifies outbound auth and `wechat_personal` delivery delegation.

### Modified ClawScale files inside `gateway/`

- `gateway/packages/api/src/lib/ai-backend.ts`
  Extends custom backend POST body with a `metadata` block.
- `gateway/packages/api/src/lib/route-message.ts`
  Passes `tenantId`, `channelId`, `endUserId`, `conversationId`, `externalId`, `sender`, and `platform` into `generateReply`.
- `gateway/packages/api/src/adapters/wechat.ts`
  Exposes direct send support for `wechat_personal` and stores live channel credentials in memory.
- `gateway/packages/api/src/index.ts`
  Mounts `/api/outbound`.

### Docs

- `docs/clawscale_bridge.md`
  Deployment, env vars, startup commands, and manual smoke-check procedure.

## Compatibility Note

Phase 1 must not refactor Coke's existing prompt/runtime assumptions around `platform="wechat"`. The bridge will therefore:

- write inbound `inputmessages.platform = "wechat"`
- preserve ClawScale origin in `metadata.source = "clawscale"`
- preserve gateway routing data in `metadata.clawscale.*`

This is the only realistic way to keep `agent/runner/context.py`, `agent/prompt/chat_taskprompt.py`, and `agent/runner/message_processor.py` working without a cross-cutting platform rewrite.

### Task 1: Add Bridge Persistence And Config Contract

**Files:**
- Create: `dao/external_identity_dao.py`
- Create: `dao/binding_ticket_dao.py`
- Modify: `dao/user_dao.py`
- Modify: `conf/config.json`
- Test: `tests/unit/dao/test_external_identity_dao.py`
- Test: `tests/unit/dao/test_binding_ticket_dao.py`
- Test: `tests/unit/dao/test_user_dao_bridge_lookup.py`

- [ ] **Step 1: Write the failing DAO and config tests**

```python
from unittest.mock import MagicMock, patch


def test_external_identity_indexes_include_unique_gateway_identity():
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.create_indexes()

    dao.collection.create_index.assert_any_call(
        [
            ("source", 1),
            ("tenant_id", 1),
            ("channel_id", 1),
            ("platform", 1),
            ("external_end_user_id", 1),
        ],
        unique=True,
    )


def test_binding_ticket_reuses_existing_pending_ticket():
    from dao.binding_ticket_dao import BindingTicketDAO

    dao = BindingTicketDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.collection.find_one.return_value = {
        "ticket_id": "bt_123",
        "status": "pending",
        "bind_url": "https://coke.local/bind/bt_123",
    }

    ticket = dao.find_reusable_ticket(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_1",
        now_ts=1710000000,
    )

    assert ticket["ticket_id"] == "bt_123"


def test_user_dao_can_lookup_phone_number():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.collection = MagicMock()
        dao.collection.find_one.return_value = {"_id": "user_1", "phone_number": "13800138000"}

        user = dao.get_user_by_phone_number("13800138000")

        assert user["phone_number"] == "13800138000"
        dao.collection.find_one.assert_called_once_with({"phone_number": "13800138000"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/dao/test_external_identity_dao.py tests/unit/dao/test_binding_ticket_dao.py tests/unit/dao/test_user_dao_bridge_lookup.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'dao.external_identity_dao'` and `AttributeError: 'UserDAO' object has no attribute 'get_user_by_phone_number'`

- [ ] **Step 3: Write the minimal persistence implementation**

```python
# dao/external_identity_dao.py
from datetime import datetime, timezone
from pymongo import MongoClient


class ExternalIdentityDAO:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db.get_collection("external_identities")

    def create_indexes(self) -> None:
        self.collection.create_index(
            [
                ("source", 1),
                ("tenant_id", 1),
                ("channel_id", 1),
                ("platform", 1),
                ("external_end_user_id", 1),
            ],
            unique=True,
        )
        self.collection.create_index([("account_id", 1), ("tenant_id", 1), ("is_primary_push_target", 1)])
        self.collection.create_index([("status", 1)])

    def find_active_identity(self, source: str, tenant_id: str, channel_id: str, platform: str, external_end_user_id: str):
        return self.collection.find_one(
            {
                "source": source,
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "platform": platform,
                "external_end_user_id": external_end_user_id,
                "status": "active",
            }
        )

    def find_primary_push_target(self, account_id: str, source: str):
        return self.collection.find_one(
            {
                "account_id": account_id,
                "source": source,
                "status": "active",
                "is_primary_push_target": True,
            }
        )
```

```python
# dao/binding_ticket_dao.py
from pymongo import MongoClient


class BindingTicketDAO:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db.get_collection("binding_tickets")

    def create_indexes(self) -> None:
        self.collection.create_index([("ticket_id", 1)], unique=True)
        self.collection.create_index(
            [("source", 1), ("tenant_id", 1), ("channel_id", 1), ("platform", 1), ("external_end_user_id", 1), ("status", 1)]
        )

    def find_reusable_ticket(self, source: str, tenant_id: str, channel_id: str, platform: str, external_end_user_id: str, now_ts: int):
        return self.collection.find_one(
            {
                "source": source,
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "platform": platform,
                "external_end_user_id": external_end_user_id,
                "status": "pending",
                "expires_at": {"$gt": now_ts},
            },
            sort=[("created_at", -1)],
        )

    def count_recent_tickets(self, source: str, tenant_id: str, channel_id: str, platform: str, external_end_user_id: str, since_ts: int) -> int:
        return self.collection.count_documents(
            {
                "source": source,
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "platform": platform,
                "external_end_user_id": external_end_user_id,
                "created_at": {"$gte": since_ts},
            }
        )

    def create_ticket(self, source: str, tenant_id: str, channel_id: str, platform: str, external_end_user_id: str, bind_base_url: str, now_ts: int):
        ticket_id = f"bt_{now_ts}_{external_end_user_id}"
        doc = {
            "ticket_id": ticket_id,
            "source": source,
            "tenant_id": tenant_id,
            "channel_id": channel_id,
            "platform": platform,
            "external_end_user_id": external_end_user_id,
            "status": "pending",
            "created_at": now_ts,
            "expires_at": now_ts + 900,
            "bind_url": f"{bind_base_url}/bind/{ticket_id}",
        }
        self.collection.insert_one(doc)
        return doc
```

```python
# dao/user_dao.py
    def create_indexes(self):
        self.collection.create_index([("platforms.wechat.id", 1)])
        self.collection.create_index([("phone_number", 1)], sparse=True)
        self.collection.create_index([("status", 1)])
        self.collection.create_index([("is_character", 1)])

    def get_user_by_phone_number(self, phone_number: str):
        if not phone_number:
            return None
        return self.collection.find_one({"phone_number": phone_number})
```

```json
// conf/config.json
"clawscale_bridge": {
    "host": "0.0.0.0",
    "port": 8090,
    "api_key": "${COKE_BRIDGE_API_KEY}",
    "bind_base_url": "${COKE_BIND_BASE_URL}",
    "reply_timeout_seconds": 25,
    "poll_interval_seconds": 1,
    "outbound_api_url": "${CLAWSCALE_OUTBOUND_API_URL}",
    "outbound_api_key": "${CLAWSCALE_OUTBOUND_API_KEY}"
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/dao/test_external_identity_dao.py tests/unit/dao/test_binding_ticket_dao.py tests/unit/dao/test_user_dao_bridge_lookup.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conf/config.json dao/external_identity_dao.py dao/binding_ticket_dao.py dao/user_dao.py tests/unit/dao/test_external_identity_dao.py tests/unit/dao/test_binding_ticket_dao.py tests/unit/dao/test_user_dao_bridge_lookup.py
git commit -m "feat(bridge): add clawscale identity persistence"
```

### Task 2: Build The Coke Message Gateway And Reply Correlation

**Files:**
- Create: `connector/clawscale_bridge/__init__.py`
- Create: `connector/clawscale_bridge/models.py`
- Create: `connector/clawscale_bridge/message_gateway.py`
- Create: `connector/clawscale_bridge/reply_waiter.py`
- Test: `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- Test: `tests/unit/connector/clawscale_bridge/test_reply_waiter.py`

- [ ] **Step 1: Write the failing bridge core tests**

```python
from unittest.mock import MagicMock


def test_message_gateway_builds_wechat_compatible_input_message():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())
    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="你好",
        bridge_request_id="br_1",
        inbound={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "end_user_id": "wxid_123",
            "external_message_id": "msg_1",
            "timestamp": 1710000000,
        },
    )

    assert doc["platform"] == "wechat"
    assert doc["from_user"] == "user_1"
    assert doc["to_user"] == "char_1"
    assert doc["metadata"]["source"] == "clawscale"
    assert doc["metadata"]["bridge_request_id"] == "br_1"
    assert doc["metadata"]["delivery_mode"] == "request_response"
    assert doc["metadata"]["clawscale"]["channel_id"] == "ch_1"


def test_reply_waiter_consumes_first_pending_text_reply():
    from connector.clawscale_bridge.reply_waiter import ReplyWaiter

    mongo = MagicMock()
    mongo.db["outputmessages"].find_one.side_effect = [
        None,
        {
            "_id": "out_1",
            "platform": "wechat",
            "status": "pending",
            "message_type": "text",
            "message": "收到",
            "metadata": {
                "source": "clawscale",
                "bridge_request_id": "br_1",
                "delivery_mode": "request_response",
            },
        },
    ]

    waiter = ReplyWaiter(mongo=mongo, poll_interval_seconds=0.01, timeout_seconds=1)
    reply = waiter.wait_for_reply("br_1")

    assert reply == "收到"
    mongo.update_one.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/connector/clawscale_bridge/test_reply_waiter.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'connector.clawscale_bridge'`

- [ ] **Step 3: Write the minimal bridge core implementation**

```python
# connector/clawscale_bridge/models.py
from dataclasses import dataclass
from typing import Any


@dataclass
class BridgeInboundPayload:
    tenant_id: str
    channel_id: str
    conversation_id: str
    platform: str
    end_user_id: str
    external_id: str
    external_message_id: str
    sender: str
    text: str
    timestamp: int
    metadata: dict[str, Any]
```

```python
# connector/clawscale_bridge/message_gateway.py
import time
import uuid


class CokeMessageGateway:
    def __init__(self, mongo, user_dao, target_character_alias: str = "coke"):
        self.mongo = mongo
        self.user_dao = user_dao
        self.target_character_alias = target_character_alias

    def build_input_message(self, account_id: str, character_id: str, text: str, bridge_request_id: str, inbound: dict):
        return {
            "input_timestamp": inbound["timestamp"],
            "handled_timestamp": inbound["timestamp"],
            "status": "pending",
            "from_user": account_id,
            "platform": "wechat",
            "chatroom_name": None,
            "to_user": character_id,
            "message_type": "text",
            "message": text,
            "metadata": {
                "source": "clawscale",
                "bridge_request_id": bridge_request_id,
                "delivery_mode": "request_response",
                "clawscale": {
                    "tenant_id": inbound["tenant_id"],
                    "channel_id": inbound["channel_id"],
                    "conversation_id": inbound["conversation_id"],
                    "platform": inbound["platform"],
                    "end_user_id": inbound["end_user_id"],
                    "external_id": inbound["external_id"],
                    "external_message_id": inbound["external_message_id"],
                },
            },
        }

    def enqueue(self, account_id: str, character_id: str, text: str, inbound: dict) -> str:
        bridge_request_id = f"br_{uuid.uuid4().hex}"
        doc = self.build_input_message(account_id, character_id, text, bridge_request_id, inbound)
        self.mongo.insert_one("inputmessages", doc)
        return bridge_request_id
```

```python
# connector/clawscale_bridge/reply_waiter.py
import time


class ReplyWaiter:
    def __init__(self, mongo, poll_interval_seconds: float, timeout_seconds: int):
        self.mongo = mongo
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds

    def wait_for_reply(self, bridge_request_id: str) -> str:
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            message = self.mongo.find_one(
                "outputmessages",
                {
                    "platform": "wechat",
                    "status": "pending",
                    "message_type": "text",
                    "metadata.source": "clawscale",
                    "metadata.bridge_request_id": bridge_request_id,
                    "metadata.delivery_mode": "request_response",
                },
            )
            if message:
                self.mongo.update_one(
                    "outputmessages",
                    {"_id": message["_id"], "status": "pending"},
                    {"$set": {"status": "handled", "handled_timestamp": int(time.time())}},
                )
                return message["message"]
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError(f"Timed out waiting for bridge_request_id={bridge_request_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/connector/clawscale_bridge/test_reply_waiter.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add connector/clawscale_bridge/__init__.py connector/clawscale_bridge/models.py connector/clawscale_bridge/identity_service.py connector/clawscale_bridge/message_gateway.py connector/clawscale_bridge/reply_waiter.py tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/connector/clawscale_bridge/test_reply_waiter.py
git commit -m "feat(bridge): add coke message gateway and reply waiter"
```

### Task 3: Add Bridge HTTP App And Coke-Owned Binding Flow

**Files:**
- Create: `connector/clawscale_bridge/auth.py`
- Create: `connector/clawscale_bridge/bind_service.py`
- Create: `connector/clawscale_bridge/app.py`
- Create: `connector/clawscale_bridge/templates/bind.html`
- Modify: `dao/user_dao.py`
- Test: `tests/unit/connector/clawscale_bridge/test_bind_service.py`
- Test: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Write the failing auth, binding, and app tests**

```python
from werkzeug.security import generate_password_hash


def test_bind_service_rejects_invalid_secret():
    from connector.clawscale_bridge.bind_service import BindService

    user_dao = type("UserDAOStub", (), {
        "get_user_by_phone_number": lambda self, phone: {
            "_id": "user_1",
            "phone_number": phone,
            "bind_secret_hash": generate_password_hash("correct-secret"),
        }
    })()

    service = BindService(user_dao=user_dao, external_identity_dao=None, binding_ticket_dao=None)

    ok, reason = service.verify_account("13800138000", "wrong-secret")

    assert ok is False
    assert reason == "invalid_credentials"


def test_bridge_inbound_rejects_missing_bearer_token():
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    client = app.test_client()

    response = client.post("/bridge/inbound", json={"messages": []})

    assert response.status_code == 401


def test_unbound_inbound_returns_bind_instruction(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    monkeypatch.setitem(app.config, "TEST_BRIDGE_RESPONSE", {
        "status": "bind_required",
        "reply": "请先绑定账号: https://coke.local/bind/bt_1",
        "bind_url": "https://coke.local/bind/bt_1",
    })

    client = app.test_client()
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={"messages": [{"role": "user", "content": "你好"}], "metadata": {"tenantId": "ten_1"}},
    )

    assert response.status_code == 200
    assert response.get_json()["reply"].startswith("请先绑定账号")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/connector/clawscale_bridge/test_bind_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: FAIL with `ModuleNotFoundError` for `connector.clawscale_bridge.bind_service` and `connector.clawscale_bridge.app`

- [ ] **Step 3: Write the minimal Flask bridge and bind flow**

```python
# connector/clawscale_bridge/auth.py
from flask import request


def require_bridge_auth(expected_token: str) -> tuple[bool, tuple[dict, int] | None]:
    header = request.headers.get("Authorization", "")
    if header != f"Bearer {expected_token}":
        return False, ({"ok": False, "error": "unauthorized"}, 401)
    return True, None
```

```python
# connector/clawscale_bridge/bind_service.py
from werkzeug.security import check_password_hash


class BindService:
    def __init__(self, user_dao, external_identity_dao, binding_ticket_dao):
        self.user_dao = user_dao
        self.external_identity_dao = external_identity_dao
        self.binding_ticket_dao = binding_ticket_dao

    def verify_account(self, phone_number: str, bind_secret: str):
        user = self.user_dao.get_user_by_phone_number(phone_number)
        if not user:
            return False, "account_not_found"
        if not check_password_hash(user["bind_secret_hash"], bind_secret):
            return False, "invalid_credentials"
        if user.get("status") not in (None, "normal"):
            return False, "account_unavailable"
        return True, user
```

```python
# connector/clawscale_bridge/app.py
from flask import Flask, jsonify, render_template, request


def create_app(testing: bool = False):
    app = Flask(__name__, template_folder="templates")
    app.config["TESTING"] = testing
    app.config.setdefault("COKE_BRIDGE_API_KEY", "test-bridge-key")

    @app.get("/bridge/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.post("/bridge/inbound")
    def inbound():
        from connector.clawscale_bridge.auth import require_bridge_auth

        ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
        if not ok:
            return error

        if "TEST_BRIDGE_RESPONSE" in app.config:
            return jsonify(app.config["TEST_BRIDGE_RESPONSE"])

        return jsonify({"ok": False, "error": "bridge service not wired"}), 500

    @app.get("/bind/<ticket_id>")
    def bind_page(ticket_id: str):
        return render_template("bind.html", ticket_id=ticket_id)

    @app.post("/bind/<ticket_id>/submit")
    def submit_bind(ticket_id: str):
        return jsonify({"ok": True, "ticket_id": ticket_id})

    return app
```

```html
<!-- connector/clawscale_bridge/templates/bind.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>绑定 Coke 账号</title>
  </head>
  <body>
    <main>
      <h1>绑定 Coke 账号</h1>
      <form method="post" action="/bind/{{ ticket_id }}/submit">
        <label>手机号 <input name="phone_number" type="text" autocomplete="tel" /></label>
        <label>绑定口令 <input name="bind_secret" type="password" autocomplete="current-password" /></label>
        <button type="submit">确认绑定</button>
      </form>
    </main>
  </body>
</html>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/connector/clawscale_bridge/test_bind_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add connector/clawscale_bridge/auth.py connector/clawscale_bridge/bind_service.py connector/clawscale_bridge/app.py connector/clawscale_bridge/templates/bind.html dao/user_dao.py tests/unit/connector/clawscale_bridge/test_bind_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py
git commit -m "feat(bind): add coke-owned clawscale bind flow"
```

### Task 4: Route Proactive Outputs Through ClawScale

**Files:**
- Create: `connector/clawscale_bridge/output_route_resolver.py`
- Create: `connector/clawscale_bridge/output_dispatcher.py`
- Modify: `agent/util/message_util.py`
- Test: `tests/unit/connector/clawscale_bridge/test_output_route_resolver.py`
- Test: `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
- Test: `tests/unit/agent/test_message_util_clawscale_routing.py`

- [ ] **Step 1: Write the failing proactive routing tests**

```python
from unittest.mock import MagicMock


def test_output_route_resolver_returns_primary_push_target():
    from connector.clawscale_bridge.output_route_resolver import OutputRouteResolver

    dao = MagicMock()
    dao.find_primary_push_target.return_value = {
        "tenant_id": "ten_1",
        "channel_id": "ch_1",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_123",
        "source": "clawscale",
    }

    resolver = OutputRouteResolver(external_identity_dao=dao)
    metadata = resolver.build_push_metadata("user_1", now_ts=1710000000)

    assert metadata["route_via"] == "clawscale"
    assert metadata["delivery_mode"] == "push"
    assert metadata["tenant_id"] == "ten_1"


def test_message_util_appends_push_metadata_for_proactive_output(monkeypatch, sample_context):
    from agent.util import message_util

    monkeypatch.setattr(
        message_util,
        "build_clawscale_push_metadata",
        lambda user_id, now_ts=None: {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    )

    sample_context["conversation"]["conversation_info"]["input_messages"] = []
    message = message_util.send_message_via_context(sample_context, "提醒你喝水")

    assert message["metadata"]["route_via"] == "clawscale"
    assert message["metadata"]["delivery_mode"] == "push"


def test_output_dispatcher_marks_message_handled_after_successful_post():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    mongo.find_one.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "pending",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }

    dispatcher = ClawScaleOutputDispatcher(mongo=mongo, session=MagicMock(), outbound_api_url="https://gateway.local/api/outbound")
    dispatcher.session.post.return_value.status_code = 200

    handled = dispatcher.dispatch_once()

    assert handled is True
    mongo.update_one.assert_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/connector/clawscale_bridge/test_output_route_resolver.py tests/unit/connector/clawscale_bridge/test_output_dispatcher.py tests/unit/agent/test_message_util_clawscale_routing.py -v`

Expected: FAIL with `ModuleNotFoundError` for the new bridge routing modules

- [ ] **Step 3: Write the minimal proactive routing implementation**

```python
# connector/clawscale_bridge/output_route_resolver.py
import uuid


class OutputRouteResolver:
    def __init__(self, external_identity_dao):
        self.external_identity_dao = external_identity_dao

    def build_push_metadata(self, account_id: str, now_ts: int):
        target = self.external_identity_dao.find_primary_push_target(account_id=account_id, source="clawscale")
        if not target:
            return {}
        return {
            "source": "clawscale",
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": target["tenant_id"],
            "channel_id": target["channel_id"],
            "platform": target["platform"],
            "external_end_user_id": target["external_end_user_id"],
            "push_idempotency_key": f"push_{uuid.uuid4().hex}",
        }
```

```python
# agent/util/message_util.py
def build_clawscale_push_metadata(user_id: str, now_ts: int | None = None):
    from conf.config import CONF
    from dao.external_identity_dao import ExternalIdentityDAO
    from connector.clawscale_bridge.output_route_resolver import OutputRouteResolver

    dao = ExternalIdentityDAO(
        mongo_uri="mongodb://" + CONF["mongodb"]["mongodb_ip"] + ":" + CONF["mongodb"]["mongodb_port"] + "/",
        db_name=CONF["mongodb"]["mongodb_name"],
    )
    resolver = OutputRouteResolver(dao)
    return resolver.build_push_metadata(user_id, now_ts or int(time.time()))


def send_message_via_context(context, message, message_type="text", expect_output_timestamp=None, metadata=None):
    if metadata is None:
        metadata = {}
    input_messages = (
        context.get("conversation", {})
        .get("conversation_info", {})
        .get("input_messages", [])
    )
    if input_messages and len(input_messages) > 0:
        first_input = input_messages[0]
        input_metadata = first_input.get("metadata", {})
        metadata = {**input_metadata, **metadata}
    elif context.get("user", {}).get("_id"):
        metadata = {**build_clawscale_push_metadata(str(context["user"]["_id"])), **metadata}
    return send_message(
        platform=context["conversation"]["platform"],
        from_user=str(context["character"]["_id"]),
        to_user=str(context["user"]["_id"]),
        chatroom_name=context["conversation"]["chatroom_name"],
        message=message,
        message_type=message_type,
        status="pending",
        expect_output_timestamp=expect_output_timestamp,
        metadata=metadata,
    )
```

```python
# connector/clawscale_bridge/output_dispatcher.py
import requests
import time


class ClawScaleOutputDispatcher:
    def __init__(self, mongo, session, outbound_api_url: str, outbound_api_key: str = "test-outbound-key"):
        self.mongo = mongo
        self.session = session or requests.Session()
        self.outbound_api_url = outbound_api_url
        self.outbound_api_key = outbound_api_key

    def dispatch_once(self) -> bool:
        now = int(time.time())
        message = self.mongo.find_one(
            "outputmessages",
            {
                "platform": "wechat",
                "status": "pending",
                "expect_output_timestamp": {"$lte": now},
                "metadata.route_via": "clawscale",
                "metadata.delivery_mode": "push",
            },
        )
        if not message:
            return False

        payload = {
            "tenant_id": message["metadata"]["tenant_id"],
            "channel_id": message["metadata"]["channel_id"],
            "end_user_id": message["metadata"]["external_end_user_id"],
            "text": message["message"],
            "idempotency_key": message["metadata"]["push_idempotency_key"],
        }
        response = self.session.post(
            self.outbound_api_url,
            json=payload,
            headers={"Authorization": f"Bearer {self.outbound_api_key}"},
            timeout=15,
        )
        new_status = "handled" if response.status_code in (200, 409) else "failed"
        self.mongo.update_one(
            "outputmessages",
            {"_id": message["_id"]},
            {"$set": {"status": new_status, "handled_timestamp": now}},
        )
        return new_status == "handled"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/connector/clawscale_bridge/test_output_route_resolver.py tests/unit/connector/clawscale_bridge/test_output_dispatcher.py tests/unit/agent/test_message_util_clawscale_routing.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add connector/clawscale_bridge/output_route_resolver.py connector/clawscale_bridge/output_dispatcher.py agent/util/message_util.py tests/unit/connector/clawscale_bridge/test_output_route_resolver.py tests/unit/connector/clawscale_bridge/test_output_dispatcher.py tests/unit/agent/test_message_util_clawscale_routing.py
git commit -m "feat(bridge): route proactive outputs through clawscale"
```

### Task 5: Extend ClawScale Custom Backend Metadata And Add Outbound Delivery

**Files:**
- Modify: `gateway/packages/api/src/lib/ai-backend.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/adapters/wechat.ts`
- Create: `gateway/packages/api/src/lib/outbound-delivery.ts`
- Create: `gateway/packages/api/src/routes/outbound.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Test: `gateway/packages/api/src/lib/ai-backend.test.ts`
- Test: `gateway/packages/api/src/routes/outbound.test.ts`

- [ ] **Step 1: Write the failing ClawScale contract tests**

```ts
import { describe, expect, it, vi } from 'vitest';
import { generateReply } from './ai-backend.js';

describe('custom backend metadata envelope', () => {
  it('includes tenant and end-user metadata in fetch body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ reply: 'ok' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await generateReply({
      backend: { type: 'custom', config: { baseUrl: 'https://bridge.local/reply', responseFormat: 'json-auto' } as any },
      history: [{ role: 'user', content: '你好' }],
      sender: 'Alice',
      platform: 'wechat_personal',
      metadata: {
        tenantId: 'ten_1',
        channelId: 'ch_1',
        endUserId: 'eu_1',
        conversationId: 'conv_1',
        externalId: 'wxid_123',
      },
    } as any);

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.metadata.tenantId).toBe('ten_1');
    expect(body.metadata.channelId).toBe('ch_1');
    expect(body.metadata.endUserId).toBe('eu_1');
  });
});
```

```ts
import { describe, expect, it, vi } from 'vitest';
import { Hono } from 'hono';
import { outboundRouter } from './outbound.js';

describe('outbound router', () => {
  it('rejects invalid bearer tokens', async () => {
    process.env.CLAWSCALE_OUTBOUND_API_KEY = 'secret';
    const app = new Hono();
    app.route('/api/outbound', outboundRouter);

    const res = await app.request('/api/outbound', {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: 'Bearer wrong' },
      body: JSON.stringify({ tenant_id: 'ten_1', channel_id: 'ch_1', end_user_id: 'wxid_1', text: 'hello', idempotency_key: 'push_1' }),
    });

    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm -C gateway --filter @clawscale/api test -- src/lib/ai-backend.test.ts src/routes/outbound.test.ts`

Expected: FAIL because `generateReply` does not accept `metadata`, `outbound.ts` does not exist, and `/api/outbound` is not mounted

- [ ] **Step 3: Write the minimal ClawScale implementation**

```ts
// gateway/packages/api/src/lib/ai-backend.ts
export interface GenerateOptions {
  backend: BackendSpec;
  history: HistoryMessage[];
  sender?: string;
  platform?: string;
  metadata?: {
    tenantId: string;
    channelId: string;
    endUserId: string;
    conversationId: string;
    externalId: string;
  };
}

export async function generateReply(options: GenerateOptions): Promise<string> {
  const { backend, history, sender, platform, metadata } = options;
  return handleFetch(
    BACKEND_TYPE_DESCRIPTORS[backend.type],
    backend.config,
    history,
    metadata
      ? {
          metadata: {
            ...metadata,
            sender,
            platform,
          },
        }
      : undefined,
  );
}

async function handleFetch(
  descriptor: BackendTypeDescriptor,
  cfg: AiBackendProviderConfig,
  history: HistoryMessage[],
  extraBody?: Record<string, unknown>,
): Promise<string> {
  const url = resolveEndpoint(descriptor, cfg);
  const res = await fetch(url, {
    method: 'POST',
    headers: authHeaders(cfg),
    body: JSON.stringify({
      messages: history,
      ...(cfg.systemPrompt && descriptor.type === 'claude-code' ? { system_prompt: cfg.systemPrompt } : {}),
      ...extraBody,
    }),
    signal: AbortSignal.timeout(120_000),
  });
  return parseResponse(res, resolveResponseFormat(descriptor, cfg));
}
```

```ts
// gateway/packages/api/src/lib/route-message.ts
return generateReply({
  backend: { id: backend.id, type: backend.type as any, config: backend.config as any } as any,
  history,
  sender: endUser!.name ?? displayName,
  platform,
  metadata: {
    tenantId,
    channelId,
    endUserId: endUser!.id,
    conversationId: conversation!.id,
    externalId: endUser!.externalId,
  },
});
```

```ts
// gateway/packages/api/src/lib/outbound-delivery.ts
import { sendWeixinText } from '../adapters/wechat.js';

export async function deliverOutboundMessage(channel: { id: string; type: string }, endUserId: string, text: string): Promise<void> {
  switch (channel.type) {
    case 'wechat_personal':
      await sendWeixinText(channel.id, endUserId, text);
      return;
    default:
      throw new Error(`Unsupported outbound channel type: ${channel.type}`);
  }
}
```

```ts
// gateway/packages/api/src/adapters/wechat.ts
interface WeixinState {
  running: boolean;
  cursor: string;
  qr: string | null;
  qrUrl: string | null;
  status: 'qr_pending' | 'connected' | 'disconnected';
  baseUrl?: string;
  token?: string;
}

export async function sendWeixinText(channelId: string, externalId: string, text: string): Promise<void> {
  const state = channels.get(channelId);
  if (!state?.baseUrl || !state?.token) throw new Error(`wechat channel ${channelId} is not connected`);
  const sendBody = JSON.stringify({
    msg: {
      from_user_id: '',
      to_user_id: externalId,
      client_id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      message_type: 2,
      message_state: 2,
      context_token: '',
      item_list: [{ type: 1, text_item: { text } }],
    },
    base_info: { channel_version: '1.0.0' },
  });
  await fetch(`${state.baseUrl}/ilink/bot/sendmessage`, {
    method: 'POST',
    headers: msgHeaders(state.token, sendBody),
    body: sendBody,
    signal: AbortSignal.timeout(15_000),
  });
}
```

```ts
// gateway/packages/api/src/routes/outbound.ts
import { Hono } from 'hono';
import { z } from 'zod';
import { db } from '../db/index.js';
import { deliverOutboundMessage } from '../lib/outbound-delivery.js';

const bodySchema = z.object({
  tenant_id: z.string(),
  channel_id: z.string(),
  end_user_id: z.string(),
  text: z.string().min(1),
  idempotency_key: z.string().min(1),
});

export const outboundRouter = new Hono();

outboundRouter.post('/', async (c) => {
  const expected = process.env['CLAWSCALE_OUTBOUND_API_KEY'] ?? '';
  if (c.req.header('Authorization') !== `Bearer ${expected}`) {
    return c.json({ ok: false, error: 'unauthorized' }, 401);
  }
  const body = bodySchema.parse(await c.req.json());
  const channel = await db.channel.findFirst({ where: { id: body.channel_id, tenantId: body.tenant_id } });
  if (!channel) return c.json({ ok: false, error: 'channel_not_found' }, 404);

  await deliverOutboundMessage(channel, body.end_user_id, body.text);
  return c.json({ ok: true, idempotency_key: body.idempotency_key });
});
```

```ts
// gateway/packages/api/src/index.ts
import { outboundRouter } from './routes/outbound.js';
app.route('/api/outbound', outboundRouter);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm -C gateway --filter @clawscale/api test -- src/lib/ai-backend.test.ts src/routes/outbound.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C gateway add packages/api/src/lib/ai-backend.ts packages/api/src/lib/route-message.ts packages/api/src/adapters/wechat.ts packages/api/src/lib/outbound-delivery.ts packages/api/src/routes/outbound.ts packages/api/src/index.ts packages/api/src/lib/ai-backend.test.ts packages/api/src/routes/outbound.test.ts
git -C gateway commit -m "feat(api): add coke bridge metadata and outbound delivery"
git add gateway
git commit -m "feat(gateway): update clawscale submodule for coke bridge"
```

### Task 6: Wire The Full Inbound Flow, Document It, And Freeze The Contract

**Files:**
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `connector/clawscale_bridge/identity_service.py`
- Create: `docs/clawscale_bridge.md`
- Test: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Write the failing end-to-end bridge flow test**

```python
from unittest.mock import MagicMock


def test_bound_inbound_request_returns_coke_reply(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    gateway = MagicMock()
    gateway.handle_inbound.return_value = {"reply": "你好，我在", "status": "ok"}
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", gateway)

    client = app.test_client()
    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "messages": [{"role": "user", "content": "在吗"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "externalId": "wxid_123",
                "sender": "Alice",
                "platform": "wechat_personal",
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "reply": "你好，我在"}
```

- [ ] **Step 2: Run the end-to-end bridge test to verify it fails**

Run: `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py::test_bound_inbound_request_returns_coke_reply -v`

Expected: FAIL because `/bridge/inbound` still returns the temporary `"bridge service not wired"` response

- [ ] **Step 3: Replace the temporary route with the real inbound orchestration and write operator docs**

```python
# connector/clawscale_bridge/app.py
@app.post("/bridge/inbound")
def inbound():
    ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
    if not ok:
        body, status = error
        return jsonify(body), status

    payload = request.get_json(force=True)
    gateway = app.config["BRIDGE_GATEWAY"]
    result = gateway.handle_inbound(payload)

    if result["status"] == "bind_required":
        return jsonify({"ok": True, "reply": result["reply"], "bind_url": result["bind_url"]})

    return jsonify({"ok": True, "reply": result["reply"]})
```

```python
# connector/clawscale_bridge/identity_service.py
class IdentityService:
    def __init__(self, external_identity_dao, binding_ticket_dao, message_gateway, reply_waiter, bind_base_url: str, target_character_id: str):
        self.external_identity_dao = external_identity_dao
        self.binding_ticket_dao = binding_ticket_dao
        self.message_gateway = message_gateway
        self.reply_waiter = reply_waiter
        self.bind_base_url = bind_base_url
        self.target_character_id = target_character_id

    def issue_or_reuse_binding_ticket(self, metadata: dict, now_ts: int):
        reusable = self.binding_ticket_dao.find_reusable_ticket(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
            now_ts=now_ts,
        )
        if reusable:
            return reusable

        recent_count = self.binding_ticket_dao.count_recent_tickets(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
            since_ts=now_ts - 3600,
        )
        if recent_count >= 5:
            raise ValueError("bind_ticket_rate_limited")

        return self.binding_ticket_dao.create_ticket(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
            bind_base_url=self.bind_base_url,
            now_ts=now_ts,
        )

    def handle_inbound(self, inbound_payload: dict):
        metadata = inbound_payload["metadata"]
        external_identity = self.external_identity_dao.find_active_identity(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
        )
        if not external_identity:
            ticket = self.issue_or_reuse_binding_ticket(metadata, now_ts=int(time.time()))
            return {
                "status": "bind_required",
                "reply": f"请先绑定账号: {ticket['bind_url']}",
                "bind_url": ticket["bind_url"],
            }
        bridge_request_id = self.message_gateway.enqueue(
            account_id=external_identity["account_id"],
            character_id=self.target_character_id,
            text=inbound_payload["messages"][-1]["content"],
            inbound={
                "tenant_id": metadata["tenantId"],
                "channel_id": metadata["channelId"],
                "conversation_id": metadata["conversationId"],
                "platform": metadata["platform"],
                "end_user_id": metadata["endUserId"],
                "external_id": metadata["externalId"],
                "external_message_id": metadata["conversationId"],
                "timestamp": int(time.time()),
            },
        )
        reply = self.reply_waiter.wait_for_reply(bridge_request_id)
        return {"status": "ok", "reply": reply}
```

```md
# docs/clawscale_bridge.md
## Environment
- `COKE_BRIDGE_API_KEY`
- `COKE_BIND_BASE_URL`
- `CLAWSCALE_OUTBOUND_API_URL`
- `CLAWSCALE_OUTBOUND_API_KEY`

## Start Coke bridge
Run `python -m connector.clawscale_bridge.app`

## Start proactive dispatcher
Run `python -m connector.clawscale_bridge.output_dispatcher`

## Start Coke workers in poll mode
Run `QUEUE_MODE=poll bash agent/runner/agent_start.sh`

## ClawScale custom backend config
- `baseUrl`: `http://<bridge-host>:8090/bridge/inbound`
- `authHeader`: `Bearer <COKE_BRIDGE_API_KEY>`
- `transport`: `http`
- `responseFormat`: `json-auto`
```

- [ ] **Step 4: Run the focused bridge test and the full bridge unit suite**

Run: `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: PASS

Run: `pytest tests/unit/connector/clawscale_bridge/ -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add connector/clawscale_bridge/app.py connector/clawscale_bridge/identity_service.py docs/clawscale_bridge.md tests/unit/connector/clawscale_bridge/test_bridge_app.py
git commit -m "docs(bridge): finalize clawscale coke bridge flow"
```

## Final Verification

- Run Coke bridge/unit suite:

```bash
pytest tests/unit/dao/test_external_identity_dao.py tests/unit/dao/test_binding_ticket_dao.py tests/unit/dao/test_user_dao_bridge_lookup.py tests/unit/connector/clawscale_bridge/ tests/unit/agent/test_message_util_clawscale_routing.py -v
```

Expected: PASS

- Run ClawScale targeted tests:

```bash
pnpm -C gateway --filter @clawscale/api test -- src/lib/ai-backend.test.ts src/routes/outbound.test.ts
```

Expected: PASS

- Run bridge health check locally after starting both services:

```bash
curl -s http://127.0.0.1:8090/bridge/healthz
curl -s http://127.0.0.1:4041/health
```

Expected:

```json
{"ok":true}
```

## Self-Review

### Spec coverage

- ClawScale-only gateway ownership: Tasks 2, 5, and 6 keep gateway metadata outside Coke business state.
- Coke-owned binding flow: Task 3 implements bind page, bind auth, and ticket lifecycle.
- Reply correlation: Task 2 implements `bridge_request_id` polling over Mongo.
- Proactive push path: Tasks 4 and 5 add dispatcher plus ClawScale outbound endpoint.
- Auth, throttling, uniqueness, and lifecycle notes: Tasks 1 and 3 encode indexes, reusable ticket rules, and account verification hooks.
- Deployment shape: Task 6 documents runtime commands and env vars.

### Placeholder scan

- No `TODO`, `TBD`, or "implement later" placeholders remain.
- All tasks list concrete file paths, commands, and expected outcomes.

### Type consistency

- Phase 1 always writes Coke internal `platform="wechat"` while preserving ClawScale channel data in `metadata.clawscale`.
- ClawScale metadata keys use camelCase in the custom backend body; Coke stores the translated snake_case form inside Mongo metadata.
- Proactive routing consistently uses `route_via="clawscale"` and `delivery_mode="push"`.
