from datetime import UTC, datetime

from agent.prompt.agent_instructions_prompt import (
    INSTRUCTIONS_REMINDER_DETECT,
    get_reminder_detect_instructions,
)


def _non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def test_reminder_detect_instructions_are_small_positive_boundary():
    """v2 prompt: ~600-1000 token budget, focused on intent + ISO time output.

    Avoid asserting individual edge-case rule wording — those are exactly
    the kind of accumulated text that ADR 0004 forbids. Assert only the
    structural sections and the load-bearing AM/PM disambiguation rule.
    """
    instructions = get_reminder_detect_instructions("2026年04月30日12时00分")
    lines = _non_empty_lines(instructions)

    # Structure: must stay under ~60 non-empty lines.
    assert len(lines) <= 60
    # Dynamic timestamps belong in per-turn input data, not static instructions.
    assert "Current time:" not in instructions
    assert "2026年04月30日12时00分" not in instructions
    # Four intent classes appear by name.
    for intent in ("crud", "clarify", "query", "discussion"):
        assert f"- {intent}:" in instructions
    # Time output is the critical contract.
    assert "ISO 8601" in instructions
    # AM/PM disambiguation is load-bearing (Phase 0 v2 evidence).
    assert "prefer PM same day" in instructions
    # Output discipline.
    assert "Output only the structured decision" in instructions


def test_static_reminder_detect_instructions_do_not_embed_dynamic_current_time():
    assert "Current time:" not in INSTRUCTIONS_REMINDER_DETECT


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


def test_reminder_few_shot_fixture_stays_small_and_representative():
    from agent.prompt.reminder_few_shot import load_reminder_few_shots

    shots = load_reminder_few_shots()
    classes = {shot["decision_class"] for shot in shots}

    assert len(shots) <= 18
    assert classes == {
        "crud.create",
        "crud.batch",
        "crud.update",
        "crud.delete",
        "query",
        "clarify",
        "discussion",
        "clarify.status_only",
        "clarify.completion_condition",
        "clarify.date_only",
        "clarify.ambiguous_range",
        "discussion.meta",
        "discussion.feature_work",
        "discussion.plain_schedule",
        "discussion.acknowledgement",
        "discussion.opt_out",
    }
