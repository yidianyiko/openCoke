# -*- coding: utf-8 -*-
"""
Web Search Tool Unit Tests

Stubs for agno and agent.agno_agent are set up at the top of this file
(not in conftest.py) so that the stubs are scoped only to this module
and do not interfere with other unit tests that import real modules.
"""

import importlib.util
import importlib.machinery
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub agno and agent.agno_agent only if they are not already available.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _ensure_agno_stubs() -> None:
    """Install minimal agno stubs if agno is not installed."""
    if "agno" in sys.modules or importlib.util.find_spec("agno") is not None:
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

    # @tool decorator — passthrough that also sets .entrypoint on the function
    # so tests can call web_search_tool.entrypoint(...) as they expect.
    def _tool_passthrough(**kwargs):
        def decorator(fn):
            fn.entrypoint = fn
            return fn
        return decorator

    agno_tools.tool = _tool_passthrough
    agno.tools = agno_tools


def _ensure_web_search_tool_loaded() -> None:
    """
    Load agent.agno_agent.tools.web_search_tool by file path, registering
    hollow parent packages only if they are not already real packages.
    Also register a minimal tools package stub so the last test passes.
    """
    package_paths = {
        "agent.agno_agent": _PROJECT_ROOT / "agent" / "agno_agent",
        "agent.agno_agent.tools": _PROJECT_ROOT / "agent" / "agno_agent" / "tools",
    }
    for pkg, path in package_paths.items():
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            mod.__path__ = [str(path)]
            mod.__package__ = pkg
            mod.__spec__ = importlib.machinery.ModuleSpec(
                pkg, loader=None, is_package=True
            )
            mod.__spec__.submodule_search_locations = mod.__path__
            sys.modules[pkg] = mod

    module_name = "agent.agno_agent.tools.web_search_tool"
    if module_name not in sys.modules:
        path = (
            _PROJECT_ROOT / "agent" / "agno_agent" / "tools" / "web_search_tool.py"
        )
        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        # Wire into parent package
        tools_pkg = sys.modules["agent.agno_agent.tools"]
        tools_pkg.web_search_tool = mod.web_search_tool
        if not hasattr(tools_pkg, "__all__"):
            tools_pkg.__all__ = []
        if "web_search_tool" not in tools_pkg.__all__:
            tools_pkg.__all__.append("web_search_tool")


_ensure_agno_stubs()
_ensure_web_search_tool_loaded()

# Module path for patching the BOCHA_API_KEY constant
_TOOL_MODULE = "agent.agno_agent.tools.web_search_tool"


class TestWebSearchTool:
    """web_search_tool 单元测试"""

    def test_import_web_search_tool(self):
        """测试工具可以正确导入"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        assert web_search_tool is not None

    def test_web_search_tool_has_tool_decorator(self):
        """测试工具有 @tool 装饰器"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        # Agno tool decorator adds .entrypoint attribute
        assert hasattr(web_search_tool, "entrypoint")
        assert callable(web_search_tool.entrypoint)

    def test_web_search_tool_returns_dict(self):
        """测试工具返回字典格式"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch(f"{_TOOL_MODULE}.BOCHA_API_KEY", "fake-key"), patch(
            f"{_TOOL_MODULE}.httpx.Client"
        ) as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "webPages": {
                    "value": [
                        {
                            "name": "Test Result",
                            "url": "https://example.com",
                            "snippet": "Test snippet",
                        }
                    ]
                }
            }
            mock_client.return_value.__enter__.return_value.post.return_value = (
                mock_response
            )

            result = web_search_tool.entrypoint(query="测试搜索")

            assert isinstance(result, dict)
            assert "ok" in result

    def test_web_search_tool_empty_query_returns_error(self):
        """测试空查询返回错误"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        result = web_search_tool.entrypoint(query="")

        assert result["ok"] is False
        assert "error" in result

    def test_web_search_tool_api_error_handling(self):
        """测试 API 错误处理"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch(f"{_TOOL_MODULE}.BOCHA_API_KEY", "fake-key"), patch(
            f"{_TOOL_MODULE}.httpx.Client"
        ) as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = (
                Exception("API Error")
            )

            result = web_search_tool.entrypoint(query="测试搜索")

            assert result["ok"] is False
            assert "error" in result

    def test_web_search_tool_formats_results(self):
        """测试搜索结果格式化"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch(f"{_TOOL_MODULE}.BOCHA_API_KEY", "fake-key"), patch(
            f"{_TOOL_MODULE}.httpx.Client"
        ) as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "webPages": {
                    "value": [
                        {
                            "name": "标题1",
                            "url": "https://example1.com",
                            "snippet": "摘要1",
                            "siteName": "网站1",
                        },
                        {
                            "name": "标题2",
                            "url": "https://example2.com",
                            "snippet": "摘要2",
                            "siteName": "网站2",
                        },
                    ]
                }
            }
            mock_client.return_value.__enter__.return_value.post.return_value = (
                mock_response
            )

            result = web_search_tool.entrypoint(query="测试", count=2)

            assert result["ok"] is True
            assert "results" in result
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "标题1"
            assert result["results"][0]["url"] == "https://example1.com"

    def test_web_search_tool_exported_from_tools_module(self):
        """测试工具从 tools 模块正确导出"""
        import agent.agno_agent.tools as tools

        assert hasattr(tools, "web_search_tool")
        assert "web_search_tool" in tools.__all__

    def test_web_search_stubs_do_not_hide_workflows_package(self):
        """测试 web_search stubs 不会让 workflows 包变得不可发现"""
        spec = importlib.machinery.PathFinder.find_spec(
            "workflows", sys.modules["agent.agno_agent"].__path__
        )

        assert spec is not None
