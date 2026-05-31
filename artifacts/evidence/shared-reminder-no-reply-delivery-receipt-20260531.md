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
