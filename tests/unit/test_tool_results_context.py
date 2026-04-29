from types import SimpleNamespace

import pytest


class CapturingStreamingAgent:
    def __init__(self):
        self.input = None

    async def arun(self, *, input, session_state, stream):
        self.input = input
        yield SimpleNamespace(
            content='{"MultiModalResponses":[{"type":"text","content":"ok"}]}'
        )


def install_chat_workflow_stubs(monkeypatch):
    import sys
    import types

    agno = types.ModuleType("agno")
    agno.__path__ = []
    agno_agent = types.ModuleType("agno.agent")
    agno_models = types.ModuleType("agno.models")
    agno_models.__path__ = []
    agno_tools = types.ModuleType("agno.tools")

    class StubClass:
        def __init__(self, *args, **kwargs):
            pass

        async def arun(self, *args, **kwargs):
            return None

    def tool_decorator(*args, **kwargs):
        def decorate(fn):
            return fn

        return decorate

    agno_agent.Agent = StubClass
    agno_tools.tool = tool_decorator

    monkeypatch.setitem(sys.modules, "agno", agno)
    monkeypatch.setitem(sys.modules, "agno.agent", agno_agent)
    monkeypatch.setitem(sys.modules, "agno.models", agno_models)
    monkeypatch.setitem(sys.modules, "agno.tools", agno_tools)
    monkeypatch.setitem(
        sys.modules,
        "agno.models.deepseek",
        types.SimpleNamespace(DeepSeek=StubClass),
    )
    monkeypatch.setitem(
        sys.modules,
        "agno.models.openai",
        types.SimpleNamespace(OpenAIChat=StubClass),
    )
    monkeypatch.setitem(
        sys.modules,
        "agno.models.siliconflow",
        types.SimpleNamespace(Siliconflow=StubClass),
    )


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


def test_reminder_operation_direct_reply_joins_exact_tool_summaries():
    from agent.prompt.chat_contextprompt import get_reminder_operation_direct_reply

    state = {
        "tool_results": [
            {
                "tool_name": "提醒操作",
                "ok": True,
                "result_summary": "已创建提醒：喝水（2026-04-29 18:02）",
                "extra_notes": "action=create",
            },
            {
                "tool_name": "提醒操作",
                "ok": True,
                "result_summary": "已创建提醒：吃饭（每天 18:04）",
                "extra_notes": "action=create",
            },
        ]
    }

    assert get_reminder_operation_direct_reply(state) == (
        "已创建提醒：喝水（2026-04-29 18:02）；"
        "已创建提醒：吃饭（每天 18:04）"
    )


def test_reminder_operation_direct_reply_skips_list_results():
    from agent.prompt.chat_contextprompt import get_reminder_operation_direct_reply

    state = {
        "tool_results": [
            {
                "tool_name": "提醒操作",
                "ok": True,
                "result_summary": "- 喝水 @ 2026-04-29T18:02:00+09:00",
                "extra_notes": "action=list",
            }
        ]
    }

    assert get_reminder_operation_direct_reply(state) == ""


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


def test_reminder_detect_instructions_require_aware_iso8601_rrule_and_batch():
    from agent.prompt.agent_instructions_prompt import (
        get_reminder_detect_instructions,
    )

    instructions = get_reminder_detect_instructions("2026年04月28日09时00分")

    assert "ISO 8601 aware datetime" in instructions
    assert "RFC 5545 RRULE" in instructions
    assert "batch" in instructions
    assert "multiple reminder operations" in instructions


@pytest.mark.asyncio
async def test_chat_workflow_adds_pending_reminder_notice_without_tool_result(
    monkeypatch,
):
    install_chat_workflow_stubs(monkeypatch)
    from agent.agno_agent.workflows.chat_workflow_streaming import (
        StreamingChatWorkflow,
    )

    workflow = StreamingChatWorkflow.__new__(StreamingChatWorkflow)
    workflow.agent = CapturingStreamingAgent()
    session_state = {
        "orchestrator": {"need_reminder_detect": True},
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月28日09时00分",
                "input_messages_str": "remind me tomorrow",
                "chat_history_str": "",
            }
        },
        "context_retrieve": {},
    }

    events = [
        event async for event in workflow.run_stream("remind me tomorrow", session_state)
    ]

    assert events[-1]["type"] == "done"
    assert "### System Notice: Reminder Setup Pending" in workflow.agent.input
    assert "Do not assume the reminder has been set successfully" in workflow.agent.input
    assert "Do not say you remembered" in workflow.agent.input
    assert "交给我" in workflow.agent.input
    assert "安排上" in workflow.agent.input
    assert "Ask one direct clarification question" in workflow.agent.input
    assert "Do not invent lead times" in workflow.agent.input
    assert "advance notice" in workflow.agent.input


@pytest.mark.asyncio
async def test_chat_workflow_directly_returns_reminder_tool_result(
    monkeypatch,
):
    install_chat_workflow_stubs(monkeypatch)
    from agent.agno_agent.workflows.chat_workflow_streaming import (
        StreamingChatWorkflow,
    )

    workflow = StreamingChatWorkflow.__new__(StreamingChatWorkflow)
    workflow.agent = CapturingStreamingAgent()
    session_state = {
        "orchestrator": {"need_reminder_detect": True},
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月28日09时00分",
                "input_messages_str": "remind me tomorrow",
                "chat_history_str": "",
            }
        },
        "context_retrieve": {},
        "tool_results": [
            {
                "tool_name": "提醒操作",
                "ok": True,
                "result_summary": "已创建提醒：喝水（2026-04-29 18:02）",
                "extra_notes": "",
            }
        ],
    }

    events = [
        event async for event in workflow.run_stream("remind me tomorrow", session_state)
    ]

    assert events[-1]["type"] == "done"
    assert events[0]["data"]["content"] == "已创建提醒：喝水（2026-04-29 18:02）"
    assert workflow.agent.input is None


@pytest.mark.asyncio
async def test_chat_workflow_directly_returns_prepare_direct_reply(monkeypatch):
    install_chat_workflow_stubs(monkeypatch)
    from agent.agno_agent.workflows.chat_workflow_streaming import (
        StreamingChatWorkflow,
    )

    workflow = StreamingChatWorkflow.__new__(StreamingChatWorkflow)
    workflow.agent = CapturingStreamingAgent()
    session_state = {
        "message_source": "user",
        "direct_reply": "可以循环提醒。请告诉我内容和时间。",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月28日09时00分",
                "input_messages_str": "你可以循环提醒我吗",
                "chat_history_str": "",
            }
        },
        "context_retrieve": {},
    }

    events = [
        event async for event in workflow.run_stream("你可以循环提醒我吗", session_state)
    ]

    assert events[-1]["type"] == "done"
    assert events[0]["data"]["content"] == "可以循环提醒。请告诉我内容和时间。"
    assert workflow.agent.input is None


@pytest.mark.asyncio
async def test_chat_workflow_keeps_pending_reminder_notice_for_unrelated_tool_result(
    monkeypatch,
):
    install_chat_workflow_stubs(monkeypatch)
    from agent.agno_agent.workflows.chat_workflow_streaming import (
        StreamingChatWorkflow,
    )

    workflow = StreamingChatWorkflow.__new__(StreamingChatWorkflow)
    workflow.agent = CapturingStreamingAgent()
    session_state = {
        "orchestrator": {"need_reminder_detect": True},
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月28日09时00分",
                "input_messages_str": "remind me tomorrow",
                "chat_history_str": "",
            }
        },
        "context_retrieve": {},
        "tool_results": [
            {
                "tool_name": "时区更新",
                "ok": True,
                "result_summary": "Updated timezone",
                "extra_notes": "",
            }
        ],
    }

    events = [
        event async for event in workflow.run_stream("remind me tomorrow", session_state)
    ]

    assert events[-1]["type"] == "done"
    assert "Updated timezone" in workflow.agent.input
    assert "### System Notice: Reminder Setup Pending" in workflow.agent.input


@pytest.mark.asyncio
async def test_chat_workflow_keeps_pending_notice_for_list_result_only(monkeypatch):
    install_chat_workflow_stubs(monkeypatch)
    from agent.agno_agent.workflows.chat_workflow_streaming import (
        StreamingChatWorkflow,
    )

    workflow = StreamingChatWorkflow.__new__(StreamingChatWorkflow)
    workflow.agent = CapturingStreamingAgent()
    session_state = {
        "orchestrator": {"need_reminder_detect": True},
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月28日09时00分",
                "input_messages_str": "remind me tomorrow",
                "chat_history_str": "",
            }
        },
        "context_retrieve": {},
        "tool_results": [
            {
                "tool_name": "提醒操作",
                "ok": True,
                "result_summary": "- 喝水 @ 2026-04-29T18:02:00+09:00",
                "extra_notes": "action=list",
            }
        ],
    }

    events = [
        event async for event in workflow.run_stream("remind me tomorrow", session_state)
    ]

    assert events[-1]["type"] == "done"
    assert "### System Notice: Reminder Setup Pending" in workflow.agent.input
