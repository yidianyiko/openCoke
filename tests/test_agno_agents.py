# -*- coding: utf-8 -*-
"""
Agno Agents 属性测试

测试动态 instructions 渲染完整性 (Requirements 4.5)
"""
import sys
sys.path.append(".")

import unittest


class TestDynamicInstructionsRendering(unittest.TestCase):
    """测试动态 instructions 渲染完整性 (Requirements 4.5)"""
    
    def setUp(self):
        from qiaoyun.agno_agent.agents import (
            get_query_rewrite_instructions,
            get_chat_response_instructions,
            get_post_analyze_instructions,
            get_reminder_detect_instructions,
            get_context_retrieve_instructions,
        )
        self.get_query_rewrite_instructions = get_query_rewrite_instructions
        self.get_chat_response_instructions = get_chat_response_instructions
        self.get_post_analyze_instructions = get_post_analyze_instructions
        self.get_reminder_detect_instructions = get_reminder_detect_instructions
        self.get_context_retrieve_instructions = get_context_retrieve_instructions
    
    def test_query_rewrite_instructions_without_context(self):
        """测试无上下文时的 QueryRewrite instructions"""
        result = self.get_query_rewrite_instructions()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
    
    def test_query_rewrite_instructions_with_empty_context(self):
        """测试空上下文时的 QueryRewrite instructions"""
        result = self.get_query_rewrite_instructions({})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
    
    def test_chat_response_instructions_without_context(self):
        """测试无上下文时的 ChatResponse instructions"""
        result = self.get_chat_response_instructions()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
    
    def test_chat_response_instructions_with_empty_context(self):
        """测试空上下文时的 ChatResponse instructions"""
        result = self.get_chat_response_instructions({})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
    
    def test_post_analyze_instructions_without_context(self):
        """测试无上下文时的 PostAnalyze instructions"""
        result = self.get_post_analyze_instructions()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
    
    def test_post_analyze_instructions_with_empty_context(self):
        """测试空上下文时的 PostAnalyze instructions"""
        result = self.get_post_analyze_instructions({})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
    
    def test_reminder_detect_instructions(self):
        """测试 ReminderDetect instructions"""
        result = self.get_reminder_detect_instructions()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        # 验证包含关键内容
        self.assertIn("提醒", result)
    
    def test_context_retrieve_instructions(self):
        """测试 ContextRetrieve instructions"""
        result = self.get_context_retrieve_instructions()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        # 验证包含关键内容
        self.assertIn("检索", result)
    
    def test_instructions_no_exception_with_partial_context(self):
        """测试部分上下文不会抛出异常"""
        partial_context = {
            "user": {"name": "测试用户"},
            "character": {"name": "测试角色"}
        }
        
        # 所有函数都不应该抛出异常
        try:
            self.get_query_rewrite_instructions(partial_context)
            self.get_chat_response_instructions(partial_context)
            self.get_post_analyze_instructions(partial_context)
        except Exception as e:
            self.fail(f"Instructions rendering raised exception: {e}")


class TestAgentInstantiation(unittest.TestCase):
    """测试 Agent 实例化"""
    
    def test_agents_are_instantiated(self):
        """测试所有 Agent 都已实例化"""
        from qiaoyun.agno_agent.agents import (
            query_rewrite_agent,
            reminder_detect_agent,
            context_retrieve_agent,
            chat_response_agent,
            post_analyze_agent,
        )
        
        self.assertIsNotNone(query_rewrite_agent)
        self.assertIsNotNone(reminder_detect_agent)
        self.assertIsNotNone(context_retrieve_agent)
        self.assertIsNotNone(chat_response_agent)
        self.assertIsNotNone(post_analyze_agent)
    
    def test_agents_have_required_attributes(self):
        """测试 Agent 具有必要属性"""
        from qiaoyun.agno_agent.agents import (
            query_rewrite_agent,
            chat_response_agent,
            post_analyze_agent,
        )
        
        # 检查 id 属性
        self.assertEqual(query_rewrite_agent.id, "query-rewrite-agent")
        self.assertEqual(chat_response_agent.id, "chat-response-agent")
        self.assertEqual(post_analyze_agent.id, "post-analyze-agent")
        
        # 检查 name 属性
        self.assertEqual(query_rewrite_agent.name, "QueryRewriteAgent")
        self.assertEqual(chat_response_agent.name, "ChatResponseAgent")
        self.assertEqual(post_analyze_agent.name, "PostAnalyzeAgent")


if __name__ == "__main__":
    unittest.main()
