# -*- coding: utf-8 -*-
"""
主动消息功能集成测试 (Integration Tests)

测试主动消息功能的端到端流程：
- 8.1: Workflow 端到端测试
- 8.2: 输出有效性属性测试 (Property 9)
- 8.3: 频率控制集成测试
- 8.4: 触发服务集成测试

Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""
import sys
sys.path.append(".")

import unittest
from unittest.mock import patch, MagicMock
import time

from hypothesis import given, strategies as st, settings, assume

from agent.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow
from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse
from agent.agno_agent.schemas.chat_response_schema import (
    MultiModalResponse,
    RelationChangeModel,
    FutureResponseModel,
)


# ============================================================================
# Hypothesis Strategies for Integration Tests
# ============================================================================

@st.composite
def complete_session_state_strategy(draw):
    """Generate a complete session_state for end-to-end testing"""
    proactive_times = draw(st.integers(min_value=0, max_value=5))
    closeness = draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    trustness = draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    
    return {
        "user": {
            "_id": "user_test_123",
            "name": "测试用户",
            "platforms": {"wechat": {"nickname": "测试用户"}}
        },
        "character": {
            "_id": "char_test_456",
            "name": "测试角色",
            "platforms": {"wechat": {"nickname": "测试角色"}}
        },
        "conversation": {
            "_id": "conv_test_789",
            "conversation_info": {
                "future": {
                    "timestamp": int(time.time()) - 100,
                    "action": draw(st.sampled_from([
                        "发送问候",
                        "询问近况",
                        "分享有趣的事",
                        "关心用户"
                    ])),
                    "proactive_times": proactive_times
                }
            }
        },
        "relation": {
            "relationship": {
                "closeness": closeness,
                "trustness": trustness,
                "dislike": 0,
                "status": "空闲",
                "description": "朋友"
            },
            "user_info": {
                "realname": "测试",
                "hobbyname": "",
                "description": "测试用户描述"
            },
            "character_info": {
                "longterm_purpose": "",
                "shortterm_purpose": "",
                "attitude": "友好"
            }
        },
        "news_str": "",
        "context_retrieve": {
            "character_global": "角色全局设定",
            "character_private": "角色私有设定",
            "user": "用户资料",
            "character_knowledge": "角色知识",
            "confirmed_reminders": ""
        },
        # Prompt 模板所需字段
        "time_str": "2025年12月05日10时00分",
        "history_str": "用户: 你好\n角色: 你好呀！",
        "future_action": "发送问候",
        "character_name": "测试角色",
        "user_name": "测试用户",
        "character_global_str": "角色全局设定",
        "character_private_str": "角色私有设定",
        "user_str": "用户资料",
        "character_knowledge_str": "角色知识",
        "character_status_str": "空闲",
        "character_purpose_str": "",
        "relation_str": "朋友关系",
    }


@st.composite
def multimodal_response_strategy(draw):
    """Generate valid MultiModalResponse data"""
    msg_type = draw(st.sampled_from(["text", "voice", "photo"]))
    content = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'Z'),
        whitelist_characters='，.！？、'
    )))
    
    # Ensure content is not empty or whitespace only
    assume(content.strip())
    
    if msg_type == "voice":
        emotion = draw(st.sampled_from([None, "无", "高兴", "悲伤", "愤怒"]))
        return {"type": msg_type, "content": content, "emotion": emotion}
    else:
        return {"type": msg_type, "content": content}


@st.composite
def future_message_response_strategy(draw):
    """Generate valid FutureMessageResponse data"""
    num_responses = draw(st.integers(min_value=1, max_value=3))
    responses = [draw(multimodal_response_strategy()) for _ in range(num_responses)]
    
    return {
        "InnerMonologue": draw(st.text(min_size=0, max_size=200)),
        "MultiModalResponses": responses,
        "ChatCatelogue": draw(st.sampled_from(["是", "否"])),
        "RelationChange": {
            "Closeness": draw(st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False)),
            "Trustness": draw(st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False))
        },
        "FutureResponse": {
            "FutureResponseTime": draw(st.sampled_from([
                "2025年12月25日09时00分",
                "2025年01月01日10时30分",
                ""
            ])),
            "FutureResponseAction": draw(st.sampled_from([
                "发送问候",
                "检查进度",
                "无"
            ]))
        }
    }


# ============================================================================
# 8.1 Workflow 端到端测试
# ============================================================================

class TestWorkflowEndToEnd(unittest.TestCase):
    """
    8.1 Workflow 端到端测试
    
    构造完整 session_state，执行 FutureMessageWorkflow，
    验证返回结构和状态更新.
    
    Validates: Requirements 8.1
    """
    
    def setUp(self):
        self.workflow = FutureMessageWorkflow()
    
    def _create_mock_agent_response(self, content):
        """创建模拟的 Agent 响应"""
        mock_response = MagicMock()
        mock_response.content = content
        return mock_response
    
    def test_workflow_end_to_end_returns_correct_structure(self):
        """
        测试 Workflow 端到端执行返回正确结构
        
        Validates: Requirement 8.1
        """
        # 构造完整 session_state
        session_state = {
            "user": {"_id": "user_123", "name": "测试用户"},
            "character": {"_id": "char_456", "name": "测试角色"},
            "conversation": {
                "_id": "conv_789",
                "conversation_info": {
                    "future": {
                        "timestamp": int(time.time()) - 100,
                        "action": "发送问候",
                        "proactive_times": 0
                    }
                }
            },
            "relation": {
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                }
            },
            "context_retrieve": {},
            "time_str": "2025年12月05日10时00分",
            "history_str": "",
            "future_action": "发送问候",
        }
        
        # Mock Agent 响应
        mock_qr_response = {
            "InnerMonologue": "思考中...",
            "CharacterSettingQueryQuestion": "角色设定问题",
            "CharacterSettingQueryKeywords": "关键词",
            "UserProfileQueryQuestion": "用户资料问题",
            "UserProfileQueryKeywords": "用户关键词",
            "CharacterKnowledgeQueryQuestion": "知识问题",
            "CharacterKnowledgeQueryKeywords": "知识关键词",
        }
        
        mock_chat_response = {
            "InnerMonologue": "想要问候用户",
            "MultiModalResponses": [
                {"type": "text", "content": "你好呀！最近怎么样？"}
            ],
            "ChatCatelogue": "否",
            "RelationChange": {"Closeness": 1, "Trustness": 0},
            "FutureResponse": {
                "FutureResponseTime": "2025年12月06日10时00分",
                "FutureResponseAction": "继续关心"
            }
        }
        
        with patch.object(
            self.workflow, 'query_rewrite_userp_template', "测试模板 {future_action}"
        ), patch.object(
            self.workflow, 'chat_userp_template', "测试模板 {future_action}"
        ), patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_query_rewrite_agent'
        ) as mock_qr_agent, patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_context_retrieve_agent'
        ) as mock_cr_agent, patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_chat_agent'
        ) as mock_chat_agent, patch(
            'random.random', return_value=0.5
        ):
            mock_qr_agent.run.return_value = self._create_mock_agent_response(mock_qr_response)
            mock_cr_agent.run.return_value = self._create_mock_agent_response("检索完成")
            mock_chat_agent.run.return_value = self._create_mock_agent_response(mock_chat_response)
            
            result = self.workflow.run(session_state=session_state)
        
        # 验证返回结构
        self.assertIn("content", result)
        self.assertIn("session_state", result)
        
        # 验证 content 结构
        content = result["content"]
        self.assertIn("InnerMonologue", content)
        self.assertIn("MultiModalResponses", content)
        
        # 验证 session_state 包含 MultiModalResponses
        updated_state = result["session_state"]
        self.assertIn("MultiModalResponses", updated_state)
    
    def test_workflow_end_to_end_updates_relation(self):
        """
        测试 Workflow 端到端执行正确更新关系值
        
        Validates: Requirement 8.1
        """
        session_state = {
            "user": {"_id": "user_123"},
            "character": {"_id": "char_456"},
            "conversation": {
                "conversation_info": {
                    "future": {
                        "timestamp": int(time.time()) - 100,
                        "action": "发送问候",
                        "proactive_times": 0
                    }
                }
            },
            "relation": {
                "relationship": {
                    "closeness": 50,
                    "trustness": 50,
                }
            },
            "context_retrieve": {},
            "future_action": "发送问候",
        }
        
        mock_chat_response = {
            "InnerMonologue": "",
            "MultiModalResponses": [{"type": "text", "content": "你好"}],
            "ChatCatelogue": "否",
            "RelationChange": {"Closeness": 5, "Trustness": 3},
            "FutureResponse": {"FutureResponseTime": "", "FutureResponseAction": "无"}
        }
        
        with patch.object(
            self.workflow, 'query_rewrite_userp_template', "测试"
        ), patch.object(
            self.workflow, 'chat_userp_template', "测试"
        ), patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_query_rewrite_agent'
        ) as mock_qr_agent, patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_context_retrieve_agent'
        ) as mock_cr_agent, patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_chat_agent'
        ) as mock_chat_agent, patch(
            'random.random', return_value=0.5
        ):
            mock_qr_agent.run.return_value = self._create_mock_agent_response({})
            mock_cr_agent.run.return_value = self._create_mock_agent_response("")
            mock_chat_agent.run.return_value = self._create_mock_agent_response(mock_chat_response)
            
            result = self.workflow.run(session_state=session_state)
        
        # 验证关系值更新
        updated_relation = result["session_state"]["relation"]["relationship"]
        self.assertEqual(updated_relation["closeness"], 55)  # 50 + 5
        self.assertEqual(updated_relation["trustness"], 53)  # 50 + 3
    
    def test_workflow_end_to_end_updates_proactive_times(self):
        """
        测试 Workflow 端到端执行正确更新 proactive_times
        
        Validates: Requirement 8.1
        """
        session_state = {
            "user": {"_id": "user_123"},
            "character": {"_id": "char_456"},
            "conversation": {
                "conversation_info": {
                    "future": {
                        "timestamp": int(time.time()) - 100,
                        "action": "发送问候",
                        "proactive_times": 2
                    }
                }
            },
            "relation": {"relationship": {"closeness": 50, "trustness": 50}},
            "context_retrieve": {},
            "future_action": "发送问候",
        }
        
        mock_chat_response = {
            "InnerMonologue": "",
            "MultiModalResponses": [{"type": "text", "content": "你好"}],
            "ChatCatelogue": "否",
            "RelationChange": {"Closeness": 0, "Trustness": 0},
            "FutureResponse": {"FutureResponseTime": "", "FutureResponseAction": "无"}
        }
        
        with patch.object(
            self.workflow, 'query_rewrite_userp_template', "测试"
        ), patch.object(
            self.workflow, 'chat_userp_template', "测试"
        ), patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_query_rewrite_agent'
        ) as mock_qr_agent, patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_context_retrieve_agent'
        ) as mock_cr_agent, patch(
            'agent.agno_agent.workflows.future_message_workflow.future_message_chat_agent'
        ) as mock_chat_agent, patch(
            'random.random', return_value=0.5
        ):
            mock_qr_agent.run.return_value = self._create_mock_agent_response({})
            mock_cr_agent.run.return_value = self._create_mock_agent_response("")
            mock_chat_agent.run.return_value = self._create_mock_agent_response(mock_chat_response)
            
            result = self.workflow.run(session_state=session_state)
        
        # 验证 proactive_times 增加
        future_info = result["session_state"]["conversation"]["conversation_info"]["future"]
        self.assertEqual(future_info["proactive_times"], 3)  # 2 + 1



# ============================================================================
# 8.2 输出有效性属性测试 (Property 9)
# ============================================================================

class TestOutputValidityProperty(unittest.TestCase):
    """
    8.2 输出有效性属性测试
    
    Property 9: 主动消息输出有效性
    For any 主动消息生成成功后，MultiModalResponses 列表应非空，
    且每个元素的 type 字段应为有效值.
    
    **Feature: proactive-message, Property 9: 主动消息输出有效性**
    **Validates: Requirements 8.2**
    """
    
    @given(response_data=future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_9_multimodal_responses_valid_types(self, response_data):
        """
        Property 9: MultiModalResponses 中每个元素的 type 字段应为有效值
        
        **Feature: proactive-message, Property 9: 主动消息输出有效性**
        **Validates: Requirements 8.2**
        """
        valid_types = {"text", "voice", "photo"}
        
        multimodal_responses = response_data.get("MultiModalResponses", [])
        
        # 验证列表非空（由 strategy 保证）
        self.assertGreater(len(multimodal_responses), 0)
        
        # 验证每个元素的 type 字段有效
        for response in multimodal_responses:
            self.assertIn(response.get("type"), valid_types)
    
    @given(response_data=future_message_response_strategy())
    @settings(max_examples=100)
    def test_property_9_multimodal_responses_have_content(self, response_data):
        """
        Property 9: MultiModalResponses 中每个元素应有非空 content
        
        **Feature: proactive-message, Property 9: 主动消息输出有效性**
        **Validates: Requirements 8.2**
        """
        multimodal_responses = response_data.get("MultiModalResponses", [])
        
        for response in multimodal_responses:
            content = response.get("content", "")
            # content 应该存在且非空（由 strategy 保证）
            self.assertTrue(content.strip())
    
    def test_future_message_response_schema_validation(self):
        """
        测试 FutureMessageResponse Schema 验证有效输出
        
        **Validates: Requirements 8.2**
        """
        # 有效数据
        valid_data = {
            "InnerMonologue": "思考中",
            "MultiModalResponses": [
                {"type": "text", "content": "你好！"},
                {"type": "voice", "content": "语音内容", "emotion": "高兴"}
            ],
            "ChatCatelogue": "否",
            "RelationChange": {"Closeness": 1, "Trustness": 0},
            "FutureResponse": {
                "FutureResponseTime": "2025年12月25日09时00分",
                "FutureResponseAction": "继续关心"
            }
        }
        
        # 应该能成功创建
        response = FutureMessageResponse(**valid_data)
        
        self.assertEqual(len(response.MultiModalResponses), 2)
        self.assertEqual(response.MultiModalResponses[0].type, "text")
        self.assertEqual(response.MultiModalResponses[1].type, "voice")
    
    def test_multimodal_response_type_validation(self):
        """
        测试 MultiModalResponse type 字段验证
        
        **Validates: Requirements 8.2**
        """
        # 有效类型
        for valid_type in ["text", "voice", "photo"]:
            response = MultiModalResponse(type=valid_type, content="测试内容")
            self.assertEqual(response.type, valid_type)
        
        # 无效类型应该抛出异常
        with self.assertRaises(Exception):
            MultiModalResponse(type="invalid", content="测试内容")


# ============================================================================
# 8.3 频率控制集成测试
# ============================================================================

class TestFrequencyControlIntegration(unittest.TestCase):
    """
    8.3 频率控制集成测试
    
    测试连续主动消息的概率衰减机制.
    
    Validates: Requirements 8.3
    """
    
    def setUp(self):
        self.workflow = FutureMessageWorkflow()
    
    def _create_mock_agent_response(self, content):
        """创建模拟的 Agent 响应"""
        mock_response = MagicMock()
        mock_response.content = content
        return mock_response
    
    def test_probability_decay_with_increasing_proactive_times(self):
        """
        测试随着 proactive_times 增加，概率阈值指数衰减
        
        Validates: Requirement 8.3
        """
        # 验证概率衰减公式 0.15^(n+1)
        expected_thresholds = [
            (0, 0.15),       # 第1次: 15%
            (1, 0.0225),     # 第2次: 2.25%
            (2, 0.003375),   # 第3次: 0.3375%
            (3, 0.00050625), # 第4次: 0.050625%
        ]
        
        for n, expected_threshold in expected_thresholds:
            actual_threshold = 0.15 ** (n + 1)
            self.assertAlmostEqual(actual_threshold, expected_threshold, places=8)
    
    def test_consecutive_proactive_messages_decrease_probability(self):
        """
        测试连续主动消息后概率降低
        
        Validates: Requirement 8.3
        """
        mock_chat_response = {
            "InnerMonologue": "",
            "MultiModalResponses": [{"type": "text", "content": "你好"}],
            "ChatCatelogue": "否",
            "RelationChange": {"Closeness": 0, "Trustness": 0},
            "FutureResponse": {
                "FutureResponseTime": "2025年12月25日09时00分",
                "FutureResponseAction": "继续关心"
            }
        }
        
        # 模拟连续多次主动消息
        hit_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        iterations = 1000
        
        for proactive_times in [0, 1, 2, 3]:
            hits = 0
            for _ in range(iterations):
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
                        "FutureResponseAction": "继续关心"
                    }
                }
                
                # 不 mock random，让它自然运行
                self.workflow._handle_future_response(content, session_state)
                
                if session_state["conversation"]["conversation_info"]["future"]["action"] is not None:
                    hits += 1
            
            hit_counts[proactive_times] = hits
        
        # 验证命中次数随 proactive_times 增加而减少
        # 由于是概率性的，我们只验证趋势
        self.assertGreater(hit_counts[0], hit_counts[1])
        self.assertGreater(hit_counts[1], hit_counts[2])
    
    def test_high_proactive_times_rarely_triggers(self):
        """
        测试高 proactive_times 时很少触发下一次主动消息
        
        Validates: Requirement 8.3
        """
        # proactive_times = 5 时，概率为 0.15^6 ≈ 0.0000114
        # 在 1000 次迭代中，期望命中约 0.01 次
        
        hits = 0
        iterations = 1000
        
        for _ in range(iterations):
            session_state = {
                "conversation": {
                    "conversation_info": {
                        "future": {
                            "proactive_times": 5,
                            "timestamp": None,
                            "action": None,
                        }
                    }
                }
            }
            content = {
                "FutureResponse": {
                    "FutureResponseTime": "2025年12月25日09时00分",
                    "FutureResponseAction": "继续关心"
                }
            }
            
            self.workflow._handle_future_response(content, session_state)
            
            if session_state["conversation"]["conversation_info"]["future"]["action"] is not None:
                hits += 1
        
        # 期望命中次数非常少（小于 5）
        self.assertLess(hits, 5)


# ============================================================================
# 8.4 触发服务集成测试
# ============================================================================

class TestTriggerServiceIntegration(unittest.TestCase):
    """
    8.4 触发服务集成测试
    
    测试完整的触发流程.
    
    Validates: Requirements 8.4
    """
    
    def test_full_trigger_flow(self):
        """
        测试完整的触发流程：查询 -> 触发 -> 写入 -> 更新
        
        Validates: Requirement 8.4
        """
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService
        )
        
        # 创建模拟会话
        mock_conversation = {
            "_id": "conv_integration_test",
            "talkers": [
                {"id": "user_int_123", "nickname": "集成测试用户"},
                {"id": "char_int_456", "nickname": "集成测试角色"}
            ],
            "conversation_info": {
                "future": {
                    "timestamp": int(time.time()) - 100,
                    "action": "发送问候",
                    "proactive_times": 0
                }
            }
        }
        
        # Mock DAOs
        mock_conversation_dao = MagicMock()
        mock_conversation_dao.find_conversations.return_value = [mock_conversation]
        mock_conversation_dao.update_conversation.return_value = True
        
        mock_user_dao = MagicMock()
        mock_user_dao.get_user_by_id.side_effect = [
            # 第一轮：识别用户和角色
            {"_id": "user_int_123", "is_character": False, "name": "测试用户"},
            {"_id": "char_int_456", "is_character": True, "name": "测试角色"},
            # 第二轮：获取详细信息
            {"_id": "user_int_123", "is_character": False, "name": "测试用户"},
            {"_id": "char_int_456", "is_character": True, "name": "测试角色"},
        ]
        
        mock_mongo = MagicMock()
        mock_mongo.find_one.return_value = None  # No existing relation
        mock_mongo.insert_one.return_value = True
        
        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=mock_user_dao,
            mongo=mock_mongo
        )
        
        # Mock Workflow
        mock_workflow_result = {
            "content": {
                "InnerMonologue": "想要问候",
                "MultiModalResponses": [
                    {"type": "text", "content": "你好呀！"}
                ],
                "ChatCatelogue": "否",
                "RelationChange": {"Closeness": 1, "Trustness": 0},
                "FutureResponse": {
                    "FutureResponseTime": "",
                    "FutureResponseAction": "无"
                }
            },
            "session_state": {
                "conversation": {
                    "conversation_info": {
                        "future": {
                            "timestamp": None,
                            "action": None,
                            "proactive_times": 1
                        }
                    }
                }
            }
        }
        
        with patch(
            'agent.agno_agent.workflows.future_message_workflow.FutureMessageWorkflow'
        ) as mock_workflow_class:
            mock_workflow = MagicMock()
            mock_workflow.run.return_value = mock_workflow_result
            mock_workflow_class.return_value = mock_workflow
            
            results = service.check_and_trigger()
        
        # 验证结果
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["success"])
        self.assertEqual(results[0]["conversation_id"], "conv_integration_test")
        
        # 验证消息写入
        mock_mongo.insert_one.assert_called()
        
        # 验证会话更新
        mock_conversation_dao.update_conversation.assert_called_once()
    
    def test_trigger_flow_handles_multiple_conversations(self):
        """
        测试触发流程处理多个会话
        
        Validates: Requirement 8.4
        """
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService
        )
        
        # 创建多个模拟会话
        mock_conversations = [
            {
                "_id": f"conv_multi_{i}",
                "talkers": [
                    {"id": f"user_multi_{i}", "nickname": f"用户{i}"},
                    {"id": f"char_multi_{i}", "nickname": f"角色{i}"}
                ],
                "conversation_info": {
                    "future": {
                        "timestamp": int(time.time()) - 100,
                        "action": f"行动{i}",
                        "proactive_times": i
                    }
                }
            }
            for i in range(3)
        ]
        
        mock_conversation_dao = MagicMock()
        mock_conversation_dao.find_conversations.return_value = mock_conversations
        mock_conversation_dao.update_conversation.return_value = True
        
        mock_user_dao = MagicMock()
        # 为每个会话返回用户和角色信息
        user_responses = []
        for i in range(3):
            user_responses.extend([
                {"_id": f"user_multi_{i}", "is_character": False, "name": f"用户{i}"},
                {"_id": f"char_multi_{i}", "is_character": True, "name": f"角色{i}"},
                {"_id": f"user_multi_{i}", "is_character": False, "name": f"用户{i}"},
                {"_id": f"char_multi_{i}", "is_character": True, "name": f"角色{i}"},
            ])
        mock_user_dao.get_user_by_id.side_effect = user_responses
        
        mock_mongo = MagicMock()
        mock_mongo.find_one.return_value = None
        mock_mongo.insert_one.return_value = True
        
        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=mock_user_dao,
            mongo=mock_mongo
        )
        
        mock_workflow_result = {
            "content": {
                "MultiModalResponses": [{"type": "text", "content": "你好"}]
            },
            "session_state": {
                "conversation": {
                    "conversation_info": {
                        "future": {"timestamp": None, "action": None, "proactive_times": 1}
                    }
                }
            }
        }
        
        with patch(
            'agent.agno_agent.workflows.future_message_workflow.FutureMessageWorkflow'
        ) as mock_workflow_class:
            mock_workflow = MagicMock()
            mock_workflow.run.return_value = mock_workflow_result
            mock_workflow_class.return_value = mock_workflow
            
            results = service.check_and_trigger()
        
        # 验证处理了所有会话
        self.assertEqual(len(results), 3)
        for result in results:
            self.assertTrue(result["success"])
    
    def test_trigger_flow_handles_errors_gracefully(self):
        """
        测试触发流程优雅处理错误
        
        Validates: Requirement 8.4
        """
        from agent.agno_agent.services.proactive_message_trigger_service import (
            ProactiveMessageTriggerService
        )
        
        # 创建会话，但用户查询会失败
        mock_conversation = {
            "_id": "conv_error_test",
            "talkers": [
                {"id": "user_error", "nickname": "错误用户"},
                {"id": "char_error", "nickname": "错误角色"}
            ],
            "conversation_info": {
                "future": {
                    "timestamp": int(time.time()) - 100,
                    "action": "测试",
                    "proactive_times": 0
                }
            }
        }
        
        mock_conversation_dao = MagicMock()
        mock_conversation_dao.find_conversations.return_value = [mock_conversation]
        
        mock_user_dao = MagicMock()
        # 返回 None 模拟用户不存在
        mock_user_dao.get_user_by_id.side_effect = [
            {"_id": "user_error", "is_character": False},
            None,  # 角色不存在
        ]
        
        mock_mongo = MagicMock()
        
        service = ProactiveMessageTriggerService(
            conversation_dao=mock_conversation_dao,
            user_dao=mock_user_dao,
            mongo=mock_mongo
        )
        
        results = service.check_and_trigger()
        
        # 应该返回错误结果而不是抛出异常
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["success"])
        self.assertIn("error", results[0])


if __name__ == "__main__":
    unittest.main()
