---
title: Agent shared-reminder smoke — closed the loop after multiple fixes
kind: progress_note
date: 2026-05-24
status: substantially_resolved
affected_surfaces:
  - agent/agno_agent/runtime/agent_runtime.py (envelope parsing, unconfirmed-write detection)
  - agent/agno_agent/runtime/chat_response_instructions.py (chat persona invocation discipline)
  - agent/agno_agent/runtime/execution_agents.py (scheduling worker chaining)
  - agent/runner/output_delivery.py (empty-response fallback wording)
  - gateway/packages/api/src/routes/internal-scheduling-routes.ts (friend_name fuzzy lookup)
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t122533Z.json (initial failure)
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t124407Z.json (after WIP)
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t135741Z.json (after prompt fix)
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t143500Z.json (after detector extension)
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t145018Z.json (closed loop)
---

# Agent shared-reminder smoke — closed the loop after multiple fixes

## Outcome

The core closed loop (greet → inbox → user link → friend request → accept → shared reminder create) **now works end-to-end against the live stack**. Final batch `20260524t145018Z` confirmed in postgres:

| Surface | Before | After |
|---|---|---|
| `friend_requests.status` | pending forever | **accepted** |
| `friendships.status` | empty | **active** |
| `shared_reminder_requests.status` | empty | **pending_invitee_confirmation** + title + fire_at |

Only the **final invitee acceptance** of the shared reminder is unresolved — same architectural shape as the friend-accept issue but for shared-reminder backend (see "Remaining work" below).

## Bugs that were genuine product defects, and what fixed them

### Bug A — Raw MultiModalResponses envelope leaked to user (intermittent)

The model occasionally emits the runtime's structured envelope as plain or fenced JSON instead of clean text. The parser's old `json.loads(final_text)` path missed two real shapes:

1. **Fenced JSON envelope** — model wraps the envelope in ```` ```json ... ``` ```` markdown.
2. **Malformed envelope** — model emits the envelope with a brace error (real example: extra `}` before `]`).

**Fix** (`agent/agno_agent/runtime/agent_runtime.py`):
- `_try_parse_envelope_json` strips markdown fences before `json.loads`.
- `_recover_lenient_envelope` regex-extracts `"content": "..."` segments when the envelope signature is present but JSON parsing fails — last-resort recovery, never invoked for non-envelope text.

Regression tests: `test_fenced_multimodal_json_envelope_is_unwrapped`, `test_malformed_envelope_json_recovers_text_lenient`, `test_non_envelope_invalid_json_still_falls_back_to_raw`.

### Bug B — Empty-response fallback fires often (still flaky on first turns)

`agent_handler.py:418` triggers `_chat_response_timeout_fallback` whenever `result.output_disposition.status == "empty"`. The old fallback wording — "我这次没能及时整理出回复。你把刚才那句再发我一遍" — mislead users into retrying when the underlying scheduling tool never even ran.

**Partial fix** (`agent/runner/output_delivery.py`):
- Reworded to "我没接住你刚才的意思。你可以换个说法再说一次吗？" — honest about not understanding rather than implying retry will work.

**Still present:** the empty-response itself fires ~15–25% of turns, concentrated on first-turn greetings (T4 Bob across multiple batches) and during agent_runner crashes (T7 across multiple batches always took 205s and returned empty — see "agent_runner crash mid-turn" below). Not fully root-caused; deserves a separate dig.

### Bug C — Assistant hallucinates side effects (critical)

Original symptom (batch 122533Z T11): assistant said "已经通过了，现在你们是好友啦💪" while postgres `friend_requests` still showed `pending`. Real user is misled.

**Fix** (user/me, `agent/agno_agent/runtime/agent_runtime.py::_UNCONFIRMED_DURABLE_WRITE_PATTERNS`):
- Added pattern for friend-accept claims (`"已经/帮你...通过/接受...请求/好友"` either order; English `"I've accepted the friend request"`).
- Added pattern for the "现在你们是好友啦" / "now you are friends" tail.
- Patterns require a first-person lead-in so safe statements like "等对方通过你的好友请求就成啦" don't false-positive.
- Lifted into `direct_promise_patterns` so they fire even when the reply contains a question mark.

Regression test: `test_unconfirmed_durable_write_friend_accept_patterns`.

After this fix, when the underlying accept fails, the assistant returns an honest "刚才系统有点卡，回头帮你通过" instead of lying.

### Bug C-secondary — Chat persona too cautious, didn't invoke scheduling tools

After Bug C protections went in, the assistant correctly stopped lying — but still didn't successfully invoke the scheduling write. Investigation showed the chat persona was sending "我帮你看一下" / "let me check" instead of calling `scheduling_domain`. The `_DELEGATION_BOUNDARY` rule was permissive ("Use scheduling_domain only for X") rather than mandatory.

**Fix** (`agent/agno_agent/runtime/chat_response_instructions.py`):
- Mandatory invocation rule: when the user explicitly directs a scheduling action with a clear target, the chat persona MUST call `scheduling_domain` in the same turn. No "I'll go check" intermediates.
- Listed every scheduling action (send/accept/reject/cancel friend-request, accept/reject/cancel shared-reminder, friendship/block/unblock, user-link, list-X) so the model recognizes coverage.
- Added explicit rule: a message containing "加好友" / "add friend" + alphanumeric link code is a `send_friend_request_by_user_link_code` directive.
- Removed the legacy "ask for confirmation before accept/reject" rule that was reading explicit directives as "still ambiguous, please re-confirm".

Regression test updated: `test_delegation_boundary_restores_scheduling_safety_policy`.

### Bug D1 — Chat persona tried to pass args to scheduling_domain, burned tool budget

Even after the chat persona started invoking `scheduling_domain`, observation of a session (batch 135741Z T8) showed it trying to pass `_model_supplied_args={request_id: ...}` to the tool. The `scheduling_domain(intent: Any)` wrapper rejects all kwargs except `intent`. The model burned 4 tool calls hitting pydantic validation errors, then produced the empty fallback.

**Fix** (`agent/agno_agent/runtime/chat_response_instructions.py`):
- Explicit rule: "scheduling_domain ONLY accepts a single `intent` argument. Never pass request_id, friend_request_id, id, _model_supplied_args, or any other parameter."
- The inner scheduling worker resolves args from the user message (using `friend_name` / `invitee_name` semantics, server-side).

### Bug D2 — Backend `accept_friend_request` required request_id the agent couldn't supply

The inner scheduling agent called `accept_friend_request` without a `request_id` (it didn't know one), the gateway returned `friend_request_not_found`, the agent gave up. The "one tool per call" pattern means no in-agent list-then-accept chain.

**Fix** (user/codex, `gateway/packages/api/src/routes/internal-scheduling-routes.ts`):
- `acceptFriendRequest` (and reject/cancel) now accept `friend_name`. The gateway resolves a single pending request matching that name; fails closed if ambiguous or missing.
- `agent/agno_agent/runtime/scheduling_types.py`, `execution_agents.py`, `capabilities/scheduling.py`: `friend_name` field added to the scheduling args, passed through.
- Scheduling-worker prompt updated to use `friend_name` for these intents.

After this combination, batch 145018Z T8 succeeded: assistant said "好啦，已经通过 Bob 的好友请求了～以后你们就是跑步搭子啦"; postgres confirmed both `friend_requests.status=accepted` and `friendships.status=active`.

## Additional findings (open, not in scope for this round)

### agent_runner crash mid-turn

`pm2 status` shows `coke-agent` has restarted **119 times** historically. During this smoke session, T7 of every batch consistently took 205s and returned empty `output_id`. `logs/agent-error.log` shows `KeyboardInterrupt` + `asyncio.exceptions.CancelledError` traces around those windows, followed by pm2 auto-restart. Cause unclear from the trace.

Implication: even with all the LLM fixes, T7 was always unanswerable in this batch. Worth a separate investigation of why the runner periodically dies under what is otherwise normal load.

### Bug D for `accept_shared_reminder` parallel to D2

Batches 145018Z post-loop showed Bob's "接受 Alice 那个共享提醒" calls failing the same way `accept_friend_request` used to fail: tool needs `request_id`, agent can't supply, gateway returns no-match. The backend fix that worked for friend-request (`friend_name`) was not extended to shared-reminder accept. The same shape applies: take `inviter_name` (or simply pick the single pending shared reminder when only one matches the invitee).

### `list_pending_shared_reminders` returned empty when 2 actually pending

Batch 145018Z T15: Bob asked "我现在有没有待处理的共享提醒？" → assistant said "目前你没有待处理的共享提醒". One turn later Bob asked "接受 Alice 的共享提醒" → assistant said "我看到 Alice 有两个待接受的共享提醒". Same user, same minute. Direct API call to gateway returned both. So the agent's tool call for `list_pending_shared_reminders` was either filtered too tightly (wrong direction default?) or the assistant misinterpreted the result. Needs a quick look.

### Friend-request note leaked into visible reply

Batch 152859Z T6 surfaced the raw friend-request `message` field ("跑步搭子") instead of the write summary. Root cause: the scheduling capability treated any `message` field as an explicit visible summary for durable writes. Fixed by only honoring explicit `visible_summary` / `summary` for scheduling writes, then backfilling the canonical summary. Live recheck on 2026-05-25 with Bob `ck_smoke_20260524t152859Z_bob` and Alice's link code `jPXX93OrUKHq` returned `已发送好友请求。` as expected.

### First-turn empty-fallback bursts

Bob's T4 ("你好，我是 Bob，我刚登录") triggered empty fallback in batches 124407Z, 143500Z, 145018Z. Always ~5–8s elapsed, suggesting the model returned nothing useful quickly. Possible signal of cold-conversation prompt issues.

### Dev `bridge` (Flask) silently exits

The development bridge process (`python -m connector.clawscale_bridge.app`) died once during this session with no traceback in `logs/bridge.log`. Production wraps it in docker, but dev paper-cut. Worth wrapping in `setsid` + gunicorn for dev too.

### Pre-existing boot-time couplings (out of scope, per BRIEFING §6)

- Stripe constructor at module load (gateway boot requires `STRIPE_SECRET_KEY` even though our test path never touches subscriptions).
- WeChat adapter prisma probe at boot; logs a non-fatal `PrismaClientInitializationError`.

These are real "remove unused gateway features" candidates but separate from the smoke.

## Verification log (chronological)

| Batch | Notable result | Bugs A / B / C / D / D1 status |
|---|---|---|
| 122533Z | Initial smoke, 14 turns. Closed loop NOT completed. | A leaked T1; B fired 3/14; C lied T11; D friendship never formed. |
| 124407Z | After user's WIP + my Bug A fix. | A clean; B 4/14 + worker crash; C improved (T8 honest); D still no friendship. |
| 135741Z | After chat-persona `MUST invoke` prompt + send_friend_request rule. | A clean; D send_friend_request landed in postgres; D accept still blocked. |
| 143500Z | After accept-claim patterns + friend_name backend support. | C catches "已经通过" lies; agent now honest about defer. D accept still blocked at agent level (D1 root cause). |
| **145018Z** | After "scheduling_domain only takes intent" prompt. | **D2 closed: friendship active in postgres; shared reminder created.** Bob's accept of shared reminder still fails (same D shape, not extended to shared_reminder backend). |

## Status

- Core loop closed. Significant ongoing improvements committed.
- Remaining work: D-shaped extension for `accept_shared_reminder`, agent_runner crash diagnosis, first-turn empty-burst diagnosis, `list_pending_shared_reminders` filter issue.
- No business code reverted; everything fits with the user's WIP committed during this session.
