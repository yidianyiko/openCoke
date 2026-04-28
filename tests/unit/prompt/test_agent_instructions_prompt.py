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
