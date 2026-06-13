# Olivers Onboarding Express Fix Evidence

Date: 2026-06-13

## Change

- Commit: `90f50774cf9c0f33574484f8257c6ea381962172`
- Surface: clean rebuild backend, repo issue record
- Bug: `olivers@coke.keep4oforever.com` received only `Hi~` after activation
  reset, but `first_guidance_sent_at` was stamped.
- Root cause: `onboarding_guidance` stopped at `TurnPipelineRequest.trusted_facts`
  and was not passed to Express.

## Verification

- `tests/unit/coke/turn/inbound/test_express.py::test_render_appends_onboarding_guidance_when_model_omits_it`
  failed before the fix with `ExpressRequest.__init__() got an unexpected
  keyword argument 'onboarding_guidance'`.
- `tests/unit/coke/turn/inbound/test_pipeline.py::test_pipeline_passes_onboarding_guidance_to_express`
  failed before the fix with `ExpressRequest` missing `onboarding_guidance`.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  `940 passed, 1 skipped`; the skip was
  `COKE_TEST_DATABASE_URL is not set`.
- `zsh scripts/review-trigger --base HEAD~1` returned
  `human_review_required: no`.

## Deployment

- `scripts/deploy-compose-to-gcp.sh` deployed
  `90f50774cf9c0f33574484f8257c6ea381962172`.
- Deploy rebuilt and restarted `coke-api`, `coke-worker`, `coke-scheduler`, and
  `coke-outbox-relay`.
- Deploy output ended with `clean deploy health checks passed`.
- Remote `.deployed-sha` returned
  `90f50774cf9c0f33574484f8257c6ea381962172`.
- Remote compose services after deploy:
  `coke-api`, `coke-outbox-relay`, `coke-scheduler`, `coke-web`,
  `coke-worker`, `postgres`, and `redis` were `running`.

## Post-Deploy Olivers Reset

After deploy, `account_activation` for account
`ae02ff01-6fcd-4d39-a189-e51c8c8a31e6` was reset again:

```text
olivers@coke.keep4oforever.com|ae02ff01-6fcd-4d39-a189-e51c8c8a31e6|NULL|NULL|NULL|connected|0
```

Fields in order: email, account id, `first_inbound_received_at`,
`activation_completed_at`, `first_guidance_sent_at`, active channel state,
open turn count.

Public `/api/health` and `/health` returned 404; this stack does not expose
those public routes. The deploy script's health checks and compose service state
were the runtime health evidence for this deployment.

## Follow-up: Duplicate Onboarding Segment

After the first fix deployed, Olivers sent `Hi～` at
`2026-06-13 04:24:16 UTC`. The turn completed normally:

```text
turn_id=408fe4b9-c76c-4ecf-97a2-1fcf7af0466b
input_from_seq=221
input_to_seq=221
disposition=replied
reason_code=reply_ready
```

The persisted outbound messages showed the real user-visible issue was duplicate
first-use guidance, not a stuck turn:

```text
segment 1: Hi～
segment 2: 我是Coke，可以帮你设提醒、和朋友共享提醒、查空闲时间，还会记住你的偏好，随时找我聊
segment 3: 我是 Coke。你可以直接让我设置提醒、和好友创建共享提醒、查询好友空闲时间、记住你的长期偏好。
```

Root cause: Express's deterministic onboarding fallback only recognized a narrow
set of onboarding words. It did not treat `朋友共享提醒` as covering the
shared-reminder-with-friends capability, so it appended a second onboarding
segment even though the model had already produced one.

Local verification after the follow-up fix:

- `tests/unit/coke/turn/inbound/test_express.py::test_render_does_not_append_duplicate_onboarding_when_model_mentions_synonyms`
  failed before the fix and passed after it.
- `tests/unit/coke/llm/test_interaction_agent.py` passed: `74 passed`.
- `tests/unit/coke/turn/inbound/test_pipeline.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/test_delivery_lifecycle_callbacks.py`
  passed: `34 passed`.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  `942 passed, 1 skipped`; the skip was
  `COKE_TEST_DATABASE_URL is not set`.

## Follow-up: First-Use Must Start With Complete Onboarding

The next Olivers retest showed that "not duplicated" was still not enough:
first-use `Hi` could be rendered as only the starter question, e.g. "这两天有什么要做
的事情吗？我到时候提醒你", which did not read as the product onboarding flow.

Root cause: the previous implementation treated onboarding as a model
instruction with an Express fallback. The prompt encouraged a starter question,
but no-action first-use replies did not have a deterministic visible opening.

Fix shape:

- no-action first-use turns now render configured onboarding copy before model
  content;
- the first segment uses the configured greeting, for example
  `Hi, Oliver！我是 Coke，你的提醒和约课小助手。`;
- the second segment frames Coke as the user's health buddy: it will 督促近期目标并
  提醒, use calendar tooling to coordinate time with others, and answer
  questions;
- redundant model greetings, model-written onboarding, and duplicate starter
  questions are suppressed;
- first-use turns with settled outcomes still preserve the outcome reply and
  append guidance, so product-state facts are not hidden.

Local verification before deployment:

- `tests/unit/coke/turn/inbound/test_express.py::test_no_action_first_use_renders_configured_onboarding_before_model_starter`
  failed before the fix with the starter question as segment 1 and configured
  onboarding appended as segment 2.
- `tests/unit/coke/turn/inbound/test_express.py::test_no_action_first_use_normalizes_model_onboarding_to_configured_copy`
  failed before the fix with model-generated onboarding left visible.
- After the fix, `tests/unit/coke/turn/inbound/test_express.py` passed:
  `9 passed`.
- `tests/unit/coke/turn/inbound/test_express.py tests/unit/coke/turn/inbound/test_pipeline.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/test_delivery_lifecycle_callbacks.py`
  passed: `43 passed`.
- `black coke/turn/inbound/express.py tests/unit/coke/turn/inbound/test_express.py --check`
  passed.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  `942 passed, 1 skipped`; the skip was
  `COKE_TEST_DATABASE_URL is not set`. Repo docs check passed.

## Follow-up: Role Intro Duplicate Suppression

Post-deploy live retest showed the new deterministic copy was sent, but Express
kept one model-generated role intro as a third segment:

```text
Hi！我是 Coke，你的提醒和约课小助手。
我会在微信里做你的健康搭子：督促你推进近期目标并提醒，帮你用日历和别人约时间，也可以直接回答问题。
Hi！我是 Coke，你的微信健康搭子、提醒和约课小助手
```

Root cause: first-use duplicate suppression recognized complete capability
onboarding, but not short role-intro duplicates containing `Coke`,
`健康搭子`, and `提醒和约课小助手`.

Fix shape:

- no-action first-use duplicate suppression now drops model segments that
  re-introduce Coke with the same role markers;
- configured greeting and role guidance remain the only visible onboarding
  opening for a plain first-use `Hi`.

Local verification:

- `tests/unit/coke/turn/inbound/test_express.py::test_no_action_first_use_drops_role_intro_duplicate`
  failed before the fix and passed after it.
- `tests/unit/coke/turn/inbound/test_express.py` passed: `10 passed`.
- `tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/inbound/test_express.py tests/unit/coke/turn/inbound/test_pipeline.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/test_delivery_lifecycle_callbacks.py`
  passed: `118 passed`.

## Follow-up: Role/Greeting Copy

After the first complete-onboarding fix, the visible reply still read too much
like a capability checklist and could still be influenced by the old starter
question. The required first-use framing is now:

- `Hi, <user name>！我是 Coke，你的提醒和约课小助手。`
- Coke is the user's 微信健康搭子.
- Coke's goals are to 督促近期目标并提醒, use calendar tooling to coordinate time
  with others, and answer questions.

Code changes in this follow-up:

- Express deterministic no-action onboarding now emits the greeting and role
  framing as two configured segments instead of a capability checklist.
- The interaction-agent onboarding prompt block now uses the same role/greeting
  framing and treats product surfaces as constraints rather than a required
  visible list.
- The runner `onboarding_guidance` fact now carries the greeting template and no
  longer carries the old `starter_question` / `task_followup_question` fields.
- `CokeVoicePolicy` no longer includes the old first-use starter example, so the
  model is less likely to regenerate it before Express normalization.

Local verification:

- `tests/unit/coke/llm/test_interaction_agent.py::test_voice_policy_uses_coke_health_buddy_role_and_work_boundaries`
  failed before the prompt update because `使用日历工具` was absent from the
  role policy.
- `tests/unit/coke/llm/test_interaction_agent.py::test_onboarding_guidance_block_uses_supported_current_capabilities_only`
  failed before the prompt update because onboarding still used old supported
  capability wording.
- `tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/inbound/test_express.py tests/unit/coke/turn/inbound/test_pipeline.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/test_delivery_lifecycle_callbacks.py`
  passed: `117 passed`.
- `black coke/llm/agno_interaction_agent.py coke/turn/runner.py coke/turn/inbound/express.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/inbound/test_express.py --check`
  passed.
- `zsh scripts/suggest-verification --base HEAD~1` suggested
  `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`.
- `zsh scripts/review-trigger --base HEAD~1` returned
  `human_review_required: no`.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  `942 passed, 1 skipped`; the skip was
  `COKE_TEST_DATABASE_URL is not set`. Repo docs check passed.
