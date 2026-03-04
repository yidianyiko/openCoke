# -*- coding: utf-8 -*-
"""
Unit test conftest for tests/unit/.

Pre-stubs heavyweight / unavailable packages (agno, pydantic compat, etc.)
so that @patch('agent.agno_agent.tools.timezone_tools.UserDAO') decorators
can resolve paths without triggering the full import chain.

The strategy:
1. Stub sys.modules entries for 'agent.agno_agent' and its sub-packages
   using real types.ModuleType objects that have a __path__ (marking them
   as packages). This prevents Python's import machinery from trying to
   load agent/agno_agent/__init__.py when walking the dotted path.
2. Actually load the specific tool module (timezone_tools.py) by file path
   so its real implementation is available for testing.
"""
import sys
import types
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _make_package(name: str) -> types.ModuleType:
    """Create a minimal package stub and register it in sys.modules."""
    mod = types.ModuleType(name)
    mod.__path__ = []           # required for Python to treat it as a package
    mod.__package__ = name
    mod.__spec__ = None
    sys.modules[name] = mod
    return mod


def _setup_agno_stubs() -> None:
    """
    Stub agno and its sub-modules so that 'from agno.tools import tool' resolves
    to a no-op decorator without requiring the real agno package.
    """
    if "agno" in sys.modules:
        return

    agno = _make_package("agno")
    agno_tools = _make_package("agno.tools")
    agno_agent_mod = _make_package("agno.agent")
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

    # The @tool decorator — make it a passthrough so decorated functions
    # remain ordinary callables in tests.
    def _tool_passthrough(**kwargs):
        def decorator(fn):
            return fn
        return decorator

    agno_tools.tool = _tool_passthrough
    agno.tools = agno_tools
    agno_agent_mod.Agent = MagicMock(name="Agent")


def _setup_agno_agent_stubs() -> None:
    """
    Stub agent.agno_agent package hierarchy so that @patch can resolve dotted
    paths like 'agent.agno_agent.tools.timezone_tools.UserDAO' without
    importing agent/agno_agent/__init__.py (which has broken transitive deps).
    """
    # agent is a namespace package (no __init__.py); it auto-registers
    # but we need to make sure sub-packages are registered.
    if "agent.agno_agent" not in sys.modules:
        _make_package("agent.agno_agent")
    if "agent.agno_agent.tools" not in sys.modules:
        _make_package("agent.agno_agent.tools")

    # Now load the actual timezone_tools module by file path so the real
    # implementation is tested, not a mock.
    module_name = "agent.agno_agent.tools.timezone_tools"
    if module_name not in sys.modules:
        path = _PROJECT_ROOT / "agent" / "agno_agent" / "tools" / "timezone_tools.py"
        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)

        # Wire it into the parent package so attribute access works
        sys.modules["agent.agno_agent.tools"].timezone_tools = mod


# Run stubs at import time (module-level) so they are in place before any
# @patch decorator is evaluated during test collection.
_setup_agno_stubs()
_setup_agno_agent_stubs()
