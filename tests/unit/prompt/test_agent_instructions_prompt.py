from agent.prompt.agent_instructions_prompt import get_reminder_detect_instructions


def test_reminder_detect_instructions_require_aware_iso_trigger_at():
    instructions = get_reminder_detect_instructions("2026年04月21日12时00分")

    assert "trigger_at" in instructions
    assert "new_trigger_at" in instructions
    assert "2026-04-21T15:30:00+08:00" in instructions
    assert "FREQ=DAILY" in instructions
    assert "Do not pass relative time strings" in instructions
    assert "trigger_time" not in instructions
    assert "new_trigger_time" not in instructions


def test_reminder_detect_instructions_reject_date_only_default_time_creation():
    instructions = get_reminder_detect_instructions("2026年04月29日02时30分")

    assert "You are the semantic parser for reminder operations" in instructions
    assert "Do not invent a default time" in instructions
    assert "Date-only expressions" in instructions
    assert "明天继续提醒我看文章" in instructions


def test_reminder_detect_instructions_do_not_list_for_ambiguous_create():
    instructions = get_reminder_detect_instructions("2026年04月29日02时30分")

    assert "Only call list" in instructions
    assert "Do not call list as a fallback" in instructions


def test_reminder_detect_instructions_do_not_create_for_schedule_statement_only():
    instructions = get_reminder_detect_instructions("2026年04月29日02时30分")

    assert "A plan or schedule statement is not enough" in instructions
    assert "七点半开始正式学习" in instructions
    assert "return time" in instructions
    assert "之后吃饭，8点回来" in instructions


def test_reminder_detect_instructions_deduplicate_recurring_batch_creates():
    instructions = get_reminder_detect_instructions("2026年04月29日02时30分")

    assert "habitual or general schedule" in instructions
    assert "Do not also create one-shot reminders" in instructions
    assert "same title and local time" in instructions
    assert "我一般7:15起床" in instructions


def test_reminder_detect_instructions_do_not_create_for_routine_description():
    instructions = get_reminder_detect_instructions("2026年04月29日02时30分")

    assert "Routine descriptions are not reminder requests" in instructions
    assert "我的作息，6点半起床" in instructions


def test_reminder_detect_instructions_do_not_infer_recurrence_from_day_period():
    instructions = get_reminder_detect_instructions("2026年04月29日02时30分")

    assert "Day-period words are not recurrence" in instructions
    assert "Only set rrule" in instructions
    assert "早上10:30提醒我看报表" in instructions


def test_reminder_detect_instructions_use_next_occurrence_for_past_clock_time():
    instructions = get_reminder_detect_instructions("2026年04月29日11时51分")

    assert "If a bare clock time has already passed today" in instructions
    assert "next occurrence" in instructions
    assert "10:40提醒我思考一个问题" in instructions


def test_reminder_detect_instructions_allow_generic_title_for_bare_time_reminders():
    instructions = get_reminder_detect_instructions("2026年04月29日14时27分")

    assert 'title="提醒"' in instructions
    assert "missing reminder content" in instructions
    assert "clarification" in instructions
    assert "11点10分还有12点提醒我一下" in instructions
    assert "two one-shot reminders" in instructions


def test_reminder_detect_instructions_treat_no_disturb_as_cancel_intent():
    instructions = get_reminder_detect_instructions("2026年04月29日14时27分")

    assert "do-not-disturb" in instructions
    assert "不要打扰我了" in instructions
    assert "do not create anything" in instructions


def test_reminder_detect_instructions_enumerate_unsupported_interval_deadlines():
    instructions = get_reminder_detect_instructions("2026年04月29日15时07分")

    assert "cannot represent exactly with the supported RRULE subset" in instructions
    assert "enumerate each one-shot occurrence" in instructions
    assert "current time is the schedule anchor" in instructions
    assert "15:57, 16:47, 17:37" in instructions


def test_reminder_detect_instructions_use_user_supplied_interval_anchor():
    instructions = get_reminder_detect_instructions("2026年04月29日15时07分")

    assert "explicit occurrence anchor" in instructions
    assert "correction point" in instructions
