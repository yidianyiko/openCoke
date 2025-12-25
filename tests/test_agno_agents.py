# -*- coding: utf-8 -*-
"""
Agno Agents 属性测试

测试动态 instructions 渲染完整性 (Requirements 4.5)
"""
import pytest

from agent.agno_agent.agents import (
    get_chat_response_instructions,
    get_orchestrator_instructions,
    get_post_analyze_instructions,
    get_query_rewrite_instructions,
    get_reminder_detect_instructions,
)


class TestDynamicInstructionsRendering:
    """测试动态 instructions 渲染完整性 (Requirements 4.5)"""

    def test_query_rewrite_instructions_without_context(self):
        """测试无上下文时的 QueryRewrite instructions"""
        result = get_query_rewrite_instructions()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_query_rewrite_instructions_with_empty_context(self):
        """测试空上下文时的 QueryRewrite instructions"""
        result = get_query_rewrite_instructions({})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_chat_response_instructions_without_context(self):
        """测试无上下文时的 ChatResponse instructions"""
        result = get_chat_response_instructions()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_chat_response_instructions_with_empty_context(self):
        """测试空上下文时的 ChatResponse instructions"""
        result = get_chat_response_instructions({})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_post_analyze_instructions_without_context(self):
        """测试无上下文时的 PostAnalyze instructions"""
        result = get_post_analyze_instructions()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_post_analyze_instructions_with_empty_context(self):
        """测试空上下文时的 PostAnalyze instructions"""
        result = get_post_analyze_instructions({})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_reminder_detect_instructions(self):
        """测试 ReminderDetect instructions"""
        result = get_reminder_detect_instructions()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "提醒" in result

    def test_orchestrator_instructions(self):
        """测试 Orchestrator instructions"""
        result = get_orchestrator_instructions()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_instructions_no_exception_with_partial_context(self):
        """测试部分上下文不会抛出异常"""
        partial_context = {
            "user": {"name": "测试用户"},
            "character": {"name": "测试角色"},
        }

        # 所有函数都不应该抛出异常
        get_query_rewrite_instructions(partial_context)
        get_chat_response_instructions(partial_context)
        get_post_analyze_instructions(partial_context)


class TestAgentInstantiation:
    """测试 Agent 实例化"""

    def test_agents_are_instantiated(self):
        """测试所有 Agent 都已实例化"""
        from agent.agno_agent.agents import (
            chat_response_agent,
            orchestrator_agent,
            post_analyze_agent,
            query_rewrite_agent,
            reminder_detect_agent,
        )

        assert query_rewrite_agent is not None
        assert reminder_detect_agent is not None
        assert orchestrator_agent is not None
        assert chat_response_agent is not None
        assert post_analyze_agent is not None

    def test_agents_have_required_attributes(self):
        """测试 Agent 具有必要属性"""
        from agent.agno_agent.agents import (
            chat_response_agent,
            orchestrator_agent,
            post_analyze_agent,
            query_rewrite_agent,
        )

        # 检查 id 属性
        assert query_rewrite_agent.id == "query-rewrite-agent"
        assert chat_response_agent.id == "chat-response-agent"
        assert post_analyze_agent.id == "post-analyze-agent"
        assert orchestrator_agent.id == "orchestrator-agent"

        # 检查 name 属性
        assert query_rewrite_agent.name == "QueryRewriteAgent"
        assert chat_response_agent.name == "ChatResponseAgent"
        assert post_analyze_agent.name == "PostAnalyzeAgent"
        assert orchestrator_agent.name == "OrchestratorAgent"
