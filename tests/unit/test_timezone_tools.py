# tests/unit/test_timezone_tools.py
"""
Tests for agent.agno_agent.tools.timezone_tools.

Stubs for agno and agent.agno_agent are set up at the top of this file
(not in conftest.py) so that the stubs are scoped only to this module
and do not interfere with other unit tests that import real modules.
"""
import sys
import types
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub agno and agent.agno_agent only if they are not already available.
# This allows the test to run without the real agno package installed.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent


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
    _make_package("agno.agent")
    _make_package("agno.models")
    _make_package("agno.models.deepseek")
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
            mod.__path__ = []
            mod.__package__ = pkg
            mod.__spec__ = None
            sys.modules[pkg] = mod

    module_name = "agent.agno_agent.tools.timezone_tools"
    if module_name not in sys.modules:
        path = _PROJECT_ROOT / "agent" / "agno_agent" / "tools" / "timezone_tools.py"
        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        # Wire into parent package so attribute access works
        sys.modules["agent.agno_agent.tools"].timezone_tools = mod


_ensure_agno_stubs()
_ensure_timezone_tools_loaded()

import pytest  # noqa: E402 (must come after stubs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session_state(user_id="507f1f77bcf86cd799439011"):
    return {
        "user": {"_id": user_id},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_success(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    dao_instance = MagicMock()
    dao_instance.update_timezone.return_value = True
    mock_dao_class.return_value = dao_instance

    session_state = make_session_state()
    result = set_user_timezone(
        timezone="America/New_York",
        session_state=session_state,
    )

    assert result["ok"] is True
    assert "纽约" in result["message"] or "America/New_York" in result["message"]
    dao_instance.update_timezone.assert_called_once_with(
        "507f1f77bcf86cd799439011", "America/New_York"
    )


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_invalid_iana(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    session_state = make_session_state()
    result = set_user_timezone(
        timezone="Not/AValid",
        session_state=session_state,
    )

    assert result["ok"] is False
    mock_dao_class.return_value.update_timezone.assert_not_called()


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_missing_user(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    result = set_user_timezone(
        timezone="Asia/Tokyo",
        session_state={},
    )

    assert result["ok"] is False
    mock_dao_class.return_value.update_timezone.assert_not_called()
