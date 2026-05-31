# WeChat Personal Connector

Standalone provider-edge connector for Coke's `wechat_personal` provider adapter.

The clean Coke stack sends text to:

```text
POST /send
Authorization: Bearer <WECHAT_CONNECTOR_API_KEY>
JSON: {"account_id": "<coke_account_id>", "to": "<wxid>", "context_token": "<inbound_context_token>", "text": "<text>"}
```

The connector polls Tencent iLink updates and posts inbound text to:

```text
POST <WECHAT_CONNECTOR_WEBHOOK_URL>
X-Coke-Webhook-Secret: <COKE_WEBHOOK_INBOUND_SECRET>  # when configured
JSON: {"account_id": "<coke_account_id>", "session_id": "<connector_session_id>", "message_id": "<context_token>", "wxid": "<from_user_id>", "text": "<text>", "context_token": "<context_token>"}
```

Set `COKE_WEBHOOK_INBOUND_SECRET` to the same value on `coke-api` and this
connector. When Coke has the secret configured, inbound webhook payloads without
that header are rejected before JSON normalization.

Human login is required per Coke account. Start a per-account iLink bot login
with:

```bash
curl -sS -X POST http://127.0.0.1:8095/login/start \
  -H "Authorization: Bearer $WECHAT_CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"acct_..."}'
curl -sS \
  -H "Authorization: Bearer $WECHAT_CONNECTOR_API_KEY" \
  'http://127.0.0.1:8095/login/status?account_id=acct_...&session_id=...'
```

Scan `qrcode_image_data_url` with the intended personal WeChat account. The
connector stores each account's iLink bot token, base URL, and getupdates cursor
in its local Docker volume. One iLink bot session maps to one Coke account and
one WeChat account; Coke users never share a personal-WeChat bot token.
