# Gateway Integration Handover

> Date: 2026-03-26
> Status: Design Phase
> Branch: `feature/gateway-integration`

## Context

Coke currently uses E云管家 (ecloud) as its WeChat connector — a third-party protocol that we plan to phase out. We want to replace it with an **independent Gateway service** that handles all channel connections (WeChat, Telegram, Discord, WhatsApp, etc.) and forwards messages to Coke's agent backend via HTTP API.

### Why a Separate Gateway Service

- **Separation of concerns**: Gateway handles channel protocols + multi-account + access control. Coke handles AI agent logic only.
- **Reusability**: Gateway can serve other agent projects beyond Coke.
- **Independent scaling**: Gateway and Coke scale independently.
- **Channel isolation**: WeChat API changes, account bans, or protocol updates only affect Gateway — zero impact on Coke.
- **Multi-tenancy**: Different WeChat accounts (or other channels) map to different Coke characters/agents. Gateway routes by `account_id`, Coke routes by `character`.
- **Tech stack freedom**: Gateway can use the best-fit language/framework for networking (e.g., Python async, Node.js, Go), decoupled from Coke's Python agent stack.

### Why Not Use OpenClaw Directly

OpenClaw was evaluated as a ready-made gateway. Decision: **not adopted**. Reasons:

- Too heavy for our use case — ships with built-in LLM, 60+ provider plugins, Canvas/ACP runtime, device pairing, CLI tools, media pipeline, etc.
- We only need: channel connections, multi-account, message forwarding.
- WeChat plugin (`@tencent-weixin/openclaw-weixin`) is tied to OpenClaw's plugin SDK — can't extract it standalone.
- Adds a Node.js dependency to a Python-based stack.
- We want full control over the gateway layer for production deployments.

### Prior Art

- `doc/plans/2026-01-02-langbot-gateway-design.md` (clever-star branch): LangBot integration plan. Similar concept (external gateway → webhook → Coke), but LangBot-specific. The new design generalizes this pattern.

---

## Target Architecture

```
                    ┌──────────────────────────────────┐
                    │         Gateway Service           │
                    │  (independent repo / deployment)  │
                    │                                   │
                    │  ┌───────────┐  ┌───────────┐    │
Users ──── WeChat ──┤  │ WeChat    │  │ Telegram  │    │
           Telegram ┤  │ Adapter   │  │ Adapter   │    │
           Discord ─┤  │           │  │           │    │
           WhatsApp ┤  ├───────────┤  ├───────────┤    │
                    │  │ Discord   │  │ WhatsApp  │    │
                    │  │ Adapter   │  │ Adapter   │    │
                    │  └───────────┘  └───────────┘    │
                    │         │                         │
                    │    Multi-Account Manager          │
                    │    Access Control (allowlist)      │
                    │    Reply Delivery                  │
                    └──────────┬───────────────────────┘
                               │ HTTP API
                               ▼
                    ┌──────────────────────────────────┐
                    │         Coke Agent Backend        │
                    │  (this repo)                      │
                    │                                   │
                    │  POST /v1/chat  (new endpoint)    │
                    │         │                         │
                    │    User/Character Resolution      │
                    │         │                         │
                    │    MongoDB inputmessages          │
                    │         │                         │
                    │    Three-Phase Workflow            │
                    │    (Prepare → Chat → PostAnalyze) │
                    │         │                         │
                    │    MongoDB outputmessages          │
                    │         │                         │
                    │  Response → HTTP callback / poll   │
                    └──────────────────────────────────┘
```

---

## Interface Contract (Draft)

This is the core agreement between Gateway and Coke. Both sides implement to this spec.

### 1. Inbound: Gateway → Coke

```
POST /v1/chat
Content-Type: application/json
Authorization: Bearer <shared_secret>
```

**Request Body:**

```json
{
  "message_id": "gw-msg-uuid-001",
  "channel": "wechat",
  "account_id": "bot-a",
  "sender": {
    "platform_id": "wx_user_abc123",
    "display_name": "Alice",
    "avatar_url": "https://..."
  },
  "chat_type": "private",
  "message_type": "text",
  "content": "Hello",
  "media_url": null,
  "reply_to": null,
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
| `sender.avatar_url` | string | no | User avatar |
| `chat_type` | enum | yes | `private` or `group` |
| `message_type` | enum | yes | `text`, `image`, `voice`, `video`, `file`, `reference` |
| `content` | string | yes | Text content, or caption for media |
| `media_url` | string | no | URL to media file (image/voice/video) |
| `reply_to` | string | no | Original message content being replied to |
| `group_id` | string | no | Group/room ID (when `chat_type=group`) |
| `timestamp` | int | yes | Unix timestamp |
| `metadata` | object | no | Channel-specific extra data |

**Response (sync ack):**

```json
{
  "status": "accepted",
  "coke_message_id": "60f1a2b3c4d5e6f7a8b9c0d1"
}
```

Coke accepts the message into its queue and returns immediately. Processing is async.

### 2. Outbound: Coke → Gateway

Two options (to be decided during design phase):

**Option A: Callback (push)**

Coke calls Gateway's delivery endpoint when a reply is ready:

```
POST <gateway_callback_url>/v1/deliver
Content-Type: application/json
Authorization: Bearer <shared_secret>
```

```json
{
  "reply_to_message_id": "gw-msg-uuid-001",
  "channel": "wechat",
  "account_id": "bot-a",
  "recipient": {
    "platform_id": "wx_user_abc123"
  },
  "messages": [
    { "type": "text", "content": "Hi Alice!" },
    { "type": "voice", "content": "Hi Alice!", "url": "https://oss.../voice.mp3", "emotion": "happy" },
    { "type": "image", "url": "https://oss.../photo.jpg" }
  ],
  "group_id": null
}
```

**Option B: Polling (pull)**

Gateway polls Coke for pending replies:

```
GET /v1/replies?account_id=bot-a&since=<timestamp>
```

**Recommendation:** Option A (callback) for lower latency. Option B as fallback.

### 3. Account ↔ Character Mapping

Gateway manages channel accounts. Coke maps accounts to characters.

```
Coke config (conf/config.json):

{
  "gateway": {
    "account_mapping": {
      "bot-a": { "character_alias": "coke", "character_id": "60f..." },
      "bot-b": { "character_alias": "luna", "character_id": "70a..." }
    },
    "callback_url": "http://gateway-host:9000/v1/deliver",
    "shared_secret": "${GATEWAY_SHARED_SECRET}"
  }
}
```

### 4. Auth

- Shared secret (Bearer token) for both directions.
- Both services validate the token on every request.
- Secret stored in environment variables, never in config files.

---

## Multi-Tenancy Flow

```
User A (on WeChat account "bot-a")
  → Gateway: { channel: "wechat", account_id: "bot-a", sender: "wx_user_A" }
    → Coke: account_mapping["bot-a"] → character "coke"
      → MongoDB: user=A, character=coke, conversation isolated
      → Reply → Gateway: deliver to wechat/bot-a/wx_user_A

User B (on WeChat account "bot-b")
  → Gateway: { channel: "wechat", account_id: "bot-b", sender: "wx_user_B" }
    → Coke: account_mapping["bot-b"] → character "luna"
      → MongoDB: user=B, character=luna, conversation isolated
      → Reply → Gateway: deliver to wechat/bot-b/wx_user_B

User C (on Telegram, same account "bot-a")
  → Gateway: { channel: "telegram", account_id: "bot-a", sender: "tg_user_C" }
    → Coke: same character "coke", different user
      → MongoDB: user=C, character=coke, conversation isolated
```

Existing Coke isolation (per user + per character) handles multi-tenancy naturally. No changes to agent core needed.

---

## Coke-Side Changes Required

### New (to build)

1. **`POST /v1/chat` endpoint** — Accepts gateway messages, resolves user/character, inserts into `inputmessages`.
2. **Callback delivery** — Output handler that POSTs replies to Gateway instead of calling ecloud API.
3. **Account → Character mapping** — Config-driven lookup from `account_id` to character.
4. **User auto-creation** — Create user record from `sender` info if not exists (generalized from current ecloud-specific logic).

### Refactor (existing code)

5. **Decouple `ecloud_input.py`** — Extract user resolution, message normalization, and dedup logic into shared utilities. Keep ecloud as one adapter (transitional).
6. **Decouple output handler** — Current output goes through ecloud API or MongoDB polling. Add a gateway callback output path.

### No changes needed

- Three-phase workflow (PrepareWorkflow → StreamingChatWorkflow → PostAnalyzeWorkflow)
- Agent tools (RAG, reminders, voice, image, search)
- MongoDB schema (users, conversations, relations, embeddings)
- Access control gate (works on user records, channel-agnostic)
- Background handler (reminders, future messages, decay)

---

## Gateway-Side Scope (Separate Repo)

Not designed here — will be its own project. Key responsibilities:

- Channel adapters (WeChat official API / E云管家 transitional, Telegram Bot API, Discord Bot, WhatsApp)
- Multi-account management (multiple WeChat accounts, etc.)
- Inbound access control (allowlist, rate limiting)
- Message normalization → POST to Coke `/v1/chat`
- Reply delivery: receive from Coke callback → deliver to correct channel/account/user
- Health monitoring, reconnection, credential management

---

## Migration Path

| Phase | What | ecloud Status |
|-------|------|---------------|
| 1 | Build Coke `/v1/chat` + callback delivery | ecloud still primary |
| 2 | Build Gateway with one channel (e.g., Telegram) | ecloud still primary for WeChat |
| 3 | Add WeChat adapter to Gateway | ecloud + Gateway in parallel |
| 4 | Validate, switch WeChat traffic to Gateway | ecloud standby |
| 5 | Remove ecloud connector | ecloud removed |

---

## Open Questions

1. **WeChat API choice**: Official iLink Bot API (灰度中), 企业微信 API, or keep E云管家 as transitional adapter in Gateway?
2. **Outbound delivery**: Callback (push) vs polling (pull) vs both?
3. **Media handling**: Does Gateway proxy media files, or pass URLs directly to Coke?
4. **Gateway tech stack**: Python (reuse Coke patterns) vs Go/Node (better for networking)?
5. **Gateway repo**: New standalone repo, or subdirectory in Coke monorepo?
