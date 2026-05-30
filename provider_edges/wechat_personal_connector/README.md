# WeChat Personal Connector

Standalone provider-edge connector for Coke's `wechat_personal` provider adapter.

The clean Coke stack sends text to:

```text
POST /send
Authorization: Bearer <WECHAT_CONNECTOR_API_KEY>
JSON: {"to": "<wxid>", "text": "<text>"}
```

The connector polls Tencent iLink updates and posts inbound text to:

```text
POST <WECHAT_CONNECTOR_WEBHOOK_URL>
JSON: {"message_id": "<context_token>", "wxid": "<from_user_id>", "text": "<text>", "pairing_code": "<optional pairing_...>"}
```

Human login is required. Start login with:

```bash
curl -sS -X POST http://127.0.0.1:8095/login/start \
  -H "Authorization: Bearer $WECHAT_CONNECTOR_API_KEY"
curl -sS http://127.0.0.1:8095/login/status
```

Scan `qrcode_image_data_url` with the intended personal WeChat account. The
connector stores the resulting iLink bot token in its local Docker volume.
