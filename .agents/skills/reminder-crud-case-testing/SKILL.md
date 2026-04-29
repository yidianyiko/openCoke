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

- Do not add case-local `Avoid X` prompt rules as the first response to a failing case. Prefer a positive decision boundary or a smaller tool instruction that covers a class of inputs.
- Do not add `title_variants` as the first response to a title mismatch. First check whether punctuation, quote style, whitespace, leading verbs, or semantic containment should be handled by the shared title validator.
- Fixture `evaluation_expectation` overrides are appropriate when the case data should classify the request as CRUD, clarification, query, capability, or discussion. Keep the reason explicit.
- After a run of case fixes, produce a drift report before continuing if prompt constraints or title aliases are growing quickly.

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
