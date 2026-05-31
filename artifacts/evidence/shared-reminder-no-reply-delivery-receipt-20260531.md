# Shared Reminder No-Reply And Delivery Receipt Fix Evidence

Date: 2026-05-31

## Commands

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_semantic_intentional_no_reply_still_reaches_interaction_agent tests/unit/coke/turn/test_turn_runner.py::test_interaction_agent_can_still_intentionally_no_reply -q
```

Result: failed before implementation because semantic `intentional_no_reply`
closed the turn before Interaction Agent invocation.

```text
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_group_shared_reminder_creation_is_one_object_with_participant_projections tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_shared_reminder_receiver_delivery_creates_creator_visible_receipt -q
```

Result: failed before implementation because shared-reminder-created
notification recipients included the creator and receiver delivery did not
create a creator-visible receipt.

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_semantic_intentional_no_reply_still_reaches_interaction_agent tests/unit/coke/turn/test_turn_runner.py::test_interaction_agent_can_still_intentionally_no_reply tests/unit/coke/llm/test_interaction_agent.py::test_output_contract_keeps_product_notification_followups_visible -q
```

Result: 3 passed in 2.06s.

```text
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_group_shared_reminder_creation_is_one_object_with_participant_projections tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_shared_reminder_receiver_delivery_creates_creator_visible_receipt -q
```

Result: 2 passed in 0.55s.

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/worker/test_notification_render_trigger.py tests/unit/coke/test_delivery_lifecycle_callbacks.py -q
```

Result: 100 passed in 2.30s.

```text
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
zsh scripts/check
.venv/bin/python -m pytest tests/unit/coke -q
git diff --check
```

Result: docs sync passed; scripts/check passed; 582 unit tests passed in
17.45s; git diff whitespace check passed.

```text
zsh scripts/review-trigger --base HEAD~1
```

Result: human_review_required=no; medium risk triggers recorded for docs,
change size, and evidence path before this evidence file was added.

```text
scripts/deploy-compose-to-gcp.sh
```

Result: deployed local SHA `97efc4115194b6cbad89bd32ba90a690496a9fb3` to
`gcp-coke`; clean deploy health checks passed. Remote `.deployed-sha` returned
`97efc4115194b6cbad89bd32ba90a690496a9fb3`.

```text
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml ps'
```

Result: `coke-api` was up and healthy; `coke-worker`, `coke-outbox-relay`, and
`coke-scheduler` were up after deploy.

```text
runtime.social_scheduling_service.record_notification_delivery(
    notification_fact_id='069f3fbd-8852-4290-a62a-13ac070b3b3f',
    recipient_account_id='ae02ff01-6fcd-4d39-a189-e51c8c8a31e6',
    delivery_state='delivered',
    error_facts={},
    turn_id='3eb6b416-5f5c-4ae1-8e2c-67f8e6980489',
)
```

Result: production replay completed for the already-delivered receiver
notification.

```text
select nf.id, nf.type, nf.object_id, nr.recipient_account_id, nr.delivery_state,
       nr.turn_id, m.id as outbound_message_id, m.text as outbound_text,
       da.status as attempt_status, da.provider_message_id, da.attempted_at
from notification_fact nf
join notification_recipient nr on nr.notification_fact_id = nf.id
left join message m on m.turn_id=nr.turn_id and m.direction='outbound'
left join delivery_attempt da on da.message_id=m.id
where nf.type='shared_reminder_delivery_confirmed'
  and nf.object_id='654c9b24-5318-4619-875b-773f08212590'
order by nf.created_at desc;
```

Result: production created and delivered creator receipt
`cf11766a-b8aa-4386-bbb0-2297aeb4cdb5` to account
`635d3bdc-1b02-4a08-acf4-9940b91a9de5`. Outbound message
`03c92b4c-37e3-4853-a47b-f73ee81b94bf` text was
`olivers 已收到明天 10:00 brunch 的提醒`; provider status was `sent` with id
`coke-1780228670318-2e4dc32da443`.
