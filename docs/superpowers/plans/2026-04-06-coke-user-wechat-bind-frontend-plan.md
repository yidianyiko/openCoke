# Coke User WeChat Bind Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal Coke user-facing web flow where a desktop user registers or logs in, opens a `Bind WeChat` page, scans a QR code with personal WeChat, sends any first message in WeChat, and then sees the account marked as bound.

**Architecture:** Keep the existing ClawScale admin dashboard untouched and add a separate Coke user route group under `gateway/packages/web/app/(coke-user)/coke/*`. Coke owns web-user auth, bind-session lifecycle, and final `external_identity -> coke_user_id` persistence in the Python bridge app; ClawScale remains the live WeChat transport and must round-trip a bind token through inbound `metadata.contextToken` so the first inbound WeChat message can consume the pending bind session automatically.

**Tech Stack:** Python 3.12, Flask, PyMongo, itsdangerous, Werkzeug password hashing, pytest, TypeScript, Next.js, qrcode, Vitest, pnpm

---

## Scope Notes

- This plan does **not** replace the existing ClawScale admin auth flow in `gateway/packages/web/app/login` and `gateway/packages/web/app/register`.
- Coke user pages live under `/coke/login`, `/coke/register`, and `/coke/bind-wechat` in v1 so admin routes keep working.
- This plan assumes a single already-connected official WeChat entrypoint for Coke. The public user-entry URL is supplied via `COKE_WECHAT_PUBLIC_CONNECT_URL_TEMPLATE`, and that template must include a `{bind_token}` placeholder that iLink round-trips into inbound `metadata.contextToken`.
- Because the browser app runs on `gateway/packages/web` and the Coke user APIs live on the Python bridge, the bridge must return CORS headers for the configured web origin in local and production deployments.
- This plan does **not** implement mobile-web binding, self-service unbind, or WeChat replacement rules.

## File Structure

### New Python files

- `dao/wechat_bind_session_dao.py`
  Persists short-lived website-first bind sessions in Mongo.
- `connector/clawscale_bridge/user_auth.py`
  Handles web-user password hashing, token issue/verify, and auth helpers for Coke user APIs.
- `connector/clawscale_bridge/wechat_bind_session_service.py`
  Creates/reuses bind sessions, builds QR/connect URLs, reports bind status, and consumes a pending bind session when the first WeChat message arrives.
- `tests/unit/dao/test_user_dao_web_auth.py`
  Covers email lookup/index behavior for Coke web users.
- `tests/unit/dao/test_wechat_bind_session_dao.py`
  Covers bind-session indexes and pending/bound state transitions.
- `tests/unit/connector/clawscale_bridge/test_user_auth.py`
  Covers register/login/token verification behavior.
- `tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py`
  Covers bind-session creation, reuse, status, and consume flow.
- `tests/unit/connector/clawscale_bridge/test_identity_service.py`
  Covers auto-bind on first inbound WeChat message and fallback to the legacy `bind_required` path.

### Modified Python files

- `dao/user_dao.py`
  Adds email-based lookup/index helpers for Coke web-user auth without changing existing character/user reads.
- `dao/external_identity_dao.py`
  Adds lookup by Coke account ID so the bind page can report `already bound`.
- `connector/clawscale_bridge/identity_service.py`
  Tries to consume a pending website-first bind session before falling back to the old bind-required response.
- `connector/clawscale_bridge/app.py`
  Mounts Coke user auth and bind-session APIs alongside the existing `/bridge/*` routes.
- `conf/config.json`
  Adds Coke user-auth and WeChat bind-session config.
- `docs/clawscale_bridge.md`
  Documents new env vars, user-facing routes, and the manual bind smoke test.

### New web files inside `gateway/packages/web/`

- `gateway/packages/web/lib/coke-user-api.ts`
  Separate API client for Coke user APIs so admin API calls do not collide.
- `gateway/packages/web/lib/coke-user-auth.ts`
  Stores Coke user auth under separate localStorage keys from the admin dashboard.
- `gateway/packages/web/lib/coke-user-auth.test.ts`
  Verifies Coke user auth storage keys and clear/load helpers.
- `gateway/packages/web/app/(coke-user)/coke/layout.tsx`
  Provides Coke branding and a simple logged-in shell for user-facing pages.
- `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
  Coke user login page that calls the new Python auth API.
- `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
  Coke user registration page that creates a Coke web account.
- `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
  Desktop-only bind page with QR rendering, polling, and bound-state display.

### Modified web files inside `gateway/packages/web/`

- `gateway/packages/web/package.json`
  Adds `qrcode`, `vitest`, `jsdom`, and a `test` script for the Coke user helpers.

## Data Contracts

### Coke web user fields in `users`

Use the existing `users` collection and add only the minimum fields needed for web auth:

```text
email
password_hash
display_name
web_auth_enabled
```

Characters continue to use `is_character = true`, and Coke web-auth lookups must always exclude characters.

### WeChat bind session document

Persist bind sessions in Mongo collection `wechat_bind_sessions`:

```text
session_id
account_id
bind_token
status = pending | bound | expired | failed
connect_url
masked_identity
matched_external_end_user_id
created_at
expires_at
bound_at
```

### Bind status API shape

Return only the v1 page states the bind screen needs:

```json
{
  "status": "unbound | pending | bound | expired | failed",
  "connect_url": "https://...",
  "expires_at": 1775472000,
  "masked_identity": "wxid_***9f2c"
}
```

The API response must not expose internal `bind_token`, `session_id`, or `account_id` fields back to the browser.

## Task 1: Add Coke Web-User Auth Primitives

**Files:**
- Modify: `dao/user_dao.py`
- Create: `connector/clawscale_bridge/user_auth.py`
- Test: `tests/unit/dao/test_user_dao_web_auth.py`
- Test: `tests/unit/connector/clawscale_bridge/test_user_auth.py`

- [ ] **Step 1: Write the failing DAO and auth tests**

```python
# tests/unit/dao/test_user_dao_web_auth.py
from unittest.mock import MagicMock, patch


def test_user_dao_creates_unique_sparse_email_index():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.collection = MagicMock()

        dao.create_indexes()

        dao.collection.create_index.assert_any_call(
            [("email", 1)],
            unique=True,
            sparse=True,
        )


def test_user_dao_can_lookup_email_case_insensitively():
    with patch("dao.user_dao.MongoClient"):
        from dao.user_dao import UserDAO

        dao = UserDAO(mongo_uri="mongodb://example", db_name="test")
        dao.collection = MagicMock()
        dao.collection.find_one.return_value = {
            "_id": "user_1",
            "email": "alice@example.com",
            "is_character": False,
        }

        user = dao.get_user_by_email("Alice@Example.com")

        assert user["email"] == "alice@example.com"
        dao.collection.find_one.assert_called_once_with(
            {"email": "alice@example.com", "is_character": {"$ne": True}}
        )
```

```python
# tests/unit/connector/clawscale_bridge/test_user_auth.py
from unittest.mock import MagicMock


def test_register_hashes_password_and_returns_token():
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_email.return_value = None
    user_dao.create_user.return_value = "65f000000000000000000111"

    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    result = service.register(
        display_name="Alice",
        email="Alice@Example.com",
        password="correct horse battery staple",
    )

    stored = user_dao.create_user.call_args[0][0]
    assert stored["email"] == "alice@example.com"
    assert stored["password_hash"] != "correct horse battery staple"
    assert result["user"]["email"] == "alice@example.com"
    assert result["token"]


def test_login_rejects_invalid_password():
    from werkzeug.security import generate_password_hash
    from connector.clawscale_bridge.user_auth import UserAuthService

    user_dao = MagicMock()
    user_dao.get_user_by_email.return_value = {
        "_id": "65f000000000000000000111",
        "email": "alice@example.com",
        "display_name": "Alice",
        "password_hash": generate_password_hash("correct-password"),
        "is_character": False,
    }

    service = UserAuthService(
        user_dao=user_dao,
        secret_key="test-secret",
        token_ttl_seconds=3600,
    )

    ok, error = service.login("alice@example.com", "wrong-password")

    assert ok is False
    assert error == "invalid_credentials"
```

- [ ] **Step 2: Run the auth tests to verify they fail**

Run: `pytest tests/unit/dao/test_user_dao_web_auth.py tests/unit/connector/clawscale_bridge/test_user_auth.py -v`

Expected: FAIL with `AttributeError: 'UserDAO' object has no attribute 'get_user_by_email'` and `ModuleNotFoundError: No module named 'connector.clawscale_bridge.user_auth'`

- [ ] **Step 3: Write the minimal DAO and auth implementation**

```python
# dao/user_dao.py
def create_indexes(self):
    self.collection.create_index([("platforms.wechat.id", 1)])
    self.collection.create_index([("phone_number", 1)], sparse=True)
    self.collection.create_index([("email", 1)], unique=True, sparse=True)
    self.collection.create_index([("status", 1)])
    self.collection.create_index([("is_character", 1)])


def get_user_by_email(self, email: str) -> Optional[Dict]:
    if not email:
        return None
    return self.collection.find_one(
        {"email": email.lower(), "is_character": {"$ne": True}}
    )
```

```python
# connector/clawscale_bridge/user_auth.py
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash, generate_password_hash


class UserAuthService:
    def __init__(self, user_dao, secret_key: str, token_ttl_seconds: int):
        self.user_dao = user_dao
        self.serializer = URLSafeTimedSerializer(secret_key=secret_key, salt="coke-user-auth")
        self.token_ttl_seconds = token_ttl_seconds

    def _issue_token(self, user_id: str) -> str:
        return self.serializer.dumps({"user_id": user_id})

    def verify_token(self, token: str):
        try:
            payload = self.serializer.loads(token, max_age=self.token_ttl_seconds)
        except (BadSignature, SignatureExpired):
            return None
        return self.user_dao.get_user_by_id(payload["user_id"])

    def register(self, display_name: str, email: str, password: str) -> dict:
        normalized_email = email.lower().strip()
        if self.user_dao.get_user_by_email(normalized_email):
            raise ValueError("email_already_exists")

        user_id = self.user_dao.create_user(
            {
                "display_name": display_name.strip(),
                "email": normalized_email,
                "password_hash": generate_password_hash(password),
                "web_auth_enabled": True,
                "is_character": False,
                "status": "normal",
            }
        )
        return {
            "token": self._issue_token(user_id),
            "user": {
                "id": user_id,
                "email": normalized_email,
                "display_name": display_name.strip(),
            },
        }

    def login(self, email: str, password: str):
        user = self.user_dao.get_user_by_email(email.lower().strip())
        if not user or not check_password_hash(user["password_hash"], password):
            return False, "invalid_credentials"
        if user.get("status") not in (None, "normal"):
            return False, "account_unavailable"
        return True, {
            "token": self._issue_token(str(user["_id"])),
            "user": {
                "id": str(user["_id"]),
                "email": user["email"],
                "display_name": user.get("display_name") or user.get("name") or "Coke User",
            },
        }
```

- [ ] **Step 4: Run the auth tests to verify they pass**

Run: `pytest tests/unit/dao/test_user_dao_web_auth.py tests/unit/connector/clawscale_bridge/test_user_auth.py -v`

Expected: PASS with `4 passed`

- [ ] **Step 5: Commit the auth primitives**

```bash
git add dao/user_dao.py connector/clawscale_bridge/user_auth.py tests/unit/dao/test_user_dao_web_auth.py tests/unit/connector/clawscale_bridge/test_user_auth.py
git commit -m "feat(coke-auth): add coke web user auth primitives"
```

## Task 2: Add WeChat Bind Session Persistence And User APIs

**Files:**
- Create: `dao/wechat_bind_session_dao.py`
- Modify: `dao/external_identity_dao.py`
- Create: `connector/clawscale_bridge/wechat_bind_session_service.py`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `conf/config.json`
- Test: `tests/unit/dao/test_wechat_bind_session_dao.py`
- Test: `tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Write the failing bind-session tests**

```python
# tests/unit/dao/test_wechat_bind_session_dao.py
from unittest.mock import MagicMock


def test_bind_session_indexes_include_unique_session_and_bind_token():
    from dao.wechat_bind_session_dao import WechatBindSessionDAO

    dao = WechatBindSessionDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.create_indexes()

    dao.collection.create_index.assert_any_call([("session_id", 1)], unique=True)
    dao.collection.create_index.assert_any_call([("bind_token", 1)], unique=True)


def test_find_latest_session_for_account_keeps_expired_rows_visible_for_status_checks():
    from dao.wechat_bind_session_dao import WechatBindSessionDAO

    dao = WechatBindSessionDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.find_latest_session_for_account("user_1")

    dao.collection.find_one.assert_called_once_with(
        {"account_id": "user_1"},
        sort=[("created_at", -1)],
    )
```

```python
# tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py
from unittest.mock import MagicMock


def test_create_or_reuse_session_returns_sanitized_pending_payload():
    from connector.clawscale_bridge.wechat_bind_session_service import WechatBindSessionService

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_for_account.return_value = None
    bind_session_dao.create_session.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_123",
        "status": "pending",
        "connect_url": "https://wx.example.com/entry?bind_token=ctx_123",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = None

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        connect_url_template="https://wx.example.com/entry?bind_token={bind_token}",
        ttl_seconds=600,
    )

    result = service.create_or_reuse_session(account_id="user_1", now_ts=1775472000)

    assert result["status"] == "pending"
    assert result["connect_url"].startswith("https://wx.example.com/entry")
    assert "bind_token" not in result
    assert "account_id" not in result


def test_create_or_reuse_session_returns_bound_when_account_already_linked():
    from connector.clawscale_bridge.wechat_bind_session_service import WechatBindSessionService

    bind_session_dao = MagicMock()
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = {
        "external_end_user_id": "wxid_9f2c8e0a",
        "status": "active",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        connect_url_template="https://wx.example.com/entry?bind_token={bind_token}",
        ttl_seconds=600,
    )

    result = service.create_or_reuse_session(account_id="user_1", now_ts=1775472000)

    assert result["status"] == "bound"
    assert result["masked_identity"].startswith("wxid_")


def test_get_status_returns_expired_when_latest_session_elapsed():
    from connector.clawscale_bridge.wechat_bind_session_service import WechatBindSessionService

    bind_session_dao = MagicMock()
    bind_session_dao.find_latest_session_for_account.return_value = {
        "session_id": "bs_1",
        "status": "pending",
        "expires_at": 1775471999,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = None

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        connect_url_template="https://wx.example.com/entry?bind_token={bind_token}",
        ttl_seconds=600,
    )

    result = service.get_status(account_id="user_1", now_ts=1775472000)

    assert result == {"status": "expired"}
```

```python
# tests/unit/connector/clawscale_bridge/test_bridge_app.py
def test_user_bind_session_requires_user_bearer_token():
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    client = app.test_client()

    response = client.post("/user/wechat-bind/session")

    assert response.status_code == 401
    assert response.get_json()["ok"] is False


def test_user_bind_session_returns_pending_payload(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    client = app.test_client()
    app.config["COKE_WEB_ALLOWED_ORIGIN"] = "http://127.0.0.1:4040"
    app.config["USER_AUTH_SERVICE"] = type(
        "Auth",
        (),
        {"verify_token": lambda self, token: {"_id": "user_1", "email": "alice@example.com"}},
    )()
    app.config["USER_BIND_SERVICE"] = type(
        "Bind",
        (),
        {
            "create_or_reuse_session": lambda self, account_id, now_ts: {
                "status": "pending",
                "connect_url": "https://wx.example.com/entry?bind_token=ctx_123",
                "expires_at": 1775472600,
            }
        },
    )()

    response = client.post(
        "/user/wechat-bind/session",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "pending"
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:4040"
```

- [ ] **Step 2: Run the bind-session tests to verify they fail**

Run: `pytest tests/unit/dao/test_wechat_bind_session_dao.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'dao.wechat_bind_session_dao'`, missing `find_latest_session_for_account`, missing `find_active_identity_for_account`, and missing `/user/wechat-bind/session`

- [ ] **Step 3: Write the minimal bind-session persistence and user APIs**

```python
# dao/wechat_bind_session_dao.py
from pymongo import MongoClient


class WechatBindSessionDAO:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db.get_collection("wechat_bind_sessions")

    def create_indexes(self) -> None:
        self.collection.create_index([("session_id", 1)], unique=True)
        self.collection.create_index([("bind_token", 1)], unique=True)
        self.collection.create_index([("account_id", 1), ("status", 1), ("expires_at", 1)])

    def find_active_session_for_account(self, account_id: str, now_ts: int):
        return self.collection.find_one(
            {
                "account_id": account_id,
                "status": "pending",
                "expires_at": {"$gt": now_ts},
            },
            sort=[("created_at", -1)],
        )

    def find_latest_session_for_account(self, account_id: str):
        return self.collection.find_one(
            {"account_id": account_id},
            sort=[("created_at", -1)],
        )

    def find_active_session_by_bind_token(self, bind_token: str, now_ts: int):
        return self.collection.find_one(
            {
                "bind_token": bind_token,
                "status": "pending",
                "expires_at": {"$gt": now_ts},
            }
        )

    def create_session(self, doc: dict):
        self.collection.insert_one(doc)
        return doc

    def mark_bound(self, session_id: str, masked_identity: str, external_end_user_id: str, now_ts: int):
        self.collection.update_one(
            {"session_id": session_id, "status": "pending"},
            {
                "$set": {
                    "status": "bound",
                    "masked_identity": masked_identity,
                    "matched_external_end_user_id": external_end_user_id,
                    "bound_at": now_ts,
                }
            },
        )
```

```python
# dao/external_identity_dao.py
def find_active_identity_for_account(self, account_id: str):
    return self.collection.find_one(
        {
            "account_id": account_id,
            "source": "clawscale",
            "status": "active",
        }
    )
```

```python
# connector/clawscale_bridge/wechat_bind_session_service.py
import secrets


class WechatBindSessionService:
    def __init__(self, bind_session_dao, external_identity_dao, connect_url_template: str, ttl_seconds: int):
        self.bind_session_dao = bind_session_dao
        self.external_identity_dao = external_identity_dao
        self.connect_url_template = connect_url_template
        self.ttl_seconds = ttl_seconds

    def _mask_identity(self, external_end_user_id: str) -> str:
        if len(external_end_user_id) <= 4:
            return "*" * len(external_end_user_id)
        return f"{external_end_user_id[:4]}***{external_end_user_id[-4:]}"

    def _serialize_state(self, session: dict) -> dict:
        return {
            "status": session["status"],
            "connect_url": session.get("connect_url"),
            "expires_at": session.get("expires_at"),
            "masked_identity": session.get("masked_identity"),
        }

    def create_or_reuse_session(self, account_id: str, now_ts: int):
        active_identity = self.external_identity_dao.find_active_identity_for_account(account_id)
        if active_identity:
            return {
                "status": "bound",
                "masked_identity": self._mask_identity(active_identity["external_end_user_id"]),
            }

        session = self.bind_session_dao.find_active_session_for_account(account_id, now_ts)
        if session:
            return self._serialize_state(session)

        bind_token = f"ctx_{secrets.token_urlsafe(18)}"
        session = {
            "session_id": f"bs_{secrets.token_hex(8)}",
            "account_id": account_id,
            "bind_token": bind_token,
            "status": "pending",
            "connect_url": self.connect_url_template.replace("{bind_token}", bind_token),
            "created_at": now_ts,
            "expires_at": now_ts + self.ttl_seconds,
        }
        created = self.bind_session_dao.create_session(session)
        return self._serialize_state(created)

    def get_status(self, account_id: str, now_ts: int):
        active_identity = self.external_identity_dao.find_active_identity_for_account(account_id)
        if active_identity:
            return {
                "status": "bound",
                "masked_identity": self._mask_identity(active_identity["external_end_user_id"]),
            }
        session = self.bind_session_dao.find_latest_session_for_account(account_id)
        if not session:
            return {"status": "unbound"}
        if session["expires_at"] <= now_ts:
            return {"status": "expired"}
        return self._serialize_state(session)
```

```python
# conf/config.json
"clawscale_bridge": {
  "host": "0.0.0.0",
  "port": 8090,
  "api_key": "${COKE_BRIDGE_API_KEY}",
  "bind_base_url": "${COKE_BIND_BASE_URL}",
  "reply_timeout_seconds": 25,
  "poll_interval_seconds": 1,
  "outbound_api_url": "${CLAWSCALE_OUTBOUND_API_URL}",
  "outbound_api_key": "${CLAWSCALE_OUTBOUND_API_KEY}",
  "user_auth_secret": "${COKE_USER_AUTH_SECRET}",
  "user_auth_token_ttl_seconds": 604800,
  "wechat_public_connect_url_template": "${COKE_WECHAT_PUBLIC_CONNECT_URL_TEMPLATE}",
  "wechat_bind_session_ttl_seconds": 600,
  "web_allowed_origin": "${COKE_WEB_ALLOWED_ORIGIN}"
}
```

```python
# connector/clawscale_bridge/app.py
import time

from connector.clawscale_bridge.user_auth import UserAuthService
from connector.clawscale_bridge.wechat_bind_session_service import WechatBindSessionService
from dao.wechat_bind_session_dao import WechatBindSessionDAO


def _build_user_bind_service():
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]
    bridge_conf = CONF["clawscale_bridge"]
    return WechatBindSessionService(
        bind_session_dao=WechatBindSessionDAO(mongo_uri=mongo_uri, db_name=db_name),
        external_identity_dao=ExternalIdentityDAO(mongo_uri=mongo_uri, db_name=db_name),
        connect_url_template=bridge_conf["wechat_public_connect_url_template"],
        ttl_seconds=bridge_conf["wechat_bind_session_ttl_seconds"],
    )


def _build_user_auth_service():
    bridge_conf = CONF["clawscale_bridge"]
    return UserAuthService(
        user_dao=UserDAO(mongo_uri=_mongo_uri(), db_name=CONF["mongodb"]["mongodb_name"]),
        secret_key=bridge_conf["user_auth_secret"],
        token_ttl_seconds=bridge_conf["user_auth_token_ttl_seconds"],
    )


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = app.config["COKE_WEB_ALLOWED_ORIGIN"]
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.post("/user/register")
def user_register():
    payload = request.get_json(force=True)
    service = app.config["USER_AUTH_SERVICE"]
    try:
        result = service.register(
            display_name=payload["display_name"],
            email=payload["email"],
            password=payload["password"],
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, "data": result}), 201


@app.post("/user/login")
def user_login():
    payload = request.get_json(force=True)
    service = app.config["USER_AUTH_SERVICE"]
    ok, result = service.login(payload["email"], payload["password"])
    if not ok:
        return jsonify({"ok": False, "error": result}), 401
    return jsonify({"ok": True, "data": result})


def require_user_auth():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header.split(" ", 1)[1]
    return app.config["USER_AUTH_SERVICE"].verify_token(token)


@app.post("/user/wechat-bind/session")
def create_wechat_bind_session():
    user = require_user_auth()
    if not user:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    result = app.config["USER_BIND_SERVICE"].create_or_reuse_session(
        account_id=str(user["_id"]),
        now_ts=int(time.time()),
    )
    return jsonify({"ok": True, "data": result})


@app.get("/user/wechat-bind/status")
def get_wechat_bind_status():
    user = require_user_auth()
    if not user:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    result = app.config["USER_BIND_SERVICE"].get_status(
        account_id=str(user["_id"]),
        now_ts=int(time.time()),
    )
    return jsonify({"ok": True, "data": result})


if testing:
    app.config["COKE_WEB_ALLOWED_ORIGIN"] = "http://127.0.0.1:4040"
else:
    app.config["COKE_WEB_ALLOWED_ORIGIN"] = CONF["clawscale_bridge"]["web_allowed_origin"]
    app.config["USER_AUTH_SERVICE"] = _build_user_auth_service()
    app.config["USER_BIND_SERVICE"] = _build_user_bind_service()
```

- [ ] **Step 4: Run the bind-session tests to verify they pass**

Run: `pytest tests/unit/dao/test_wechat_bind_session_dao.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: PASS with `7 passed`

- [ ] **Step 5: Commit the bind-session APIs**

```bash
git add dao/wechat_bind_session_dao.py dao/external_identity_dao.py connector/clawscale_bridge/wechat_bind_session_service.py connector/clawscale_bridge/app.py conf/config.json tests/unit/dao/test_wechat_bind_session_dao.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py
git commit -m "feat(bind): add coke web bind session apis"
```

## Task 3: Auto-Bind The First WeChat Message In Bridge Ingress

**Files:**
- Modify: `dao/external_identity_dao.py`
- Modify: `connector/clawscale_bridge/wechat_bind_session_service.py`
- Modify: `connector/clawscale_bridge/identity_service.py`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py`
- Create: `tests/unit/connector/clawscale_bridge/test_identity_service.py`

- [ ] **Step 1: Write the failing auto-bind tests**

```python
# tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py
from unittest.mock import MagicMock


def test_consume_matching_session_creates_external_identity_and_marks_session_bound():
    from connector.clawscale_bridge.wechat_bind_session_service import WechatBindSessionService

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_token.return_value = {
        "session_id": "bs_1",
        "account_id": "user_1",
        "bind_token": "ctx_bind_123",
        "status": "pending",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity_for_account.return_value = None
    external_identity_dao.find_active_identity.return_value = {
        "account_id": "user_1",
        "external_end_user_id": "wxid_123",
        "status": "active",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        connect_url_template="https://wx.example.com/entry?bind_token={bind_token}",
        ttl_seconds=600,
    )

    identity = service.consume_matching_session(
        bind_token="ctx_bind_123",
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        now_ts=1775472000,
    )

    assert identity["account_id"] == "user_1"
    external_identity_dao.activate_identity.assert_called_once()
    bind_session_dao.mark_bound.assert_called_once()
```

- [ ] **Step 1A: Add the failing bridge ingress unit tests**

```python
# tests/unit/connector/clawscale_bridge/test_identity_service.py
from unittest.mock import MagicMock


def test_handle_inbound_consumes_matching_bind_session_before_reply():
    from connector.clawscale_bridge.identity_service import IdentityService

    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    binding_ticket_dao = MagicMock()
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "绑定成功后的第一条回复"
    bind_session_service = MagicMock()
    bind_session_service.consume_matching_session.return_value = {"account_id": "user_1"}

    service = IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "contextToken": "ctx_bind_123",
            },
        }
    )

    assert result == {"status": "ok", "reply": "绑定成功后的第一条回复"}
    bind_session_service.consume_matching_session.assert_called_once()


def test_handle_inbound_without_matching_bind_session_returns_bind_required():
    from connector.clawscale_bridge.identity_service import IdentityService

    service = IdentityService(
        external_identity_dao=MagicMock(find_active_identity=MagicMock(return_value=None)),
        binding_ticket_dao=MagicMock(),
        bind_session_service=MagicMock(consume_matching_session=MagicMock(return_value=None)),
        message_gateway=MagicMock(),
        reply_waiter=MagicMock(),
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )
    service.issue_or_reuse_binding_ticket = MagicMock(return_value={"bind_url": "https://coke.local/bind/bt_1"})

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "你好"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "contextToken": "ctx_missing",
            },
        }
    )

    assert result["status"] == "bind_required"
    assert result["bind_url"] == "https://coke.local/bind/bt_1"
```

- [ ] **Step 2: Run the auto-bind tests to verify they fail**

Run: `pytest tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_identity_service.py -v`

Expected: FAIL because `consume_matching_session` does not exist and `IdentityService.__init__()` does not accept `bind_session_service`

- [ ] **Step 3: Write the minimal auto-bind implementation**

```python
# dao/external_identity_dao.py
def activate_identity(
    self,
    source: str,
    tenant_id: str,
    channel_id: str,
    platform: str,
    external_end_user_id: str,
    account_id: str,
    now_ts: int,
):
    self.collection.update_one(
        {
            "source": source,
            "tenant_id": tenant_id,
            "channel_id": channel_id,
            "platform": platform,
            "external_end_user_id": external_end_user_id,
        },
        {
            "$set": {
                "account_id": account_id,
                "status": "active",
                "updated_at": now_ts,
                "last_seen_at": now_ts,
                "is_primary_push_target": True,
            },
            "$setOnInsert": {"created_at": now_ts},
        },
        upsert=True,
    )
    return self.find_active_identity(
        source=source,
        tenant_id=tenant_id,
        channel_id=channel_id,
        platform=platform,
        external_end_user_id=external_end_user_id,
    )
```

```python
# connector/clawscale_bridge/wechat_bind_session_service.py
def consume_matching_session(
    self,
    bind_token: str,
    source: str,
    tenant_id: str,
    channel_id: str,
    platform: str,
    external_end_user_id: str,
    now_ts: int,
):
    if not bind_token:
        return None
    session = self.bind_session_dao.find_active_session_by_bind_token(bind_token, now_ts)
    if not session:
        return None
    active_identity = self.external_identity_dao.find_active_identity_for_account(session["account_id"])
    if active_identity:
        return active_identity

    identity = self.external_identity_dao.activate_identity(
        source=source,
        tenant_id=tenant_id,
        channel_id=channel_id,
        platform=platform,
        external_end_user_id=external_end_user_id,
        account_id=session["account_id"],
        now_ts=now_ts,
    )
    self.bind_session_dao.mark_bound(
        session_id=session["session_id"],
        masked_identity=self._mask_identity(external_end_user_id),
        external_end_user_id=external_end_user_id,
        now_ts=now_ts,
    )
    return identity
```

```python
# connector/clawscale_bridge/identity_service.py
class IdentityService:
    def __init__(
        self,
        external_identity_dao,
        binding_ticket_dao,
        bind_session_service,
        message_gateway,
        reply_waiter,
        bind_base_url: str,
        target_character_id: str,
    ):
        self.external_identity_dao = external_identity_dao
        self.binding_ticket_dao = binding_ticket_dao
        self.bind_session_service = bind_session_service
        self.message_gateway = message_gateway
        self.reply_waiter = reply_waiter
        self.bind_base_url = bind_base_url
        self.target_character_id = target_character_id


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
        bind_token = metadata.get("contextToken")
        if bind_token:
            external_identity = self.bind_session_service.consume_matching_session(
                bind_token=bind_token,
                source="clawscale",
                tenant_id=metadata["tenantId"],
                channel_id=metadata["channelId"],
                platform=metadata["platform"],
                external_end_user_id=metadata["externalId"],
                now_ts=int(time.time()),
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

- [ ] **Step 3A: Wire the bind-session service into the default bridge app**

```python
# connector/clawscale_bridge/app.py
def _build_default_bridge_gateway():
    bridge_conf = CONF["clawscale_bridge"]
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]

    user_dao = UserDAO(mongo_uri=mongo_uri, db_name=db_name)
    external_identity_dao = ExternalIdentityDAO(mongo_uri=mongo_uri, db_name=db_name)
    binding_ticket_dao = BindingTicketDAO(mongo_uri=mongo_uri, db_name=db_name)
    bind_session_dao = WechatBindSessionDAO(mongo_uri=mongo_uri, db_name=db_name)
    bind_session_service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        connect_url_template=bridge_conf["wechat_public_connect_url_template"],
        ttl_seconds=bridge_conf["wechat_bind_session_ttl_seconds"],
    )
    mongo = MongoDBBase(connection_string=mongo_uri, db_name=db_name)
    message_gateway = CokeMessageGateway(mongo=mongo, user_dao=user_dao)
    reply_waiter = ReplyWaiter(
        mongo=mongo,
        poll_interval_seconds=bridge_conf["poll_interval_seconds"],
        timeout_seconds=bridge_conf["reply_timeout_seconds"],
    )

    return IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url=bridge_conf["bind_base_url"],
        target_character_id=_resolve_target_character_id(user_dao),
    )
```

- [ ] **Step 4: Run the auto-bind tests to verify they pass**

Run: `pytest tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_identity_service.py -v`

Expected: PASS with the new auto-bind path and no regression in the existing `bind_required` path

- [ ] **Step 5: Commit the auto-bind ingress flow**

```bash
git add dao/external_identity_dao.py connector/clawscale_bridge/wechat_bind_session_service.py connector/clawscale_bridge/identity_service.py connector/clawscale_bridge/app.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_identity_service.py
git commit -m "feat(bind): auto-bind first wechat message from web session"
```

## Task 4: Add Coke User Pages Under `/coke/*`

**Files:**
- Modify: `gateway/packages/web/package.json`
- Create: `gateway/packages/web/lib/coke-user-api.ts`
- Create: `gateway/packages/web/lib/coke-user-auth.ts`
- Create: `gateway/packages/web/lib/coke-user-auth.test.ts`
- Create: `gateway/packages/web/app/(coke-user)/coke/layout.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`

- [ ] **Step 1: Write the failing Coke user auth storage test**

```ts
// gateway/packages/web/lib/coke-user-auth.test.ts
import { beforeEach, describe, expect, it } from 'vitest';
import { clearCokeUserAuth, getCokeUser, getCokeUserToken, storeCokeUserAuth } from './coke-user-auth';

describe('coke user auth storage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('stores coke user auth under separate keys', () => {
    storeCokeUserAuth({
      token: 'user-token',
      user: {
        id: 'user_1',
        email: 'alice@example.com',
        display_name: 'Alice',
      },
    });

    expect(getCokeUserToken()).toBe('user-token');
    expect(getCokeUser()?.email).toBe('alice@example.com');

    clearCokeUserAuth();
    expect(getCokeUserToken()).toBeNull();
    expect(getCokeUser()).toBeNull();
  });
});
```

- [ ] **Step 2: Run the web auth test to verify it fails**

Run: `pnpm -C gateway --filter @clawscale/web test`

Expected: FAIL because `test` script does not exist and `coke-user-auth.ts` is missing

- [ ] **Step 3: Write the minimal Coke user web implementation**

```json
// gateway/packages/web/package.json
{
  "scripts": {
    "dev": "next dev --port 4040",
    "build": "next build",
    "start": "next start --port 4040",
    "lint": "eslint",
    "test": "vitest run --environment jsdom"
  },
  "dependencies": {
    "@clawscale/shared": "workspace:*",
    "next": "16.2.1",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "lucide-react": "^1.7.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^3.5.0",
    "qrcode": "^1.5.4"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/node": "^25",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^10",
    "eslint-config-next": "16.2.1",
    "tailwindcss": "^4",
    "typescript": "^6",
    "vitest": "^3.1.3",
    "jsdom": "^26.1.0"
  }
}
```

```ts
// gateway/packages/web/lib/coke-user-auth.ts
const TOKEN_KEY = 'coke_user_token';
const USER_KEY = 'coke_user_profile';

export interface CokeUser {
  id: string;
  email: string;
  display_name: string;
}

export interface CokeAuthResult {
  token: string;
  user: CokeUser;
}

export function storeCokeUserAuth(result: CokeAuthResult): void {
  localStorage.setItem(TOKEN_KEY, result.token);
  localStorage.setItem(USER_KEY, JSON.stringify(result.user));
}

export function clearCokeUserAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getCokeUserToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getCokeUser(): CokeUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as CokeUser;
  } catch {
    return null;
  }
}
```

```ts
// gateway/packages/web/lib/coke-user-api.ts
import { getCokeUserToken } from './coke-user-auth';

const BASE = process.env['NEXT_PUBLIC_COKE_API_URL'] ?? 'http://127.0.0.1:8090';

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = getCokeUserToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
  });

  return (await res.json()) as T;
}

export const cokeUserApi = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
};
```

```tsx
// gateway/packages/web/app/(coke-user)/coke/layout.tsx
import type { ReactNode } from 'react';
import Link from 'next/link';

export default function CokeUserLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-white text-slate-950">
      <header className="border-b border-slate-200">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <Link href="/coke/bind-wechat" className="text-lg font-semibold">Coke</Link>
          <nav className="text-sm text-slate-500">Bind your personal WeChat</nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-12">{children}</main>
    </div>
  );
}
```

```tsx
// gateway/packages/web/app/(coke-user)/coke/login/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { cokeUserApi } from '@/lib/coke-user-api';
import { storeCokeUserAuth } from '@/lib/coke-user-auth';

export default function CokeLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    const res = await cokeUserApi.post<any>('/user/login', { email, password });
    if (!res.ok) {
      setError(res.error);
      return;
    }
    storeCokeUserAuth(res.data);
    router.push('/coke/bind-wechat');
  }

  return (
    <form onSubmit={handleSubmit}>
      <input value={email} onChange={(e) => setEmail(e.target.value)} />
      <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <p>{error}</p>}
      <button type="submit">Sign in to Coke</button>
    </form>
  );
}
```

```tsx
// gateway/packages/web/app/(coke-user)/coke/register/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { cokeUserApi } from '@/lib/coke-user-api';
import { storeCokeUserAuth } from '@/lib/coke-user-auth';

export default function CokeRegisterPage() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const res = await cokeUserApi.post<any>('/user/register', {
      display_name: displayName,
      email,
      password,
    });
    if (!res.ok) return;
    storeCokeUserAuth(res.data);
    router.push('/coke/bind-wechat');
  }

  return (
    <form onSubmit={handleSubmit}>
      <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
      <input value={email} onChange={(e) => setEmail(e.target.value)} />
      <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button type="submit">Create Coke account</button>
    </form>
  );
}
```

```tsx
// gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import QRCode from 'qrcode';
import { cokeUserApi } from '@/lib/coke-user-api';
import { getCokeUserToken } from '@/lib/coke-user-auth';

type BindState =
  | { status: 'unbound' }
  | { status: 'pending'; connect_url: string; expires_at: number }
  | { status: 'bound'; masked_identity: string }
  | { status: 'expired' }
  | { status: 'failed' };

export default function BindWechatPage() {
  const router = useRouter();
  const [bindState, setBindState] = useState<BindState>({ status: 'unbound' });
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [isDesktop, setIsDesktop] = useState(true);

  useEffect(() => {
    if (!getCokeUserToken()) {
      router.replace('/coke/login');
      return;
    }
    void cokeUserApi.post<any>('/user/wechat-bind/session').then((res) => {
      if (!res.ok) {
        setBindState({ status: 'failed' });
        return;
      }
      setBindState(res.data);
    });
  }, [router]);

  useEffect(() => {
    setIsDesktop(window.innerWidth >= 1024);
  }, []);

  useEffect(() => {
    if (bindState.status !== 'pending') return;
    void QRCode.toDataURL(bindState.connect_url).then(setQrDataUrl);
    const timer = setInterval(() => {
      void cokeUserApi.get<any>('/user/wechat-bind/status').then((res) => {
        if (res.ok) setBindState(res.data);
      });
    }, 3000);
    return () => clearInterval(timer);
  }, [bindState]);

  if (bindState.status === 'bound') {
    return <p>WeChat bound: {bindState.masked_identity}</p>;
  }

  if (bindState.status === 'expired') {
    return <button onClick={() => window.location.reload()}>Generate a new QR code</button>;
  }

  if (!isDesktop) {
    return <p>Please open this page on desktop for the v1 WeChat bind flow.</p>;
  }

  return (
    <div>
      <p>Use WeChat on your phone to scan this code, then send any message to Coke.</p>
      {qrDataUrl && <img src={qrDataUrl} alt="Bind Coke WeChat" />}
    </div>
  );
}
```

- [ ] **Step 4: Run the web auth test and web build**

Run: `pnpm -C gateway --filter @clawscale/web test && pnpm -C gateway --filter @clawscale/web build`

Expected: PASS with `1 passed` from `coke-user-auth.test.ts` and a successful Next.js production build

- [ ] **Step 5: Commit the Coke user pages**

```bash
git -C gateway add packages/web/package.json packages/web/lib/coke-user-api.ts packages/web/lib/coke-user-auth.ts packages/web/lib/coke-user-auth.test.ts packages/web/app/'(coke-user)'/coke/layout.tsx packages/web/app/'(coke-user)'/coke/login/page.tsx packages/web/app/'(coke-user)'/coke/register/page.tsx packages/web/app/'(coke-user)'/coke/bind-wechat/page.tsx
git -C gateway commit -m "feat(web): add coke user wechat bind pages"
```

## Task 5: Document And Verify The Full Desktop Bind Flow

**Files:**
- Modify: `docs/clawscale_bridge.md`

- [ ] **Step 1: Write the failing documentation expectation**

```text
The docs must explain:
1. the new Coke user routes (`/coke/login`, `/coke/register`, `/coke/bind-wechat`)
2. the new env vars (`COKE_USER_AUTH_SECRET`, `COKE_WECHAT_PUBLIC_CONNECT_URL_TEMPLATE`)
3. the desktop-only manual smoke test
```

- [ ] **Step 2: Run the current verification suite to capture the pre-doc baseline**

Run: `pytest tests/unit/connector/clawscale_bridge/ tests/unit/dao/test_user_dao_web_auth.py tests/unit/dao/test_wechat_bind_session_dao.py -v`

Expected: PASS on all new backend tests after Tasks 1-3

- [ ] **Step 3: Write the user-bind documentation**

```md
## Coke User Frontend

- User login: `http://<web-host>:4040/coke/login`
- User registration: `http://<web-host>:4040/coke/register`
- User bind page: `http://<web-host>:4040/coke/bind-wechat`

## New environment

- `COKE_USER_AUTH_SECRET`
- `COKE_WECHAT_PUBLIC_CONNECT_URL_TEMPLATE`
- `NEXT_PUBLIC_COKE_API_URL`

`COKE_WECHAT_PUBLIC_CONNECT_URL_TEMPLATE` must contain `{bind_token}` and must round-trip that token into inbound WeChat `contextToken`.

Example:

```text
https://wx.example.com/coke-entry?bind_token={bind_token}
```

## Manual smoke

1. Start ClawScale WeChat channel and confirm the official account is already connected.
2. Start the Coke bridge: `python -m connector.clawscale_bridge.app`
3. Start the web app:
   `NEXT_PUBLIC_COKE_API_URL=http://127.0.0.1:8090 pnpm -C gateway --filter @clawscale/web dev`
4. Open `/coke/register`, create a test account, and land on `/coke/bind-wechat`.
5. Confirm the QR renders.
6. Scan with an unbound personal WeChat account.
7. Send any message in WeChat.
8. Confirm `/coke/bind-wechat` refreshes to `bound`.
9. Confirm `external_identities` contains one active mapping for that `coke_user_id`.
```
```

- [ ] **Step 4: Run the final verification commands**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/ tests/unit/dao/test_user_dao_web_auth.py tests/unit/dao/test_wechat_bind_session_dao.py -v
pnpm -C gateway --filter @clawscale/web test
pnpm -C gateway --filter @clawscale/web build
```

Expected:

```text
All Python tests PASS
Web Vitest PASS
Next.js build PASS
```

- [ ] **Step 5: Commit the docs and verification pass**

```bash
git add docs/clawscale_bridge.md
git commit -m "docs(bind): document coke user wechat bind flow"
```

## Self-Review

### Spec coverage

- User-facing Coke auth is covered by Task 1 and Task 4.
- Desktop-only bind page with QR flow is covered by Task 2 and Task 4.
- Automatic bind on first WeChat message is covered by Task 3.
- Bound status display is covered by Task 2 and Task 4.
- Existing admin auth remaining untouched is covered by the `/coke/*` route split in Task 4.

### Placeholder scan

- No `TODO`, `TBD`, or deferred implementation markers remain.
- Every code step includes concrete file paths, concrete snippets, and concrete commands.

### Type consistency

- Coke web-user auth uses `display_name`, `email`, `password_hash`, and `token` consistently across Python and Next.js.
- Bind session states stay limited to `unbound | pending | bound | expired | failed`.
- The WeChat bind correlation token is consistently named `bind_token` in persistence and `contextToken` at inbound message time.
