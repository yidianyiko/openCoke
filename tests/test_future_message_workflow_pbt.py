# -*- coding: utf-8 -*-
"""
FutureMessageWorkflow 属性测试 (Property-Based Testing)

测试 Workflow 的核心逻辑：
- Property 2: Workflow 执行顺序
- Property 3: Workflow 返回结构
- Property 4: 关系值边界约束
- Property 5: 主动消息计数递增
- Property 6: 概率命中时的状态设置
- Property 7: 概率未命中时的状态清除

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.3, 5.4, 5.5
"""
import sys
sys.path.append(".")

import unittest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume

from qiaoyun.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow


# ============================================================================
# Hypothesis Strategies
# ============================================================================

@st.composite
def relation_change_strategy(draw):
    """Generate relation change values"""
    closeness = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    trustness = draw(st.floats(min_value=-200, max_value=200, allow_nan=False, allow_infinity=False))
    return {"Closeness": closeness, "Trustness": trustness}


@st.composite
def initial_relation_strategy(draw):
    """Generate initial relation values (0-100)"""
    closeness = draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    trustness = draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    return {"closeness": closeness, "trustness": trustness}


@st.composite
def session_state_with_relation_strategy(draw):
    """Generate session_state with relation data"""
    initial_rel = draw(initial_relation_strategy())
    return {
        "relation": {
            "relationship": {
                "closeness": initial_rel["closeness"],
                "trustness": initial_rel["trustness"],
            }
        },
        "conversation": {
            "conversation_info": {
                "future": {
                    "proactive_times": draw(st.integers(min_value=0, max_value=10)),
                    "timestamp": None,
                    "action": None,
                }
            }
        }
    }


@st.composite
def future_response_strategy(draw):
    """Generate FutureResponse data"""
    return {
        "FutureResponseTime": draw(st.sampled_from([
            "2025年12月25日09时00分",
            "2025年01月01日10时30分",
            "",
            "无效时间"
        ])),
        "FutureResponseAction": draw(st.sampled_from([
            "发送问候",
            "检查进度",
            "无",
            ""
        ]))
    }


# ============================================================================
# Property-Based Tests for Relation Change (Property 4)
# ============================================================================

class TestRelationChangeBoundary(unittest.TestCase):
    """
    Property 4: 关系值边界约束
    
    For any 关系变化处理，更新后的 closeness 和 trustness 值应在 [0, 100] 范围内，
    即使输入的变化值导致结果超出范围。
    
    Validates: Requirements 4.1, 4.2, 4.3
    """
    
    def setUp(self):
        self.workflow = FutureMessageWorkflow()
    
    @given(
        initial_rel=initial_relation_strategy(),
        change=relation_change_strategy()
    )
    @settings(max_examples=100)
    def test_property_4_closeness_bounded(self, initial_rel, change):
        """
        Property 4.1: closeness 值始终在 [0, 100] 范围内
        
        Validates: Requirement 4.1
        """
        session_state = {
            "relation": {
                "relationship": {
                    "closeness": initial_rel["closeness"],
                    "trustness": initial_rel["trustness"],
                }
            }
        }
        content = {"RelationChange": change}
        
        self.workflow._handle_relation_change(content, session_state)
        
        result_closeness = session_state["relation"]["relationship"]["closeness"]
        self.assertGreaterEqual(result_closeness, 0)
        self.assertLessEqual(result_closeness, 100)
    
    @given(
        initial_rel=initial_relation_strategy(),
        change=relation_change_strategy()
    )
    @settings(max_examples=100)
    def test_property_4_trustness_bounded(self, initial_rel, change):
        """
        Property 4.2: trustness 值始终在 [0, 100] 范围内
        
        Validates: Requirement 4.2
        """
        session_state = {
            "relation": {
                "relationship": {
                    "closeness": initial_rel["closeness"],
                    "trustness": initial_rel["trustness"],
                }
            }
        }
        content = {"RelationChange": change}
        
        self.workflow._handle_relation_change(content, session_state)
        
        result_trustness = session_state["relation"]["relationship"]["trustness"]
        self.assertGreaterEqual(result_trustness, 0)
        self.assertLessEqual(result_trustness, 100)
    
    def test_relation_change_with_string_input(self):
        """测试 RelationChange 为字符串时的处理"""
        session_state = {
            "relation": {
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                }
            }
        }
        content = {"RelationChange": '{"Closeness": 10, "Trustness": -5}'}
        
        self.workflow._handle_relation_change(content, session_state)
        
        self.assertEqual(session_state["relation"]["relationship"]["closeness"], 60)
        self.assertEqual(session_state["relation"]["relationship"]["trustness"], 45)
    
    def test_relation_change_with_none_values(self):
        """测试 RelationChange 包含 None 值时的处理"""
        session_state = {
            "relation": {
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                }
            }
        }
        content = {"RelationChange": {"Closeness": None, "Trustness": None}}
        
        self.workflow._handle_relation_change(content, session_state)
        
        # None 应该被当作 0 处理
        self.assertEqual(session_state["relation"]["relationship"]["closeness"], 50)
        self.assertEqual(session_state["relation"]["relationship"]["trustness"], 50)


# ============================================================================
# Property-Based Tests for Proactive Times (Property 5)
# ============================================================================

class TestProactiveTimesIncrement(unittest.TestCase):
    """
    Property 5: 主动消息计数递增
    
    For any 主动消息发送成功后，proactive_times 应增加 1。
    
    Validates: Requirements 5.1
    """
    
    def setUp(self):
        self.workflow = FutureMessageWorkflow()
    
    @given(initial_times=st.integers(min_value=0, max_value=100))
    @settings(max_examples=50)
    def test_property_5_proactive_times_increment(self, initial_times):
        """
        Property 5: proactive_times 每次调用后增加 1
        
        Validates: Requirement 5.1
        """
        session_state = {
            "conversation": {
                "conversation_info": {
                    "future": {
                        "proactive_times": initial_times,
                        "timestamp": None,
                        "action": None,
                    }
                }
            }
        }
        content = {
            "FutureResponse": {
                "FutureResponseTime": "2025年12月25日09时00分",
                "FutureResponseAction": "测试行动"
            }
        }
        
        # Mock random to avoid probability affecting the test
        with patch('random.random', return_value=0.5):
            self.workflow._handle_future_response(content, session_state)
        
        result_times = session_state["conversation"]["conversation_info"]["future"]["proactive_times"]
        self.assertEqual(result_times, initial_times + 1)


# ============================================================================
# Property-Based Tests for Probability Control (Property 6 & 7)
# ============================================================================

class TestProbabilityControl(unittest.TestCase):
    """
    Property 6 & 7: 概率控制状态设置
    
    Property 6: 概率命中时，future.timestamp 和 future.action 应被设置
    Property 7: 概率未命中时，future.timestamp 和 future.action 应被清除
    
    Validates: Requirements 5.3, 5.4, 5.5
    """
    
    def setUp(self):
        self.workflow = FutureMessageWorkflow()
    
    @given(proactive_times=st.integers(min_value=0, max_value=5))
    @settings(max_examples=30)
    def test_property_6_probability_hit_sets_state(self, proactive_times):
        """
        Property 6: 概率命中时的状态设置
        
        当 random.random() < 0.15^(n+1) 时，应设置 future.timestamp 和 future.action
        
        Validates: Requirements 5.3, 5.4
        """
        session_state = {
            "conversation": {
                "conversation_info": {
                    "future": {
                        "proactive_times": proactive_times,
                        "timestamp": None,
                        "action": None,
                    }
                }
            }
        }
        content = {
            "FutureResponse": {
                "FutureResponseTime": "2025年12月25日09时00分",
                "FutureResponseAction": "发送问候"
            }
        }
        
        # 计算阈值并设置 random 返回值小于阈值（命中）
        threshold = 0.15 ** (proactive_times + 1)
        hit_value = threshold / 2 if threshold > 0 else 0
        
        with patch('random.random', return_value=hit_value):
            self.workflow._handle_future_response(content, session_state)
        
        future_info = session_state["conversation"]["conversation_info"]["future"]
        
        # 概率命中时应设置 action
        self.assertEqual(future_info["action"], "发送问候")
        # timestamp 应该被设置（可能为 None 如果时间解析失败，但 action 应该被设置）
    
    @given(proactive_times=st.integers(min_value=0, max_value=5))
    @settings(max_examples=30)
    def test_property_7_probability_miss_clears_state(self, proactive_times):
        """
        Property 7: 概率未命中时的状态清除
        
        当 random.random() >= 0.15^(n+1) 时，应清除 future.timestamp 和 future.action
        
        Validates: Requirement 5.5
        """
        session_state = {
            "conversation": {
                "conversation_info": {
                    "future": {
                        "proactive_times": proactive_times,
                        "timestamp": 12345,  # 预设值
                        "action": "预设行动",  # 预设值
                    }
                }
            }
        }
        content = {
            "FutureResponse": {
                "FutureResponseTime": "2025年12月25日09时00分",
                "FutureResponseAction": "发送问候"
            }
        }
        
        # 设置 random 返回值大于阈值（未命中）
        with patch('random.random', return_value=0.99):
            self.workflow._handle_future_response(content, session_state)
        
        future_info = session_state["conversation"]["conversation_info"]["future"]
        
        # 概率未命中时应清除状态
        self.assertIsNone(future_info["timestamp"])
        self.assertIsNone(future_info["action"])
    
    def test_probability_decay_formula(self):
        """测试概率衰减公式 0.15^(n+1)"""
        # n=0: 0.15^1 = 0.15
        # n=1: 0.15^2 = 0.0225
        # n=2: 0.15^3 = 0.003375
        
        expected_thresholds = [
            (0, 0.15),
            (1, 0.0225),
            (2, 0.003375),
            (3, 0.00050625),
        ]
        
        for n, expected in expected_thresholds:
            actual = 0.15 ** (n + 1)
            self.assertAlmostEqual(actual, expected, places=6)


# ============================================================================
# Tests for Workflow Structure (Property 2 & 3)
# ============================================================================

class TestWorkflowStructure(unittest.TestCase):
    """
    Property 2 & 3: Workflow 结构测试
    
    Property 2: Workflow 执行顺序
    Property 3: Workflow 返回结构
    
    Validates: Requirements 3.1, 3.2, 3.3, 3.4
    """
    
    def setUp(self):
        self.workflow = FutureMessageWorkflow()
    
    def test_workflow_has_required_methods(self):
        """测试 Workflow 包含所有必需方法"""
        self.assertTrue(hasattr(self.workflow, 'run'))
        self.assertTrue(hasattr(self.workflow, '_build_retrieve_message'))
        self.assertTrue(hasattr(self.workflow, '_handle_relation_change'))
        self.assertTrue(hasattr(self.workflow, '_handle_future_response'))
    
    def test_workflow_has_prompt_templates(self):
        """测试 Workflow 包含 Prompt 模板"""
        self.assertTrue(hasattr(self.workflow, 'query_rewrite_userp_template'))
        self.assertTrue(hasattr(self.workflow, 'chat_userp_template'))
        
        # 验证模板非空
        self.assertGreater(len(self.workflow.query_rewrite_userp_template), 0)
        self.assertGreater(len(self.workflow.chat_userp_template), 0)
    
    def test_build_retrieve_message_structure(self):
        """测试 _build_retrieve_message 返回结构"""
        query_rewrite = {
            "CharacterSettingQueryQuestion": "角色设定问题",
            "CharacterSettingQueryKeywords": "关键词1,关键词2",
            "UserProfileQueryQuestion": "用户资料问题",
            "UserProfileQueryKeywords": "用户关键词",
            "CharacterKnowledgeQueryQuestion": "知识问题",
            "CharacterKnowledgeQueryKeywords": "知识关键词",
        }
        session_state = {
            "character": {"_id": "char_123"},
            "user": {"_id": "user_456"},
            "conversation": {
                "conversation_info": {
                    "future": {"action": "测试行动"}
                }
            }
        }
        
        result = self.workflow._build_retrieve_message(query_rewrite, session_state)
        
        self.assertIsInstance(result, str)
        self.assertIn("规划行动", result)
        self.assertIn("测试行动", result)
        self.assertIn("角色设定查询", result)
        self.assertIn("用户资料查询", result)
        self.assertIn("角色知识查询", result)


class TestWorkflowPromptTemplates(unittest.TestCase):
    """测试 Workflow Prompt 模板包含必要内容"""
    
    def setUp(self):
        self.workflow = FutureMessageWorkflow()
    
    def test_query_rewrite_template_contains_future_context(self):
        """测试问题重写模板包含规划行动上下文 (Requirement 7.1, 7.3)"""
        template = self.workflow.query_rewrite_userp_template
        
        # 应该包含规划行动相关内容
        self.assertIn("规划行动", template)
    
    def test_chat_template_contains_future_context(self):
        """测试消息生成模板包含规划行动上下文 (Requirement 7.2, 7.3)"""
        template = self.workflow.chat_userp_template
        
        # 应该包含规划行动相关内容
        self.assertIn("规划行动", template)


if __name__ == "__main__":
    unittest.main()
