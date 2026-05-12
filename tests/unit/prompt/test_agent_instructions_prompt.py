from datetime import UTC, datetime

from agent.prompt.agent_instructions_prompt import (
    INSTRUCTIONS_ORCHESTRATOR,
    get_reminder_detect_instructions,
)


def _non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def test_reminder_detect_instructions_are_small_positive_boundary():
    instructions = get_reminder_detect_instructions("2026年04月30日12时00分")
    lines = _non_empty_lines(instructions)

    assert len(lines) <= 82
    assert "Current time: 2026年04月30日12时00分" in instructions
    assert "create only when the user asks to be reminded" in instructions
    assert "Date-only or time-missing reminder requests clarify" in instructions
    assert "Bounded recurring cadence with a deadline uses one compact recurrence" in (
        instructions
    )
    assert "Cadence with a deadline and no start uses the next future" in (instructions)
    assert "Preserve all meaningful title text" in instructions
    assert "Exclude sentence-final modal particles" in instructions
    assert 'Any decision with operations must use top-level action="batch"' in (
        instructions
    )
    assert "one operation per listed time" in instructions
    assert "contacted, nudged, or supervised at a concrete time/cadence" in instructions
    assert "A task time range is a work block" in instructions
    assert "clarify before creating any reminder from that message" in instructions
    assert "use the task governed by the reminder verb" in instructions
    assert "bare call/wake/alarm-me requests" in instructions
    assert "Name/address preferences" in instructions
    assert "One-shot deadline wording" in instructions
    assert "Event time plus an advance offset is complete" in instructions
    assert "vague advance request without an offset" in instructions
    assert "task/content appears before the reminder verb" in instructions
    assert "need/intention statements" in instructions
    assert "return discussion" in instructions
    assert "schedule_evidence may summarize the concrete cadence/time" in (instructions)
    assert "include every listed weekday in" in instructions
    assert "Output only the structured decision" in instructions


def test_orchestrator_does_not_route_name_preferences_to_reminder_detect():
    assert "Name/address preferences" in INSTRUCTIONS_ORCHESTRATOR
    assert "concrete reminder time, cadence, or task" in INSTRUCTIONS_ORCHESTRATOR


def test_reminder_detect_instructions_do_not_embed_case_examples():
    instructions = get_reminder_detect_instructions("2026年04月30日12时00分")

    assert "Example:" not in instructions
    assert "->" not in instructions
    for stale_phrase in (
        "我8点回来",
        "七点半开始正式学习",
        "今晚7点上课",
        "之后吃饭，8点回来",
        "我的作息，6点半起床",
        "11点10分还有12点提醒我一下",
    ):
        assert stale_phrase not in instructions


def _run_context():
    from agent.agno_agent.runtime.context import (
        AgentRunContext,
        TrustedCharacterContext,
        TrustedConversationContext,
        TrustedRelationContext,
        TrustedUserContext,
    )

    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="wechat_personal:primary",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        runtime_metadata={},
    )


def test_reminder_detect_retry_reuses_primary_instructions():
    from agent.agno_agent.agents import (
        get_reminder_detect_instructions as agent_instructions,
        get_reminder_detect_retry_instructions,
        reminder_detect_agent,
        reminder_detect_retry_agent,
    )

    assert get_reminder_detect_retry_instructions() == agent_instructions()
    assert (
        reminder_detect_retry_agent.instructions == reminder_detect_agent.instructions
    )


def test_reminder_few_shots_are_input_context_not_system_prompt():
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    reminder_input = build_reminder_intent_input("18:00提醒我喝水", _run_context())
    instructions = get_reminder_detect_instructions("2026年04月30日12时00分")

    assert "### Reminder Few-Shot Decisions" in reminder_input
    assert '"decision_class": "crud.create"' in reminder_input
    assert "我一般7:15起床，23:00睡觉" in reminder_input
    assert "早上8:00开始学习，下午13:00开始健身" not in reminder_input
    assert "帮我记住今天任务" in reminder_input
    assert "工作应该去做“非我不可”的事情" in reminder_input
    assert '"decision_class": "discussion"' in reminder_input
    assert "Reminder Few-Shot Decisions" not in instructions


def test_reminder_detect_retry_input_keeps_schedule_schema_constraints():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    retry_input = _build_reminder_retry_input(
        "我一般7:15起床，23:00睡觉。我需要你在上述这些时间提醒我",
        _run_context(),
        reason="schema validation failed",
    )

    assert "For same-message listed routine times" in retry_input
    assert 'schedule_basis="explicit_occurrences"' in retry_input
    assert "one operation per listed time" in retry_input
    assert "bounded recurring cadence requests with a deadline" in retry_input
    assert "deadline_at" in retry_input
    assert "Drop final particles" in retry_input
    assert "preserve quoted title" in retry_input
    assert "bare call/wake/alarm-me requests" in retry_input
    assert "One-shot deadline wording" in retry_input
    assert "Need/intention statements" in retry_input
    assert "return discussion" in retry_input
    assert "include every listed weekday in" in retry_input


def test_reminder_few_shot_fixture_stays_small_and_representative():
    from agent.prompt.reminder_few_shot import load_reminder_few_shots

    shots = load_reminder_few_shots()
    classes = {shot["decision_class"] for shot in shots}

    assert len(shots) <= 8
    assert classes == {
        "crud.create",
        "crud.batch",
        "crud.update",
        "crud.delete",
        "query",
        "clarify",
        "discussion",
    }
