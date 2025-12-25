# -*- coding: utf-8 -*-
"""
会话数据结构向后兼容性测试

测试旧数据（没有完整 conversation_info 结构）能否正常工作

Requirements:
- 旧数据（空的 conversation_info）能被自动修复
- 旧数据（缺少部分字段）能被自动补全
- 新数据保持完整结构
"""

import logging
import uuid

import pytest
from bson import ObjectId

from dao.conversation_dao import ConversationDAO

logger = logging.getLogger(__name__)


class TestConversationBackwardCompatibility:
    """会话数据结构向后兼容性测试"""
    
    def test_old_data_with_empty_conversation_info(self, mongo_client):
        """测试旧数据：空的 conversation_info"""
        conv_dao = ConversationDAO()
        conv_id = ObjectId()
        
        # 模拟旧数据：只有空的 conversation_info
        old_conversation = {
            "_id": conv_id,
            "chatroom_name": None,
            "talkers": [
                {"id": "user1", "nickname": "用户1"},
                {"id": "user2", "nickname": "用户2"}
            ],
            "platform": "wechat",
            "conversation_info": {}  # 旧数据：空字典
        }
        
        # 直接插入到数据库
        mongo_client.insert_one("conversations", old_conversation)
        logger.info(f"✓ 插入旧数据（空 conversation_info）: {conv_id}")
        
        # 通过 DAO 获取
        conversation = conv_dao.get_conversation_by_id(str(conv_id))
        
        # 验证结构已被自动补全
        assert conversation is not None
        assert "conversation_info" in conversation
        assert "chat_history" in conversation["conversation_info"]
        assert "input_messages" in conversation["conversation_info"]
        assert "future" in conversation["conversation_info"]
        assert "turn_sent_contents" in conversation["conversation_info"]
        
        # 验证可以直接使用
        conversation["conversation_info"]["chat_history"].append({
            "role": "user",
            "message": "测试消息",
            "timestamp": 123456
        })
        
        logger.info("✓ 旧数据已自动补全，可以正常使用")
        
        # 清理
        mongo_client.delete_one("conversations", {"_id": conv_id})
    
    def test_old_data_with_partial_conversation_info(self, mongo_client):
        """测试旧数据：部分字段缺失"""
        conv_dao = ConversationDAO()
        conv_id = ObjectId()
        
        # 模拟旧数据：只有部分字段
        old_conversation = {
            "_id": conv_id,
            "chatroom_name": None,
            "talkers": [
                {"id": "user1", "nickname": "用户1"},
                {"id": "user2", "nickname": "用户2"}
            ],
            "platform": "wechat",
            "conversation_info": {
                "chat_history": [
                    {"role": "user", "message": "历史消息", "timestamp": 123456}
                ],
                # 缺少其他字段
            }
        }
        
        # 直接插入到数据库
        mongo_client.insert_one("conversations", old_conversation)
        logger.info(f"✓ 插入旧数据（部分字段）: {conv_id}")
        
        # 通过 DAO 获取
        conversation = conv_dao.get_conversation_by_id(str(conv_id))
        
        # 验证已有字段保持不变
        assert len(conversation["conversation_info"]["chat_history"]) == 1
        assert conversation["conversation_info"]["chat_history"][0]["message"] == "历史消息"
        
        # 验证缺失字段已补全
        assert "input_messages" in conversation["conversation_info"]
        assert "future" in conversation["conversation_info"]
        assert "turn_sent_contents" in conversation["conversation_info"]
        
        logger.info("✓ 旧数据保留已有字段，补全缺失字段")
        
        # 清理
        mongo_client.delete_one("conversations", {"_id": conv_id})
    
    def test_old_data_with_incomplete_future(self, mongo_client):
        """测试旧数据：future 字段不完整"""
        conv_dao = ConversationDAO()
        conv_id = ObjectId()
        
        # 模拟旧数据：future 只有部分字段
        old_conversation = {
            "_id": conv_id,
            "chatroom_name": None,
            "talkers": [
                {"id": "user1", "nickname": "用户1"},
                {"id": "user2", "nickname": "用户2"}
            ],
            "platform": "wechat",
            "conversation_info": {
                "chat_history": [],
                "future": {
                    "timestamp": 123456,
                    "action": "测试动作"
                    # 缺少 proactive_times 和 status
                }
            }
        }
        
        # 直接插入到数据库
        mongo_client.insert_one("conversations", old_conversation)
        logger.info(f"✓ 插入旧数据（不完整的 future）: {conv_id}")
        
        # 通过 DAO 获取
        conversation = conv_dao.get_conversation_by_id(str(conv_id))
        
        # 验证已有字段保持不变
        assert conversation["conversation_info"]["future"]["timestamp"] == 123456
        assert conversation["conversation_info"]["future"]["action"] == "测试动作"
        
        # 验证缺失字段已补全
        assert "proactive_times" in conversation["conversation_info"]["future"]
        assert "status" in conversation["conversation_info"]["future"]
        assert conversation["conversation_info"]["future"]["proactive_times"] == 0
        assert conversation["conversation_info"]["future"]["status"] == "pending"
        
        logger.info("✓ future 字段保留已有值，补全缺失字段")
        
        # 清理
        mongo_client.delete_one("conversations", {"_id": conv_id})
    
    def test_new_data_keeps_complete_structure(self, mongo_client):
        """测试新数据：保持完整结构"""
        conv_dao = ConversationDAO()
        
        # 使用 DAO 创建新会话
        conv_id, created = conv_dao.get_or_create_private_conversation(
            platform="wechat",
            user_id1=f"user_{uuid.uuid4().hex[:8]}",
            nickname1="新用户1",
            user_id2=f"user_{uuid.uuid4().hex[:8]}",
            nickname2="新用户2"
        )
        
        assert created
        logger.info(f"✓ 创建新会话: {conv_id}")
        
        # 获取会话
        conversation = conv_dao.get_conversation_by_id(conv_id)
        
        # 验证所有字段都存在
        assert "conversation_info" in conversation
        assert "chat_history" in conversation["conversation_info"]
        assert "input_messages" in conversation["conversation_info"]
        assert "input_messages_str" in conversation["conversation_info"]
        assert "chat_history_str" in conversation["conversation_info"]
        assert "photo_history" in conversation["conversation_info"]
        assert "future" in conversation["conversation_info"]
        assert "turn_sent_contents" in conversation["conversation_info"]
        
        # 验证 future 的所有子字段
        future = conversation["conversation_info"]["future"]
        assert "timestamp" in future
        assert "action" in future
        assert "proactive_times" in future
        assert "status" in future
        
        logger.info("✓ 新会话包含完整的数据结构")
        
        # 清理
        mongo_client.delete_one("conversations", {"_id": ObjectId(conv_id)})
    
    def test_get_private_conversation_with_old_data(self, mongo_client):
        """测试通过 get_private_conversation 获取旧数据"""
        conv_dao = ConversationDAO()
        conv_id = ObjectId()
        user_id1 = f"user_{uuid.uuid4().hex[:8]}"
        user_id2 = f"user_{uuid.uuid4().hex[:8]}"
        
        # 插入旧数据
        old_conversation = {
            "_id": conv_id,
            "chatroom_name": None,
            "talkers": [
                {"id": user_id1, "nickname": "用户1"},
                {"id": user_id2, "nickname": "用户2"}
            ],
            "platform": "wechat",
            "conversation_info": {}
        }
        
        mongo_client.insert_one("conversations", old_conversation)
        logger.info(f"✓ 插入旧数据: {conv_id}")
        
        # 通过 get_private_conversation 获取
        conversation = conv_dao.get_private_conversation(
            "wechat", user_id1, user_id2
        )
        
        # 验证结构已被自动补全
        assert conversation is not None
        assert "chat_history" in conversation["conversation_info"]
        assert "future" in conversation["conversation_info"]
        
        logger.info("✓ get_private_conversation 也能自动补全旧数据")
        
        # 清理
        mongo_client.delete_one("conversations", {"_id": conv_id})
    
    def test_get_group_conversation_with_old_data(self, mongo_client):
        """测试通过 get_group_conversation 获取旧数据"""
        conv_dao = ConversationDAO()
        conv_id = ObjectId()
        chatroom_name = f"group_{uuid.uuid4().hex[:8]}"
        
        # 插入旧数据
        old_conversation = {
            "_id": conv_id,
            "chatroom_name": chatroom_name,
            "talkers": [
                {"id": "user1", "nickname": "用户1"},
                {"id": "user2", "nickname": "用户2"}
            ],
            "platform": "wechat",
            "conversation_info": {"chat_history": []}
        }
        
        mongo_client.insert_one("conversations", old_conversation)
        logger.info(f"✓ 插入旧群聊数据: {conv_id}")
        
        # 通过 get_group_conversation 获取
        conversation = conv_dao.get_group_conversation("wechat", chatroom_name)
        
        # 验证结构已被自动补全
        assert conversation is not None
        assert "chat_history" in conversation["conversation_info"]
        assert "future" in conversation["conversation_info"]
        assert "turn_sent_contents" in conversation["conversation_info"]
        
        logger.info("✓ get_group_conversation 也能自动补全旧数据")
        
        # 清理
        mongo_client.delete_one("conversations", {"_id": conv_id})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
