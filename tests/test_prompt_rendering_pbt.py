# -*- coding: utf-8 -*-
"""
Prompt 模板渲染属性测试 (Property-Based Testing)

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
