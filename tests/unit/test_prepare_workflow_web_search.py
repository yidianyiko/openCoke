# -*- coding: utf-8 -*-
"""
PrepareWorkflow Web Search Integration Tests
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPrepareWorkflowWebSearch:
    """PrepareWorkflow 联网搜索集成测试"""

    @pytest.mark.asyncio
    async def test_web_search_executed_when_needed(self):
        """测试当 need_web_search=True 时执行搜索"""
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()

        # Mock orchestrator_agent 返回 need_web_search=True
        mock_orchestrator_response = MagicMock()
        mock_orchestrator_response.content = MagicMock()
        mock_orchestrator_response.metrics = None
        mock_orchestrator_response.content.model_dump.return_value = {
            "inner_monologue": "用户询问天气",
            "need_context_retrieve": True,
            "context_retrieve_params": {},
            "need_reminder_detect": False,
            "need_web_search": True,
            "web_search_query": "杭州今天天气",
        }

        with (
            patch(
                "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
            ) as mock_orch,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
            ) as mock_ctx,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.web_search_tool.entrypoint"
            ) as mock_search,
        ):

            mock_orch.arun = AsyncMock(return_value=mock_orchestrator_response)
            mock_ctx.return_value = {"character_global": "", "user": ""}
            mock_search.return_value = {
                "ok": True,
                "results": [{"title": "天气", "snippet": "晴天"}],
                "formatted": "【联网搜索结果】\n1. 天气 - 晴天",
            }

            session_state = {
                "conversation": {
                    "conversation_info": {
                        "time_str": "2026年01月28日",
                        "chat_history": [],
                    }
                },
                "character": {"_id": "char1"},
                "user": {"_id": "user1"},
            }

            result = await workflow.run("杭州今天天气怎么样", session_state)

            # 验证搜索被调用
            mock_search.assert_called_once_with(query="杭州今天天气")

            # 验证结果存入 session_state
            assert "web_search_result" in result["session_state"]
            assert result["session_state"]["web_search_result"]["ok"] is True

    @pytest.mark.asyncio
    async def test_web_search_skipped_when_not_needed(self):
        """测试当 need_web_search=False 时跳过搜索"""
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()

        mock_orchestrator_response = MagicMock()
        mock_orchestrator_response.content = MagicMock()
        mock_orchestrator_response.metrics = None
        mock_orchestrator_response.content.model_dump.return_value = {
            "inner_monologue": "普通闲聊",
            "need_context_retrieve": True,
            "context_retrieve_params": {},
            "need_reminder_detect": False,
            "need_web_search": False,
            "web_search_query": "",
        }

        with (
            patch(
                "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
            ) as mock_orch,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
            ) as mock_ctx,
            patch(
                "agent.agno_agent.workflows.prepare_workflow.web_search_tool.entrypoint"
            ) as mock_search,
        ):

            mock_orch.arun = AsyncMock(return_value=mock_orchestrator_response)
            mock_ctx.return_value = {"character_global": "", "user": ""}

            session_state = {
                "conversation": {
                    "conversation_info": {
                        "time_str": "2026年01月28日",
                        "chat_history": [],
                    }
                },
                "character": {"_id": "char1"},
                "user": {"_id": "user1"},
            }

            await workflow.run("你好呀", session_state)

            # 验证搜索未被调用
            mock_search.assert_not_called()
