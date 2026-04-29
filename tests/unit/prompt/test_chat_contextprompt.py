from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_提醒未执行,
    CONTEXTPROMPT_提醒无需操作,
)


def test_pending_reminder_prompt_stays_compact_and_positive():
    non_empty_lines = [
        line for line in CONTEXTPROMPT_提醒未执行.splitlines() if line.strip()
    ]

    assert len(non_empty_lines) <= 25
    assert "Bad Chinese replies" not in CONTEXTPROMPT_提醒未执行
    assert "记下了" not in CONTEXTPROMPT_提醒未执行
    assert "安排上" not in CONTEXTPROMPT_提醒未执行
    assert "每 X 提醒一次" not in CONTEXTPROMPT_提醒未执行


def test_no_action_reminder_prompt_stays_compact_and_general():
    non_empty_lines = [
        line for line in CONTEXTPROMPT_提醒无需操作.splitlines() if line.strip()
    ]

    assert len(non_empty_lines) <= 8
    assert "ReminderDetect No Reminder Action" in CONTEXTPROMPT_提醒无需操作
    assert (
        "Only say a reminder will happen after a successful reminder tool result"
        in (CONTEXTPROMPT_提醒无需操作)
    )
    assert (
        "Frame reminder follow-up questions as optional confirmation"
        in (CONTEXTPROMPT_提醒无需操作)
    )
    assert "提醒功能增强" not in CONTEXTPROMPT_提醒无需操作
