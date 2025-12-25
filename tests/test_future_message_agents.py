# -*- coding: utf-8 -*-
"""
Future Message Agents 单元测试

测试主动消息相关 Agent 的实现：
- FutureMessageQueryRewriteAgent (Requirements 2.1, 2.4)
- FutureMessageContextRetrieveAgent (Requirements 2.2)
- FutureMessageChatAgent (Requirements 2.3, 2.4)

Validates: Requirements 2.1, 2.2, 2.3, 2.4
"""
import sys

sys.path.append(".")

import unittest


class TestFutureMessageAgentInstantiation(unittest.TestCase):
    """测试 Future Message Agent 实例化"""

    def test_agents_are_instantiated(self):
        """测试所有 Future Message Agent 都已实例化"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_chat_agent,
            future_message_context_retrieve_agent,
            future_message_query_rewrite_agent,
        )

        self.assertIsNotNone(future_message_query_rewrite_agent)
        self.assertIsNotNone(future_message_context_retrieve_agent)
        self.assertIsNotNone(future_message_chat_agent)

    def test_query_rewrite_agent_attributes(self):
        """测试 FutureMessageQueryRewriteAgent 属性 (Requirements 2.1)"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_query_rewrite_agent,
        )
        from agent.agno_agent.schemas.query_rewrite_schema import QueryRewriteResponse

        # 检查 id 和 name
        self.assertEqual(
            future_message_query_rewrite_agent.id,
            "future-message-query-rewrite-agent",
        )
        self.assertEqual(
            future_message_query_rewrite_agent.name, "FutureMessageQueryRewriteAgent"
        )

        # 检查 output_schema 配置为 QueryRewriteResponse
        self.assertEqual(
            future_message_query_rewrite_agent.output_schema, QueryRewriteResponse
        )

    def test_context_retrieve_agent_attributes(self):
        """测试 FutureMessageContextRetrieveAgent 属性 (Requirements 2.2)"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_context_retrieve_agent,
        )

        # 检查 id 和 name
        self.assertEqual(
            future_message_context_retrieve_agent.id,
            "future-message-context-retrieve-agent",
        )
        self.assertEqual(
            future_message_context_retrieve_agent.name,
            "FutureMessageContextRetrieveAgent",
        )

        # 检查 tools 包含 context_retrieve_tool
        self.assertIsNotNone(future_message_context_retrieve_agent.tools)
        self.assertGreater(len(future_message_context_retrieve_agent.tools), 0)

    def test_chat_agent_attributes(self):
        """测试 FutureMessageChatAgent 属性 (Requirements 2.3)"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_chat_agent,
        )
        from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse

        # 检查 id 和 name
        self.assertEqual(
            future_message_chat_agent.id, "future-message-chat-agent"
        )
        self.assertEqual(future_message_chat_agent.name, "FutureMessageChatAgent")

        # 检查 output_schema 配置为 FutureMessageResponse
        self.assertEqual(future_message_chat_agent.output_schema, FutureMessageResponse)


class TestFutureMessageDynamicInstructions(unittest.TestCase):
    """测试 Future Message Agent 动态 instructions 渲染 (Requirements 2.4)"""

    def setUp(self):
        from agent.agno_agent.agents.future_message_agents import (
            get_future_context_retrieve_instructions,
            get_future_message_chat_instructions,
            get_future_query_rewrite_instructions,
        )

        self.get_future_query_rewrite_instructions = (
            get_future_query_rewrite_instructions
        )
        self.get_future_message_chat_instructions = get_future_message_chat_instructions
        self.get_future_context_retrieve_instructions = (
            get_future_context_retrieve_instructions
        )

    def test_query_rewrite_instructions_without_context(self):
        """测试无上下文时的 FutureQueryRewrite instructions"""
        result = self.get_future_query_rewrite_instructions()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_query_rewrite_instructions_with_empty_context(self):
        """测试空上下文时的 FutureQueryRewrite instructions"""
        result = self.get_future_query_rewrite_instructions({})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_chat_instructions_without_context(self):
        """测试无上下文时的 FutureMessageChat instructions"""
        result = self.get_future_message_chat_instructions()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_chat_instructions_with_empty_context(self):
        """测试空上下文时的 FutureMessageChat instructions"""
        result = self.get_future_message_chat_instructions({})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_context_retrieve_instructions(self):
        """测试 FutureContextRetrieve instructions"""
        result = self.get_future_context_retrieve_instructions()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        # 验证包含关键内容
        self.assertIn("检索", result)
        self.assertIn("规划行动", result)

    def test_instructions_no_exception_with_partial_context(self):
        """测试部分上下文不会抛出异常"""
        partial_context = {
            "user": {"name": "测试用户"},
            "character": {"name": "测试角色"},
            "conversation": {"conversation_info": {"future": {"action": "测试行动"}}},
        }

        # 所有函数都不应该抛出异常
        try:
            self.get_future_query_rewrite_instructions(partial_context)
            self.get_future_message_chat_instructions(partial_context)
            self.get_future_context_retrieve_instructions(partial_context)
        except Exception as e:
            self.fail(f"Instructions rendering raised exception: {e}")

    def test_instructions_graceful_degradation(self):
        """测试 instructions 渲染失败时的优雅降级"""
        # 使用会导致 KeyError 的不完整上下文
        incomplete_context = {"some_random_key": "value"}

        # 应该返回默认 prompt，不抛出异常
        result1 = self.get_future_query_rewrite_instructions(incomplete_context)
        result2 = self.get_future_message_chat_instructions(incomplete_context)
        result3 = self.get_future_context_retrieve_instructions(incomplete_context)

        self.assertIsInstance(result1, str)
        self.assertIsInstance(result2, str)
        self.assertIsInstance(result3, str)


class TestFutureMessageAgentOutputSchema(unittest.TestCase):
    """测试 Future Message Agent 输出格式"""

    def test_query_rewrite_output_schema_fields(self):
        """测试 QueryRewriteResponse 包含所有必需字段"""
        from agent.agno_agent.schemas.query_rewrite_schema import QueryRewriteResponse

        # 创建默认实例
        response = QueryRewriteResponse()

        # 验证所有必需字段存在
        self.assertTrue(hasattr(response, "InnerMonologue"))
        self.assertTrue(hasattr(response, "CharacterSettingQueryQuestion"))
        self.assertTrue(hasattr(response, "CharacterSettingQueryKeywords"))
        self.assertTrue(hasattr(response, "UserProfileQueryQuestion"))
        self.assertTrue(hasattr(response, "UserProfileQueryKeywords"))
        self.assertTrue(hasattr(response, "CharacterKnowledgeQueryQuestion"))
        self.assertTrue(hasattr(response, "CharacterKnowledgeQueryKeywords"))

    def test_future_message_response_output_schema_fields(self):
        """测试 FutureMessageResponse 包含所有必需字段"""
        from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse

        # 创建默认实例
        response = FutureMessageResponse()

        # 验证所有必需字段存在
        self.assertTrue(hasattr(response, "InnerMonologue"))
        self.assertTrue(hasattr(response, "MultiModalResponses"))
        self.assertTrue(hasattr(response, "ChatCatelogue"))
        self.assertTrue(hasattr(response, "RelationChange"))
        self.assertTrue(hasattr(response, "FutureResponse"))

        # 验证 FutureResponse 子字段
        self.assertTrue(hasattr(response.FutureResponse, "FutureResponseTime"))
        self.assertTrue(hasattr(response.FutureResponse, "FutureResponseAction"))


class TestFutureMessageAgentExports(unittest.TestCase):
    """测试 Future Message Agent 模块导出"""

    def test_all_exports_available(self):
        """测试所有导出项可用"""
        from agent.agno_agent.agents.future_message_agents import __all__

        expected_exports = [
            "get_future_query_rewrite_instructions",
            "get_future_message_chat_instructions",
            "get_future_context_retrieve_instructions",
            "future_message_query_rewrite_agent",
            "future_message_context_retrieve_agent",
            "future_message_chat_agent",
        ]

        for export in expected_exports:
            self.assertIn(export, __all__)

    def test_can_import_all_exports(self):
        """测试可以导入所有导出项"""
        try:
            from agent.agno_agent.agents.future_message_agents import (
                future_message_chat_agent,
                future_message_context_retrieve_agent,
                future_message_query_rewrite_agent,
                get_future_context_retrieve_instructions,
                get_future_message_chat_instructions,
                get_future_query_rewrite_instructions,
            )
        except ImportError as e:
            self.fail(f"Failed to import exports: {e}")


if __name__ == "__main__":
    unittest.main()
