def test_empty_when_no_tool_results():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    assert get_tool_results_context({}) == ""
    assert get_tool_results_context({"tool_results": []}) == ""


def test_single_success_result():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    state = {
        "tool_results": [
            {"tool_name": "时区更新", "ok": True, "result_summary": "已更新为纽约时间", "extra_notes": ""}
        ]
    }
    output = get_tool_results_context(state)
    assert "### System Operation Results" in output
    assert "[时区更新]" in output
    assert "Status: Success" in output
    assert "已更新为纽约时间" in output


def test_single_failure_result():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    state = {
        "tool_results": [
            {"tool_name": "提醒创建", "ok": False, "result_summary": "时间格式不正确", "extra_notes": ""}
        ]
    }
    output = get_tool_results_context(state)
    assert "Status: Failed" in output
    assert "时间格式不正确" in output


def test_extra_notes_appended_when_present():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    state = {
        "tool_results": [
            {
                "tool_name": "提醒创建",
                "ok": False,
                "result_summary": "频率过高",
                "extra_notes": "每小时以上的重复提醒才支持",
            }
        ]
    }
    output = get_tool_results_context(state)
    assert "每小时以上的重复提醒才支持" in output


def test_multiple_results_all_rendered():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    state = {
        "tool_results": [
            {"tool_name": "时区更新", "ok": True, "result_summary": "纽约", "extra_notes": ""},
            {"tool_name": "提醒创建", "ok": True, "result_summary": "明天9点", "extra_notes": ""},
        ]
    }
    output = get_tool_results_context(state)
    assert "[时区更新]" in output
    assert "[提醒创建]" in output
    # Both appear in single block
    assert output.count("### System Operation Results") == 1


def test_timezone_context_stays_quiet_for_non_time_dependent_tool_results():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    state = {
        "user": {
            "timezone": "Europe/London",
            "timezone_status": "system_inferred",
            "timezone_source": "web_region",
        },
        "tool_results": [
            {"tool_name": "时区更新", "ok": True, "result_summary": "已更新为伦敦时间", "extra_notes": ""}
        ],
    }

    output = get_tool_results_context(state)

    assert "Europe/London" not in output
    assert "system inferred" not in output.lower()


def test_timezone_context_mentions_inferred_state_for_reminder_results():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    state = {
        "user": {
            "timezone": "Europe/London",
            "timezone_status": "system_inferred",
            "timezone_source": "web_region",
        },
        "tool_results": [
            {"tool_name": "提醒操作", "ok": True, "result_summary": "明天早上9点提醒开会", "extra_notes": ""}
        ],
    }

    output = get_tool_results_context(state)

    assert "Europe/London" in output
    assert "system inferred" in output.lower()
