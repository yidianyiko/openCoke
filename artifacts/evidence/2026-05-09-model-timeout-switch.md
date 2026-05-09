# 2026-05-09 Model Timeout Switch Evidence

## Scope

- Switched local and deploy LLM role config away from `deepseek-ai/DeepSeek-V4-Flash` for `chat_response` and `prepare_fast`.
- Kept SiliconFlow-backed role configs and set `reminder_detect` to `Pro/MiniMaxAI/MiniMax-M2.5`.
- Added Agno `tool_call_limit=4` to the single-agent runtime to bound native tool-call loops.
- Added fail-closed reminder-result handling for invalid detector output and failed reminder tool results.

## Focused Runtime Evidence

PM2 restart:

```text
./pm2-manager.sh restart coke-agent
coke-agent pid=1588033 status=online
```

Business ClawScale real-path cases:

```text
.venv/bin/python scripts/eval_reminder_normal_path_cases.py --offset 116 --limit 1 --case-timeout-seconds 120 --transport business-clawscale --batch-id reminder-case116-minimax-toollimit-20260509-01 --output /tmp/reminder-case116-minimax-toollimit-20260509-01.json
summary: total=1 passed=1 failed=0
elapsed_seconds: 6.012
output: normal user-visible schedule acknowledgement
reminders: []
```

```text
.venv/bin/python scripts/eval_reminder_normal_path_cases.py --offset 146 --limit 1 --case-timeout-seconds 120 --transport business-clawscale --batch-id reminder-case146-minimax-toollimit-20260509-01 --output /tmp/reminder-case146-minimax-toollimit-20260509-01.json
summary: total=1 passed=1 failed=0
elapsed_seconds: 12.023
output: 创建提醒失败：这个提醒时间已经过去了，请告诉我一个未来的时间。
reminders: []
```

Log check after case146:

```text
No Agent runtime timed out, Traceback, ERROR, Api key is invalid, or fallback output.
ReminderDetect emitted a schema warning, but AgentRuntime completed with visible_messages=1 and status=ok.
```

## Test Evidence

```text
.venv/bin/python -m pytest tests/unit/agent/test_model_factory.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_command_executor.py tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_reminder_detect_structured_output.py -q
83 passed in 22.28s
```

```text
zsh scripts/verify-surface worker-runtime deploy
tests/unit/runner/: 100 passed
tests/unit/agent/: 169 passed
tests/unit/test_clawscale_only_topology.py: 7 passed
scripts/test-deploy-compose-to-gcp.sh: PASS
scripts/check: check passed
```
