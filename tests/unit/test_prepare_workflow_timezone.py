# -*- coding: utf-8 -*-
"""
PrepareWorkflow timezone integration tests.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_AGNO_AGENT_ROOT = _PROJECT_ROOT / "agent" / "agno_agent"
_AGNO_AGENT_WORKFLOWS_ROOT = _AGNO_AGENT_ROOT / "workflows"
_AGNO_AGENT_TOOLS_ROOT = _AGNO_AGENT_ROOT / "tools"
_AGNO_AGENT_UTILS_ROOT = _AGNO_AGENT_ROOT / "utils"


def _make_package(name: str, path: Path | None = None) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)] if path else []
    mod.__package__ = name
    mod.__spec__ = importlib.util.spec_from_loader(name, loader=None, is_package=True)
    sys.modules[name] = mod
    return mod


def _load_module_by_path(module_name: str, rel_path: str) -> None:
    if module_name in sys.modules:
        return

    path = _PROJECT_ROOT / rel_path
    if path.name == "__init__.py":
        spec = importlib.util.spec_from_file_location(
            module_name,
            path,
            submodule_search_locations=[str(path.parent)],
        )
    else:
        spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    parent_name, _, attr = module_name.rpartition(".")
    if parent_name in sys.modules:
        setattr(sys.modules[parent_name], attr, mod)


def _ensure_prepare_workflow_loaded() -> None:
    if "agent.agno_agent.workflows.prepare_workflow" in sys.modules:
        return

    if "agno" not in sys.modules:
        agno_mod = _make_package("agno")
        agno_tools_mod = _make_package("agno.tools")

        def _tool_passthrough(**kwargs):
            def decorator(fn):
                fn.entrypoint = fn
                return fn

            return decorator

        agno_tools_mod.tool = _tool_passthrough
        agno_mod.tools = agno_tools_mod

    if "agent.agno_agent" not in sys.modules:
        _make_package("agent.agno_agent", _AGNO_AGENT_ROOT)
    if "agent.agno_agent.workflows" not in sys.modules:
        _make_package("agent.agno_agent.workflows", _AGNO_AGENT_WORKFLOWS_ROOT)
    if "agent.agno_agent.tools" not in sys.modules:
        _make_package("agent.agno_agent.tools", _AGNO_AGENT_TOOLS_ROOT)
    if "agent.agno_agent.utils" not in sys.modules:
        _make_package("agent.agno_agent.utils", _AGNO_AGENT_UTILS_ROOT)
    if "agent.prompt" not in sys.modules:
        _make_package("agent.prompt", _PROJECT_ROOT / "agent" / "prompt")
    if "agent.util" not in sys.modules:
        _make_package("agent.util", _PROJECT_ROOT / "agent" / "util")

    if "agent.agno_agent.agents" not in sys.modules:
        agents_mod = types.ModuleType("agent.agno_agent.agents")
        agents_mod.orchestrator_agent = types.SimpleNamespace(arun=AsyncMock())
        agents_mod.reminder_detect_agent = types.SimpleNamespace(arun=AsyncMock())
        sys.modules["agent.agno_agent.agents"] = agents_mod
        sys.modules["agent.agno_agent"].agents = agents_mod

    if "agent.agno_agent.tools.context_retrieve_tool" not in sys.modules:
        context_mod = types.ModuleType("agent.agno_agent.tools.context_retrieve_tool")
        context_mod.context_retrieve_tool = lambda **kwargs: {}
        sys.modules["agent.agno_agent.tools.context_retrieve_tool"] = context_mod
        sys.modules["agent.agno_agent.tools"].context_retrieve_tool = context_mod

    if "agent.agno_agent.tools.url_reader" not in sys.modules:
        url_mod = types.ModuleType("agent.agno_agent.tools.url_reader")
        url_mod.extract_urls_content = lambda _message: []
        url_mod.format_url_context = lambda _items: ""
        sys.modules["agent.agno_agent.tools.url_reader"] = url_mod
        sys.modules["agent.agno_agent.tools"].url_reader = url_mod

    if "agent.agno_agent.tools.web_search_tool" not in sys.modules:
        web_mod = types.ModuleType("agent.agno_agent.tools.web_search_tool")
        web_mod.web_search_tool = types.SimpleNamespace(
            entrypoint=lambda query: {"ok": True, "results": [], "formatted": ""}
        )
        sys.modules["agent.agno_agent.tools.web_search_tool"] = web_mod
        sys.modules["agent.agno_agent.tools"].web_search_tool = web_mod

    if "agent.agno_agent.utils.usage_tracker" not in sys.modules:
        tracker_mod = types.ModuleType("agent.agno_agent.utils.usage_tracker")
        tracker_mod.usage_tracker = types.SimpleNamespace(
            record_from_metrics=lambda **kwargs: None
        )
        sys.modules["agent.agno_agent.utils.usage_tracker"] = tracker_mod
        sys.modules["agent.agno_agent.utils"].usage_tracker = tracker_mod

    if "agent.prompt.rendering" not in sys.modules:
        rendering_mod = types.ModuleType("agent.prompt.rendering")
        rendering_mod.render_prompt_template = lambda template, _context: template
        sys.modules["agent.prompt.rendering"] = rendering_mod
        sys.modules["agent.prompt"].rendering = rendering_mod

    if "agent.prompt.chat_taskprompt" not in sys.modules:
        taskprompt_mod = types.ModuleType("agent.prompt.chat_taskprompt")
        taskprompt_mod.TASKPROMPT_语义理解 = ""
        sys.modules["agent.prompt.chat_taskprompt"] = taskprompt_mod
        sys.modules["agent.prompt"].chat_taskprompt = taskprompt_mod

    if "agent.util.message_util" not in sys.modules:
        message_util_mod = types.ModuleType("agent.util.message_util")
        message_util_mod.messages_to_str = lambda messages: "\n".join(
            str(message) for message in messages
        )
        sys.modules["agent.util.message_util"] = message_util_mod
        sys.modules["agent.util"].message_util = message_util_mod

    _load_module_by_path(
        "agent.prompt.chat_contextprompt",
        "agent/prompt/chat_contextprompt.py",
    )
    _load_module_by_path(
        "agent.agno_agent.tools.tool_result",
        "agent/agno_agent/tools/tool_result.py",
    )
    _load_module_by_path(
        "agent.agno_agent.tools.timezone_tools",
        "agent/agno_agent/tools/timezone_tools.py",
    )
    if "agent.agno_agent.tools.deferred_action" not in sys.modules:
        deferred_mod = _make_package(
            "agent.agno_agent.tools.deferred_action",
            _AGNO_AGENT_TOOLS_ROOT / "deferred_action",
        )
        sys.modules["agent.agno_agent.tools"].deferred_action = deferred_mod

    deferred_mod = sys.modules["agent.agno_agent.tools.deferred_action"]
    if not hasattr(deferred_mod, "set_deferred_action_session_state"):
        deferred_mod.set_deferred_action_session_state = lambda session_state: None

    _load_module_by_path(
        "agent.agno_agent.tools.deferred_action.time_parser",
        "agent/agno_agent/tools/deferred_action/time_parser.py",
    )
    _load_module_by_path(
        "agent.agno_agent.workflows.prepare_workflow",
        "agent/agno_agent/workflows/prepare_workflow.py",
    )


_ensure_prepare_workflow_loaded()


def _session_state_with_pending(pending_timezone_change=None):
    return {
        "conversation": {
            "_id": "conv-1",
            "conversation_info": {
                "time_str": "2026年04月23日",
                "chat_history": [],
            },
        },
        "character": {"_id": "char-1"},
        "user": {
            "id": "user-1",
            "timezone": "Asia/Shanghai",
            "timezone_status": "system_inferred",
            "timezone_source": "messaging_identity_region",
            "pending_timezone_change": pending_timezone_change,
        },
    }


def _orchestrator_result(*, timezone_action="none", timezone_value=""):
    return {
        "inner_monologue": "",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": False,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": timezone_action != "none",
        "timezone_action": timezone_action,
        "timezone_value": timezone_value,
    }


class TestPrepareWorkflowTimezone:
    @pytest.mark.asyncio
    async def test_prepare_workflow_surfaces_google_calendar_import_link(self, monkeypatch):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        monkeypatch.setenv("DOMAIN_CLIENT", "https://coke.example")
        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending()

        async def fake_orchestrator(_message, state):
            state["orchestrator"] = _orchestrator_result()

        with patch.object(
            workflow,
            "_run_orchestrator",
            AsyncMock(side_effect=fake_orchestrator),
        ):
            result = await workflow.run("我想导入谷歌日历", session_state)

        assert result["session_state"]["tool_results"] == [
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

    @pytest.mark.asyncio
    async def test_prepare_workflow_applies_direct_timezone_change(self):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending()

        async def fake_orchestrator(_message, state):
            state["orchestrator"] = _orchestrator_result(
                timezone_action="direct_set",
                timezone_value="Asia/Tokyo",
            )

        with (
            patch.object(
                workflow,
                "_run_orchestrator",
                AsyncMock(side_effect=fake_orchestrator),
            ),
            patch(
                "agent.agno_agent.workflows.prepare_workflow.set_user_timezone.entrypoint",
                return_value={
                    "ok": True,
                    "message": "已切换到东京时间",
                    "state": {
                        "timezone": "Asia/Tokyo",
                        "timezone_status": "user_confirmed",
                        "timezone_source": "user_explicit",
                        "pending_timezone_change": None,
                        "pending_task_draft": None,
                    },
                },
            ) as mock_set_timezone,
        ):
            result = await workflow.run("改成东京时间", session_state)

        mock_set_timezone.assert_called_once()
        assert result["session_state"]["timezone_update_message"] == "已切换到东京时间"

    @pytest.mark.asyncio
    async def test_prepare_workflow_legacy_need_timezone_update_still_direct_sets(self):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending()

        async def fake_orchestrator(_message, state):
            state["orchestrator"] = {
                "inner_monologue": "",
                "need_context_retrieve": False,
                "context_retrieve_params": {},
                "need_reminder_detect": False,
                "need_web_search": False,
                "web_search_query": "",
                "need_timezone_update": True,
                "timezone_value": "Asia/Tokyo",
            }

        with (
            patch.object(
                workflow,
                "_run_orchestrator",
                AsyncMock(side_effect=fake_orchestrator),
            ),
            patch(
                "agent.agno_agent.workflows.prepare_workflow.set_user_timezone.entrypoint",
                return_value={
                    "ok": True,
                    "message": "已切换到东京时间",
                    "state": {
                        "timezone": "Asia/Tokyo",
                        "timezone_status": "user_confirmed",
                        "timezone_source": "user_explicit",
                        "pending_timezone_change": None,
                        "pending_task_draft": None,
                    },
                },
            ) as mock_set_timezone,
        ):
            result = await workflow.run("改成东京时间", session_state)

        mock_set_timezone.assert_called_once()
        assert result["session_state"]["user"]["timezone"] == "Asia/Tokyo"

    @pytest.mark.asyncio
    async def test_prepare_workflow_ignores_unknown_timezone_action(self):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending()

        async def fake_orchestrator(_message, state):
            state["orchestrator"] = {
                **_orchestrator_result(),
                "need_timezone_update": True,
                "timezone_action": "mystery_mode",
                "timezone_value": "Asia/Tokyo",
            }

        with (
            patch.object(
                workflow,
                "_run_orchestrator",
                AsyncMock(side_effect=fake_orchestrator),
            ),
            patch(
                "agent.agno_agent.workflows.prepare_workflow.set_user_timezone.entrypoint"
            ) as mock_set_timezone,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.store_timezone_proposal.entrypoint"
            ) as mock_store_proposal,
        ):
            result = await workflow.run("切到东京", session_state)

        mock_set_timezone.assert_not_called()
        mock_store_proposal.assert_not_called()
        assert "timezone_update_message" not in result["session_state"]
        assert result["session_state"]["user"]["timezone"] == "Asia/Shanghai"

    @pytest.mark.asyncio
    async def test_prepare_workflow_stores_pending_timezone_proposal(self):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending()

        async def fake_orchestrator(_message, state):
            state["orchestrator"] = _orchestrator_result(
                timezone_action="proposal",
                timezone_value="Europe/London",
            )

        with (
            patch.object(
                workflow,
                "_run_orchestrator",
                AsyncMock(side_effect=fake_orchestrator),
            ),
            patch(
                "agent.agno_agent.workflows.prepare_workflow.store_timezone_proposal.entrypoint",
                return_value={
                    "ok": True,
                    "message": "检测到您可能在伦敦，需要确认是否切换时区。",
                    "state": {
                        "timezone": "Asia/Shanghai",
                        "timezone_status": "system_inferred",
                        "timezone_source": "messaging_identity_region",
                        "pending_timezone_change": {
                            "timezone": "Europe/London",
                            "origin_conversation_id": "conv-1",
                            "expires_at": 1770000000,
                        },
                        "pending_task_draft": None,
                    },
                },
            ) as mock_store_proposal,
        ):
            result = await workflow.run("我现在在伦敦", session_state)

        mock_store_proposal.assert_called_once()
        pending = result["session_state"]["user"]["pending_timezone_change"]
        assert pending["timezone"] == "Europe/London"
        assert pending["origin_conversation_id"] == "conv-1"
        assert pending["expires_at"] == 1770000000

    @pytest.mark.asyncio
    async def test_prepare_workflow_upgrades_explicit_future_timezone_request_to_direct_set(
        self,
    ):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending()

        async def fake_orchestrator(_message, state):
            state["orchestrator"] = _orchestrator_result(
                timezone_action="proposal",
                timezone_value="America/New_York",
            )

        with (
            patch.object(
                workflow,
                "_run_orchestrator",
                AsyncMock(side_effect=fake_orchestrator),
            ),
            patch(
                "agent.agno_agent.workflows.prepare_workflow.set_user_timezone.entrypoint",
                return_value={
                    "ok": True,
                    "message": "已切换到纽约时间",
                    "state": {
                        "timezone": "America/New_York",
                        "timezone_status": "user_confirmed",
                        "timezone_source": "user_explicit",
                        "pending_timezone_change": None,
                        "pending_task_draft": None,
                    },
                },
            ) as mock_set_timezone,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.store_timezone_proposal.entrypoint"
            ) as mock_store_proposal,
        ):
            result = await workflow.run(
                "我现在在纽约，之后按纽约时间和我说",
                session_state,
            )

        mock_set_timezone.assert_called_once()
        mock_store_proposal.assert_not_called()
        assert result["session_state"]["user"]["timezone"] == "America/New_York"

    @pytest.mark.asyncio
    async def test_prepare_workflow_consumes_same_conversation_short_confirmation(self):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending(
            {
                "timezone": "Europe/London",
                "origin_conversation_id": "conv-1",
                "expires_at": 1893456000,
            }
        )

        with (
            patch.object(workflow, "_run_orchestrator", AsyncMock()) as mock_orchestrator,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.consume_timezone_confirmation.entrypoint",
                return_value={
                    "ok": True,
                    "message": "已切换到伦敦时间。",
                    "state": {
                        "timezone": "Europe/London",
                        "timezone_status": "user_confirmed",
                        "timezone_source": "user_confirmation",
                        "pending_timezone_change": None,
                        "pending_task_draft": None,
                    },
                },
            ) as mock_consume_confirmation,
        ):
            result = await workflow.run("yes", session_state)

        mock_consume_confirmation.assert_called_once_with(
            decision="yes",
            session_state=session_state,
        )
        mock_orchestrator.assert_not_awaited()
        assert result["session_state"]["timezone_update_message"] == "已切换到伦敦时间。"
        assert result["session_state"]["user"]["timezone"] == "Europe/London"
        assert result["session_state"]["user"]["pending_timezone_change"] is None

    @pytest.mark.asyncio
    async def test_prepare_workflow_clears_expired_proposal_for_non_confirmation_message(
        self,
    ):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending(
            {
                "timezone": "Europe/London",
                "origin_conversation_id": "conv-1",
                "expires_at": 1000,
            }
        )

        async def fake_orchestrator(_message, state):
            state["orchestrator"] = _orchestrator_result()

        with (
            patch.object(
                workflow,
                "_run_orchestrator",
                AsyncMock(side_effect=fake_orchestrator),
            ) as mock_orchestrator,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.is_timezone_proposal_expired",
                return_value=True,
            ),
            patch(
                "agent.agno_agent.workflows.prepare_workflow.clear_pending_timezone_proposal",
                return_value={
                    "ok": True,
                    "state": {
                        "timezone": "Asia/Shanghai",
                        "timezone_status": "system_inferred",
                        "timezone_source": "messaging_identity_region",
                        "pending_timezone_change": None,
                        "pending_task_draft": None,
                    },
                },
            ) as mock_clear_pending,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.consume_timezone_confirmation.entrypoint"
            ) as mock_consume_confirmation,
        ):
            result = await workflow.run("tell me more", session_state)

        mock_clear_pending.assert_called_once_with(session_state=session_state)
        mock_consume_confirmation.assert_not_called()
        mock_orchestrator.assert_awaited_once()
        assert result["session_state"]["user"]["pending_timezone_change"] is None
        assert "tool_results" not in result["session_state"]

    @pytest.mark.asyncio
    async def test_prepare_workflow_surfaces_expired_confirmation_reply(self):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow
        from agent.agno_agent.tools.timezone_tools import (
            PENDING_PROPOSAL_EXPIRED_MESSAGE,
        )

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending(
            {
                "timezone": "Europe/London",
                "origin_conversation_id": "conv-1",
                "expires_at": 1000,
            }
        )

        with (
            patch.object(workflow, "_run_orchestrator", AsyncMock()) as mock_orchestrator,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.is_timezone_proposal_expired",
                return_value=True,
            ),
            patch(
                "agent.agno_agent.workflows.prepare_workflow.clear_pending_timezone_proposal",
                return_value={
                    "ok": True,
                    "state": {
                        "timezone": "Asia/Shanghai",
                        "timezone_status": "system_inferred",
                        "timezone_source": "messaging_identity_region",
                        "pending_timezone_change": None,
                        "pending_task_draft": None,
                    },
                },
            ) as mock_clear_pending,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.consume_timezone_confirmation.entrypoint"
            ) as mock_consume_confirmation,
        ):
            result = await workflow.run("yes", session_state)

        mock_clear_pending.assert_called_once_with(session_state=session_state)
        mock_consume_confirmation.assert_not_called()
        mock_orchestrator.assert_not_awaited()
        assert result["session_state"]["user"]["pending_timezone_change"] is None
        assert result["session_state"]["tool_results"] == [
            {
                "tool_name": "时区确认",
                "ok": False,
                "result_summary": PENDING_PROPOSAL_EXPIRED_MESSAGE,
                "extra_notes": "",
            }
        ]

    @pytest.mark.asyncio
    async def test_prepare_workflow_clears_pending_proposal_on_unrelated_message(self):
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()
        session_state = _session_state_with_pending(
            {
                "timezone": "Europe/London",
                "origin_conversation_id": "conv-1",
                "expires_at": 1893456000,
            }
        )
        session_state["user"]["pending_task_draft"] = {"kind": "visible_reminder"}

        async def fake_orchestrator(_message, state):
            state["orchestrator"] = _orchestrator_result()

        with (
            patch.object(
                workflow,
                "_run_orchestrator",
                AsyncMock(side_effect=fake_orchestrator),
            ) as mock_orchestrator,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.clear_pending_timezone_proposal",
                return_value={
                    "ok": True,
                    "state": {
                        "timezone": "Asia/Shanghai",
                        "timezone_status": "system_inferred",
                        "timezone_source": "messaging_identity_region",
                        "pending_timezone_change": None,
                        "pending_task_draft": None,
                    },
                },
            ) as mock_clear_pending,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.is_timezone_proposal_expired",
                return_value=False,
            ),
            patch(
                "agent.agno_agent.workflows.prepare_workflow.consume_timezone_confirmation.entrypoint"
            ) as mock_consume_confirmation,
        ):
            result = await workflow.run("tell me more", session_state)

        mock_clear_pending.assert_called_once_with(session_state=session_state)
        mock_consume_confirmation.assert_not_called()
        mock_orchestrator.assert_awaited_once()
        assert result["session_state"]["user"]["pending_timezone_change"] is None
        assert result["session_state"]["user"]["pending_task_draft"] is None
