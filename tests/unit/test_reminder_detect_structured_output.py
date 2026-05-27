import pytest
from pydantic import ValidationError


def test_reminder_detect_schema_normalizes_write_action_to_crud():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="clarify",
        action="create",
        title="喝水",
        trigger_at="2026-04-29T18:00:00+09:00",
    )

    assert decision.intent_type == "crud"


def test_reminder_detect_schema_normalizes_mislabeled_clarification():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="",
        clarification_reason="ambiguous_request",
    )

    assert decision.intent_type == "clarify"
    assert decision.action == ""


def test_reminder_detect_schema_drops_action_for_non_executable_clarification():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="clarify",
        action="create",
        clarification_reason="ambiguous_request",
    )

    assert decision.intent_type == "clarify"
    assert decision.action == ""


def test_reminder_detect_schema_rejects_naive_create_trigger_at():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError, match="trigger_at must include timezone"):
        ReminderDetectDecision(
            intent_type="crud",
            action="create",
            title="吃饭",
            trigger_at="2026-04-30T16:37:00",
        )


def test_reminder_detect_schema_requires_batch_operations():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(intent_type="crud", action="batch")


def test_reminder_detect_schema_requires_batch_create_fields():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            operations=[{"action": "create", "title": "提醒"}],
        )


def test_reminder_detect_schema_rejects_generic_create_title():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError, match="non-generic title"):
        ReminderDetectDecision(
            intent_type="crud",
            action="create",
            title="提醒我",
            trigger_at="2026-05-13T16:00:00+09:00",
        )


def test_reminder_detect_schema_rejects_create_with_reminder_id():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(
        ValidationError, match="create action must not include reminder_id"
    ):
        ReminderDetectDecision(
            intent_type="crud",
            action="create",
            title="喝水-fire-real-20260527T073551Z",
            trigger_at="2026-05-27T15:39:00+08:00",
            reminder_id="fire-real-20260527T073551Z",
        )


def test_reminder_detect_schema_rejects_batch_create_operation_with_reminder_id():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(
        ValidationError, match="batch create operation must not include reminder_id"
    ):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            operations=[
                {
                    "action": "create",
                    "title": "喝水-fire-real-20260527T073551Z",
                    "trigger_at": "2026-05-27T15:39:00+08:00",
                    "reminder_id": "fire-real-20260527T073551Z",
                }
            ],
            schedule_basis="explicit_occurrences",
            schedule_evidence="2分钟后",
        )


def test_reminder_detect_schema_rejects_generic_batch_create_title():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError, match="non-generic title"):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            operations=[
                {
                    "action": "create",
                    "title": "提醒",
                    "trigger_at": "2026-05-13T16:00:00+09:00",
                }
            ],
            schedule_basis="explicit_occurrences",
            schedule_evidence="周三下午4点",
        )


def test_reminder_detect_schema_rejects_batch_operation_after_deadline():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            deadline_at="2026-04-29T18:00:00+09:00",
            operations=[
                {
                    "action": "create",
                    "title": "提醒",
                    "trigger_at": "2026-04-29T18:27:00+09:00",
                }
            ],
        )


def test_reminder_detect_schema_accepts_deadline_batch_rrule_operation():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        deadline_at="2026-04-29T20:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="每小时",
        operations=[
            {
                "action": "create",
                "title": "打卡",
                "trigger_at": "2026-04-29T16:00:00+09:00",
                "rrule": "FREQ=HOURLY;INTERVAL=1",
            }
        ],
    )

    assert decision.operations[0].rrule == "FREQ=HOURLY;INTERVAL=1"


def test_reminder_detect_schema_accepts_operation_at_deadline_boundary():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        deadline_at="2026-04-29T20:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="每小时",
        operations=[
            {
                "action": "create",
                "title": "打卡",
                "trigger_at": "2026-04-29T20:00:00+09:00",
            }
        ],
    )

    assert decision.operations[0].trigger_at == "2026-04-29T20:00:00+09:00"


def test_reminder_detect_schema_accepts_nightly_cadence_evidence():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="create",
        title="洗漱",
        trigger_at="2026-04-30T22:30:00+09:00",
        rrule="FREQ=DAILY;INTERVAL=1",
        schedule_basis="explicit_cadence",
        schedule_evidence="每晚",
    )

    assert decision.schedule_evidence == "每晚"


def test_reminder_detect_schema_accepts_schedule_changing_update_evidence():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="update",
        keyword="打卡",
        new_title="及时完成任务，及时打卡",
        new_trigger_at="2026-05-11T08:00:00+09:00",
        rrule="FREQ=HOURLY;INTERVAL=1",
        deadline_at="2026-05-11T23:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="从早上7点到晚上11点，每一小时提醒我一次",
    )

    assert decision.action == "update"
    assert decision.schedule_basis == "explicit_cadence"


def test_reminder_detect_schema_accepts_structured_target_selector_fields():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="update",
        target_title="吃药",
        target_local_date="2026-05-26",
        target_local_time="08:00",
        target_rrule="FREQ=DAILY",
        target_scope="current_conversation",
        new_title="吃维生素",
    )

    assert decision.target_title == "吃药"
    assert decision.target_local_date == "2026-05-26"
    assert decision.target_local_time == "08:00"
    assert decision.target_rrule == "FREQ=DAILY"
    assert decision.target_scope == "current_conversation"


def test_reminder_detect_schema_accepts_query_list_scope_fields():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="query",
        action="list",
        list_from_local_date="2026-05-26",
        list_to_local_date="2026-05-26",
        list_title_query="喝水",
        list_states=["active"],
    )

    assert decision.list_from_local_date == "2026-05-26"
    assert decision.list_to_local_date == "2026-05-26"
    assert decision.list_title_query == "喝水"
    assert decision.list_states == ["active"]


def test_reminder_detect_schema_rejects_list_scope_fields_on_write_decisions():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError, match="list scope fields"):
        ReminderDetectDecision(
            intent_type="crud",
            action="create",
            title="喝水",
            trigger_at="2026-05-26T09:00:00+08:00",
            list_title_query="喝水",
        )


def test_reminder_detect_schema_rejects_invalid_list_scope_shapes():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(
        ValidationError, match="list_from_local_date must be YYYY-MM-DD"
    ):
        ReminderDetectDecision(
            intent_type="query",
            action="list",
            list_from_local_date="2026-5-26",
        )

    with pytest.raises(ValidationError, match="list_states must not be empty"):
        ReminderDetectDecision(
            intent_type="query",
            action="list",
            list_states=[],
        )


def test_reminder_detect_schema_rejects_invalid_target_selector_shapes():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="cancel",
            target_local_date="2026-5-26",
        )

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="cancel",
            target_local_time="8:00",
        )

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="cancel",
            target_scope="latest",
        )


def test_reminder_detect_schema_accepts_batch_operation_before_deadline():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        deadline_at="2026-04-29T18:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="每50分钟",
        operations=[
            {
                "action": "create",
                "title": "喝水",
                "trigger_at": "2026-04-29T17:37:00+09:00",
            }
        ],
    )

    assert decision.operations[0].trigger_at == "2026-04-29T17:37:00+09:00"


def test_reminder_detect_schema_rejects_batch_without_schedule_basis():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            operations=[
                {
                    "action": "create",
                    "title": "写作",
                    "trigger_at": "2026-04-29T10:13:00+09:00",
                },
                {
                    "action": "create",
                    "title": "写作",
                    "trigger_at": "2026-04-29T10:23:00+09:00",
                },
            ],
        )


def test_reminder_detect_schema_rejects_single_create_batch_without_schedule_basis():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            operations=[
                {
                    "action": "create",
                    "title": "练腹肌",
                    "trigger_at": "2026-04-29T19:00:00+09:00",
                }
            ],
        )


def test_reminder_detect_schema_accepts_detector_owned_cadence_evidence_text():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_cadence",
        schedule_evidence="keep me focused",
        operations=[
            {
                "action": "create",
                "title": "写作",
                "trigger_at": "2026-04-29T10:13:00+09:00",
            },
            {
                "action": "create",
                "title": "写作",
                "trigger_at": "2026-04-29T10:23:00+09:00",
            },
        ],
    )

    assert decision.schedule_basis == "explicit_cadence"
    assert decision.schedule_evidence == "keep me focused"


def test_reminder_detect_schema_accepts_whole_hour_cadence_evidence():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="create",
        title="打卡",
        trigger_at="2026-04-29T10:00:00+09:00",
        rrule="FREQ=HOURLY",
        schedule_basis="explicit_cadence",
        schedule_evidence="每个整点",
    )

    assert decision.schedule_evidence == "每个整点"


def test_reminder_detect_schema_accepts_weekday_pair_cadence_evidence():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="create",
        title="好好学习",
        trigger_at="2026-05-11T09:00:00+09:00",
        rrule="FREQ=WEEKLY;BYDAY=MO,FR",
        schedule_basis="explicit_cadence",
        schedule_evidence="每个周一周五早上九点",
    )

    assert decision.schedule_evidence == "每个周一周五早上九点"


def test_reminder_detect_schema_accepts_detector_owned_time_range_cadence_evidence():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_cadence",
        schedule_evidence="10:13-11:00",
        operations=[
            {
                "action": "create",
                "title": "写作",
                "trigger_at": "2026-04-29T10:13:00+09:00",
            },
            {
                "action": "create",
                "title": "写作",
                "trigger_at": "2026-04-29T10:23:00+09:00",
            },
        ],
    )

    assert decision.schedule_basis == "explicit_cadence"
    assert decision.schedule_evidence == "10:13-11:00"


def test_reminder_detect_schema_accepts_explicit_occurrence_batch():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="11点10分还有12点提醒我一下",
        operations=[
            {
                "action": "create",
                "title": "喝水",
                "trigger_at": "2026-04-30T11:10:00+09:00",
            },
            {
                "action": "create",
                "title": "喝水",
                "trigger_at": "2026-04-30T12:00:00+09:00",
            },
        ],
    )

    assert decision.schedule_basis == "explicit_occurrences"


def test_reminder_detect_agents_use_structured_decision_schema():
    from agent.agno_agent.capabilities.reminder_intent import _create_reminder_detector
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    reminder_detect_agent = _create_reminder_detector()

    assert reminder_detect_agent.output_schema is ReminderDetectDecision
    assert not reminder_detect_agent.tools
    assert reminder_detect_agent.structured_outputs is True
    assert reminder_detect_agent.use_json_mode is False


def test_reminder_detect_schedule_evidence_schema_rejects_vague_references():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    description = ReminderDetectDecision.model_fields["schedule_evidence"].description

    assert "not vague references like" in description
    assert "these time points" in description


def test_reminder_detect_trigger_schema_rejects_date_only_midnight_defaults():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    description = ReminderDetectDecision.model_fields["trigger_at"].description

    assert "Do not use midnight" in description
    assert "date-only" in description


def test_reminder_operation_schema_marks_update_fields_update_only():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderOperation

    assert (
        "Exclude sentence-final modal particles"
        in ReminderOperation.model_fields["title"].description
    )
    assert (
        "preserve meaningful quoted"
        in ReminderOperation.model_fields["title"].description
    )
    assert "update only" in ReminderOperation.model_fields["new_title"].description
    assert (
        "do not use for create"
        in ReminderOperation.model_fields["new_trigger_at"].description
    )


def test_reminder_detect_title_schema_preserves_quoted_content():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    description = ReminderDetectDecision.model_fields["title"].description

    assert "Exclude sentence-final modal particles" in description
    assert "preserve meaningful quoted" in description
    assert "task governed by the reminder verb" in description


def test_reminder_detect_reminder_id_schema_limits_ids_to_existing_context():
    from agent.agno_agent.schemas.reminder_detect_schema import (
        ReminderDetectDecision,
        ReminderOperation,
    )

    top_level_description = ReminderDetectDecision.model_fields[
        "reminder_id"
    ].description
    operation_description = ReminderOperation.model_fields["reminder_id"].description

    for description in (top_level_description, operation_description):
        assert "trusted runtime context" in description
        assert "Leave empty for create" in description
        assert "never copy user title" in description


def test_reminder_detect_schema_rejects_free_form_workflow_key():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="clarify",
            action="",
            clarification_reason="ambiguous_request",
            workflow={"id": "wrong"},
        )


def test_reminder_detect_clarify_requires_clarification_reason():
    import pytest
    from pydantic import ValidationError
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError, match="clarification_reason"):
        ReminderDetectDecision(
            intent_type="clarify", action="", clarification_reason=""
        )


def test_reminder_detect_non_clarify_with_reason_normalizes_to_clarify():
    """Discussion intent + a clarification_reason is treated as model confusion;
    the normalizer upgrades to clarify intent so the user gets a clarification
    rather than a silent no_action. The after-validator's strict ⇔ invariant
    still applies — see test_reminder_detect_clarify_requires_clarification_reason
    for the reverse direction."""
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="discussion",
        action="",
        clarification_reason="date_only_missing_time",
    )

    assert decision.intent_type == "clarify"
    assert decision.action == ""
    assert decision.clarification_reason == "date_only_missing_time"


def test_reminder_detect_clarify_accepts_known_reason():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="clarify",
        action="",
        clarification_reason="date_only_missing_time",
    )
    assert decision.clarification_reason == "date_only_missing_time"


def test_reminder_detect_rejects_unknown_clarification_reason():
    import pytest
    from pydantic import ValidationError
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="clarify",
            action="",
            clarification_reason="not_a_real_reason",
        )
