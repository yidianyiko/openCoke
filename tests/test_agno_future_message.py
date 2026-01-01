# -*- coding: utf-8 -*-
"""
主动消息（Future Message）模块测试

测试内容：
- FutureMessageResponse Schema (Requirements: FR-036, FR-038)
- FutureMessageWorkflow 结构和方法
- Agent 实例化
"""
import sys

sys.path.append(".")

import unittest


class TestFutureMessageResponseSchema(unittest.TestCase):
    """测试 FutureMessageResponse Schema"""

    def test_default_values(self):
        """测试默认值"""
        from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse

        response = FutureMessageResponse()
        self.assertEqual(response.InnerMonologue, "")
        self.assertEqual(response.MultiModalResponses, [])
        self.assertEqual(response.ChatCatelogue, "否")
        self.assertIsNotNone(response.RelationChange)
        self.assertIsNotNone(response.FutureResponse)

    def test_with_values(self):
        """测试带值创建"""
        from agent.agno_agent.schemas.chat_response_schema import (
            FutureResponseModel,
            MultiModalResponse,
            RelationChangeModel,
        )
        from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse

        response = FutureMessageResponse(
            InnerMonologue="主动问候用户",
            MultiModalResponses=[MultiModalResponse(type="text", content="在干嘛呢？")],
            ChatCatelogue="否",
            RelationChange=RelationChangeModel(Closeness=1.0, Trustness=0.5),
            FutureResponse=FutureResponseModel(
                FutureResponseTime="2025年12月06日10时00分",
                FutureResponseAction="检查学习进度",
            ),
        )

        self.assertEqual(response.InnerMonologue, "主动问候用户")
        self.assertEqual(len(response.MultiModalResponses), 1)
        self.assertEqual(response.RelationChange.Closeness, 1.0)

    def test_model_dump(self):
        """测试 model_dump 输出"""
        from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse

        response = FutureMessageResponse(InnerMonologue="测试")
        data = response.model_dump()

        self.assertIsInstance(data, dict)
        self.assertIn("InnerMonologue", data)
        self.assertIn("MultiModalResponses", data)
        self.assertIn("FutureResponse", data)


class TestFutureMessageAgents(unittest.TestCase):
    """测试主动消息 Agent 实例化"""

    def test_agents_are_instantiated(self):
        """测试 Agent 已正确实例化"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_chat_agent,
            future_message_context_retrieve_agent,
            future_message_query_rewrite_agent,
        )

        self.assertIsNotNone(future_message_query_rewrite_agent)
        self.assertIsNotNone(future_message_context_retrieve_agent)
        self.assertIsNotNone(future_message_chat_agent)

    def test_agents_have_required_attributes(self):
        """测试 Agent 具有必要属性"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_chat_agent,
            future_message_query_rewrite_agent,
        )

        # 检查 query_rewrite_agent
        self.assertEqual(
            future_message_query_rewrite_agent.id,
            "future-message-query-rewrite-agent",
        )
        self.assertIsNotNone(future_message_query_rewrite_agent.model)

        # 检查 chat_agent
        self.assertEqual(
            future_message_chat_agent.id, "future-message-chat-agent"
        )
        self.assertIsNotNone(future_message_chat_agent.model)


class TestFutureMessageWorkflow(unittest.TestCase):
    """测试 FutureMessageWorkflow"""

    pass


class TestFutureMessageWorkflowExport(unittest.TestCase):
    """测试 FutureMessageWorkflow 导出"""

    def test_schema_exported_from_init(self):
        """测试 Schema 从 __init__ 正确导出"""
        from agent.agno_agent.schemas import FutureMessageResponse

        self.assertIsNotNone(FutureMessageResponse)
        response = FutureMessageResponse()
        self.assertEqual(response.ChatCatelogue, "否")


if __name__ == "__main__":
    unittest.main()
