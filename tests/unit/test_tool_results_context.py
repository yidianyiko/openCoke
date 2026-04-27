def test_empty_when_no_tool_results():
    from agent.prompt.chat_contextprompt import get_tool_results_context

    assert get_tool_results_context({}) == ""
    assert get_tool_results_context({"tool_results": []}) == ""


def test_calendar_import_direct_reply_contains_link_and_instructions():
    from agent.prompt.chat_contextprompt import get_calendar_import_direct_reply

    state = {
        "tool_results": [
            {
                "tool_name": "日历导入入口",
                "ok": True,
                "result_summary": (
                    "用户想导入 Google Calendar。请把这个入口链接发给用户："
                    "https://coke.example/account/calendar-import。"
                    "说明打开后登录或验证邮箱，然后点击 Start Google Calendar import 授权 Google。"
                    "不要说导入已经完成。"
                ),
                "extra_notes": "",
            }
        ]
    }

    reply = get_calendar_import_direct_reply(state)

    assert "https://coke.example/account/calendar-import" in reply
    assert "Start Google Calendar import" in reply
    assert "授权" in reply


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


def test_inferred_timezone_visibility_surfaces_for_explicit_timezone_question():
    from agent.prompt.chat_contextprompt import get_inferred_timezone_visibility_context

    state = {
        "user": {
            "timezone": "Europe/London",
            "timezone_status": "system_inferred",
            "timezone_source": "web_region",
        }
    }

    output = get_inferred_timezone_visibility_context(
        state,
        "你现在按什么时区理解时间？",
    )

    assert "Europe/London" in output
    assert "system inferred" in output.lower()


def test_confirmed_timezone_visibility_surfaces_for_explicit_timezone_question():
    from agent.prompt.chat_contextprompt import get_inferred_timezone_visibility_context

    state = {
        "user": {
            "timezone": "Europe/London",
            "timezone_status": "user_confirmed",
            "timezone_source": "user_explicit",
        }
    }

    output = get_inferred_timezone_visibility_context(
        state,
        "你现在按什么时区理解时间？",
    )

    assert "Europe/London" in output
    assert "system inferred" not in output.lower()


def test_inferred_timezone_visibility_surfaces_for_explicit_local_time_question():
    from agent.prompt.chat_contextprompt import get_inferred_timezone_visibility_context

    state = {
        "user": {
            "timezone": "Europe/London",
            "timezone_status": "system_inferred",
            "timezone_source": "web_region",
        }
    }

    output = get_inferred_timezone_visibility_context(
        state,
        "现在当地时间几点了？",
    )

    assert "Europe/London" in output
    assert "system inferred" in output.lower()


def test_inferred_timezone_visibility_stays_quiet_for_generic_conversation():
    from agent.prompt.chat_contextprompt import get_inferred_timezone_visibility_context

    state = {
        "user": {
            "timezone": "Europe/London",
            "timezone_status": "system_inferred",
            "timezone_source": "web_region",
        }
    }

    output = get_inferred_timezone_visibility_context(
        state,
        "今天过得怎么样？",
    )

    assert output == ""


def test_inferred_timezone_visibility_uses_effective_timezone_when_timezone_missing():
    from agent.prompt.chat_contextprompt import get_inferred_timezone_visibility_context

    state = {
        "user": {
            "effective_timezone": "Asia/Tokyo",
            "timezone_status": "system_inferred",
            "timezone_source": "deployment_default",
        }
    }

    output = get_inferred_timezone_visibility_context(
        state,
        "你现在按什么时区理解时间？",
    )

    assert "Asia/Tokyo" in output
    assert "system inferred" in output.lower()


def test_inferred_timezone_visibility_uses_effective_timezone_for_local_time_question():
    from agent.prompt.chat_contextprompt import get_inferred_timezone_visibility_context

    state = {
        "user": {
            "effective_timezone": "Asia/Tokyo",
            "timezone_status": "system_inferred",
            "timezone_source": "deployment_default",
        }
    }

    output = get_inferred_timezone_visibility_context(
        state,
        "现在当地时间几点了？",
    )

    assert "Asia/Tokyo" in output
    assert "system inferred" in output.lower()


def test_confirmed_timezone_visibility_stays_quiet_for_local_time_question():
    from agent.prompt.chat_contextprompt import get_inferred_timezone_visibility_context

    state = {
        "user": {
            "timezone": "Europe/London",
            "timezone_status": "user_confirmed",
            "timezone_source": "user_explicit",
        }
    }

    output = get_inferred_timezone_visibility_context(
        state,
        "现在当地时间几点了？",
    )

    assert output == ""
