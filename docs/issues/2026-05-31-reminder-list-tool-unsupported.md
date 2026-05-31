---
kind: incident
status: fixed_deployed
surface: conversation-runtime, reminder, interaction-agent
created: 2026-05-31
fixed_commit: ba4c005cc4e2aa220e6fd9b2fd3bfac3f24ec58a
deployed_sha: ba4c005cc4e2aa220e6fd9b2fd3bfac3f24ec58a
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
- `scripts/deploy-compose-to-gcp.sh` deployed
  `ba4c005cc4e2aa220e6fd9b2fd3bfac3f24ec58a`; remote `.deployed-sha` matches
  that commit.
- Production `docker compose ps` showed `coke-api` healthy and worker, outbox
  relay, and scheduler up after deployment.
- Production direct tool check returned `ok=True`, `action=list_reminders`, and
  `count=28` for the affected account.
- Production user-path smoke
  `codex-reminder-list-smoke-20260531T133138Z-retrybody` completed turn
  `9d6bf3e5-780c-4f4a-a010-49f4bf6ebeca` as `replied / reply_ready`; outbound
  message `d109fd5f-4b48-4ee7-bcff-6527991411ee` said
  `你目前一共有 28 个提醒。` and provider delivery status was `sent`.
