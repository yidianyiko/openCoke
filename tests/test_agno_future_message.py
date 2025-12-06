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
        from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse
        from agent.agno_agent.schemas.chat_response_schema import (
            MultiModalResponse,
            RelationChangeModel,
            FutureResponseModel,
        )
        
        response = FutureMessageResponse(
            InnerMonologue="主动问候用户",
            MultiModalResponses=[
                MultiModalResponse(type="text", content="在干嘛呢？")
            ],
            ChatCatelogue="否",
            RelationChange=RelationChangeModel(Closeness=1.0, Trustness=0.5),
            FutureResponse=FutureResponseModel(
                FutureResponseTime="2025年12月06日10时00分",
                FutureResponseAction="检查学习进度"
            )
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
            future_message_query_rewrite_agent,
            future_message_context_retrieve_agent,
            future_message_chat_agent,
        )
        
        self.assertIsNotNone(future_message_query_rewrite_agent)
        self.assertIsNotNone(future_message_context_retrieve_agent)
        self.assertIsNotNone(future_message_chat_agent)
    
    def test_agents_have_required_attributes(self):
        """测试 Agent 具有必要属性"""
        from agent.agno_agent.agents.future_message_agents import (
            future_message_query_rewrite_agent,
            future_message_chat_agent,
        )
        
        # 检查 query_rewrite_agent
        self.assertEqual(future_message_query_rewrite_agent.id, "future-message-query-rewrite-agent")
        self.assertIsNotNone(future_message_query_rewrite_agent.model)
        
        # 检查 chat_agent
        self.assertEqual(future_message_chat_agent.id, "future-message-chat-agent")
        self.assertIsNotNone(future_message_chat_agent.model)


class TestFutureMessageWorkflow(unittest.TestCase):
    """测试 FutureMessageWorkflow"""
    
    def test_workflow_has_run_method(self):
        """测试 Workflow 有 run 方法"""
        from agent.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow
        
        workflow = FutureMessageWorkflow()
        self.assertTrue(hasattr(workflow, 'run'))
        self.assertTrue(callable(workflow.run))
    
    def test_workflow_has_templates(self):
        """测试 Workflow 有 prompt 模板"""
        from agent.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow
        
        workflow = FutureMessageWorkflow()
        self.assertTrue(hasattr(workflow, 'query_rewrite_userp_template'))
        self.assertTrue(hasattr(workflow, 'chat_userp_template'))
        self.assertIsInstance(workflow.query_rewrite_userp_template, str)
        self.assertIsInstance(workflow.chat_userp_template, str)
    
    def test_build_retrieve_message(self):
        """测试构建检索消息"""
        from agent.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow
        
        workflow = FutureMessageWorkflow()
        
        query_rewrite = {
            "CharacterSettingQueryQuestion": "角色的日常习惯",
            "CharacterSettingQueryKeywords": "习惯,日常",
            "UserProfileQueryQuestion": "用户的学习情况",
            "UserProfileQueryKeywords": "学习,进度",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": "",
        }
        
        session_state = {
            "character": {"_id": "char123"},
            "user": {"_id": "user456"},
            "conversation": {
                "conversation_info": {
                    "future": {
                        "action": "检查学习进度"
                    }
                }
            }
        }
        
        message = workflow._build_retrieve_message(query_rewrite, session_state)
        
        self.assertIn("检查学习进度", message)
        self.assertIn("角色的日常习惯", message)
        self.assertIn("char123", message)
        self.assertIn("user456", message)
    
    def test_handle_relation_change(self):
        """测试关系变化处理"""
        from agent.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow
        
        workflow = FutureMessageWorkflow()
        
        content = {
            "RelationChange": {
                "Closeness": 2.0,
                "Trustness": 1.0
            }
        }
        
        session_state = {
            "relation": {
                "relationship": {
                    "closeness": 50,
                    "trustness": 50
                }
            }
        }
        
        workflow._handle_relation_change(content, session_state)
        
        self.assertEqual(session_state["relation"]["relationship"]["closeness"], 52)
        self.assertEqual(session_state["relation"]["relationship"]["trustness"], 51)
    
    def test_handle_relation_change_bounds(self):
        """测试关系变化边界处理"""
        from agent.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow
        
        workflow = FutureMessageWorkflow()
        
        # 测试上限
        content = {"RelationChange": {"Closeness": 100, "Trustness": 100}}
        session_state = {
            "relation": {
                "relationship": {"closeness": 90, "trustness": 90}
            }
        }
        workflow._handle_relation_change(content, session_state)
        self.assertEqual(session_state["relation"]["relationship"]["closeness"], 100)
        self.assertEqual(session_state["relation"]["relationship"]["trustness"], 100)
        
        # 测试下限
        content = {"RelationChange": {"Closeness": -100, "Trustness": -100}}
        session_state = {
            "relation": {
                "relationship": {"closeness": 10, "trustness": 10}
            }
        }
        workflow._handle_relation_change(content, session_state)
        self.assertEqual(session_state["relation"]["relationship"]["closeness"], 0)
        self.assertEqual(session_state["relation"]["relationship"]["trustness"], 0)


class TestFutureMessageWorkflowExport(unittest.TestCase):
    """测试 FutureMessageWorkflow 导出"""
    
    def test_workflow_exported_from_init(self):
        """测试 Workflow 从 __init__ 正确导出"""
        from agent.agno_agent.workflows import FutureMessageWorkflow
        
        self.assertIsNotNone(FutureMessageWorkflow)
        workflow = FutureMessageWorkflow()
        self.assertTrue(hasattr(workflow, 'run'))
    
    def test_schema_exported_from_init(self):
        """测试 Schema 从 __init__ 正确导出"""
        from agent.agno_agent.schemas import FutureMessageResponse
        
        self.assertIsNotNone(FutureMessageResponse)
        response = FutureMessageResponse()
        self.assertEqual(response.ChatCatelogue, "否")


if __name__ == "__main__":
    unittest.main()
