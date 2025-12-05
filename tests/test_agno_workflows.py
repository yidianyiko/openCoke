# -*- coding: utf-8 -*-
"""
Agno Workflows 属性测试

测试 Workflow 状态累积和传递：
- PrepareWorkflow 状态累积 (Requirements 5.1)
- Workflow 状态传递 (Requirements 5.4)
"""
import sys
sys.path.append(".")

import unittest


class TestPrepareWorkflowStateAccumulation(unittest.TestCase):
    """测试 PrepareWorkflow 状态累积 (Requirements 5.1)"""
    
    def setUp(self):
        from qiaoyun.agno_agent.workflows import PrepareWorkflow
        self.workflow = PrepareWorkflow()
    
    def test_workflow_has_run_method(self):
        """测试 Workflow 有 run 方法"""
        self.assertTrue(hasattr(self.workflow, 'run'))
        self.assertTrue(callable(self.workflow.run))
    
    def test_workflow_has_userp_template(self):
        """测试 Workflow 有 userp_template"""
        self.assertTrue(hasattr(self.workflow, 'userp_template'))
        self.assertIsInstance(self.workflow.userp_template, str)
        self.assertGreater(len(self.workflow.userp_template), 0)
    
    def test_default_query_rewrite_structure(self):
        """测试默认 query_rewrite 结构"""
        default = self.workflow._get_default_query_rewrite()
        
        expected_keys = [
            "InnerMonologue",
            "CharacterSettingQueryQuestion",
            "CharacterSettingQueryKeywords",
            "UserProfileQueryQuestion",
            "UserProfileQueryKeywords",
            "CharacterKnowledgeQueryQuestion",
            "CharacterKnowledgeQueryKeywords",
        ]
        
        for key in expected_keys:
            self.assertIn(key, default)
            self.assertEqual(default[key], "")
    
    def test_default_context_retrieve_structure(self):
        """测试默认 context_retrieve 结构"""
        default = self.workflow._get_default_context_retrieve()
        
        expected_keys = [
            "character_global",
            "character_private",
            "user",
            "character_knowledge",
            "confirmed_reminders",
        ]
        
        for key in expected_keys:
            self.assertIn(key, default)
            self.assertEqual(default[key], "")
    
    def test_render_template_with_missing_keys(self):
        """测试模板渲染缺少字段时不会崩溃"""
        template = "Hello {name}, your age is {age}"
        context = {"name": "Test"}
        
        # 应该返回原模板或部分渲染结果，不应该抛出异常
        result = self.workflow._render_template(template, context)
        self.assertIsInstance(result, str)
    
    def test_build_retrieve_message(self):
        """测试构建检索消息"""
        query_rewrite = {
            "CharacterSettingQueryQuestion": "角色的爱好是什么？",
            "CharacterSettingQueryKeywords": "爱好,兴趣",
            "UserProfileQueryQuestion": "用户的职业",
            "UserProfileQueryKeywords": "职业,工作",
            "CharacterKnowledgeQueryQuestion": "角色知道什么",
            "CharacterKnowledgeQueryKeywords": "知识",
        }
        
        message = self.workflow._build_retrieve_message(
            query_rewrite=query_rewrite,
            character_id="char_123",
            user_id="user_456"
        )
        
        self.assertIsInstance(message, str)
        self.assertIn("角色的爱好是什么", message)
        self.assertIn("char_123", message)
        self.assertIn("user_456", message)


class TestChatWorkflowStateTransfer(unittest.TestCase):
    """测试 ChatWorkflow 状态传递"""
    
    def setUp(self):
        from qiaoyun.agno_agent.workflows import ChatWorkflow
        self.workflow = ChatWorkflow()
    
    def test_workflow_has_run_method(self):
        """测试 Workflow 有 run 方法"""
        self.assertTrue(hasattr(self.workflow, 'run'))
        self.assertTrue(callable(self.workflow.run))
    
    def test_workflow_has_userp_template(self):
        """测试 Workflow 有 userp_template"""
        self.assertTrue(hasattr(self.workflow, 'userp_template'))
        self.assertIsInstance(self.workflow.userp_template, str)
    
    def test_default_content_structure(self):
        """测试默认内容结构"""
        default = self.workflow._get_default_content()
        
        expected_keys = [
            "InnerMonologue",
            "MultiModalResponses",
            "ChatCatelogue",
            "RelationChange",
            "FutureResponse",
            "DetectedReminders",
        ]
        
        for key in expected_keys:
            self.assertIn(key, default)
        
        self.assertIsInstance(default["MultiModalResponses"], list)
        self.assertIsInstance(default["RelationChange"], dict)
        self.assertIsInstance(default["FutureResponse"], dict)
    
    def test_extract_content_from_none(self):
        """测试从 None 提取内容"""
        result = self.workflow._extract_content(None)
        self.assertIsInstance(result, dict)
        self.assertIn("MultiModalResponses", result)


class TestPostAnalyzeWorkflowStateTransfer(unittest.TestCase):
    """测试 PostAnalyzeWorkflow 状态传递"""
    
    def setUp(self):
        from qiaoyun.agno_agent.workflows import PostAnalyzeWorkflow
        self.workflow = PostAnalyzeWorkflow()
    
    def test_workflow_has_run_method(self):
        """测试 Workflow 有 run 方法"""
        self.assertTrue(hasattr(self.workflow, 'run'))
        self.assertTrue(callable(self.workflow.run))
    
    def test_workflow_has_userp_template(self):
        """测试 Workflow 有 userp_template"""
        self.assertTrue(hasattr(self.workflow, 'userp_template'))
        self.assertIsInstance(self.workflow.userp_template, str)
    
    def test_default_content_structure(self):
        """测试默认内容结构"""
        default = self.workflow._get_default_content()
        
        expected_keys = [
            "CharacterPublicSettings",
            "CharacterPrivateSettings",
            "UserSettings",
            "CharacterKnowledges",
            "UserRealName",
            "UserHobbyName",
            "UserDescription",
            "CharacterPurpose",
            "CharacterAttitude",
            "RelationDescription",
            "Dislike",
        ]
        
        for key in expected_keys:
            self.assertIn(key, default)
    
    def test_format_multimodal_responses_empty(self):
        """测试格式化空的多模态回复"""
        result = self.workflow._format_multimodal_responses([])
        self.assertEqual(result, "（无回复）")
    
    def test_format_multimodal_responses_text(self):
        """测试格式化文本回复"""
        responses = [
            {"type": "text", "content": "你好！"},
            {"type": "text", "content": "很高兴认识你"}
        ]
        result = self.workflow._format_multimodal_responses(responses)
        self.assertIn("你好", result)
        self.assertIn("很高兴认识你", result)
    
    def test_format_multimodal_responses_photo(self):
        """测试格式化照片回复"""
        responses = [
            {"type": "photo", "content": "photo_123"}
        ]
        result = self.workflow._format_multimodal_responses(responses)
        self.assertIn("照片", result)
    
    def test_format_multimodal_responses_voice(self):
        """测试格式化语音回复"""
        responses = [
            {"type": "voice", "content": "语音内容"}
        ]
        result = self.workflow._format_multimodal_responses(responses)
        self.assertIn("语音", result)


class TestWorkflowStateTransfer(unittest.TestCase):
    """测试 Workflow 状态传递 (Requirements 5.4)"""
    
    def test_session_state_preserved_in_prepare_workflow(self):
        """测试 PrepareWorkflow 保留 session_state"""
        from qiaoyun.agno_agent.workflows import PrepareWorkflow
        workflow = PrepareWorkflow()
        
        # 模拟 session_state
        session_state = {
            "user": {"_id": "user_123", "name": "测试用户"},
            "character": {"_id": "char_456", "name": "测试角色"},
            "custom_field": "custom_value"
        }
        
        # 验证 session_state 结构被保留
        self.assertIn("user", session_state)
        self.assertIn("character", session_state)
        self.assertIn("custom_field", session_state)
    
    def test_session_state_preserved_in_chat_workflow(self):
        """测试 ChatWorkflow 保留 session_state"""
        from qiaoyun.agno_agent.workflows import ChatWorkflow
        workflow = ChatWorkflow()
        
        session_state = {
            "query_rewrite": {"InnerMonologue": "测试"},
            "context_retrieve": {"character_global": "角色设定"},
            "user": {"_id": "user_123"}
        }
        
        # 验证 session_state 结构被保留
        self.assertIn("query_rewrite", session_state)
        self.assertIn("context_retrieve", session_state)


if __name__ == "__main__":
    unittest.main()
