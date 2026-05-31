---
kind: incident
status: fixed_pending_deploy
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

## Follow-up UX Gap

After the first production fix, the same user path could answer only
`你目前一共有 28 个提醒。`. That proved the read path worked, but it did not
meet the user expectation for a reminder-list question because the final reply
did not enumerate the reminders.

The follow-up fix tightens the successful `list_reminders` reply contract:

- tool facts include `display_lines` for every active reminder;
- the domain result uses `reply_contract=render_reminder_list`;
- the visible summary is a directly renderable list, not raw JSON only;
- Interaction Agent instructions and the reminder tool doc state that
  count-only answers are incomplete and the final reply must include every
  returned active reminder.

Production smoke of the prompt/tool-contract-only fix still produced
`你现在一共有 28 个提醒。`. The final fix therefore adds a runtime contract
guard in the Interaction Agent: if a successful tool call returns
`reply_contract=render_reminder_list` and the model's final reply does not
contain every returned reminder content, the runtime renders the list directly
from trusted tool facts.

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
- Follow-up focused tests for the reminder tool facts, Agent instructions, and
  composition visible reply pass with the expanded list contract.
- Production smoke
  `codex-reminder-list-detail-smoke-20260531T135815Z` on deployed
  `202d13084e108674958aa6b1ad7e6dc9988a9833` still produced the count-only
  reply, confirming that prompt-only enforcement was insufficient.
- The runtime guard test covers the exact failure mode: a model that calls the
  list tool but returns only `你现在一共有 2 个提醒。` is replaced with a reply
  containing the total count and every reminder line.
