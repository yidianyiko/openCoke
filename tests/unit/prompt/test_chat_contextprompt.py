from agent.prompt.chat_contextprompt import (
    CONTEXTPROMPT_提醒未执行,
    CONTEXTPROMPT_提醒无需操作,
    get_reminder_operation_direct_reply,
)


def test_pending_reminder_prompt_stays_compact_and_positive():
    non_empty_lines = [
        line for line in CONTEXTPROMPT_提醒未执行.splitlines() if line.strip()
    ]

    assert len(non_empty_lines) <= 15
    assert "Ask one direct question" in CONTEXTPROMPT_提醒未执行
    assert "successful reminder tool result" in CONTEXTPROMPT_提醒未执行
    assert "Bad Chinese replies" not in CONTEXTPROMPT_提醒未执行
    assert "记下了" not in CONTEXTPROMPT_提醒未执行
    assert "安排上" not in CONTEXTPROMPT_提醒未执行
    assert "每 X 提醒一次" not in CONTEXTPROMPT_提醒未执行
    assert "If trigger time is missing" not in CONTEXTPROMPT_提醒未执行
    assert "If cadence is missing" not in CONTEXTPROMPT_提醒未执行


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
    assert "Frame reminder follow-up questions as optional confirmation" in (
        CONTEXTPROMPT_提醒无需操作
    )
    assert "提醒功能增强" not in CONTEXTPROMPT_提醒无需操作


def test_reminder_clarification_tool_result_returns_direct_reply():
    reply = get_reminder_operation_direct_reply(
        {
            "tool_results": [
                {
                    "tool_name": "提醒操作",
                    "ok": False,
                    "result_summary": "几点提醒你开始学习？",
                    "extra_notes": "action=clarify; error_code=ReminderDetectClarify",
                }
            ]
        }
    )

    assert reply == "几点提醒你开始学习？"


def test_reminder_no_action_can_return_optional_confirmation_direct_reply():
    reply = get_reminder_operation_direct_reply(
        {
            "prepare_reminder_detect_no_action": True,
            "tool_results": [],
        }
    )

    assert reply == "需要我帮你设置一个提醒吗？"
