---
kind: active_issue
status: resolved
surface:
  - agent-runtime
created_at: 2026-05-25
updated_at: 2026-05-25
---

# 2026-05-25 Booking Refusal Text Dropped by Reminder Guardrail

## What Happened

The coach/class booking refusal smoke exposed an empty fallback for direct
booking requests. The model generated safe refusal text, but the runtime
dropped it and sent "我没接住你刚才的意思。你可以换个说法再说一次吗？".

The affected replies were refusal/capability-boundary text such as "我没法帮你
直接约彭教练" plus "可以帮你设个提醒". The unconfirmed durable-write guardrail
classified those offers as unconfirmed reminder writes even though no reminder
had been promised as already created.

After the output guardrail was corrected, a deeper issue appeared in the same
scenario: for `周日下午 3 点帮我约彭教练`, the chat agent called `reminder_domain`
repeatedly, the reminder detector created a real `约彭教练` reminder, and the
final reply still asked the user whether they wanted a reminder. That made the
reply look safe while Mongo contained an unconfirmed hidden write.

## Why It Matters

The user-visible contract for unsupported booking is a clear refusal plus a
redirect to supported Coke capabilities. The false positive converted a correct
refusal into an empty fallback, making the agent appear unable to answer and
masking the real product boundary.

The hidden reminder write is worse: it turns an unsupported booking request
into a durable reminder without user confirmation, while the final text implies
no reminder has been created yet.

## Affected Surfaces

- `agent-runtime`
- `reminder-intent`
- `tools/agent_smoke`

## Evidence

- Failed smoke artifact:
  `artifacts/evidence/shared-reminder-agent-smoke/coach-booking-refusal-coach-booking-refusal-20260525t073749Z.json`
- Mongo `agent_sessions` showed the model produced refusal text for the same
  turns, while `outputmessages` contained the empty fallback.
- Batch `coach-booking-refusal-20260525t075734Z` later contained an active
  Mongo reminder owned by the smoke user:
  `title=约彭教练`, `local_date=2026-05-31`, `local_time=15:00:00`,
  `timezone=Asia/Shanghai`.
- Mongo `agent_sessions` showed `reminder_domain` tool calls before the final
  refusal reply for that turn.
- Focused regression:
  `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -q`

## Current Status

- Resolved locally. The guardrail now allows reminder capability offers inside
  refusal text when there is no completed-write claim.
- Resolved locally. The reminder intent boundary now rejects unsupported
  coach/class booking requests before reminder detection unless the user
  explicitly asks for a reminder.

## Resolution

- Fix commit: included in the scenario commit `smoke(coach-booking-refusal): cover unsupported class booking`.
- The smoke runner now fails when any reminder is written for the refusal-only
  booking prompts.
