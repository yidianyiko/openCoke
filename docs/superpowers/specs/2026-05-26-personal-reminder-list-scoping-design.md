---
status: active
created_at: 2026-05-26
owner: design-codex
kind: reminder-design
---

# Personal reminder list scoping design

## Reviewable summary

PR-23 and PR-24 are the same L1 class: personal reminder list requests can be
delegated to `reminder_domain`, but the agent-side list contract cannot carry
the requested scope. The detector/schema, executor, and visible reminder tool
only model `action=list`; they do not model a local date range or title query.
When the detector fails, the reply assembly reports a system problem. If the
detector succeeded today, the tool would still list all active reminders.

The minimal fix is to add query-only list filters to the agent reminder
contract and execute them in the existing Reminder Runtime path. Do not route
agent list traffic through the customer gateway, do not add compatibility
aliases, and do not use prompt-only case patches.

## Evidence reviewed

- Long-tail smoke design:
  `docs/superpowers/specs/2026-05-26-personal-reminder-long-tail-design.md`
- Batch B evidence:
  `artifacts/evidence/shared-reminder-agent-smoke/personal-reminder-time-content-list-20260525t215504Z.json`
- Detector entry:
  `agent/agno_agent/capabilities/reminder_intent.py`
- Executor:
  `agent/agno_agent/adapters/reminder_command_executor.py`
- Customer route:
  `gateway/packages/api/src/routes/customer-reminder-routes.ts`

## Current list path

1. Main Agno runtime exposes `reminder_domain`.
2. The main model calls `reminder_domain`; model-supplied arguments are ignored.
   `run_reminder_domain()` passes the original user text into
   `ReminderIntentPort`.
3. `ReminderIntentPort` can short-circuit a narrow set of explicit list
   phrases, otherwise it asks `ReminderDetectAgent` for a
   `ReminderDetectDecision`.
4. `ReminderCommandExecutor` forwards only the existing command fields to
   `visible_reminder_tool`.
5. `visible_reminder_tool(action=list)` calls
   `runtime.list_visible_reminders(owner_user_id, query=active)`.
6. The command executor stores `summary`, `count`, and reminder facts in a
   read operation.
7. The final reply model answers from the domain result.

The customer API path is separate:

- `GET /api/customer/reminders?from=YYYY-MM-DD&to=YYYY-MM-DD&state=active`
  validates auth, date range, and states.
- It calls gateway `listRuntimeReminders()`.
- The gateway client calls bridge
  `GET /bridge/internal/reminders?customer_id=...&from=...&to=...&state=...`.
- The bridge calls
  `ReminderRuntimeContract.list_visible_reminders_in_local_date_range()`.

## Case trace: PR-23 list today

User asks: `我今天有什么提醒`.

| Layer | Observed behavior | Problem |
| --- | --- | --- |
| Main agent | Calls `reminder_domain` with empty model arguments. | Delegation is correct. |
| Detector pre-check | `_is_explicit_reminder_list_query()` does not match `有什么` or the date word `今天`. | The deterministic list gate is too narrow. |
| Detector schema | The only query shape is `intent_type=query, action=list`. | No field can carry `today` as `from=to=<local today>`. |
| Executor | Not reached in the evidence because the detector returns invalid decision and the domain result asks for `title` and `trigger_at`. | The list query is converted into a create-style clarification. |
| Tool/runtime | If reached, `action=list` would list all active visible reminders. | It would not apply a date range. |
| Gateway | Customer route and bridge route accept date range and states. | This is not the route used by the agent path; route shape is not the immediate failure. |
| Reply assembly | Reports a system problem and does not mention the existing today reminder. | The reply is grounded in the failed domain result, not hallucinated reminder data. |

Root cause: missing agent-side date-range list filter, plus a too-narrow
explicit list detector. The gateway route is not wrong for this case, but its
date-range capability is not exposed through `reminder_domain`.

## Case trace: PR-24 list fuzzy title

User asks: `我设过哪些喝水提醒`.

| Layer | Observed behavior | Problem |
| --- | --- | --- |
| Main agent | Calls `reminder_domain`, first with model arguments containing `query=喝水`. | Delegation is correct, but these arguments are ignored by design. |
| Detector pre-check | `_is_explicit_reminder_list_query()` does not match `设过哪些` or plain `哪些`. | The deterministic list gate misses a common Chinese list phrasing. |
| Detector schema | Query decisions cannot carry a title query. Existing `keyword`/`target_title` are write target selectors and are forbidden for non-crud decisions. | A reasonable detector output like `action=list, keyword=喝水` becomes invalid. |
| Executor | Not reached for a successful list. The first invalid result triggers later duplicate-call failures. | No filtered read operation is produced. |
| Tool/runtime | If reached, `action=list` would list all active visible reminders. | It would not apply title filtering. |
| Gateway | Customer list route has date range and states, but no title query. | This is not the route used by the agent path. Adding gateway title search is not required for PR-24. |
| Reply assembly | Reports a system problem and does not list the existing `喝水` reminder. | The reply is a failure response after detector/tool-call failure, not a hallucinated list. |

Root cause: missing query-only title filter in the detector schema and executor
contract. The follow-on duplicate-call errors are symptoms after the first
invalid domain result.

## Options considered

Recommended: add an agent list filter contract.

- Add query-only list fields to `ReminderDetectDecision`, executor, and
  `visible_reminder_tool`.
- Execute date and title filters in the existing Reminder Runtime path.
- Keep gateway routes unchanged unless a separate customer API title-search
  requirement is accepted.
- This fixes both cases at the correct boundary and keeps read behavior
  testable without adding legacy shims.

Rejected: prompt-only detector tuning.

- Adding examples for these exact phrases may make Batch B pass, but it leaves
  the executor/tool unable to represent filters.
- It would preserve the current hidden contract gap.

Rejected for this bug: route all agent lists through the gateway customer API.

- The agent already owns an in-process Reminder Runtime contract.
- Gateway auth, customer DTO shape, and board route constraints are not needed
  for an internal agent read.
- PR-24 title filtering is not a current customer route feature.

## Proposed minimal contract

Add query-only fields. Names are illustrative; implementation can choose the
nearest local naming style.

```python
list_from_local_date: str | None  # YYYY-MM-DD
list_to_local_date: str | None    # YYYY-MM-DD
list_title_query: str | None      # user phrase such as "喝水"
list_states: list[str] | None     # default ["active"]
```

Rules:

- These fields are allowed only when `intent_type=query` and `action=list`.
- They are forbidden for create/update/delete/cancel/complete.
- Keep write target selectors (`keyword`, `target_title`, `target_local_date`,
  `target_local_time`, `target_rrule`, `target_scope`) write-only.
- Date filters are inclusive local dates in the user's timezone.
- A single-day query sets `from=to=<local date>`.
- Title filtering is conservative: normalize whitespace/case, then match title
  containment. Do not invent semantic synonyms.
- Default states remain `["active"]`.

## Proposed detector changes

1. Extend `ReminderDetectDecision` with query-only list filter fields and
   validation.
2. Update detector instructions so query/list can emit those fields.
3. Extend the explicit list gate to cover general product phrases, not just
   these cases:
   - `有什么提醒`
   - `有哪些提醒`
   - `哪些...提醒`
   - `设过哪些...提醒`
   - English equivalents already covered by model/few-shot can stay model-led.
4. Extract high-confidence date scope from explicit date words in list queries:
   - `今天/今日/今晚/今早` -> current local date
   - `明天/明日` -> current local date + 1
   - Leave broader ranges such as `这周` out of this PR unless the same change
     adds complete range tests.
5. Extract a title query only from bounded phrases such as
   `哪些<query>提醒` and `<query>提醒`. If extraction is ambiguous, let the
   detector decide or return an unfiltered list; do not ask for create fields.

This is a current product parser for read-only list scope, not a compatibility
shim for old prompts.

## Proposed executor and tool changes

1. Include the new list fields in `ReminderCommandExecutor`'s decision field
   set and tool kwargs.
2. Add matching optional parameters to `visible_reminder_tool`.
3. For `action=list`:
   - If a date range is present, call a runtime list method that returns
     reminders due in that local date range.
   - If no date range is present, keep the current active visible list.
   - Apply `list_title_query` after owner/state/date scoping.
   - Return only filtered reminders and a deterministic summary.
4. Keep failed runtime reads as failures. Do not return a fabricated empty list
   on adapter errors.

Date-range semantics need one implementation check: the current bridge
management list uses `schedule.local_date` range filtering. That handles the
PR-23 one-shot evidence, but "today's reminders" should mean occurrences due
today. If recurring reminders are in scope for the implementation PR, the
runtime list should merge one-shot sources with recurrence sources whose
expanded occurrence lands in the requested local date range.

## Proposed reply assembly changes

List replies should be grounded in read facts as strongly as write replies are
grounded today.

- For successful list reads, include a `visible_summary` or equivalent
  deterministic list summary in operation facts.
- `ReplyContract` for list should require the list facts or summary path.
- Empty filtered results should be an executed read with count `0`, not a
  system-error reply.
- The final reply must not mention reminders outside the filtered result.
- The final reply must preserve exact reminder titles from facts.

## Risk analysis

- Over-filtering: title containment can hide relevant reminders if the user
  expects semantic fuzzy matching. Keep the first fix conservative and document
  that synonym matching is out of scope.
- Under-filtering: date-only filtering by `schedule.local_date` misses recurring
  occurrences. Verification must include at least one recurring reminder if the
  implementation claims occurrence semantics.
- Detector fragility: schema support is more important than prompt wording.
  Tests should assert the structured decision and executor kwargs, not only the
  final chat text.
- Reply drift: a successful filtered read can still be paraphrased badly unless
  the reply contract carries required list facts.
- Route drift: gateway and agent list surfaces may diverge. This design avoids
  changing the customer route for PR-23/PR-24; any future title-search customer
  API should be a separate product/API spec.

## Verification plan

Unit and contract tests:

- `tests/unit/test_reminder_detect_structured_output.py`: query/list accepts
  `list_from_local_date`, `list_to_local_date`, and `list_title_query`; rejects
  write selectors on query decisions.
- `tests/unit/agent/test_reminder_intent_capability.py`: `我今天有什么提醒`
  bypasses or normalizes to `action=list` with today's local date range.
- `tests/unit/agent/test_reminder_intent_capability.py`: `我设过哪些喝水提醒`
  normalizes to `action=list` with `list_title_query=喝水`.
- `tests/unit/agent/test_reminder_command_executor.py`: executor forwards list
  filters to the tool and preserves filtered reminder facts.
- `tests/unit/agent/test_visible_reminder_protocol_tool.py`: list with date
  range calls the date-range runtime method; list with title query excludes
  non-matching titles.
- Existing gateway route tests should remain green; no customer route behavior
  should change in this PR.

User-path verification:

- Re-run PR-23 and PR-24 with `GLM-5.1 thinking-off`.
- PR-23 passes only if the reply includes the today reminder, excludes the
  tomorrow reminder, and Mongo has no list-turn writes.
- PR-24 passes only if the reply lists the existing `喝水` reminder, excludes
  the non-matching reminder, and Mongo has no list-turn writes.
- Save fresh evidence under
  `artifacts/evidence/shared-reminder-agent-smoke/`.

Suggested diff-aware routing after implementation:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/agent/test_reminder_command_executor.py \
  tests/unit/agent/test_visible_reminder_protocol_tool.py \
  tests/unit/test_reminder_detect_structured_output.py -v
```

## Out of scope

- Customer API title-search route.
- Broad semantic synonym matching for fuzzy reminder titles.
- Weekly/monthly natural-language range support beyond today/tomorrow list
  scope.
- Prompt-only fixes that do not change the structured list contract.
- Any product code change in this design commit.
