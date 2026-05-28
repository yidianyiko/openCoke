# 2026-05-28 Product Notification Context Leak Evidence

## Production Symptom

- User-facing fallback observed: `系统刚才没能生成回复，请稍后再试一次。`
- Failed production turns were ordinary reminder/todo list requests, including `我有几个提醒` and `我现在有几个待办项`.
- Adjacent general turns such as greetings and time questions returned normal replies.

## Root Cause Evidence

- Gateway persisted and forwarded `metadata.product_notification` for ordinary user turns when recent delivered product notifications existed in the same business conversation.
- Bridge propagated that metadata into worker input.
- Worker runtime treated the presence of `product_notification` as a product-notification delivery turn, which disabled domain tools.
- Agent logs for failed turns showed no visible output after a no-tool run.

## Local Red Tests

```text
pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts -t "does not thread recent product notifications into ordinary reminder list requests" --pool forks --maxWorkers=1
Result before fix: 1 failed, productNotification.findMany was called.

.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_stale_product_notification_context_keeps_domain_tools tests/unit/agent/test_agent_handler.py::test_agent_handler_extracts_product_notification_metadata_for_runtime tests/unit/agent/test_chat_response_instructions.py::test_prompt_ignores_stale_product_notification_context_without_delivery_message_type -q
Result before fix: 3 failed.
```

## Local Green Verification

```text
pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts --pool forks --maxWorkers=1
Result after fix: 36 passed.

.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_handler.py tests/unit/agent/test_chat_response_instructions.py -q
Result after fix: 108 passed.

zsh scripts/check
Result after fix: check passed.

.venv/bin/python -m pytest tests/unit/runner/ tests/unit/agent/ tests/unit/test_clawscale_only_topology.py -q
Result after fix: 635 passed.
```

## Deploy Smoke

```text
./scripts/deploy-compose-to-gcp.sh --restart
Result: Deploy script completed; remote health endpoints and public site verified.

ssh gcp-coke 'cd /home/whoami/coke && docker compose -f docker-compose.prod.yml ps'
Result: coke-agent up, coke-bridge healthy, gateway healthy, mongo/postgres/redis healthy.
```

Production smoke used active route:

```text
coke_account_id: ck_CsFu-A91jbCSBwtizPx1K
display_name: 李梓豪
channel_id: ch_ICWrBoOhpB_3TA65OZwPM
business_conversation_key: bc_6a1019b60fedec4719365fd5
```

Precondition:

```text
Recent delivered product_notifications existed for this account and business conversation within 24 hours.
```

Smoke input through production gateway `routeInboundMessage`:

```text
text: 我有几个提醒
smokeMarker: prod-smoke-20260528T1035Z
```

Smoke result:

```text
ok: true
conversationId: conv_Q6aTCJx3mVTPZFT_nitO9
reply:
你有 5 个提醒：
- 数学课（2026-05-28 20:00）
- 数学课（2026-05-28 20:00）
- 数学课（2026-05-28 20:00）
- 思考会（2026-05-28 21:00）
- 篮球课（2026-05-30 15:30）
```

Persistence and log checks:

```text
messages.metadata ? 'product_notification' for smoke user row: false
agent log: tools=5
agent log: AgentRuntime 完成 (visible_messages=1, status=ok)
agent warning search after deploy: no AgentRuntime 未产出用户可见回复 entries
gateway fallback search after deploy: no new fallback send entries
```
