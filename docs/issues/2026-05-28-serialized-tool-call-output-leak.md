---
kind: incident
status: resolved
surface: agent-runtime
owner: agent
created_at: 2026-05-28
resolved_at: 2026-05-28
---

# Serialized Tool Call Output Leak

## What Happened

At 2026-05-28 00:30:13 UTC, the production reminder scheduler fired an
internal follow-up for account `ck_SXk_J0U0V5JKcK09QHEuo` (`olivers`). The
agent runtime returned serialized MiniMax tool-call markup as final assistant
text:

```text
<minimax:tool_call>
<invoke name="scheduling_domain">
<parameter name="_model_supplied_args">{"intent": "list_shared_reminders"}</parameter>
</invoke>
</minimax:tool_call>
```

The runtime treated that markup as visible text and the reminder event handler
wrote it to `outputmessages` as a push message.

## Why It Mattered

Tool-call transport markup is internal protocol data. It must never be sent as
user-visible text.

## Root Cause

`reminder.fired` runtime turns do not expose interactive tools. When the model
nevertheless emitted MiniMax tool-call markup as plain text, the visible-output
parser had no guard for serialized tool-call artifacts. Because the text was
non-empty and not a supported multimodal envelope, it was accepted as a visible
message.

## Fix

The runtime now fails closed when visible text contains serialized tool-call
markers such as `<minimax:tool_call>`, `<invoke name=...>`, or the
`_model_supplied_args` parameter wrapper. In that case it returns no visible
messages and records `serialized_tool_call_output` instead of allowing the
reminder event handler to write a user-visible output.

## Evidence

- Production log: `2026-05-28 00:30:13` wrote output message
  `6a178c954c81eda22f969ea9` for reminder
  `6a1707b51e70f8484c19b1ff`.
- Production Mongo showed the output belonged to `olivers` and contained the
  serialized `scheduling_domain` tool call.
- Regression test first failed because the runtime produced one visible
  message containing the tool-call markup.
- After the fix:
  `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/runner/test_reminder_event_handler.py -q`
  passed with 65 tests.
