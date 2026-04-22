# tests/unit/test_timezone_tools.py
"""
Tests for agent.agno_agent.tools.timezone_tools.

Stubs for agno and agent.agno_agent are set up at the top of this file
(not in conftest.py) so that the stubs are scoped only to this module
and do not interfere with other unit tests that import real modules.
"""
import sys
import time
import types
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub agno and agent.agno_agent only if they are not already available.
# This allows the test to run without the real agno package installed.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_AGNO_AGENT_ROOT = _PROJECT_ROOT / "agent" / "agno_agent"
_AGNO_AGENT_TOOLS_ROOT = _PROJECT_ROOT / "agent" / "agno_agent" / "tools"


def _ensure_agno_stubs() -> None:
    """Install minimal agno stubs if agno is not installed."""
    if "agno" in sys.modules:
        return

    def _make_package(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        mod.__path__ = []
        mod.__package__ = name
        mod.__spec__ = None
        sys.modules[name] = mod
        return mod

    agno = _make_package("agno")
    agno_tools = _make_package("agno.tools")
    agno_agent = _make_package("agno.agent")
    _make_package("agno.models")
    agno_models_deepseek = _make_package("agno.models.deepseek")
    _make_package("agno.memory")
    _make_package("agno.storage")
    _make_package("agno.embedder")
    _make_package("agno.embedder.dashscope")
    _make_package("agno.vectordb")
    _make_package("agno.vectordb.mongodb")
    _make_package("agno.workflow")
    _make_package("agno.workflow.workflow")
    _make_package("agno.run")
    _make_package("agno.run.response")

    # @tool decorator — passthrough that also sets .entrypoint on the function,
    # matching the real agno @tool decorator behaviour expected by tests.
    def _tool_passthrough(**kwargs):
        def decorator(fn):
            fn.entrypoint = fn
            return fn
        return decorator

    agno_tools.tool = _tool_passthrough
    agno.tools = agno_tools

    class _Agent:
        def __init__(self, *args, **kwargs):
            pass

    class _DeepSeek:
        def __init__(self, *args, **kwargs):
            pass

    agno_agent.Agent = _Agent
    agno_models_deepseek.DeepSeek = _DeepSeek


def _load_module_by_path(module_name: str, rel_path: str) -> None:
    """Load a module by file path and register it in sys.modules."""
    if module_name not in sys.modules:
        path = _PROJECT_ROOT / rel_path
        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        # Wire into parent package so attribute access works
        parent_name, _, attr = module_name.rpartition(".")
        if parent_name in sys.modules:
            setattr(sys.modules[parent_name], attr, mod)


def _ensure_timezone_tools_loaded() -> None:
    """
    Load agent.agno_agent.tools.timezone_tools by file path, registering
    hollow parent packages only if they are not already real packages.
    """
    # Only register hollow stubs for the parent packages if they don't
    # already exist as real importable packages.
    for pkg in ("agent.agno_agent", "agent.agno_agent.tools"):
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            if pkg == "agent.agno_agent":
                mod.__path__ = [str(_AGNO_AGENT_ROOT)]
            elif pkg == "agent.agno_agent.tools":
                mod.__path__ = [str(_AGNO_AGENT_TOOLS_ROOT)]
            else:
                mod.__path__ = []
            mod.__package__ = pkg
            mod.__spec__ = None
            sys.modules[pkg] = mod

    # Load tool_result first (timezone_tools imports it at call time)
    _load_module_by_path(
        "agent.agno_agent.tools.tool_result",
        "agent/agno_agent/tools/tool_result.py",
    )
    _load_module_by_path(
        "agent.agno_agent.tools.timezone_tools",
        "agent/agno_agent/tools/timezone_tools.py",
    )


_ensure_agno_stubs()
_ensure_timezone_tools_loaded()

import pytest  # noqa: E402 (must come after stubs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session_state(user_id="507f1f77bcf86cd799439011"):
    return {
        "user": {"id": user_id},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("agent.agno_agent.tools.timezone_tools.TimezoneService")
@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_uses_canonical_state_update(
    mock_dao_class,
    mock_service_class,
):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    dao_instance = MagicMock()
    dao_instance.get_timezone_state.return_value = {
        "timezone": "Asia/Shanghai",
        "timezone_source": "messaging_identity_region",
        "timezone_status": "system_inferred",
        "pending_timezone_change": {"timezone": "Europe/London"},
        "pending_task_draft": None,
    }
    dao_instance.update_timezone_state.return_value = True
    mock_dao_class.return_value = dao_instance

    service_instance = MagicMock()
    service_instance.apply_user_explicit_change.return_value = {
        "timezone": "America/New_York",
        "timezone_source": "user_explicit",
        "timezone_status": "user_confirmed",
        "pending_timezone_change": None,
        "pending_task_draft": None,
    }
    mock_service_class.return_value = service_instance

    session_state = make_session_state()
    result = set_user_timezone.entrypoint(
        timezone="America/New_York",
        session_state=session_state,
    )

    assert result["ok"] is True
    assert result["state"]["timezone"] == "America/New_York"
    service_instance.apply_user_explicit_change.assert_called_once_with(
        dao_instance.get_timezone_state.return_value,
        "America/New_York",
    )
    dao_instance.update_timezone_state.assert_called_once_with(
        "507f1f77bcf86cd799439011",
        service_instance.apply_user_explicit_change.return_value,
    )
    dao_instance.update_timezone.assert_not_called()
    assert session_state["tool_results"][0]["tool_name"] == "时区更新"
    assert session_state["tool_results"][0]["ok"] is True


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_invalid_iana(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    session_state = make_session_state()
    result = set_user_timezone.entrypoint(
        timezone="Not/AValid",
        session_state=session_state,
    )

    assert result["ok"] is False
    mock_dao_class.return_value.update_timezone.assert_not_called()


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_missing_user(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    result = set_user_timezone.entrypoint(
        timezone="Asia/Tokyo",
        session_state={},
    )

    assert result["ok"] is False
    mock_dao_class.return_value.update_timezone.assert_not_called()


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_consume_timezone_confirmation_rejects_other_conversation(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import consume_timezone_confirmation

    dao_instance = MagicMock()
    dao_instance.get_timezone_state.return_value = {
        "timezone": "Asia/Shanghai",
        "timezone_source": "messaging_identity_region",
        "timezone_status": "system_inferred",
        "pending_timezone_change": {
            "timezone": "Europe/London",
            "origin_conversation_id": "conv-1",
            "expires_at": 1770000000,
        },
        "pending_task_draft": None,
    }
    mock_dao_class.return_value = dao_instance

    result = consume_timezone_confirmation.entrypoint(
        decision="yes",
        session_state={"user": {"id": "acct-1"}, "conversation": {"_id": "conv-2"}},
    )

    assert result["ok"] is False
    dao_instance.update_timezone_state.assert_not_called()


@patch("agent.agno_agent.tools.timezone_tools.time.time", return_value=2000)
@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_consume_timezone_confirmation_rejects_expired_proposal(
    mock_dao_class,
    _mock_time,
):
    from agent.agno_agent.tools.timezone_tools import consume_timezone_confirmation

    dao_instance = MagicMock()
    dao_instance.get_timezone_state.return_value = {
        "timezone": "Asia/Shanghai",
        "timezone_source": "messaging_identity_region",
        "timezone_status": "system_inferred",
        "pending_timezone_change": {
            "timezone": "Europe/London",
            "origin_conversation_id": "conv-1",
            "expires_at": 1999,
        },
        "pending_task_draft": None,
    }
    dao_instance.update_timezone_state.return_value = True
    mock_dao_class.return_value = dao_instance

    result = consume_timezone_confirmation.entrypoint(
        decision="yes",
        session_state={"user": {"id": "acct-1"}, "conversation": {"_id": "conv-1"}},
    )

    assert result["ok"] is False
    assert "已过期" in result["message"]
    dao_instance.update_timezone_state.assert_called_once()
    persisted_state = dao_instance.update_timezone_state.call_args[0][1]
    assert persisted_state["timezone"] == "Asia/Shanghai"
    assert persisted_state["pending_timezone_change"] is None
