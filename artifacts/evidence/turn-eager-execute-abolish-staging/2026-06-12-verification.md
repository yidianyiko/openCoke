# Turn Eager Execute Abolish Staging Verification

Date: 2026-06-12
Branch: `turn-eager-execute-abolish-staging`
Base checked: `main`

## Review Conclusion

The spec should not be abandoned. The feature branch is the correct place for the
work, and the main branch still has the old staged-command design. The main gap
found during review was that the branch needed the reminder temporal contract
integrated before it could be judged against the B2 no-staging design.

The stale failing expectations were:

- timed user-visible reminders without a user-provided duration expected a
  silent 15 minute default;
- shared-reminder detector tool calls expected `duration_minutes: 15` even when
  the user did not provide a duration.

Those expectations conflict with the current temporal contract. Timed
calendar-visible reminders need an explicit or inferred positive duration. The
15 minute storage fallback remains valid for no-trigger, proactive, or internal
storage cases, not as a silent user-visible default.

## Implementation State

- Cherry-picked `451e4e6e9394ac9346cdde8705d16af200f5bc61` as
  `244cd524 fix(reminders): enforce temporal create contract`.
- Skipped cherry-picking `c906bcd9 test(reminders): align handler duration
  expectations` because it conflicted by reintroducing old
  `resolve_and_stage`/staged handler tests. The current branch already carries
  B2 handler tests for the duration contract.
- Updated smoke/probe scripts so verdicts rely on row effects and real
  state-change calls, not `staged_command` rows.
- Updated `docs/ARCHITECTURE.md` to say Execute calls real domain services in
  the shared turn transaction and Close commits domain writes, outbound rows,
  disposition, and close state atomically.
- Marked the 2026-06-10 spec's close/materialization pieces as superseded by
  the 2026-06-12 no-staging spec.
- Kept runner recovery behavior aligned with the B2 plan: pipeline failures
  recover and close the input window instead of leaving a silent failed turn.

## Verification

### RED Baseline Before Temporal Integration

Command:

```bash
.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py::test_timed_and_no_trigger_create_use_owner_timezone_and_default_duration tests/unit/coke/llm/test_interaction_agent.py::test_shared_reminder_detect_tool_defaults_to_current_user_message_and_timezone -q
```

Result:

- 2 failed.
- Failures matched stale duration expectations rather than a B2 no-staging code
  bug.

### Focused Temporal And Handler Verification

Command:

```bash
.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/llm/test_reminder_detector.py tests/unit/coke/turn/inbound/test_reminder_handler.py tests/unit/coke/llm/test_interaction_agent.py::test_shared_reminder_detect_tool_defaults_to_current_user_message_and_timezone -q
```

Result:

- 61 passed.

### Smoke Script Unit Verification

Command:

```bash
.venv/bin/python -m pytest tests/unit/coke/smoke/test_v6_wechat_smoke.py -q
```

Result:

- 12 passed.

### Final Full Unit Verification

Command:

```bash
.venv/bin/python -m pytest tests/unit/coke -q
```

Result:

- 924 passed, 1 skipped.
- Skip reason:
  `tests/unit/coke/turn/inbound/test_autonomous_commit_guard.py:65:
  COKE_TEST_DATABASE_URL is not set`.

### Diff-Aware Verification Routing

Command:

```bash
zsh scripts/suggest-verification --base main
```

Result:

- Suggested command:
  `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs`

Command:

```bash
zsh scripts/review-trigger --base main
```

Result:

- `human_review_required: no`
- Remaining risk triggers were scope/documentation-size signals, not correctness
  failures.

### Suggested Surfaces

Command:

```bash
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
```

Result:

- Passed.
- Backend surface repeated full unit verification: 924 passed, 1 skipped for
  missing `COKE_TEST_DATABASE_URL`.
- Repo-OS docs surface ran `zsh scripts/check` and passed.

Command:

```bash
zsh scripts/verify-surface clean-rebuild-docs
```

Result:

- Passed.
- Ran `bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh` and
  `zsh scripts/check`.

### Additional Checks

Command:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -q
```

Result:

- 11 passed.
- This covered the final narrow runner recovery extension after the full surface
  run.

Command:

```bash
python -m py_compile scripts/smoke/v6_wechat_smoke.py scripts/smoke/v6_cases.py scripts/turn_pipeline_probe.py
```

Result:

- Passed.

Command:

```bash
.venv/bin/alembic heads
```

Result:

- Single head: `20260612_0001 (head)`.

Command:

```bash
git diff --check
```

Result:

- Passed.

Command:

```bash
rg -n "staged_command|resolve_and_stage|MaterializationPlan|staged_pending_close|materialize_staged|StagedCommand|materialized_ops|stage_command" scripts docs/ARCHITECTURE.md tests/unit/coke/smoke/test_v6_wechat_smoke.py
```

Result:

- No matches.

## Remaining Gaps Before Merge/Deploy

- `COKE_TEST_DATABASE_URL` is not set, so the real Postgres autonomous commit
  guard did not run in this environment.
- No production deploy or live smoke was run in this review pass.
- The 2026-06-12 B2 plan still names rollout closeout smoke that must run before
  production confidence: v6 WeChat smoke, Coke agent smoke, the real "today
  8-9" smoke, Express-failure recovery smoke, deploy/restart/watch.

## Merge/Deploy Decision

Do not deploy solely from this local review. The branch is locally coherent and
the stale duration failures were correctly fixed by aligning to the temporal
contract, but production deployment still needs the missing database guard and
live smoke evidence.
