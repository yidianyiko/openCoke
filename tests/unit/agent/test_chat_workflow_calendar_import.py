import pytest


@pytest.mark.asyncio
async def test_calendar_import_tool_result_short_circuits_to_first_reply(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "agno", types.ModuleType("agno"))
    monkeypatch.setitem(
        sys.modules,
        "agno.agent",
        types.SimpleNamespace(Agent=object),
    )
    monkeypatch.setitem(sys.modules, "agno.models", types.ModuleType("agno.models"))
    monkeypatch.setitem(
        sys.modules, "agno.models.deepseek", types.SimpleNamespace(DeepSeek=object)
    )
    monkeypatch.setitem(
        sys.modules, "agno.models.openai", types.SimpleNamespace(OpenAIChat=object)
    )
    monkeypatch.setitem(
        sys.modules,
        "agno.models.siliconflow",
        types.SimpleNamespace(Siliconflow=object),
    )
    monkeypatch.setitem(sys.modules, "apscheduler", types.ModuleType("apscheduler"))
    monkeypatch.setitem(
        sys.modules, "apscheduler.jobstores", types.ModuleType("apscheduler.jobstores")
    )
    monkeypatch.setitem(
        sys.modules, "apscheduler.schedulers", types.ModuleType("apscheduler.schedulers")
    )
    monkeypatch.setitem(
        sys.modules,
        "apscheduler.jobstores.base",
        types.SimpleNamespace(JobLookupError=Exception),
    )
    monkeypatch.setitem(
        sys.modules,
        "apscheduler.schedulers.asyncio",
        types.SimpleNamespace(AsyncIOScheduler=lambda *args, **kwargs: object()),
    )
    taskprompt_mod = sys.modules.get("agent.prompt.chat_taskprompt") or types.ModuleType(
        "agent.prompt.chat_taskprompt"
    )
    taskprompt_mod.TASKPROMPT_微信对话 = ""
    taskprompt_mod.TASKPROMPT_微信对话_推理要求_纯文本 = ""
    monkeypatch.setitem(sys.modules, "agent.prompt.chat_taskprompt", taskprompt_mod)

    from agent.agno_agent.workflows.chat_workflow_streaming import StreamingChatWorkflow

    workflow = StreamingChatWorkflow.__new__(StreamingChatWorkflow)
    state = {
        "message_source": "user",
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
        ],
    }

    events = [event async for event in workflow.run_stream("我想导入谷歌日历", state)]

    assert events[0] == {
        "type": "message",
        "data": {
            "type": "text",
            "content": (
                "可以，打开这个入口导入 Google Calendar："
                "https://coke.example/account/calendar-import\n"
                "登录或验证邮箱后，点击 Start Google Calendar import 授权 Google。"
            ),
        },
    }
    assert events[1]["type"] == "done"
    assert events[1]["data"]["total_messages"] == 1
