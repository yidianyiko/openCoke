# -*- coding: utf-8 -*-
"""
OrchestratorSchema Web Search Extension Tests
"""

import pytest


class TestOrchestratorSchemaWebSearch:
    """OrchestratorSchema 联网搜索扩展测试"""

    def test_orchestrator_response_has_web_search_fields(self):
        """测试 OrchestratorResponse 包含联网搜索字段"""
        from agent.agno_agent.schemas.orchestrator_schema import OrchestratorResponse

        # 创建实例测试默认值
        response = OrchestratorResponse()

        assert hasattr(response, "need_web_search")
        assert hasattr(response, "web_search_query")
        assert response.need_web_search is False
        assert response.web_search_query == ""

    def test_orchestrator_response_web_search_serialization(self):
        """测试联网搜索字段序列化"""
        from agent.agno_agent.schemas.orchestrator_schema import OrchestratorResponse

        response = OrchestratorResponse(
            need_web_search=True,
            web_search_query="杭州今天天气",
        )

        data = response.model_dump()

        assert data["need_web_search"] is True
        assert data["web_search_query"] == "杭州今天天气"
