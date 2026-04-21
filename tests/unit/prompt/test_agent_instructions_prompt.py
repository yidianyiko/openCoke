from agent.prompt.agent_instructions_prompt import get_reminder_detect_instructions


def test_reminder_detect_instructions_require_parser_supported_time_formats():
    instructions = get_reminder_detect_instructions("2026年04月21日12时00分")

    assert "Only use trigger_time/new_trigger_time formats that the parser supports." in instructions
    assert "3分钟后" in instructions
    assert "2小时后" in instructions
    assert "明天" in instructions
    assert "2026-04-21T15:30:00+08:00" in instructions
    assert "Never output English relative time strings like \"in 1 minute\"" in instructions
