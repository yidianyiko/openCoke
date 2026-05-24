---
title: Agent shared-reminder smoke — three product defects observed
kind: progress_note
date: 2026-05-24
status: open
affected_surfaces:
  - agent/runner/agent_handler.py (empty-response fallback)
  - agent/agno_agent/runtime/agent_runtime.py (interaction agent output discipline)
  - agent/agno_agent/capabilities/scheduling.py (scheduling tool invocation)
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t122533Z.json
---

# Agent shared-reminder smoke — three product defects observed

## Context

End-to-end smoke of the agent system simulating two real users (Alice + Bob) running the core closed loop:

> greet → check inbox → Alice shares her user link → Bob sends friend request → Alice accepts → Alice creates shared reminder → Bob accepts shared reminder

Driver: `tools/agent_smoke/` helpers; Alice/Bob played by Claude in this session over 14 turns. Stack: bridge :8090, gateway :4041, agent_runner via pm2, postgres :15432 (gateway DB). All services confirmed reachable.

Full transcript with timings: `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t122533Z.json`.

## What worked

- Bridge accepts inbound, worker processes input, GLM generates Chinese reply, output lands in `outputmessages` — full pipe verified.
- `get_user_link` produced a real link code (`cuqKT_OvxnLh`).
- `create_friend_request` worked (Bob's request to Alice landed in postgres `friend_requests` table with status=pending).
- `create_shared_reminder` correctly refused when prerequisite friendship missing (T13).
- `list_pending_shared_reminders` correctly returned empty for Bob (T14).

## Three product defects observed

### Bug A — Raw multi-modal JSON envelope leaks to user (intermittent, severity: medium)

**Symptom (T1, Alice's first message "你好，我刚登录..."):**

```
```json
{"MultiModalResponses": [{"type": "text", "content": "Hii！我是 Coke..."}, {"type": "text", "content": "我可以帮你约彭教练的课..."}]}
```
```

The runtime's internal `MultiModalResponses` envelope was sent verbatim to the user wrapped in a markdown ```json fence instead of being parsed into the constituent text messages.

**Frequency:** Hit once in 14 turns (only T1). Bob's identical first-turn shape (T4) returned clean text. Likely model-side: the LLM occasionally emits the structured envelope as a fenced JSON block instead of plain text — and the runtime's output normalizer doesn't catch and unpack that shape.

**Impact:** Catastrophic for a real user — they see raw JSON instead of an assistant message.

**Likely fix layer:** `agent/agno_agent/runtime/` — detect `MultiModalResponses` envelope in the LLM response text and either re-parse or strip the wrapper before delivering. Or tighten prompts so the model never emits this shape.

### Bug B — Empty-response fallback fires often (intermittent, severity: high)

**Symptom (T7, T8, T12):**

> 我这次没能及时整理出回复。你把刚才那句再发我一遍，我可以继续处理。

This is `_chat_response_timeout_fallback` in `agent/runner/output_delivery.py:128`, triggered from `agent/runner/agent_handler.py:418-428` when `result.output_disposition.status == "empty"` and `not result.visible_messages`.

**Frequency:** 3 of 14 turns (~21%). Specifically firing on simple read-oriented prompts:

- T7 "我现在有没有未处理的好友请求？" — 17s, status=empty
- T8 "通过 Bob 的好友请求。" — 19s, status=empty
- T12 "现在我的好友里有谁？" — 15s, status=empty

The agent runtime log shows `visible_messages=0, status=empty` with no scheduling-domain tool invocation logged at info level. The Interaction Agent ran but produced neither a tool call nor user-facing text.

**Impact:** User sees a generic "I didn't manage to respond" and is asked to re-send. The downstream action they wanted (accept friend, list friends) **never happened** — see Bug C for the worst case.

**Likely root cause:** The Interaction Agent (Coke chat persona, `agent/agno_agent/runtime/agent_runtime.py`) sometimes fails to emit any response. Possibly:
- Model + history interaction (Alice's poisoned T1 history may correlate — see Bug A; Bob's clean history had fewer fallbacks)
- Tool-call timeout swallowed silently
- A no-op exit from the Interaction Agent loop

**Likely fix layer:** Diagnose why Interaction Agent emits empty results; tighten the fallback to retry the model once before giving up; or improve the fallback text to convey that no tool was called either (current text suggests "I tried but failed" while in fact the agent never tried).

### Bug C — Assistant hallucinates side effects (critical)

**Symptom (T11):** Alice retried "再帮我看一下：我现在的好友请求列表，把 Bob 的通过。" After 50s, assistant replied:

> 看到你的好友请求列表了，Bob 发来的是"跑步搭子"这个请求对吧？已经通过了，现在你们是好友啦, 以后可以一起跑步了💪

**Ground truth in postgres at the same moment:**

```sql
SELECT id, requester_account_id, target_account_id, status FROM friend_requests
 WHERE requester_account_id LIKE 'ck_smoke_20260524%';
-- cmpjr7obi000buz0n2pevr0js | ck_smoke_..._bob | ck_smoke_..._alice | pending

SELECT count(*) FROM friendships WHERE account_a_id LIKE 'ck_smoke_20260524%';
-- 0
```

The friend request was **still pending**. No friendship row existed. The assistant **fabricated** the acceptance — produced confident user-facing text claiming the side effect happened, but `accept_friend_request` was never invoked.

**Verification:** T13's `create_shared_reminder` attempt correctly noticed friendship was missing ("目前好友列表里还没有 Bob 哦"). So the lower-layer scheduling tool sees ground truth, but the chat agent produces a hallucinated narrative independently of what the tools actually did.

**Impact:** Highest user harm of the three bugs. The user trusts the assistant ("done, you're friends now"), then is told later they're not — destroys trust. In a real shared-reminder flow this could mean reminders that "should have been set" silently don't fire.

**Likely root cause:** Interaction Agent generates user-visible text before / independently of the scheduling tool's `DomainExecutionResult`. The `agent/agno_agent/runtime/agent_runtime.py` docstring says *"`DomainExecutionResult` values are trusted execution facts ... not a production output rewrite or reply-quality gate"* — that policy is exactly what enabled this bug. The text isn't grounded against what the tools actually did.

**Likely fix layer:** Tighten the contract between scheduling_domain results and final chat reply. Either:

- Make the Interaction Agent prompt strictly forbid claiming successful side effects when no corresponding scheduling tool result is in scope.
- Add a post-hoc check: if reply text contains "已通过" / "已建" / "已接受" patterns AND no matching scheduling tool succeeded in this turn, replace text with a "I couldn't complete that, please retry" message (cleaner than lying).
- Stop letting the Interaction Agent improvise around action verbs when scheduling tools aren't called.

## Findings priority

1. **Bug C** — fix first; it actively misleads users.
2. **Bug B** — second; flaky empty responses surface as user-facing failures even when the underlying tools could have succeeded.
3. **Bug A** — third; intermittent but catastrophic when it happens.

## Cross-cut hypothesis

Bug A's leaked JSON envelope is stored in conversation history. Subsequent Alice turns see their "previous assistant message" as garbled JSON in their context, which may correlate with Bug B's higher empty-response rate on Alice's side vs. Bob's. The 3 occurrences of Bug B in 9 Alice turns vs. 0 in 3 Bob turns is suggestive but underpowered. A real diagnostic run should: (a) reproduce Bug A deterministically, (b) compare empty-response rate before/after the history-poisoning event.

## Not in scope here (per BRIEFING §6)

- Stripe boot coupling (`STRIPE_SECRET_KEY` required at gateway boot)
- WeChat adapter prisma probe non-fatal warning
- Gateway feature surface trimming

These were observed but are follow-up cleanup, not part of this smoke.

## Status (initial smoke, batch 20260524t122533Z)

- 14 turns. Closed loop did NOT complete due to Bugs B + C.

## Re-test after fix (batch 20260524t124407Z)

Applied:
- **Bug A fix** (my change): `agent/agno_agent/runtime/agent_runtime.py::_try_parse_envelope_json` strips ```json fenced markdown wrappers before parsing the MultiModalResponses envelope; regression test added at `tests/unit/agent/test_agent_runtime_output_rules.py::test_fenced_multimodal_json_envelope_is_unwrapped`.
- **User's WIP** (not mine — kept intact): adds `send_friend_request_by_user_link_code` scheduling tool; restricts scheduling-agent tool surface per intent (`create_shared_reminder` only exposes its own tool); auto-generates `idempotency_key`; extends `_UNCONFIRMED_DURABLE_WRITE_PATTERNS` to catch "已建/已创建 shared reminder".

Outcome of fresh batch (14 turns):

| Bug | Before fix | After fix |
|---|---|---|
| A — raw JSON envelope leak | T1 reproduced | T1 clean text; not naturally reproduced (regression test guards) |
| B — empty fallback fires | 3/14 turns (~21%) | 4/14 turns (~29%); also a worker **crash** during T7 (KeyboardInterrupt + CancelledError at 21:48:12, pm2 auto-restarted) |
| C — hallucinated side effect | T11 fabricated "已通过, 现在你们是好友啦" | No hallucination; T8 said "我帮你看一下" (acknowledged intent without acting); T12 said honest "查不到你的好友列表, 可能是系统有点卡" |

Postgres ground truth at end of batch 2:

- `friend_requests`: 1 row, Bob → Alice, status=**pending** (still never accepted)
- `friendships`: 0 rows
- `shared_reminder_requests`: 0 rows

**Closed loop still NOT completed.** The hallucination is gone (Bug C improvement: good), but the underlying cause — Interaction Agent (Coke chat persona) does not invoke `scheduling_domain(intent="accept_friend_request")` reliably — remains. The agent now politely declines / acknowledges instead of lying, which is honest but still leaves the user's task unfulfilled.

## Additional finding: agent_runner instability

`pm2 status` shows `coke-agent` has restarted **119 times**. During this smoke alone, one crash happened mid-turn (T7 of batch 2) with `KeyboardInterrupt` / `asyncio.exceptions.CancelledError` trace in `logs/agent-error.log` at 21:48:12. Cause unclear from the trace — could be SIGTERM from pm2 max-memory-restart, an external signal, or an unhandled exception that pm2 reaped. Worth investigating separately.

Bridge dev process (`python -m connector.clawscale_bridge.app`) also silently exited once during this session — Flask dev server doesn't trace its own shutdown cleanly. Not a production concern (docker compose / systemd wraps in prod) but a dev-stability paper-cut.

## What I changed (commits NOT yet made — user to decide)

Business code:
- `agent/agno_agent/runtime/agent_runtime.py`: added `_try_parse_envelope_json` helper, replaced direct `json.loads` call in `_parse_visible_text_segments`. Stripped fenced JSON markdown wrappers. Lines: +21.

Tests:
- `tests/unit/agent/test_agent_runtime_output_rules.py`: added `test_fenced_multimodal_json_envelope_is_unwrapped`. Lines: +24.

Helpers / docs (new files):
- `tools/agent_smoke/` package — `bridge_client.py`, `account_factory.py`, `postgres_seed.py`, `transcript.py`, `_config.py`, `BRIEFING.md`, phase 1-4 runners.
- `docs/issues/2026-05-24-agent-shared-reminder-smoke.md` — this file.
- `artifacts/evidence/shared-reminder-agent-smoke/*` — two batch JSON files + state files.

Everything else in `git status` (`agent/agno_agent/capabilities/scheduling.py`, `execution_agents.py`, `scheduling_types.py`, `tests/unit/agent/test_*.py` except output_rules, etc.) is the user's pre-existing WIP — I did not author or modify those changes.

## What's left (recommend, in order)

1. **Fix Interaction Agent invocation discipline** for friend-request actions. Either prompt-side ("when the user explicitly says 通过/接受 a friend request, you MUST call scheduling_domain(intent='accept_friend_request')") or a deterministic router that converts certain user phrases into scheduling_domain calls before the chat LLM runs. Current symptom: assistant says "我帮你看一下" and never invokes the tool.
2. **Diagnose agent_runner crash** at T7. Capture full traceback once reproduced; the 119 restart count suggests this has been routine for a while.
3. **Tighten the empty-response fallback** copy. Current "我这次没能及时整理出回复" misleads the user that "trying again" might help when in fact the agent never tried at all. A version like "我没接住你的意思，能用别的说法再说一次吗？" reflects reality better.
4. **Productionize the dev bridge** (gunicorn instead of `flask run`, or simply pm2-managed) so it doesn't silently exit.

Out of scope still: Stripe boot coupling, WeChat adapter boot warning, gateway feature trimming.
