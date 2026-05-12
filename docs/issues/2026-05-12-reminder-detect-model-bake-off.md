---
kind: verification_report
status: resolved
surface:
  - worker-runtime
created_at: 2026-05-12
updated_at: 2026-05-12
---

# 2026-05-12 reminder_detect Model Bake-Off And Lock

## What Happened

Following a review of `agent/agno_agent/capabilities/reminder_intent.py` (2918
lines, 40 `_should_*` / `_normalize_*` / `_drop_*` guard helpers; recent
20+ commits all adding new edge-case patches), we suspected the
`reminder_detect` role's choice of `Pro/zai-org/GLM-5.1` with
`enable_thinking: false` was forcing the guard-accumulation cycle.

To verify before locking the model selection, we ran a curated 20-case
subset against four candidates and graded raw `intent_type` against the
existing corpus expectations.

## Why It Matters

The `reminder_detect` role is the hot path on every inbound message. Its
raw decision quality determines how much policy guarding the rest of
`reminder_intent.py` has to do. A wrong model choice locks us into either
unbounded guard accumulation, broken latency, or wrong-direction failures
that no current guard catches. The user requested this be the **final**
model-selection round; future changes only on a newer model release.

## Affected Surfaces

- `worker-runtime` (specifically `agent/agno_agent/capabilities/reminder_intent.py`
  and `conf/config.json` `llm.roles.reminder_detect`)

## Evidence

- Subset selection script: `scripts/_curate_compare_subset.py` →
  `scripts/_reduce_subset.py`
- Comparison runner: `scripts/compare_reminder_detect_models.py`
- Baseline runner: `scripts/_baseline_glm_thinking_off.py`
- Subset (20 cases): `artifacts/evidence/reminder-model-compare/2026-05-12-subset-20.json`
- Results — V4-Flash + Kimi: `artifacts/evidence/reminder-model-compare/2026-05-12-results-20.json`
- Results — GLM thinking-off baseline: `artifacts/evidence/reminder-model-compare/2026-05-12-baseline-glm-thinking-off.json`
- Method: each candidate built a fresh `Agent` with the role config swapped
  in-memory, ran each case through `build_reminder_intent_input` + agent
  `arun`, graded `decision.intent_type` against
  `scripts/reminder_normal_path_expectations.json`. No Mongo, no worker,
  no message routing.

## Findings

### Four-way summary (20 cases, balanced across 16 guard buckets)

| Model | Pass | Rate | Mean latency | Failure direction | Monthly cost est. |
|---|---|---|---|---|---|
| **GLM-5.1 thinking-off** (current prod) | 16/20 | 80% | **7.5 s** | over-eager (crud-when-should-clarify) | ~¥900 |
| Kimi-K2.6 | 18/20 | 90% | 32.5 s | over-cautious (clarify-when-should-crud) | ~¥954 |
| DeepSeek-V4-Flash Think-High | 14/20 | 70% | 28.0 s | over-eager + 1 × 180 s timeout | ~¥108 |
| GLM-5.1 thinking-on (aborted 17/40) | 13/17 | ~76% | 90–180 s, frequent timeouts | thinking chain truncated JSON output | ~¥3000+ |

Cost estimates assume ~60 MAU × 10 turns/day, ~4K input / ~1K output
tokens per turn.

### Failure-direction analysis (the decisive factor)

- GLM-5.1 thinking-off and V4-Flash both fail **over-eager**: they
  execute a `create` when the input lacks a title, time, or both. This
  is exactly the failure mode the existing `_should_clarify_date_only_create`,
  `_should_clarify_status_only_content_create`, etc. guards in
  `reminder_intent.py` were built to catch. In production, those guards
  intercept these and convert them to clarifications. The raw 80 % rate
  is therefore an underestimate of effective production pass rate.
- Kimi-K2.6 fails **over-cautious**: it clarifies on cases where the
  user already supplied a concrete time and a short noun title
  (e.g. `10:30 提醒我工作` → asks "提醒做什么工作？" instead of creating
  `工作` at 10:30). There is no `_should_force_crud_*` guard. Kimi's two
  raw fails would surface to users in production.
- GLM-5.1 with `enable_thinking: true` was the worst path: the long
  thinking chain corrupted structured-output JSON
  (`Failed to parse cleaned JSON: Expecting ',' delimiter: line 1 column 16311`)
  and pushed multiple cases past the 180 s ceiling.

### Quality-vs-latency trade-off

| Metric | GLM-5.1 thinking-off | Kimi-K2.6 |
|---|---|---|
| Raw pass | 80 % | 90 % (+10 pp) |
| Latency (median ish) | 7.5 s | 32.5 s (4.3 ×) |
| Failure direction | guards already catch | no guard exists |
| Effective production pass | likely ≥95 % | likely ~90 % (raw fails leak) |

The 10 pp raw gain inverts after accounting for existing guard coverage:
GLM-5.1 thinking-off + guards ≥ Kimi raw.

## Decision

**Keep `Pro/zai-org/GLM-5.1` with `enable_thinking: false` for the
`reminder_detect` role. No `conf/config.json` change.**

Reasoning:

1. Effective production pass rate (with existing guards) is at least as
   high as Kimi's raw 90 %, probably higher.
2. Latency 7.5 s vs 32.5 s is a meaningful UX gap on a per-turn hot
   path.
3. Kimi's failure direction (over-cautious) is not covered by the
   current guard library and would require new code, contradicting the
   stated goal of stopping guard accumulation.
4. V4-Flash is cheaper but quality is worse and its failure direction
   is the same as the current model — no structural benefit.
5. Per the user's explicit lock policy, we only revisit when a newer
   model is released (e.g. GLM-6, Kimi-K3, DeepSeek-V5).

## Resolution

- No model change applied.
- This report serves as the durable lock record. Future agents reading
  `agent/agno_agent/capabilities/reminder_intent.py` should treat
  `Pro/zai-org/GLM-5.1` + `enable_thinking: false` as a deliberate
  decision, not a default to question.

## Follow-up: Phase 0 v2 streamlined prompt experiment (same day)

After locking the model, a separate question emerged: were the ~40
Python time-handling helpers in `reminder_intent.py` over-engineering?
We measured the raw GLM-5.1 thinking-off time-accuracy on a 30-case
subset (with `expected_creates.local_time`):

| Variant | Exact | Stall | Wrong-time | Median latency |
|---|---|---|---|---|
| v1 production prompt (~3000 token system + ~1000 token inline rules) | 19/30 (63.3%) | 7/30 (23.3%) | 3 (12 h offsets) | high, frequent 120 s |
| v2 standalone (~600 token system, no inline rules, no few-shots, explicit AM/PM rule) | 26/30 (86.7%) | 1/30 (3.3%) | 0 | ~6-15 s |
| **v2 production after swap** (~839 token system, no inline rules, **few-shots retained** in input) | **25/30 (83.3%)** | **3/30 (10.0%)** | **1** | ~5-15 s |

The same 4 cases that failed under v1 (case 31, 110, 115, plus several
"晚上 X 点" timeouts) passed exactly under v2 standalone. The helpers
are still load-bearing for AM/PM disambiguation and time-math precision —
deletion is not viable — but the prompt was overwhelming the model, not
the absence of helpers.

**Production-path verification gap**: when the same v2 prompt was applied
to `agent/prompt/agent_instructions_prompt.py` and rerun against the same
30-case subset, exact-rate dropped to 25/30 (83.3%) — better than v1 by
+20 pp but worse than v2 standalone by -3.4 pp. The difference is that
the production `build_reminder_intent_input` still emits the few-shot
decision examples (~1 K tokens) on every per-turn input. v2 standalone
dropped few-shots entirely. The few-shots may help intent classification
on edge cases but appear to hurt raw time accuracy by inflating the
per-turn prompt back toward the size that overwhelms GLM-5.1
thinking-off. Quantifying the few-shot tradeoff is an explicit
follow-up.

Evidence:

- `artifacts/evidence/reminder-model-compare/2026-05-12-phase0-time-accuracy.json`
  (v1 baseline)
- `artifacts/evidence/reminder-model-compare/2026-05-12-phase0-v2-streamlined-prompt.json`
  (v2 result)
- `scripts/_phase0_time_accuracy.py`, `scripts/_phase0_v2_streamlined_prompt.py`

## Architectural reflection: prompt budget vs multi-agent runtime

The merge `feature/single-agent-native-toolcalling` (commit `7a8ca61`,
2026-05-09) retired the multi-agent runtime (`team_runtime.py`,
`plan_parser.py`, `selector.py`). The merge's stated benefit was
simpler runtime + lower latency. What was given up was the
**structural enforcement of narrow scope per agent prompt** — a single
big agent has no architectural pressure to keep its prompt small.

Phase 0 v2 evidence: the right discipline is **per-agent prompt budget**,
not "go back to multi-agent". The tool-mediated multi-agent pattern
(main agent → tool wrapper → sub-agent) preserves narrow boundaries
without paying the runtime cost. The lost discipline can be restored as
an explicit CI-enforced budget rather than as architecture.

This decision is recorded in ADR 0004
(`docs/adr/0004-per-agent-prompt-budget-discipline.md`).

## Forward changes applied 2026-05-12

1. `agent/prompt/agent_instructions_prompt.py`:
   `INSTRUCTIONS_REMINDER_DETECT` replaced with streamlined v2 (~839
   approximate tokens, down from ~3000+).
2. `agent/agno_agent/prompts/reminder_intent.py`:
   `build_reminder_intent_input` no longer emits the 25-rule "Workflow
   Boundary" block; the same rules now live (compressed) in the system
   prompt.
3. `tests/unit/prompt/test_prompt_token_budgets.py`: new CI gate
   enforces per-role budgets per ADR 0004.
4. `tests/unit/prompt/test_agent_instructions_prompt.py` and
   `tests/unit/agent/test_reminder_intent_capability.py`: assertions
   updated for v2 content (no longer encoding the legacy 25-rule list
   as test fixtures).
5. `test_reminder_intent_port_retries_today_time_range_recurring_compression`
   was xfail at the time of commit 8d2a968; fixed in a follow-up commit
   by making `_explicit_scheduled_clause_count` collapse `HH:MM-HH:MM`
   ranges to the start clock, so today-task-range retries no longer
   cascade into `_should_retry_for_missing_scheduled_clauses`.

## What This Test Did Not Prove

- Effective production pass rate **with** the full guard cascade was
  not measured. The raw-vs-effective gap is inferred, not observed.
- Costs are nominal estimates from SiliconFlow's listed prices; actual
  bills depend on tokenization and thinking-budget behavior.
- The 20-case subset covers 16 guard buckets but does not exhaust the
  full 350+ corpus. Final regression should be run against the full
  corpus only at the next major change.
- ADR 0004's approximate-token budget is not tokenizer-exact and can
  drift up to ~10% from real LLM token counts. Tighten only if a real
  regression slips past it.
