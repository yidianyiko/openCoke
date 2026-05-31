---
kind: incident
status: fixed_pending_deploy
surface: conversation-runtime, reminder, interaction-agent
created: 2026-05-31
---

# Reminder List Query Returned Unsupported Tool Failure

## What Happened

A user asked `现在我一共有几个提醒？`. The turn completed as
`replied / reply_ready`, but the visible reply said Coke could not query the
complete reminder list.

Production Agno run evidence showed the Semantic Interpreter correctly routed
the turn as `reminder_op / list_reminders`, and the Interaction Agent called
`reminder_tool` with `operation=list_reminders`. The tool returned
`unsupported_reminder_operation`, so the Interaction Agent reported failure.

## Why It Mattered

The product state was available in Postgres: the affected account had active
reminders that could be counted with the repository read model. The failure was
an adapter contract gap between semantic routing and the reminder tool exposed
to the Interaction Agent.

## Fix

- `ReminderToolAdapter` now supports the read-only `list_reminders` operation.
- The operation returns `owner_account_id`, active reminder `count`, and
  structured active reminder facts without opening a write guard.
- The Interaction Agent instructions and reminder tool doc now explicitly
  route reminder list/count requests to `list_reminders`.
- The integration user path covers a reminder count question flowing through
  the turn runner and real reminder tool adapter.

## Evidence

- Focused tests failed before implementation because `list_reminders` was not
  exposed or supported.
- Focused tests and the composition integration path pass after implementation.
- Deployment and production smoke evidence should be appended after rollout.
