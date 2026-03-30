# OpenClaw Gateway Integration Design

> Date: 2026-03-26
> Status: Approved
> Branch: `feature/gateway-integration`

## Overview

Replace Coke's legacy channel transport with a clean HTTP API that integrates with OpenClaw as the channel transport. Coke becomes a channel-agnostic agent backend: no platform SDKs and no direct platform delivery code. OpenClaw handles all platform connections (WeChat, Telegram, Discord, WhatsApp, etc.) and forwards messages to Coke via HTTP. Coke delivers replies back via OpenClaw's WebSocket `send` method while keeping enough routing metadata internally to preserve current conversation, history, and relationship semantics.

## Architecture

```
                        +---------------------------+
                        |         OpenClaw           |
                        |    (channel transport)     |
                        |                            |
  User -- WeChat ------>|   Channel Adapters         |
          Telegram ---->|   Hook Transform           |
          Discord ----->|   (coke-forward.ts)        |
                        +------+------------^--------+
                               |            |
                    POST /v1/chat    WebSocket send()
                    (inbound)        (outbound delivery)
                               |            |
                        +------v------------+--------+
                        |           Coke             |
                        |     (agent backend)        |
                        |                            |
                        |   FastAPI /v1/chat         |
                        |        |                   |
                        |   Redis Stream             |
                        |        |                   |
                        |   Worker Pool              |
                        |        |                   |
                        |   Three-Phase Workflow     |
                        |   (Prepare->Chat->Post)    |
                        |        |                   |
                        |   OpenClawClient.send()    |
                        +----------------------------+
```

**Key principles:**
- Coke is a channel-agnostic HTTP API service — no platform SDKs, no direct platform code
- OpenClaw owns all platform connections, Coke owns all AI logic
- Inbound: HTTP POST from OpenClaw to Coke
- Outbound: WebSocket RPC from Coke to OpenClaw
- Coke processes async — accepts message, returns 202, delivers replies via callback
- `account_id` is an end-to-end routing key, not just an ingest-time hint
- Outbound delivery is push-based, but outbound events remain durably journaled for history, retry analysis, and audit

## Inbound API: POST /v1/chat

FastAPI application replaces the Flask `ecloud_input.py`.

### Endpoint

```
POST /v1/chat
Authorization: Bearer <shared_secret>
Content-Type: application/json
```

### Request Body

```json
{
  "message_id": "gw-msg-uuid-001",
  "channel": "wechat",
  "account_id": "bot-a",
  "sender": {
    "platform_id": "wx_user_abc123",
    "display_name": "Alice"
  },
  "chat_type": "private",
  "message_type": "text",
  "content": "Hello",
  "media_url": null,
  "reply_to": {
    "id": "gw-msg-uuid-000",
    "content": "Previous message text",
    "author_name": "Alice"
  },
  "group_id": null,
  "timestamp": 1711411200,
  "metadata": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message_id` | string | yes | Gateway-assigned unique message ID |
| `channel` | string | yes | Channel identifier: `wechat`, `telegram`, `discord`, `whatsapp` |
| `account_id` | string | yes | Which bot account received this message (multi-tenant key) |
| `sender.platform_id` | string | yes | User's platform-specific ID |
| `sender.display_name` | string | no | User display name (for auto-creation) |
| `chat_type` | enum | yes | `private` or `group` |
| `message_type` | enum | yes | `text`, `image`, `voice`, `video`, `file`, `reference` |
| `content` | string | yes | Text content, or caption for media |
| `media_url` | string | no | URL to media file (image/voice/video) |
| `reply_to.id` | string | no | Original platform/gateway message ID being replied to |
| `reply_to.content` | string | no | Best-effort quoted content |
| `reply_to.author_name` | string | no | Best-effort quoted author name |
| `group_id` | string | no | Group/room ID (when `chat_type=group`) |
| `timestamp` | int | yes | Unix timestamp |
| `metadata` | object | no | Channel-specific extra data |

### Response

```json
{
  "status": "accepted",
  "request_message_id": "gw-msg-uuid-001",
  "input_message_id": "60f1a2b3c4d5e6f7a8b9c0d1"
}
```

HTTP 202 Accepted. Processing is async.

### Processing Steps

1. Validate auth (Bearer token)
2. Resolve `account_id` to character and outbound sender routing (from config mapping)
3. Resolve or create user from `sender.platform_id` + `channel`
4. Validate that the resolved character has routing identity for `channel`
5. Deduplicate by `(channel, account_id, message_id)`
6. Process media if needed (download `media_url` -> image2text / voice2text)
7. Write to MongoDB `inputmessages` with `to_user`, `platform`, `chatroom_name`, `metadata.gateway.account_id`, and `metadata.gateway.message_id`
8. Publish to Redis stream `coke:input`
9. Return 202 with both gateway and internal message IDs

### Ingest Contract

- `message_id` is the external gateway ID and must be stored separately from Mongo `_id`
- Deduplication key is `(channel, account_id, message_id)`
- `account_id` must be copied into stored message metadata so workers and delivery code can route replies through the same OpenClaw account
- `reply_to` should be normalized into the same `metadata.reference` shape already used by existing reference-message handling
- `group_id` maps to internal `chatroom_name`

### User Identity and Isolation

User identity is `channel` + `sender.platform_id`. Same person on different platforms creates separate user records.

User lookup:
```python
user = db.users.find_one({
    f"platforms.{channel}.id": sender.platform_id
})
```

Auto-create structure:
```json
{
  "name": "Alice",
  "platforms": {
    "wechat": { "id": "wx_abc", "display_name": "Alice" }
  }
}
```

Conversation isolation = user + character. Each user-character pair has its own conversation, memory, and relationship.

```
wx_user_A + bot-a (coke)     -> isolated conversation
wx_user_A + bot-b (luna)     -> isolated conversation
tg_user_B + bot-a (coke)     -> isolated conversation
```

Group chats use `group_id` for additional isolation.

### Conversation Key

Conversation routing must be explicit and stable:

- Private chat key: `(channel, account_id, sender.platform_id)`
- Group chat key: `(channel, account_id, group_id, sender.platform_id)` for per-user relationship state, with conversation lookup anchored by `(channel, group_id, character routing identity)`
- Pending-message batching must not merge messages from different groups just because `from_user`, `to_user`, and `platform` match

### Character Routing Identity

Even though Coke no longer talks to platforms directly, current conversation creation still depends on `character.platforms.<channel>.id` and `.nickname`. Therefore the migration keeps a synthetic per-channel routing identity for each character until the conversation schema is refactored.

That means `account_mapping` must resolve to:

- the Coke character alias / user record
- the OpenClaw `account_id`
- a valid internal routing identity for `platforms.<channel>`

This preserves existing `MessageAcquirer` and `ConversationDAO` assumptions while removing legacy connector code.

## Outbound Delivery: OpenClaw WebSocket send()

Coke maintains a persistent WebSocket connection to OpenClaw's gateway and uses the `send` method for direct message delivery. This bypasses OpenClaw's Pi agent entirely.

### Send Method

```json
{
  "method": "send",
  "params": {
    "accountId": "bot-a",
    "to": "wx_user_abc123",
    "message": "Hi Alice!",
    "channel": "wechat",
    "idempotencyKey": "coke-reply-uuid-001"
  }
}
```

### Media Delivery

Voice:
```json
{
  "method": "send",
  "params": {
    "accountId": "bot-a",
    "to": "wx_user_abc123",
    "channel": "wechat",
    "mediaUrl": "https://oss.../voice.mp3",
    "idempotencyKey": "coke-reply-uuid-002"
  }
}
```

Image:
```json
{
  "method": "send",
  "params": {
    "accountId": "bot-a",
    "to": "wx_user_abc123",
    "channel": "wechat",
    "mediaUrl": "https://oss.../photo.jpg",
    "idempotencyKey": "coke-reply-uuid-003"
  }
}
```

Group delivery:
```json
{
  "method": "send",
  "params": {
    "accountId": "bot-a",
    "channel": "wechat",
    "groupId": "room-123",
    "message": "Hi everyone!",
    "idempotencyKey": "coke-reply-uuid-004"
  }
}
```

### Delivery Flow

When `agent_handler` produces a reply segment:
1. Build a delivery command from conversation context plus `metadata.gateway.account_id`
2. Write a durable outbound journal record before or alongside send for audit / retry analysis
3. Call `OpenClawClient.send()` with the reply content, channel, account, and recipient
4. Mark the journal entry handled or failed based on OpenClaw response
5. Wait for typing delay (`asyncio.sleep()`) before next segment
6. Repeat for each segment (text, voice, image)

No polling-based transport queue is involved. Delivery is direct and immediate, but outbound attempts remain persisted as journal records. Existing `outputmessages` may be retained as that journal during migration; they are no longer the transport mechanism.

## Worker Pipeline

```
POST /v1/chat
  -> MongoDB inputmessages + Redis stream publish
  -> Worker picks up from Redis stream (coke:input / coke-workers)
  -> MessageAcquirer: validate user/character, acquire distributed lock
  -> MessageDispatcher: route message
  -> agent_handler.handle_message(): three-phase workflow
     -> Phase 1: PrepareWorkflow (orchestrator, context, web search, reminders)
     -> Phase 2: StreamingChatWorkflow -> OpenClawClient.send() per segment
     -> Phase 3: PostAnalyzeWorkflow (memory, relationship updates)
  -> MessageFinalizer: status updates, lock release
```

**What changes:**
- ingest stores `account_id` and external gateway IDs in message metadata
- `MessageAcquirer` must process pending messages for the `to_user` resolved at ingest, not only `default_character_alias`
- group pending-message queries must include group isolation so parallel groups do not merge
- `agent_handler._send_single_message()` calls a delivery abstraction that journals and then invokes `OpenClawClient.send()`
- Typing delays handled with `asyncio.sleep()` before each send
- No `ecloud_output.py` polling loop

**What stays the same:**
- Redis stream consumer group
- Worker pool with `AGENT_WORKERS` count
- Three-phase workflow
- Distributed lock management
- Interruption detection between phases
- `MessageAcquirer` / `MessageDispatcher` / `MessageFinalizer`

## New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `api/app.py` | FastAPI app | `/v1/chat` endpoint, auth middleware, validation |
| `api/ingest.py` | Ingest logic | User resolution, dedup, media processing, write to inputmessages + Redis |
| `api/openclaw_client.py` | WebSocket client | Persistent connection to OpenClaw gateway, expose `send()` method |
| `api/delivery.py` | Delivery service | Called by agent_handler, wraps OpenClawClient.send() with typing delays |
| `api/schema.py` | Pydantic models | Request/response schema, reply/reference normalization |

## Code to Remove

- legacy ecloud transport code: `connector/ecloud/ecloud_output.py`, `connector/ecloud/ecloud_input.py`, `connector/ecloud/ecloud_start.sh`
- legacy gateway runtime paths that duplicate OpenClaw transport responsibilities
- `connector/ecloud/ecloud_output.py` — replaced by `OpenClawClient.send()`
- `connector/ecloud/ecloud_input.py` — replaced by FastAPI `/v1/chat`
- Output polling logic in `agent_runner.py`
- Flask app dependency (replaced by FastAPI)
- PM2 / startup / shutdown entries that still boot or kill ecloud processes

**Keep:** `framework/tool/voice2text/`, `framework/tool/image2text/`, `framework/tool/text2voice/`, `framework/tool/text2image/` — media processing is Coke's job.

**Keep for now:** local terminal/testing helpers and any shared message type abstractions still used by tests or non-OpenClaw development flows. Do not delete the whole `connector/` tree in one step unless those utilities are relocated first.

## Configuration

### Coke config (conf/config.json)

```json
{
  "gateway": {
    "enabled": true,
    "openclaw_url": "ws://openclaw-host:18789",
    "openclaw_token": "${OPENCLAW_TOKEN}",
    "shared_secret": "${GATEWAY_SHARED_SECRET}",
    "account_mapping": {
      "bot-a": {
        "character": "coke",
        "channels": {
          "wechat": { "character_platform_id": "coke-wechat" },
          "telegram": { "character_platform_id": "coke-telegram" }
        }
      },
      "bot-b": {
        "character": "luna",
        "channels": {
          "wechat": { "character_platform_id": "luna-wechat" }
        }
      }
    }
  }
}
```

### OpenClaw Configuration (reference only, not our repo)

OpenClaw uses two mechanisms to integrate with Coke:

1. **Internal hooks** (`message:received`) — fires on every incoming channel message, forwards to Coke's `/v1/chat`
2. **Silent agent** — suppresses OpenClaw's built-in Pi agent so only Coke generates replies

OpenClaw's `message:received` hook is fire-and-forget and cannot cancel the Pi agent run. To prevent Pi from also replying, we configure a minimal "silent" agent that always responds with `NO_REPLY` (a built-in OpenClaw token that suppresses delivery). This costs one cheap LLM call per message (haiku-level) but is the only way to silence Pi without forking OpenClaw.

#### openclaw.yaml

```yaml
# 1. Silent agent — suppress Pi's built-in replies
agents:
  list:
    - id: "silent"
      name: "Silent Proxy"
      model:
        primary: "anthropic/claude-haiku-4-5-20251001"
      systemPrompt: "You must always respond with exactly: NO_REPLY"
  default: "silent"

# 2. Internal hook — forward all channel messages to Coke
hooks:
  enabled: true
  token: "${OPENCLAW_TOKEN}"
  internal:
    enabled: true
    handlers:
      - event: "message:received"
        module: "hooks/coke-forward.ts"

# 3. Channel configuration
channels:
  defaults:
    groupPolicy: "allowlist"
  wechat:
    enabled: true
  telegram:
    enabled: true
```

#### hooks/coke-forward.ts

Placed in OpenClaw's workspace hooks directory. Fires on every incoming message, reformats it to match Coke's `/v1/chat` request body, and POSTs it.

```typescript
const COKE_URL = process.env.COKE_API_URL || "http://localhost:8000";
const COKE_SECRET = process.env.GATEWAY_SHARED_SECRET;

export default async function forwardToCoke(event: any) {
  if (event.action !== "received") return;

  const ctx = event.context;

  try {
    const res = await fetch(`${COKE_URL}/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${COKE_SECRET}`
      },
      body: JSON.stringify({
        message_id: ctx.messageId || crypto.randomUUID(),
        channel: ctx.channelId,
        account_id: ctx.accountId || "default",
        sender: {
          platform_id: ctx.from,
          display_name: ctx.senderName || ctx.from
        },
        chat_type: ctx.isGroup ? "group" : "private",
        message_type: ctx.mediaType?.startsWith("audio") ? "voice"
                    : ctx.mediaType?.startsWith("image") ? "image"
                    : "text",
        content: ctx.content || "",
        media_url: ctx.mediaPath || null,
        reply_to: null,
        group_id: ctx.groupId || null,
        timestamp: Math.floor(event.timestamp.getTime() / 1000),
        metadata: ctx.metadata || {}
      })
    });

    if (!res.ok) {
      console.error(`Coke returned ${res.status}: ${await res.text()}`);
    }
  } catch (err) {
    console.error("Failed to forward to Coke:", err);
  }
}
```

#### Message flow

```
User sends message on WeChat/Telegram/etc.
  -> OpenClaw channel adapter receives it
  -> message:received hook fires -> coke-forward.ts -> POST /v1/chat -> Coke
  -> simultaneously, "silent" agent receives message -> responds NO_REPLY -> nothing sent
  -> Coke processes message -> WebSocket send() -> OpenClaw delivers to user
```

#### OpenClaw environment variables

```bash
COKE_API_URL=http://coke-host:8000       # Coke's FastAPI endpoint
GATEWAY_SHARED_SECRET=your-shared-secret  # Shared auth token for Coke HTTP
OPENCLAW_TOKEN=your-openclaw-token        # WebSocket auth token
```

### Coke Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENCLAW_TOKEN` | Token for authenticating Coke -> OpenClaw WebSocket |
| `GATEWAY_SHARED_SECRET` | Token for authenticating OpenClaw -> Coke HTTP |

## Payment Webhooks

The Flask app in `ecloud_input.py` currently hosts `/webhook/stripe` and `/webhook/creem` for subscription payment processing. These endpoints move into the new FastAPI app:

- `POST /webhook/stripe` — Stripe subscription webhook (HMAC verification, user access update)
- `POST /webhook/creem` — Creem subscription webhook (HMAC verification, user access update)

The payment logic (`agent/runner/payment/stripe_provider.py`, `creem_provider.py`) stays unchanged. Only the HTTP route registration moves from Flask to FastAPI.

## Group Chat Configuration

Group chat settings move from `ecloud.group_chat` to a channel-agnostic `gateway.group_chat` config:

```json
{
  "gateway": {
    "group_chat": {
      "enabled": true,
      "context_message_count": 20,
      "whitelist_groups": ["room-123@chatroom"],
      "reply_mode": {
        "whitelist": "all",
        "others": "mention_only"
      }
    }
  }
}
```

Group message detection moves from ecloud-specific type codes (80001, 80002, etc.) to the `chat_type: "group"` field in the `/v1/chat` request body. Mention detection relies on `metadata` from OpenClaw (e.g., `metadata.mentioned_bot: true`).

## Media URL Handling

Inbound `media_url` from OpenClaw is assumed to be a publicly accessible or pre-signed URL. Coke downloads it directly without additional auth. If OpenClaw serves media behind auth, the `coke-forward.ts` transform is responsible for producing a pre-signed URL before forwarding to Coke.

## Health and Error Responses

### Health Check

```
GET /health
```

Returns `200 OK` with `{ "status": "ok" }`. Used by load balancers and PM2/systemd health probes.

### Error Responses

| Status | When | Body |
|--------|------|------|
| 400 | Validation error (missing fields, bad types) | `{ "error": "validation_error", "detail": "..." }` |
| 401 | Invalid or missing Bearer token | `{ "error": "unauthorized" }` |
| 404 | Unknown `account_id` | `{ "error": "unknown_account", "account_id": "..." }` |
| 409 | Duplicate `message_id` | `{ "error": "duplicate", "message_id": "..." }` |
| 202 | Accepted | `{ "status": "accepted", "request_message_id": "...", "input_message_id": "..." }` |

## OpenClawClient Reconnection

The WebSocket client uses exponential backoff for reconnection:

- Initial delay: 1 second
- Max delay: 30 seconds
- Backoff factor: 2x
- Max retries: unlimited (service must stay connected)
- Health check: periodic ping/pong, reconnect on timeout
- Delivery during disconnect: journal records are written with status `pending_delivery`, a recovery sweep retries them after reconnection

## Operational Changes

- Replace the Flask/Gunicorn ecloud input service with the FastAPI gateway ingest service in `ecosystem.config.json`
- Remove PM2 entries, `start.sh`, and `stop.sh` logic that start or stop ecloud processes
- Update deployment docs to describe OpenClaw hook configuration plus Coke FastAPI ingress
- Keep worker startup unchanged aside from delivery-client initialization

## Migration Path

| Phase | What | Old System |
|-------|------|------------|
| 1 | Build `/v1/chat` + `OpenClawClient` + delivery | ecloud still running |
| 2 | Configure OpenClaw with one channel, validate account routing, dedup, and outbound journaling end-to-end | ecloud still primary |
| 3 | Switch traffic to OpenClaw and retire ecloud polling transport | ecloud standby |
| 4 | Remove legacy ecloud runtime paths and old Flask app wiring | ecloud removed |
