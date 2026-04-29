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
