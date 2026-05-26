# ADR 0004: Per-Agent Prompt Token Budget Discipline

- Status: accepted
- Date: 2026-05-12

## Context

The reminder_detect role's system prompt grew incrementally from a focused
~600-token instruction to a ~3000-token rule list. The
`build_reminder_intent_input` helper added another ~25 rules to every
per-turn input. With the GLM-5.1 model and `enable_thinking: false`, a
40-case representative subset showed 63.3% raw exact-match accuracy and
**23.3% 120 s LLM stalls** — the model was routinely getting stuck
navigating its own instruction overload.

The repository compensated by adding ~40 Python guard helpers in
`agent/agno_agent/capabilities/reminder_intent.py` (2918 lines). Each new
edge case landed as another `_should_retry_for_*` / `_should_clarify_*` /
`_normalize_*` helper, because adding a Python guard or a prompt rule is
the cheapest immediate action.

A 20-case streamlined-prompt experiment (Phase 0 v2,
`docs/issues/2026-05-12-reminder-detect-model-bake-off.md`) cut the
system prompt to ~600 tokens, dropped the 25 inline rules from the input
builder, and added one explicit AM/PM disambiguation rule. Same model,
same cases: **86.7% exact, 3.3% stall, 0 wrong-time errors**.

The lesson: agent prompt size, not agent count or model choice, was the
load-bearing variable. The single-agent vs multi-agent question is a red
herring — both architectures fail when a single role's prompt is allowed
to grow without bound. The discipline that *was* implicit in the
multi-agent topology (a role per agent, narrow scope per prompt) has to
be made explicit and enforced.

## Decision

Every active runtime prompt surface is bound by an explicit token budget
enforced as a unit test in
`tests/unit/prompt/test_prompt_token_budgets.py`. The registry covers agent
instructions, character/onboarding prompts, few-shot prompt data, and
runtime reply boundaries that are appended outside
`agent/prompt/agent_instructions_prompt.py`.

Initial budgets (approximate-token unit, CJK-aware) from 2026-05-12:

| Role | Budget | 2026-05-12 actual |
|---|---|---|
| `INSTRUCTIONS_REMINDER_DETECT` | 1000 | ~839 |
| `INSTRUCTIONS_ORCHESTRATOR` | 1100 | ~989 |
| `INSTRUCTIONS_CHAT_RESPONSE` | 600 | ~452 |
| `INSTRUCTIONS_POST_ANALYZE` | 400 | ~131 |
| `INSTRUCTIONS_QUERY_REWRITE` | 300 | ~109 |

Current enforced surfaces as of 2026-05-26:

| Surface | Budget | 2026-05-26 actual |
|---|---|---|
| `INSTRUCTIONS_REMINDER_DETECT` | 1000 | ~876 |
| `INSTRUCTIONS_POST_ANALYZE` | 400 | ~108 |
| `INSTRUCTIONS_CHAT_RESPONSE` | 600 | ~452 |
| `INSTRUCTIONS_QUERY_REWRITE` | 300 | ~109 |
| `COKE_SYSTEM_PROMPT` | 2000 | ~1685 |
| `ONBOARDING_PROMPT` | 450 | ~354 |
| `SCHEDULING_SYSTEM_PROMPT` | 750 | ~466 |
| `REMINDER_FEW_SHOTS` | 1200 | ~1119 |
| `USER_VISIBLE_REPLY_BOUNDARY` | 250 | ~199 |
| `DELEGATION_BOUNDARY` | 1200 | ~969 |
| `DOMAIN_EXECUTION_RESULT_CONTRACT` | 250 | ~183 |
| `ASSEMBLED_CHAT_RESPONSE_USER_TURN` | 4200 | ~3537 |
| `ASSEMBLED_CHAT_RESPONSE_FIRST_CHAT` | 4500 | ~3899 |
| `ASSEMBLED_CHAT_RESPONSE_REMINDER_FIRE` | 4200 | ~3607 |
| `ASSEMBLED_POST_ANALYZE_WITH_FOLLOWUP` | 1800 | ~1647 |
| `ASSEMBLED_POST_ANALYZE_SKIP_FOLLOWUP` | 1400 | ~1283 |

Adding a rule to any prompt that pushes it over budget is a CI failure.
To merge such a change one of the following must happen:

1. Find a rule that can be removed in the same change (replacement,
   not addition).
2. Move the rule into the structured few-shot data set
   (`agent/prompt/reminder_few_shot.py` and analogues), which is loaded
   into the per-turn input, not the system prompt.
3. Move the rule into a corpus expectation with a severity tier (after
   the corpus has tiering, planned follow-up).
4. Split the role into a focused sub-agent. This is the escalation path
   for genuine new scope, not the default.

Budget numbers are ceilings, not measurements. The CI gate also requires
at least 5% headroom under each ceiling. Budgets are revisited only when
(a) a new model needs explicit budget headroom or (b) a role's scope
changes structurally — never to accommodate prompt sprawl.

## Consequences

### Positive

- Reminder_detect raw accuracy jumps from 63.3% to 86.7% on the
  representative subset just by enforcing a smaller prompt. The 23.3%
  stall rate falls to 3.3%. Production effective accuracy (after
  guards) is therefore expected to be higher than current.
- "Add a rule" is no longer the cheapest fix. Adding a few-shot
  example or a corpus expectation is.
- Future model swaps are cheaper: a smaller prompt is easier to
  re-tune than a 3000-token rule list. We no longer need to re-test
  every prompt rule against every candidate model.
- The implicit "multi-agent enforced narrowness" benefit is preserved
  without paying the runtime cost of multiple LLM calls per turn.

### Tradeoff

- The budget numbers are educated guesses. The approximate-token unit is
  not exact. If we need precise budget control later we'll add `tiktoken`
  or similar.
- Some edge cases that current Python guards handle will need new
  few-shot data or corpus expectations to stay covered. This is a
  one-time migration, not a recurring tax.
- A team member adding a rule under time pressure may compress wording
  to stay under budget rather than think harder about whether the rule
  belongs in few-shot or corpus. The CI gate detects token overflow,
  not "the spirit of the rule has been preserved while the words got
  shorter." Code review still matters.

### Follow-up

- Tighten assembled prompt ceilings after the next character-prompt or
  delegation-boundary diet. The representative `build_chat_response_instructions()`
  user-turn, first-chat, and reminder-fire scenarios are now covered.
- Tighten post-analyze assembled prompt ceilings after the next
  follow-up-planning prompt diet. Both with-followup and skip-followup
  paths are now covered.
- Keep dieting the largest active prompts (`COKE_SYSTEM_PROMPT` and
  `REMINDER_FEW_SHOTS`) when touching them. They remain under the 95%
  headroom gate but are still close enough to deserve review.
- Add a corpus-severity field to
  `scripts/reminder_normal_path_expectations.json` so CI can tier its
  enforcement (`critical` 100%, `important` ≥95%, `nice` ≥80%) instead
  of demanding 100% pass on 350+ cases.
- Audit the 40 Python guard helpers in
  `agent/agno_agent/capabilities/reminder_intent.py`. With the prompt
  diet many of them now fire on near-zero cases and can be removed.
  The `_should_retry_for_missing_scheduled_clauses` interaction with
  today-task-range cases (see xfail in
  `tests/unit/agent/test_reminder_intent_capability.py`) is the first
  thing to revisit.
- If, despite the discipline, a role still cannot fit in budget after
  honest pruning, that is the trigger to split it into a sub-agent.
  Not before.

## Escalation: when budget discipline is not enough

This ADR explicitly chooses the discipline path over reverting to the
deterministic multi-agent runtime (`team_runtime` / `selector` /
`plan_parser`, retired in `feature/single-agent-native-toolcalling`).
That option remains on the table as a fallback: if a role's prompt
budget cannot be respected without losing necessary behavior, AND moving
to a sub-agent does not help, the multi-agent runtime is the more
expensive but structurally stricter answer.
