# -*- coding: utf-8 -*-
"""
Agno Schema 属性测试

测试 Schema 的输出格式一致性：
- QueryRewriteResponse (Requirements 2.1)
- ChatResponse (Requirements 2.2)
- PostAnalyzeResponse (Requirements 2.3)
"""
import sys
sys.path.append(".")

import unittest
from pydantic import ValidationError

from agent.agno_agent.schemas.query_rewrite_schema import QueryRewriteResponse
from agent.agno_agent.schemas.chat_response_schema import (
    ChatResponse, 
    MultiModalResponse, 
    RelationChangeModel, 
    FutureResponseModel
)
from agent.agno_agent.schemas.post_analyze_schema import PostAnalyzeResponse


class TestQueryRewriteResponseSchema(unittest.TestCase):
    """测试 QueryRewriteResponse Schema (Requirements 2.1)"""
    
    def test_default_values(self):
        """测试默认值"""
        response = QueryRewriteResponse()
        self.assertEqual(response.InnerMonologue, "")
        self.assertEqual(response.CharacterSettingQueryQuestion, "")
        self.assertEqual(response.CharacterSettingQueryKeywords, "")
        self.assertEqual(response.UserProfileQueryQuestion, "")
        self.assertEqual(response.UserProfileQueryKeywords, "")
        self.assertEqual(response.CharacterKnowledgeQueryQuestion, "")
        self.assertEqual(response.CharacterKnowledgeQueryKeywords, "")
    
    def test_with_values(self):
        """测试带值创建"""
        response = QueryRewriteResponse(
            InnerMonologue="用户在问我的爱好",
            CharacterSettingQueryQuestion="角色有什么爱好？",
            CharacterSettingQueryKeywords="爱好,兴趣,喜欢",
            UserProfileQueryQuestion="用户的基本信息",
            UserProfileQueryKeywords="姓名,年龄",
            CharacterKnowledgeQueryQuestion="角色知道什么？",
            CharacterKnowledgeQueryKeywords="知识,技能"
        )
        self.assertEqual(response.InnerMonologue, "用户在问我的爱好")
        self.assertEqual(response.CharacterSettingQueryKeywords, "爱好,兴趣,喜欢")
    
    def test_model_dump(self):
        """测试 model_dump 输出"""
        response = QueryRewriteResponse(
            InnerMonologue="测试",
            CharacterSettingQueryQuestion="问题"
        )
        data = response.model_dump()
        self.assertIsInstance(data, dict)
        self.assertIn("InnerMonologue", data)
        self.assertIn("CharacterSettingQueryQuestion", data)
    
    def test_json_serialization(self):
        """测试 JSON 序列化"""
        response = QueryRewriteResponse(InnerMonologue="测试")
        json_str = response.model_dump_json()
        self.assertIsInstance(json_str, str)
        self.assertIn("InnerMonologue", json_str)


class TestChatResponseSchema(unittest.TestCase):
    """测试 ChatResponse Schema (Requirements 2.2)"""
    
    def test_default_values(self):
        """测试默认值"""
        response = ChatResponse()
        self.assertEqual(response.InnerMonologue, "")
        self.assertEqual(response.MultiModalResponses, [])
        self.assertEqual(response.ChatCatelogue, "")
        self.assertIsInstance(response.RelationChange, RelationChangeModel)
        self.assertIsInstance(response.FutureResponse, FutureResponseModel)
    
    def test_multimodal_response_text(self):
        """测试文本类型多模态回复"""
        mm = MultiModalResponse(type="text", content="你好！")
        self.assertEqual(mm.type, "text")
        self.assertEqual(mm.content, "你好！")
        self.assertIsNone(mm.emotion)  # emotion defaults to None for non-voice messages
    
    def test_multimodal_response_voice(self):
        """测试语音类型多模态回复"""
        mm = MultiModalResponse(type="voice", content="你好！", emotion="高兴")
        self.assertEqual(mm.type, "voice")
        self.assertEqual(mm.emotion, "高兴")
    
    def test_multimodal_response_invalid_type(self):
        """测试无效类型"""
        with self.assertRaises(ValidationError):
            MultiModalResponse(type="invalid", content="test")
    
    def test_multimodal_response_invalid_emotion(self):
        """测试无效情感"""
        with self.assertRaises(ValidationError):
            MultiModalResponse(type="voice", content="test", emotion="invalid_emotion")
    
    def test_relation_change_model(self):
        """测试关系变化模型"""
        rc = RelationChangeModel(Closeness=5.0, Trustness=-2.0)
        self.assertEqual(rc.Closeness, 5.0)
        self.assertEqual(rc.Trustness, -2.0)
    
    def test_future_response_model(self):
        """测试未来消息规划模型"""
        fr = FutureResponseModel(
            FutureResponseTime="2024年12月25日09时00分",
            FutureResponseAction="发送节日祝福"
        )
        self.assertEqual(fr.FutureResponseTime, "2024年12月25日09时00分")
        self.assertEqual(fr.FutureResponseAction, "发送节日祝福")
    
    def test_full_chat_response(self):
        """测试完整的 ChatResponse"""
        response = ChatResponse(
            InnerMonologue="用户很友好",
            MultiModalResponses=[
                MultiModalResponse(type="text", content="你好！"),
                MultiModalResponse(type="voice", content="很高兴认识你", emotion="高兴")
            ],
            ChatCatelogue="日常问候",
            RelationChange=RelationChangeModel(Closeness=2.0, Trustness=1.0),
            FutureResponse=FutureResponseModel(
                FutureResponseTime="2024年12月25日09时00分",
                FutureResponseAction="发送问候"
            )
        )
        self.assertEqual(len(response.MultiModalResponses), 2)
        self.assertEqual(response.RelationChange.Closeness, 2.0)
    
    def test_model_dump(self):
        """测试 model_dump 输出"""
        response = ChatResponse(
            MultiModalResponses=[MultiModalResponse(type="text", content="测试")]
        )
        data = response.model_dump()
        self.assertIsInstance(data, dict)
        self.assertIn("MultiModalResponses", data)
        self.assertEqual(len(data["MultiModalResponses"]), 1)


class TestPostAnalyzeResponseSchema(unittest.TestCase):
    """测试 PostAnalyzeResponse Schema (Requirements 2.3)"""
    
    def test_default_values(self):
        """测试默认值"""
        response = PostAnalyzeResponse()
        self.assertEqual(response.InnerMonologue, "")
        self.assertEqual(response.CharacterPublicSettings, "无")
        self.assertEqual(response.CharacterPrivateSettings, "无")
        self.assertEqual(response.UserSettings, "无")
        self.assertEqual(response.UserRealName, "无")
        self.assertEqual(response.UserHobbyName, "无")
        self.assertEqual(response.Dislike, 0)
    
    def test_with_values(self):
        """测试带值创建"""
        response = PostAnalyzeResponse(
            InnerMonologue="这次对话很愉快",
            CharacterPublicSettings="喜欢-音乐：古典音乐",
            UserSettings="职业-工程师：软件开发",
            UserRealName="张三",
            UserHobbyName="小张",
            RelationDescription="朋友关系",
            Dislike=0
        )
        self.assertEqual(response.UserRealName, "张三")
        self.assertEqual(response.CharacterPublicSettings, "喜欢-音乐：古典音乐")
    
    def test_dislike_value(self):
        """测试反感度数值"""
        response = PostAnalyzeResponse(Dislike=5)
        self.assertEqual(response.Dislike, 5)
        
        response2 = PostAnalyzeResponse(Dislike=None)
        self.assertIsNone(response2.Dislike)
    
    def test_model_dump(self):
        """测试 model_dump 输出"""
        response = PostAnalyzeResponse(
            UserRealName="测试用户",
            RelationDescription="好友"
        )
        data = response.model_dump()
        self.assertIsInstance(data, dict)
        self.assertIn("UserRealName", data)
        self.assertIn("RelationDescription", data)
    
    def test_json_serialization(self):
        """测试 JSON 序列化"""
        response = PostAnalyzeResponse(UserRealName="测试")
        json_str = response.model_dump_json()
        self.assertIsInstance(json_str, str)
        self.assertIn("UserRealName", json_str)


if __name__ == "__main__":
    unittest.main()
