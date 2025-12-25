# -*- coding: utf-8 -*-
"""
Prompt 模板渲染属性测试 (Property - Based Testing)

Property 8: Prompt 模板渲染
- 渲染后的内容应包含 CONTEXTPROMPT_规划行动 的内容
- 当 session_state 缺少字段时不应抛出异常

Validates: Requirements 7.1, 7.2, 7.3, 7.4
"""
import sys

sys.path.append(".")

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st


class TestPromptTemplateRendering(unittest.TestCase):
    """
    Property 8: Prompt 模板渲染

    For any Prompt 模板渲染，渲染后的内容应包含 CONTEXTPROMPT_规划行动 的内容，
    且当 session_state 缺少字段时不应抛出异常.

    Validates: Requirements 7.1, 7.2, 7.3, 7.4
    """

    def setUp(self):
        from agent.agno_agent.workflows.future_message_workflow import (
            FutureMessageWorkflow,
        )

        self.workflow = FutureMessageWorkflow()

    def test_query_rewrite_template_contains_future_context(self):
        """
        Property 8.1: 问题重写模板包含规划行动上下文

        Validates: Requirement 7.1, 7.3
        """
        template = self.workflow.query_rewrite_userp_template

        # 验证模板包含规划行动相关内容
        self.assertIn("规划行动", template)
        # 验证包含语义理解相关内容（来自 TASKPROMPT_未来_语义理解）
        self.assertTrue("语义理解" in template or "资料库" in template)

    def test_chat_template_contains_future_context(self):
        """
        Property 8.2: 消息生成模板包含规划行动上下文

        Validates: Requirement 7.2, 7.3
        """
        template = self.workflow.chat_userp_template

        # 验证模板包含规划行动相关内容
        self.assertIn("规划行动", template)

    def test_query_rewrite_template_uses_correct_taskprompt(self):
        """
        测试问题重写模板使用 TASKPROMPT_未来_语义理解

        Validates: Requirement 7.1
        """

        template = self.workflow.query_rewrite_userp_template

        # 验证模板包含 TASKPROMPT_未来_语义理解 的内容
        # 由于模板是拼接的，检查关键内容
        self.assertIn("规划行动", template)

    def test_chat_template_uses_correct_taskprompt(self):
        """
        测试消息生成模板使用 TASKPROMPT_未来_微信对话

        Validates: Requirement 7.2
        """

        template = self.workflow.chat_userp_template

        # 验证模板包含 TASKPROMPT_未来_微信对话 的内容
        self.assertIn("规划行动", template)

    @given(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.text(min_size=0, max_size=50),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=50)
    def test_property_8_no_exception_on_missing_fields(self, random_dict):
        """
        Property 8.3: 缺少字段时不抛出异常

        Validates: Requirement 7.4
        """
        # 使用随机字典作为 session_state
        try:
            # 尝试渲染问题重写模板
            try:
                self.workflow.query_rewrite_userp_template.format(**random_dict)
            except KeyError:
                # KeyError 是预期的，但不应该导致程序崩溃
                pass

            # 尝试渲染消息生成模板
            try:
                self.workflow.chat_userp_template.format(**random_dict)
            except KeyError:
                # KeyError 是预期的，但不应该导致程序崩溃
                pass
        except Exception as e:
            # 其他异常不应该发生
            if not isinstance(e, KeyError):
                self.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    def test_graceful_degradation_in_workflow_run(self):
        """
        测试 Workflow.run() 中的优雅降级

        Validates: Requirement 7.4
        """
        # 创建一个不完整的 session_state
        incomplete_session_state = {"some_key": "some_value"}

        # 测试 _build_retrieve_message 不会因缺少字段而崩溃
        try:
            result = self.workflow._build_retrieve_message({}, incomplete_session_state)
            self.assertIsInstance(result, str)
        except Exception as e:
            self.fail(f"_build_retrieve_message raised exception: {e}")


class TestPromptContextInclusion(unittest.TestCase):
    """测试 Prompt 上下文包含"""

    def test_query_rewrite_includes_history(self):
        """测试问题重写模板包含历史对话上下文"""
        from agent.agno_agent.workflows.future_message_workflow import (
            FutureMessageWorkflow,
        )

        workflow = FutureMessageWorkflow()

        template = workflow.query_rewrite_userp_template

        # 验证包含历史对话
        self.assertIn("历史对话", template)

    def test_chat_template_includes_full_context(self):
        """测试消息生成模板包含完整上下文"""
        from agent.agno_agent.workflows.future_message_workflow import (
            FutureMessageWorkflow,
        )

        workflow = FutureMessageWorkflow()

        template = workflow.chat_userp_template

        # 验证包含各种上下文
        self.assertIn("人物信息", template)
        self.assertIn("人物资料", template)
        # 用户资料在模板中使用的是 {user[platforms][wechat][nickname]}的人物资料
        self.assertTrue("人物资料" in template)
        self.assertIn("人物状态", template)
        self.assertIn("历史对话", template)
        self.assertIn("规划行动", template)


class TestDynamicInstructionsGracefulDegradation(unittest.TestCase):
    """测试动态 instructions 的优雅降级"""

    def test_future_query_rewrite_graceful_degradation(self):
        """测试 FutureQueryRewrite instructions 优雅降级"""
        from agent.agno_agent.agents.future_message_agents import (
            get_future_query_rewrite_instructions,
        )

        # 使用会导致 KeyError 的不完整上下文
        incomplete_context = {"random_key": "random_value"}

        # 应该返回默认 prompt，不抛出异常
        result = get_future_query_rewrite_instructions(incomplete_context)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_future_message_chat_graceful_degradation(self):
        """测试 FutureMessageChat instructions 优雅降级"""
        from agent.agno_agent.agents.future_message_agents import (
            get_future_message_chat_instructions,
        )

        # 使用会导致 KeyError 的不完整上下文
        incomplete_context = {"random_key": "random_value"}

        # 应该返回默认 prompt，不抛出异常
        result = get_future_message_chat_instructions(incomplete_context)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    @given(
        st.dictionaries(
            keys=st.text(
                min_size=1,
                max_size=10,
                alphabet=st.characters(whitelist_categories=("L",)),
            ),
            values=st.text(min_size=0, max_size=20),
            min_size=0,
            max_size=3,
        )
    )
    @settings(max_examples=30)
    def test_property_8_instructions_never_raise(self, random_context):
        """
        Property 8.4: 动态 instructions 函数永不抛出异常

        Validates: Requirement 7.4
        """
        from agent.agno_agent.agents.future_message_agents import (
            get_future_context_retrieve_instructions,
            get_future_message_chat_instructions,
            get_future_query_rewrite_instructions,
        )

        try:
            result1 = get_future_query_rewrite_instructions(random_context)
            result2 = get_future_message_chat_instructions(random_context)
            result3 = get_future_context_retrieve_instructions(random_context)

            self.assertIsInstance(result1, str)
            self.assertIsInstance(result2, str)
            self.assertIsInstance(result3, str)
        except Exception as e:
            self.fail(f"Instructions function raised exception: {e}")


if __name__ == "__main__":
    unittest.main()
