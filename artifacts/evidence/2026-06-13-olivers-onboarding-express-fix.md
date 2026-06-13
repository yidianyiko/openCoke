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
