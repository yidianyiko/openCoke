---
kind: incident
status: resolved
surface: conversation-runtime, agent-runtime, notification-delivery
created_at: 2026-06-01
updated_at: 2026-06-01
---

# Confirmation Turn No Reaction After Shared-Reminder Clarification

## What Happened

In production conversation `7fed5c7c-08f9-4778-bdcc-c14b7f2cf346`, account
`olivers` sent two questions, then asked:

- `帮我和他约一个明天上午八点半的晨跑活动吧`

The requester only received:

- `你是想约 lizihao 一起晨跑吗？`

When the user later replied `是的`, the turn did not create a shared reminder
and did not send a final visible reply.

## Why It Matters

This is the core follow-up confirmation path for shared-reminder creation. A
user-visible clarification must remain actionable when the user confirms it.
The failure also hid useful progress messages because waiting replies were
persisted but not delivered.

## Affected Surfaces

- `conversation-runtime`
- `agent-runtime`
- `notification-delivery`

## Evidence

- Production `input_message` rows for the conversation show seq 76 and 77 were
  coalesced question inputs, seq 78 requested the morning run, and seq 79 was
  `是的`.
- Production `turn` rows show the seq 79 turn
  `9d750217-8587-454b-95dd-14dffd670e76` ended with
  `failed / invalid_output_protocol`.
- Production `ai.agno_sessions` for session
  `7fed5c7c08f94778bdccc14b7f2cf346` shows the last run content was literal
  `<tool_call>social_scheduling_tool({...})</arg_value>`, not a native tool
  invocation or Coke JSON output.
- The same turn's trusted semantic decision was
  `chit_chat / missing_context / ask_context`, so the runtime exposed a
  clarification-only tool profile and instructed the agent to ask context before
  any domain action.
- Waiting replies for the question and command turns were persisted but their
  delivery attempts failed with `provider_network_error`; those waiting
  delivery requests used raw provider trigger ids as idempotency keys, unlike
  compact final reply keys.

## Current Status

- Resolved and deployed to production clean stack at
  `1187295f1f89544b1bb4672c2ace35db0541518c`.
- The user-visible interruption behavior is intentional: the first two rapid
  questions are superseded by the later command, and only the newest open input
  window produces the live reply.
- The no-reaction confirmation behavior was not intentional and is fixed.

## Resolution

- Fixed commits:
  - `54f756c` repaired waiting-reply idempotency, short affirmative clearing,
    and serialized textual tool-call retry guidance.
  - `96032b5` kept tools available for concise clarification answers.
  - `4424f02` rejected state-changing success claims when no native tool ran.
  - `f1aac87` carried pending shared-reminder friend clarification context.
  - `18b0a61` kept social scheduling tools available for resolved follow-ups.
  - `3b657ee` created resolved shared reminders directly when the original
    Chinese title/time can be parsed.
  - `33b43a9` asked ambiguous friend clarifications deterministically.
  - `f86d148` avoided unnecessary tool requirements for clarification-only
    ambiguous friend questions.
  - `e6c38f7` moved pending shared-reminder follow-up resolution before the
    semantic LLM so one-word confirmations cannot time out before the
    deterministic resolver runs.
  - `1187295` accepts an affirmative follow-up such as `是的` for the only
    active friend when the prior clarification asked which friend.
- Verification:
  - `.venv/bin/python -m pytest tests/unit/coke/worker/test_waiting_reply.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/turn/test_output_protocol.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py -q`
    passed with 136 tests.
  - `git diff --check` passed.
  - `zsh scripts/verify-surface clean-rebuild-backend` passed with 687 tests.
  - `./scripts/deploy-compose-to-gcp.sh` deployed
    `1187295f1f89544b1bb4672c2ace35db0541518c`; remote `/healthz` returned
    `{"ok":true}`.
- Production smoke marker `server-smoke-20260531T192030Z`:
  - Sent `我可以对好友做什么操作？`, `我可以直接添加其他好友吗`, then
    `帮我和他约一个2029年1月1日上午八点半的晨跑活动，标题是修复验证晨跑server-smoke-20260531T192030Z`.
  - Turns for the first two inputs were `superseded /
    interrupted_by_newer_inbound`.
  - Command turn replied with `好友相关操作和添加好友目前都暂不支持` and
    `约晨跑的话，"他"是哪位好友?`.
  - Follow-up `是的` replied `好的，已帮你和lizihao创建这个共享提醒`.
  - Shared reminder `8c418dea-287c-46d2-a76a-522e8369c44f` was created
    `active` for `2029-01-01 08:30:00` in `Asia/Shanghai`, then cancelled
    during cleanup.
- Caveat:
  - Synthetic WeChat delivery attempts still failed with
    `ilink_send_failed_ret_-2` because the smoke used a stale connector
    `context_token`. The application behavior, persisted visible output, staged
    command materialization, shared-reminder creation, and cleanup were verified
    in Postgres.
  - Chat cleanup first asked for confirmation and then timed out on the
    confirmation; the marked smoke reminder was cancelled through the same
    production domain service to avoid leaving test data active.
