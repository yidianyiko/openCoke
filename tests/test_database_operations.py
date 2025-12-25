# -*- coding: utf-8 -*-
"""
真实数据库操作测试

测试真实的 MongoDB 读写操作

Requirements:
- 真实的 MongoDB 读写
- 数据持久化验证
"""

import logging
import time
import uuid

import pytest

from dao.conversation_dao import ConversationDAO
from dao.mongo import MongoDBBase
from dao.reminder_dao import ReminderDAO
from dao.user_dao import UserDAO

logger = logging.getLogger(__name__)


class TestDatabaseOperations:
    """真实数据库操作测试"""
    
    def test_user_crud_operations(self, mongo_client):
        """测试用户的 CRUD 操作"""
        from bson import ObjectId
        
        user_dao = UserDAO()
        user_id = ObjectId()
        user_id_str = str(user_id)
        
        # Create
        user_data = {
            "_id": user_id,
            "is_character": False,
            "platforms": {
                "wechat": {
                    "id": f"wxid_{user_id_str[:8]}",
                    "nickname": "测试用户"
                }
            },
            "created_at": int(time.time())
        }
        mongo_client.insert_one("users", user_data)
        logger.info(f"✓ 创建用户: {user_id_str}")
        
        # Read
        user = user_dao.get_user_by_id(user_id_str)
        assert user is not None
        assert str(user["_id"]) == user_id_str
        assert user["platforms"]["wechat"]["nickname"] == "测试用户"
        logger.info("✓ 读取用户成功")
        
        # Update
        mongo_client.update_one(
            "users",
            {"_id": user_id},
            {"$set": {"platforms.wechat.nickname": "更新后的用户"}}
        )
        user = user_dao.get_user_by_id(user_id_str)
        assert user["platforms"]["wechat"]["nickname"] == "更新后的用户"
        logger.info("✓ 更新用户成功")
        
        # Delete
        mongo_client.delete_one("users", {"_id": user_id})
        user = user_dao.get_user_by_id(user_id_str)
        assert user is None
        logger.info("✓ 删除用户成功")
    
    def test_conversation_crud_operations(self, mongo_client):
        """测试会话的 CRUD 操作"""
        conv_dao = ConversationDAO()
        
        # 使用唯一的用户ID避免冲突
        unique_id = uuid.uuid4().hex[:8]
        
        # Create
        conv_id, created = conv_dao.get_or_create_private_conversation(
            platform="wechat",
            user_id1=f"wxid_test_user_{unique_id}",
            nickname1="用户1",
            user_id2=f"wxid_test_char_{unique_id}",
            nickname2="角色1"
        )
        # 如果已存在，先删除再创建
        if not created:
            mongo_client.delete_one("conversations", {"_id": conv_id})
            conv_id, created = conv_dao.get_or_create_private_conversation(
                platform="wechat",
                user_id1=f"wxid_test_user_{unique_id}",
                nickname1="用户1",
                user_id2=f"wxid_test_char_{unique_id}",
                nickname2="角色1"
            )
        assert created or conv_id is not None
        logger.info(f"✓ 创建会话: {conv_id}")
        
        # Read
        conversation = conv_dao.get_conversation_by_id(conv_id)
        assert conversation is not None
        assert str(conversation["_id"]) == conv_id
        logger.info("✓ 读取会话成功")
        
        # Update-添加消息到历史
        conversation["conversation_info"]["chat_history"].append({
            "role": "user",
            "message": "测试消息",
            "timestamp": int(time.time())
        })
        conv_dao.update_conversation_info(
            conv_id,
            conversation["conversation_info"]
        )
        
        updated_conv = conv_dao.get_conversation_by_id(conv_id)
        assert len(updated_conv["conversation_info"]["chat_history"]) == 1
        logger.info("✓ 更新会话成功")
        
        # Delete
        from bson import ObjectId
        mongo_client.delete_one("conversations", {"_id": ObjectId(conv_id)})
        conversation = conv_dao.get_conversation_by_id(conv_id)
        assert conversation is None
        logger.info("✓ 删除会话成功")
    
    def test_reminder_crud_operations(self, mongo_client):
        """测试提醒的 CRUD 操作"""
        reminder_dao = ReminderDAO()
        reminder_id = str(uuid.uuid4())
        current_time = int(time.time())
        
        # Create
        reminder_data = {
            "user_id": "test_user",
            "reminder_id": reminder_id,
            "title": "测试提醒",
            "action_template": "记得测试提醒",
            "next_trigger_time": current_time + 3600,
            "time_original": "1小时后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        inserted_id = reminder_dao.create_reminder(reminder_data)
        assert inserted_id is not None
        logger.info(f"✓ 创建提醒: {reminder_id}")
        
        # Read
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder is not None
        assert reminder["reminder_id"] == reminder_id
        assert reminder["title"] == "测试提醒"
        logger.info("✓ 读取提醒成功")
        
        # Update
        success = reminder_dao.update_reminder(reminder_id, {"title": "更新后的提醒"})
        assert success
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder["title"] == "更新后的提醒"
        logger.info("✓ 更新提醒成功")
        
        # Delete
        success = reminder_dao.delete_reminder(reminder_id)
        assert success
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder is None
        logger.info("✓ 删除提醒成功")
        
        reminder_dao.close()
    
    def test_relation_crud_operations(self, mongo_client):
        """测试关系的 CRUD 操作"""
        relation_id = str(uuid.uuid4())
        
        # Create
        relation_data = {
            "_id": relation_id,
            "uid": "test_user",
            "cid": "test_char",
            "relationship": {
                "closeness": 50,
                "trustness": 50,
                "dislike": 0,
                "status": "空闲",
                "description": "陌生人"
            },
            "user_info": {
                "realname": "",
                "hobbyname": "",
                "description": ""
            },
            "character_info": {
                "longterm_purpose": "",
                "shortterm_purpose": "",
                "attitude": ""
            }
        }
        mongo_client.insert_one("relations", relation_data)
        logger.info(f"✓ 创建关系: {relation_id}")
        
        # Read
        relation = mongo_client.find_one("relations", {"_id": relation_id})
        assert relation is not None
        assert relation["uid"] == "test_user"
        assert relation["cid"] == "test_char"
        logger.info("✓ 读取关系成功")
        
        # Update
        mongo_client.update_one(
            "relations",
            {"_id": relation_id},
            {"$set": {"relationship.closeness": 60}}
        )
        relation = mongo_client.find_one("relations", {"_id": relation_id})
        assert relation["relationship"]["closeness"] == 60
        logger.info("✓ 更新关系成功")
        
        # Delete
        mongo_client.delete_one("relations", {"_id": relation_id})
        relation = mongo_client.find_one("relations", {"_id": relation_id})
        assert relation is None
        logger.info("✓ 删除关系成功")
    
    def test_message_queue_operations(self, mongo_client):
        """测试消息队列操作"""
        message_id = str(uuid.uuid4())
        
        # 创建输入消息
        input_message = {
            "_id": message_id,
            "from_user": "test_user",
            "to_user": "test_char",
            "platform": "wechat",
            "message": "测试消息",
            "status": "pending",
            "input_timestamp": int(time.time()),
            "retry_count": 0
        }
        mongo_client.insert_one("inputmessages", input_message)
        logger.info(f"✓ 创建输入消息: {message_id}")
        
        # 读取消息
        msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert msg is not None
        assert msg["status"] == "pending"
        logger.info("✓ 读取输入消息成功")
        
        # 更新消息状态
        mongo_client.update_one(
            "inputmessages",
            {"_id": message_id},
            {"$set": {"status": "handled"}}
        )
        msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert msg["status"] == "handled"
        logger.info("✓ 更新消息状态成功")
        
        # 创建输出消息
        output_id = str(uuid.uuid4())
        output_message = {
            "_id": output_id,
            "conversation_id": "test_conv",
            "uid": "test_user",
            "cid": "test_char",
            "type": "text",
            "content": "测试回复",
            "timestamp": int(time.time()),
            "source": "chat"
        }
        mongo_client.insert_one("outputmessages", output_message)
        logger.info(f"✓ 创建输出消息: {output_id}")
        
        # 清理
        mongo_client.delete_one("inputmessages", {"_id": message_id})
        mongo_client.delete_one("outputmessages", {"_id": output_id})
        logger.info("✓ 清理消息成功")
    
    def test_batch_operations(self, mongo_client):
        """测试批量操作"""
        # 批量插入
        test_docs = []
        for i in range(10):
            test_docs.append({
                "_id": str(uuid.uuid4()),
                "index": i,
                "data": f"测试数据{i}"
            })
        
        for doc in test_docs:
            mongo_client.insert_one("test_batch", doc)
        logger.info(f"✓ 批量插入 {len(test_docs)} 条数据")
        
        # 批量查询
        results = mongo_client.find_many("test_batch", {}, limit=20)
        assert len(results) >= 10
        logger.info(f"✓ 批量查询到 {len(results)} 条数据")
        
        # 批量更新
        for doc in test_docs:
            mongo_client.update_one(
                "test_batch",
                {"_id": doc["_id"]},
                {"$set": {"updated": True}}
            )
        logger.info("✓ 批量更新成功")
        
        # 验证更新
        updated_docs = mongo_client.find_many("test_batch", {"updated": True}, limit=20)
        assert len(updated_docs) >= 10
        logger.info("✓ 验证批量更新成功")
        
        # 批量删除
        for doc in test_docs:
            mongo_client.delete_one("test_batch", {"_id": doc["_id"]})
        logger.info("✓ 批量删除成功")
        
        # 验证删除
        remaining = mongo_client.find_many("test_batch", {}, limit=20)
        remaining_ids = [doc["_id"] for doc in remaining]
        for doc in test_docs:
            assert doc["_id"] not in remaining_ids
        logger.info("✓ 验证批量删除成功")
    
    def test_transaction_like_operations(self, mongo_client):
        """测试类事务操作（多步骤操作的原子性）"""
        user_id = str(uuid.uuid4())
        conv_id = str(uuid.uuid4())
        relation_id = str(uuid.uuid4())
        
        try:
            # Step 1: 创建用户
            user_data = {
                "_id": user_id,
                "is_character": False,
                "platforms": {"wechat": {"id": f"wxid_{user_id[:8]}", "nickname": "测试"}}
            }
            mongo_client.insert_one("users", user_data)
            logger.info("✓ Step 1: 创建用户")
            
            # Step 2: 创建会话
            conv_data = {
                "_id": conv_id,
                "talkers": [{"id": user_id, "nickname": "测试"}],
                "conversation_info": {"chat_history": []}
            }
            mongo_client.insert_one("conversations", conv_data)
            logger.info("✓ Step 2: 创建会话")
            
            # Step 3: 创建关系
            relation_data = {
                "_id": relation_id,
                "uid": user_id,
                "cid": "test_char",
                "relationship": {"closeness": 50}
            }
            mongo_client.insert_one("relations", relation_data)
            logger.info("✓ Step 3: 创建关系")
            
            # 验证所有数据都已创建
            assert mongo_client.find_one("users", {"_id": user_id}) is not None
            assert mongo_client.find_one("conversations", {"_id": conv_id}) is not None
            assert mongo_client.find_one("relations", {"_id": relation_id}) is not None
            logger.info("✓ 验证所有数据创建成功")
            
        finally:
            # 清理（模拟回滚）
            mongo_client.delete_one("users", {"_id": user_id})
            mongo_client.delete_one("conversations", {"_id": conv_id})
            mongo_client.delete_one("relations", {"_id": relation_id})
            logger.info("✓ 清理测试数据")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
