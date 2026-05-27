# Personal Reminder Create Routing Evidence

Date: 2026-05-27

Scope:

- Removed capability-level create/update repair from `ReminderIntentPort`.
- Moved the remaining create-vs-update guard to ReminderDetect prompt/schema.
- Kept runtime failed-write success-claim guard from the previous deployed fix.

Red tests before implementation:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_schema_rejects_create_with_reminder_id \
  tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_schema_rejects_batch_create_operation_with_reminder_id \
  tests/unit/test_reminder_detect_structured_output.py::test_reminder_detect_reminder_id_schema_limits_ids_to_existing_context \
  tests/unit/prompt/test_agent_instructions_prompt.py::test_reminder_detect_instructions_own_create_routing_and_id_source \
  -q
```

Result: 4 failed. Existing schema accepted create decisions with
`reminder_id`, and ReminderDetect instructions did not state create-routing or
id-source ownership.

Focused green tests:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_reminder_detect_structured_output.py \
  tests/unit/prompt/test_agent_instructions_prompt.py \
  tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_routes_referential_relative_delay_update_from_detector \
  tests/unit/agent/test_agent_runtime_output_rules.py::test_failed_reminder_domain_result_blocks_created_claim \
  -q
```

Result: 47 passed.

Capability regression file:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -q
```

Result: 105 passed.

Diff checks:

```bash
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Results:

- `git diff --check`: passed.
- Suggested surfaces: `repo-os-docs worker-runtime`.
- `review-trigger`: `human_review_required: no`; risk triggers were
  `sensitive_repo_os_change` and evidence-path expectations.

Surface verification:

```bash
zsh scripts/verify-surface repo-os-docs worker-runtime
```

Result: passed.

- `scripts/check`: passed.
- `tests/unit/runner/`: 69 passed.
- `tests/unit/agent/`: 536 passed.
- `tests/unit/test_clawscale_only_topology.py`: 7 passed.
