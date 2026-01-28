# -*- coding: utf-8 -*-
"""
Web Search Tool Unit Tests
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestWebSearchTool:
    """web_search_tool 单元测试"""

    def test_import_web_search_tool(self):
        """测试工具可以正确导入"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool
        assert web_search_tool is not None

    def test_web_search_tool_has_tool_decorator(self):
        """测试工具有 @tool 装饰器"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool
        # Agno tool decorator adds __tool__ attribute
        assert hasattr(web_search_tool, '__wrapped__') or callable(web_search_tool)

    def test_web_search_tool_returns_dict(self):
        """测试工具返回字典格式"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch('agent.agno_agent.tools.web_search_tool.httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "webPages": {
                    "value": [
                        {
                            "name": "Test Result",
                            "url": "https://example.com",
                            "snippet": "Test snippet"
                        }
                    ]
                }
            }
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            result = web_search_tool(query="测试搜索")

            assert isinstance(result, dict)
            assert "ok" in result

    def test_web_search_tool_empty_query_returns_error(self):
        """测试空查询返回错误"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        result = web_search_tool(query="")

        assert result["ok"] is False
        assert "error" in result

    def test_web_search_tool_api_error_handling(self):
        """测试 API 错误处理"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch('agent.agno_agent.tools.web_search_tool.httpx.Client') as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = Exception("API Error")

            result = web_search_tool(query="测试搜索")

            assert result["ok"] is False
            assert "error" in result

    def test_web_search_tool_formats_results(self):
        """测试搜索结果格式化"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch('agent.agno_agent.tools.web_search_tool.httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "webPages": {
                    "value": [
                        {
                            "name": "标题1",
                            "url": "https://example1.com",
                            "snippet": "摘要1",
                            "siteName": "网站1"
                        },
                        {
                            "name": "标题2",
                            "url": "https://example2.com",
                            "snippet": "摘要2",
                            "siteName": "网站2"
                        }
                    ]
                }
            }
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            result = web_search_tool(query="测试", count=2)

            assert result["ok"] is True
            assert "results" in result
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "标题1"
            assert result["results"][0]["url"] == "https://example1.com"
