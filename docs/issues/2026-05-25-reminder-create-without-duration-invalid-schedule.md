---
kind: active_issue
status: resolved
surface:
  - agent-runtime
  - reminder-intent
created_at: 2026-05-25
updated_at: 2026-05-27
---

# 2026-05-25 Reminder Create Without Duration Fails InvalidSchedule

## What Happened

Live smoke batch `reminder-complete-20260525t084602Z` tried to set up the
previously untested personal reminder complete path:

- `提醒我明天早上 8 点做平板支撑。`
- `标记平板支撑提醒完成。`

The first turn failed before the complete operation could be tested. The
assistant replied that reminders were temporarily unavailable, and Mongo had no
reminder owned by the smoke account.

`agent_sessions` showed the chat agent called `reminder_domain`. The reminder
domain result failed twice with:

```text
InvalidSchedule: 创建提醒失败：Reminder duration must be positive
```

The first failed attempt had no explicit duration. The second attempt tried to
recover with `duration_minutes=2`, but the domain still returned the same
`InvalidSchedule`.

## Why It Matters

One-shot personal reminders do not require a duration. The reminder service
schema allows `duration_minutes=None`, and existing CRUD smoke coverage creates
ordinary reminders successfully when the phrase includes an explicit duration
or when the detector produces a valid schedule.

A user asking "remind me tomorrow at 8 to do planks" should create a point
reminder or ask a targeted clarification. It should not fail with an internal
duration validation error.

## Evidence

- Failed artifact:
  `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-reminder-complete-20260525t084602Z.json`
- Smoke account:
  `ck_smoke_remindercomplete20260525t084602z_alice`
- Mongo `reminders` for that account: empty.
- `agent_sessions` tool result:
  `error.code=InvalidSchedule`, message `Reminder duration must be positive`.

Control run with explicit duration passed:

- Artifact:
  `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-reminder-complete-explicit-duration-20260525t084922Z.json`
- User said:
  `提醒我明天早上 8 点做平板支撑 5 分钟。`
- Mongo reminder:
  `title=做平板支撑`, `duration_minutes=5`,
  `lifecycle_state=completed`, `next_fire_at=None`, `completed_at` present.

## 2026-05-27 Regression

Production real-user smoke with `olivers` on 2026-05-27 reproduced the same
class of failure:

- Input:
  `2029年1月6日10:00提醒我喝水-regression-personal-20260527T061438Z。`
- Route: production `/bridge/inbound` as `olivers`.
- Domain: `reminder_domain`, not `scheduling_domain`.
- Tool result:
  `InvalidSchedule: 创建提醒失败：Reminder duration must be positive`.
- User-visible reply incorrectly asked for duration instead of creating a point
  reminder.

The active architecture contract says reminder duration is optional: absent
duration remains a point reminder. The previous local resolution defaulted
missing/non-positive create durations to 60 minutes, which is no longer the
desired contract.

Current fix direction:

- Preserve `agent.reminder.schedule.validate_duration_minutes`: positive values
  still represent occupied calendar time; invalid positive validation still
  protects the storage model.
- Normalize detector output `duration_minutes <= 0` to `None` before invoking
  the reminder protocol. This treats model-emitted `0` as "no duration", not as
  a user-facing error.
- Remove stale unit expectations that personal reminders default to 60 minutes
  when no duration was provided.

Post-deploy retest with marker `fix-personal-20260527T062239Z` exposed a
second path:

- Input:
  `2029年1月6日10:00提醒我喝水-fix-personal-20260527T062239Z。`
- The chat model did not call `reminder_domain`; it directly replied:
  `这个提醒也需要设置时长哦。你想持续多长时间？5分钟、10分钟还是其他？`
- Production logs for the same marker had no reminder domain result. The
  remaining failure was runtime routing, not schedule validation.

Updated fix direction:

- Keep the detector-level normalization above for model-emitted
  `duration_minutes=0`.
- Route explicit personal reminder requests directly through
  `run_reminder_domain` before the general chat model decides whether to call a
  tool. Shared-reminder creates keep the existing scheduling preselection.
- If the reminder detector says `no_action`, fall back to ordinary chat; if it
  executes and produces a visible summary, return the structured domain result
  directly.

## Superseded Status

This section records the old 2026-05-25 local resolution and is superseded by
the 2026-05-27 production regression above. Reminder creation must not default
missing duration to 60 minutes. Missing duration is a point reminder
(`duration_minutes=None`).

The old live smoke passed, but validated the superseded 60-minute behavior:

- Artifact:
  `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-reminder-default-duration-complete-20260525t090315Z.json`
- User said:
  `提醒我明天早上 8 点做平板支撑。`
- Mongo reminder:
  `title=做平板支撑`, `duration_minutes=60`,
  `lifecycle_state=completed`, `next_fire_at=None`, `completed_at` present.

## Resolution

- Fix: `agent/agno_agent/capabilities/reminder_intent.py` normalizes
  non-positive create durations to `None` before command execution.
- Fix: `agent/agno_agent/runtime/agent_runtime.py` directly executes explicit
  personal reminder requests through Reminder Runtime, avoiding model-only
  duration clarification replies.
- Regression tests:
  `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py -q`
  and
  `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q`

## Final Verification

Resolved by commit `1ac16de6` and deployed with:

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

Production real-user retest used `olivers` through the live bridge with marker
`fix-personal-20260527T063806Z`.

Create input:

```text
2029年1月6日10:00提醒我喝水-fix-personal-20260527T063806Z。
```

Production state after create:

- Reminder `_id=6a1691f66645e7bf138ae48d`
- `owner_user_id=ck_SXk_J0U0V5JKcK09QHEuo`
- `title=喝水-fix-personal-20260527T063806Z`
- `schedule.duration_minutes=None`
- `schedule.anchor_at=2029-01-06 02:00:00+00:00`
- `lifecycle_state=active`
- `next_fire_at=2029-01-06 02:00:00+00:00`
- Output `_id=6a1691fb6645e7bf138ae493`, `status=handled`, message:
  `已创建提醒：喝水-fix-personal-20260527T063806Z（2029-01-06 周六 10:00）`

Cleanup used natural user language from the same production account:

```text
取消喝水-fix-personal-20260527T063806Z这个提醒。
```

Production state after cancel:

- Reminder `_id=6a1691f66645e7bf138ae48d`
- `lifecycle_state=cancelled`
- `next_fire_at=None`
- `cancelled_at=2026-05-27 06:42:15.764000+00:00`
- Output `_id=6a16924a6645e7bf138ae4fc`, `status=handled`, message:
  `已取消提醒：喝水-fix-personal-20260527T063806Z`

Full verification run before deploy:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_reminder_intent_capability.py -q
zsh scripts/verify-surface repo-os-docs worker-runtime
zsh scripts/review-trigger --base HEAD~1
git diff --check
```

`verify-surface` passed `scripts/check`, `tests/unit/runner/`,
`tests/unit/agent/`, and `tests/unit/test_clawscale_only_topology.py`.
`review-trigger` reported `human_review_required: no`.
