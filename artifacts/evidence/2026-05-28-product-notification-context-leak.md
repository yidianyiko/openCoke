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

Pending.
