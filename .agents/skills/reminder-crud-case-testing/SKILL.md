---
name: reminder-crud-case-testing
description: Use when testing Coke reminder CRUD corpus cases, especially one-case-at-a-time reminder creation, update, cancel, or complete flows through the local agent worker.
---

# Reminder CRUD Case Testing

## Purpose

Run reminder corpus cases through the real local agent path with bounded waits. Do not continue to later cases when a case exposes a product or harness bug; fix and verify the current case first.

## Required Runtime

Use the project-standard local agent runtime:

```bash
./start.sh --mode pm2 --force-clean --skip-install
pm2 status
```

If only code changed after PM2 was already started, reload the agent:

```bash
./pm2-manager.sh restart coke-agent
```

Confirm `coke-agent` is online and `agent/runner/agent_runner.py` is the running process. Bridge/gateway HTTP listeners are not required for this harness; the harness simulates ClawScale request-response inbound messages by writing Mongo `inputmessages`.

## One-Case Loop

Run exactly one JSON case at a time, in corpus order:

```bash
python scripts/eval_reminder_normal_path_cases.py \
  --offset <case_index> \
  --limit 1 \
  --case-timeout-seconds 120 \
  --transport business-clawscale \
  --output /tmp/reminder-normal-case-<case_index>.json
```

Rules:

- Treat `--case-timeout-seconds` as a hard per-case budget. A timeout is a failed case, not a reason to wait indefinitely.
- Validate only reminder CRUD state and the user-visible reply. Do not test reminder firing/publication in this loop.
- Pass criteria: input reaches `handled`, expected reminder CRUD effects are present, no duplicate reminders are created, active reminders have `next_fire_at`, and the reply accurately acknowledges the CRUD action.
- After every completed case, save any needed evidence and clear historical agent logs before the next case so old lines cannot pollute the next diagnosis.
- Stop immediately on any failure or suspicious duplicate output/reminder. Diagnose logs and Mongo state, fix the root cause, restart PM2 if runtime code changed, rerun the same case, then proceed.
- Do not run 32-way batches until one-case execution is stable.
- After each code change, run the relevant tests and commit the verified change before continuing to later cases.

## Drift Guardrails

Do not let normal-path fixes become another case-by-case parser.

- LLM-first: reminder create/update/delete/complete decisions must come from
  ReminderDetectAgent or its LLM retry path, not Python NLU.
- ReminderDetectAgent and ReminderDetectRetryAgent must keep a structured
  intent boundary: `intent_type` is one of `crud`, `clarify`, `query`, or
  `discussion`, and only CRUD results may carry reminder write fields. Clarify,
  query, discussion, and commitment-style free text must have no reminder fields
  the runtime could treat as executable.
- Do not add deterministic Python reminder-create fallbacks, regex parsers, or
  hard-routed reminder replies to pass a single corpus case.
- If a detector timeout needs a fallback, use a shorter-context LLM retry that
  can still decide to clarify or do nothing; timeout is not permission to create.
- If a detector response violates the structured schema, do not repair fields in
  Python. Record the invalid structured output and retry with the shorter-context
  LLM path; if retry also fails, leave the reminder unexecuted for chat
  clarification.
- Date-only or time-missing create requests should clarify unless the product
  has an explicit default-time policy.
- Isolate eval identities by batch and case. Do not reuse corpus `from_user` as
  the runtime `from_user`; keep it only as trace metadata so profile/memory
  updates from one case cannot pollute another.
- Resolve failures in this order: tighten schema field constraints first, add
  fixture counterexamples/classification second, and improve the LLM judge third.
  Do not add case-local `Avoid X` prompt rules as the first response to a failing
  case. Prefer a positive decision boundary or a smaller tool instruction that
  covers a class of inputs.
- Do not add `title_variants` as the first response to a title mismatch. First check whether punctuation, quote style, whitespace, leading verbs, or semantic containment should be handled by the shared title validator.
- Fixture `evaluation_expectation` overrides are appropriate when the case data should classify the request as CRUD, clarification, query, capability, or discussion. Keep the reason explicit.
- Keep `agent/prompt/chat_contextprompt.py::CONTEXTPROMPT_提醒未执行` short
  and positive: at most 25 non-empty lines, no phrase blacklist, no cadence
  sub-protocol. Move concrete bad phrases, counterexamples, and corpus-specific
  expectations to `scripts/reminder_normal_path_expectations.json` or a dedicated
  fixture.
- Treat prompt changes like code changes: prefer compact positive boundaries that describe a class of inputs and expected decision, and add prompt tests for that boundary. Do not let the prompt accumulate one-case `Avoid X` clauses or narrow examples as a substitute for improving the decision boundary.
- `scripts/eval_reminder_normal_path_cases.py::output_implies_unconfirmed_reminder`
  must remain an LLM judge boundary, not a handwritten regex blacklist. If it is
  wrong, fix the judge rubric or fixture evidence rather than adding more regex
  phrases.
- Clarification-output detection in the normal-path eval must also stay on an
  LLM judge boundary. Do not grow `output_mentions_clarification` with more
  natural-language regex phrases; fix schema constraints, fixture
  classification/counterexamples, or the judge rubric instead.
- Treat title matching as shared evaluation policy. Add `title_variants` only when the variant is a legitimate semantic paraphrase that the shared normalizer cannot reasonably infer; otherwise improve the normalizer or expected-title rule once for the class.
- For cancellation/stop/no-disturb requests, route the turn to ReminderDetectAgent and let the LLM decide whether to delete or clarify. Do not convert broad quieting language into a create request or ask for create time/content.
- Every change to `chat_contextprompt.py`, ReminderDetectAgent instructions, or
  reminder detect schemas requires `pytest tests/evals/test_reminder_normal_path_eval.py -q`
  plus the full normal-path eval before merging or resuming the corpus loop.
- After a run of case fixes, produce a drift report before continuing if prompt constraints or title aliases are growing quickly.

## Refactor And Observability Debt

These are not blockers for the one-case loop, but they are the direction for
cleanup work when failures start repeating.

- `agent/agno_agent/tools/reminder_protocol/tool.py` should stay an adapter:
  argument validation, service call, and tool-result formatting. Keyword
  resolution, batch dedupe, schedule parsing, and action semantics belong in
  `ReminderService` or a domain layer under it.
- `set_reminder_session_state`/ContextVar injection is fragile. Future reminder
  tool refactors should move toward explicit runtime context parameters rather
  than hidden ambient state.
- Remove stale reminder tool directories or caches when they are no longer part
  of the package surface, for example an empty `agent/agno_agent/tools/reminder/`.
- If `_validate_reminder_decision_evidence` keeps growing, convert it into a
  rule registry: each rule is a small callable with a stable reason string and
  focused tests. Do not keep inserting unrelated `if return "..."`
  branches into one long validator.
- Watch for one-off Chinese phrase rules in prompts, validators, title matching,
  and judges. If fixes start naming narrow phrases, stop and look for a schema
  boundary, fixture classification, or semantic judge improvement that covers
  the class.
- Track normal-path eval quality with latency and routing metrics, not only
  pass/fail: p95 latency, detector timeout rate, retry rate, clarification rate,
  CRUD/clarify/query/discussion intent accuracy, and LLM judge timeout rate.
- Use structured ReminderDetect logs as a feedback loop: sample real invalid
  decisions and timeouts, add durable fixture counterexamples, then improve
  schema/prompt/judge boundaries in that order.

Drift report:

```bash
python - <<'PY'
import json, re
from pathlib import Path
data=json.loads(Path('scripts/reminder_normal_path_expectations.json').read_text())['cases']
variant_cases=[k for k,v in data.items() if any(c.get('title_variants') for c in v.get('expected_creates') or [])]
variant_count=sum(len(c.get('title_variants') or []) for v in data.values() for c in v.get('expected_creates') or [])
print('fixture_overrides', len(data))
print('title_variant_cases', len(variant_cases), variant_cases)
print('title_variants', variant_count)
for path in ['agent/prompt/agent_instructions_prompt.py','agent/prompt/chat_contextprompt.py']:
    text=Path(path).read_text()
    print(path, 'negative_constraints', len(re.findall(r'\\b(?:Avoid|avoid|Do not|do not|Never|never)\\b|不要|禁止', text)))
PY
```

## Debug Checks

For a stuck or failed case, inspect the batch id from the result JSON:

```bash
python - <<'PY'
from pymongo import MongoClient
from conf.config import CONF
client=MongoClient('mongodb://'+CONF['mongodb']['mongodb_ip']+':'+CONF['mongodb']['mongodb_port']+'/', tz_aware=True)
db=client[CONF['mongodb']['mongodb_name']]
bid='<batch_id>'
print(list(db.inputmessages.find({'metadata.batch_id': bid})))
print(list(db.outputmessages.find({'metadata.batch_id': bid})))
PY
```

Search logs with secrets redacted:

```bash
rg -n "<batch_id>|Traceback|ERROR|WARNING|Phase|Reminder" logs/agent-error.log logs/agent-out.log -S \
  | tail -n 200 \
  | sed -E 's/(Bearer )[A-Za-z0-9._~+\/=-]+/\1[REDACTED]/g; s/(sk-[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+/\1[REDACTED]/g'
```

After preserving the needed excerpt, clear the runtime logs:

```bash
: > logs/agent-error.log
: > logs/agent-out.log
```

## Regression Tests

After harness or reminder-runtime changes, run focused tests before rerunning live cases:

```bash
pytest tests/evals/test_reminder_normal_path_eval.py -v
pytest tests/unit/agent/test_agent_handler.py::test_handle_message_finishes_sync_business_text_after_first_reply -v
```
