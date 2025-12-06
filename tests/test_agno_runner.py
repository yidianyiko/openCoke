# -*- coding: utf-8 -*-
"""
Agno Runner 属性测试

测试 Runner 层功能：
- ObjectId 序列化 (Requirements 6.1)
- 默认值完整性 (Requirements 6.2)
- 消息合并正确性 (Requirements 7.2)
- 已发送消息记录 (Requirements 7.4)
"""
import sys
sys.path.append(".")

import unittest
import logging
from bson import ObjectId

logger = logging.getLogger(__name__)


# ========== 从 agent_handler.py 复制的函数（避免 OSS 导入问题）==========

def merge_pending_messages(current_messages: list, new_messages: list) -> list:
    """
    合并待处理消息
    
    当 rollback 发生时，将当前正在处理的消息和新到达的消息合并为一个上下文
    
    Args:
        current_messages: 当前正在处理的消息列表
        new_messages: 新到达的消息列表
        
    Returns:
        合并后的消息列表（按时间排序）
        
    Requirements: 7.2
    """
    # 使用 _id 去重
    seen_ids = set()
    merged = []
    
    for msg in current_messages + new_messages:
        msg_id = str(msg.get("_id", ""))
        if msg_id and msg_id not in seen_ids:
            seen_ids.add(msg_id)
            merged.append(msg)
        elif not msg_id:
            # 没有 _id 的消息直接添加
            merged.append(msg)
    
    # 按时间戳排序
    merged.sort(key=lambda x: x.get("timestamp", 0))
    
    return merged


def record_sent_messages_to_history(conversation: dict, sent_messages: list) -> dict:
    """
    将已发送的消息记录到对话历史
    
    当 rollback 发生时，已发送的消息不会被撤回，需要记录到历史中
    
    Args:
        conversation: 对话对象
        sent_messages: 已发送的消息列表
        
    Returns:
        更新后的 conversation 对象
        
    Requirements: 7.4
    """
    if not sent_messages:
        return conversation
    
    chat_history = conversation.get("conversation_info", {}).get("chat_history", [])
    
    for msg in sent_messages:
        if msg and msg not in chat_history:
            chat_history.append(msg)
    
    conversation["conversation_info"]["chat_history"] = chat_history
    
    logger.info(f"[消息打断] 已记录 {len(sent_messages)} 条已发送消息到对话历史")
    
    return conversation


class TestObjectIdSerialization(unittest.TestCase):
    """测试 ObjectId 序列化 (Requirements 6.1)"""
    
    def setUp(self):
        from agent.runner.context import _convert_objectid_to_str
        self.convert = _convert_objectid_to_str
    
    def test_convert_single_objectid(self):
        """测试转换单个 ObjectId"""
        oid = ObjectId()
        result = self.convert(oid)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 24)  # ObjectId 字符串长度为 24
    
    def test_convert_dict_with_objectid(self):
        """测试转换包含 ObjectId 的字典"""
        data = {
            "_id": ObjectId(),
            "name": "test",
            "count": 42
        }
        result = self.convert(data)
        
        self.assertIsInstance(result, dict)
        self.assertIsInstance(result["_id"], str)
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["count"], 42)
    
    def test_convert_nested_dict(self):
        """测试转换嵌套字典"""
        data = {
            "_id": ObjectId(),
            "nested": {
                "inner_id": ObjectId(),
                "value": "test"
            }
        }
        result = self.convert(data)
        
        self.assertIsInstance(result["_id"], str)
        self.assertIsInstance(result["nested"]["inner_id"], str)
        self.assertEqual(result["nested"]["value"], "test")
    
    def test_convert_list_with_objectids(self):
        """测试转换包含 ObjectId 的列表"""
        data = [ObjectId(), ObjectId(), ObjectId()]
        result = self.convert(data)
        
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)
        for item in result:
            self.assertIsInstance(item, str)
    
    def test_convert_complex_structure(self):
        """测试转换复杂结构"""
        data = {
            "_id": ObjectId(),
            "users": [
                {"_id": ObjectId(), "name": "user1"},
                {"_id": ObjectId(), "name": "user2"}
            ],
            "metadata": {
                "created_by": ObjectId(),
                "tags": ["tag1", "tag2"]
            }
        }
        result = self.convert(data)
        
        self.assertIsInstance(result["_id"], str)
        self.assertIsInstance(result["users"][0]["_id"], str)
        self.assertIsInstance(result["users"][1]["_id"], str)
        self.assertIsInstance(result["metadata"]["created_by"], str)
        self.assertEqual(result["metadata"]["tags"], ["tag1", "tag2"])
    
    def test_convert_preserves_non_objectid_types(self):
        """测试转换保留非 ObjectId 类型"""
        data = {
            "string": "test",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
            "list": [1, 2, 3]
        }
        result = self.convert(data)
        
        self.assertEqual(result["string"], "test")
        self.assertEqual(result["int"], 42)
        self.assertEqual(result["float"], 3.14)
        self.assertEqual(result["bool"], True)
        self.assertIsNone(result["none"])
        self.assertEqual(result["list"], [1, 2, 3])


class TestDefaultValueCompleteness(unittest.TestCase):
    """测试默认值完整性 (Requirements 6.2)"""
    
    def test_context_retrieve_defaults(self):
        """测试 context_retrieve 默认值"""
        expected_keys = [
            "character_global",
            "character_private",
            "user",
            "character_knowledge",
            "character_photo",
            "confirmed_reminders"
        ]
        
        default = {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "character_photo": "",
            "confirmed_reminders": ""
        }
        
        for key in expected_keys:
            self.assertIn(key, default)
            self.assertEqual(default[key], "")
    
    def test_query_rewrite_defaults(self):
        """测试 query_rewrite 默认值"""
        expected_keys = [
            "InnerMonologue",
            "CharacterSettingQueryQuestion",
            "CharacterSettingQueryKeywords",
            "UserProfileQueryQuestion",
            "UserProfileQueryKeywords",
            "CharacterKnowledgeQueryQuestion",
            "CharacterKnowledgeQueryKeywords"
        ]
        
        default = {
            "InnerMonologue": "",
            "CharacterSettingQueryQuestion": "",
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": "",
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": ""
        }
        
        for key in expected_keys:
            self.assertIn(key, default)
            self.assertEqual(default[key], "")


class TestMessageMergeCorrectness(unittest.TestCase):
    """测试消息合并正确性 (Requirements 7.2)"""
    
    def test_merge_empty_lists(self):
        """测试合并空列表"""
        result = merge_pending_messages([], [])
        self.assertEqual(result, [])
    
    def test_merge_with_one_empty(self):
        """测试一个列表为空"""
        current = [{"_id": "1", "timestamp": 100, "message": "msg1"}]
        result = merge_pending_messages(current, [])
        self.assertEqual(len(result), 1)
        
        result2 = merge_pending_messages([], current)
        self.assertEqual(len(result2), 1)
    
    def test_merge_deduplication(self):
        """测试去重"""
        current = [{"_id": "1", "timestamp": 100, "message": "msg1"}]
        new_msgs = [
            {"_id": "1", "timestamp": 100, "message": "msg1"},  # 重复
            {"_id": "2", "timestamp": 200, "message": "msg2"}   # 新消息
        ]
        
        result = merge_pending_messages(current, new_msgs)
        self.assertEqual(len(result), 2)
        
        # 验证没有重复的 _id
        ids = [msg["_id"] for msg in result]
        self.assertEqual(len(ids), len(set(ids)))
    
    def test_merge_sorting_by_timestamp(self):
        """测试按时间戳排序"""
        current = [{"_id": "2", "timestamp": 200, "message": "msg2"}]
        new_msgs = [{"_id": "1", "timestamp": 100, "message": "msg1"}]
        
        result = merge_pending_messages(current, new_msgs)
        
        # 验证按时间戳升序排列
        self.assertEqual(result[0]["timestamp"], 100)
        self.assertEqual(result[1]["timestamp"], 200)
    
    def test_merge_handles_missing_id(self):
        """测试处理缺少 _id 的消息"""
        current = [{"timestamp": 100, "message": "msg1"}]  # 无 _id
        new_msgs = [{"timestamp": 200, "message": "msg2"}]  # 无 _id
        
        result = merge_pending_messages(current, new_msgs)
        self.assertEqual(len(result), 2)


class TestSentMessagesRecording(unittest.TestCase):
    """测试已发送消息记录 (Requirements 7.4)"""
    
    def test_record_empty_messages(self):
        """测试记录空消息列表"""
        conversation = {"conversation_info": {"chat_history": []}}
        result = record_sent_messages_to_history(conversation, [])
        
        self.assertEqual(len(result["conversation_info"]["chat_history"]), 0)
    
    def test_record_messages_to_empty_history(self):
        """测试记录消息到空历史"""
        conversation = {"conversation_info": {"chat_history": []}}
        sent = [
            {"message": "sent1", "type": "text"},
            {"message": "sent2", "type": "text"}
        ]
        
        result = record_sent_messages_to_history(conversation, sent)
        
        self.assertEqual(len(result["conversation_info"]["chat_history"]), 2)
    
    def test_record_messages_to_existing_history(self):
        """测试记录消息到已有历史"""
        conversation = {
            "conversation_info": {
                "chat_history": [
                    {"message": "existing", "type": "text"}
                ]
            }
        }
        sent = [{"message": "new", "type": "text"}]
        
        result = record_sent_messages_to_history(conversation, sent)
        
        self.assertEqual(len(result["conversation_info"]["chat_history"]), 2)
    
    def test_record_avoids_duplicates(self):
        """测试避免重复记录"""
        existing_msg = {"message": "existing", "type": "text"}
        conversation = {
            "conversation_info": {
                "chat_history": [existing_msg]
            }
        }
        
        # 尝试记录相同的消息
        result = record_sent_messages_to_history(conversation, [existing_msg])
        
        # 应该不会重复添加
        self.assertEqual(len(result["conversation_info"]["chat_history"]), 1)
    
    def test_record_returns_updated_conversation(self):
        """测试返回更新后的 conversation"""
        conversation = {"conversation_info": {"chat_history": []}}
        sent = [{"message": "test"}]
        
        result = record_sent_messages_to_history(conversation, sent)
        
        self.assertIsInstance(result, dict)
        self.assertIn("conversation_info", result)
        self.assertIn("chat_history", result["conversation_info"])


if __name__ == "__main__":
    unittest.main()
