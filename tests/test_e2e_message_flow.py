# -*- coding: utf-8 -*-
"""
端到端消息处理流程测试

测试从 MongoDB 队列获取消息 → 获取锁 → 处理 → 保存 → 释放锁的完整流程

Requirements:
- 从 MongoDB 队列获取消息
- 获取分布式锁
- 完整处理后保存到数据库
- 更新消息状态
- 释放锁
"""

import logging
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from dao.conversation_dao import ConversationDAO
from dao.lock import MongoDBLockManager
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from entity.message import (
    increment_retry_count,
    read_top_inputmessages,
    save_inputmessage,
    update_message_status_safe,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def test_user(mongo_client):
    """创建测试用户"""
    user_dao = UserDAO()
    user_id = str(uuid.uuid4())
    
    user_data = {
        "_id": user_id,
        "is_character": False,
        "platforms": {
            "wechat": {
                "id": f"wxid_test_user_{user_id[:8]}",
                "nickname": "测试用户"
            }
        }
    }
    
    mongo_client.insert_one("users", user_data)
    yield user_data
    
    # 清理
    mongo_client.delete_one("users", {"_id": user_id})


@pytest.fixture
def test_character(mongo_client):
    """创建测试角色"""
    user_dao = UserDAO()
    char_id = str(uuid.uuid4())
    
    char_data = {
        "_id": char_id,
        "is_character": True,
        "platforms": {
            "wechat": {
                "id": f"wxid_test_char_{char_id[:8]}",
                "nickname": "测试角色"
            }
        }
    }
    
    mongo_client.insert_one("users", char_data)
    yield char_data
    
    # 清理
    mongo_client.delete_one("users", {"_id": char_id})


@pytest.fixture
def test_conversation(mongo_client, test_user, test_character):
    """创建测试会话"""
    conv_dao = ConversationDAO()
    
    conv_id, _ = conv_dao.get_or_create_private_conversation(
        platform="wechat",
        user_id1=test_user["platforms"]["wechat"]["id"],
        nickname1=test_user["platforms"]["wechat"]["nickname"],
        user_id2=test_character["platforms"]["wechat"]["id"],
        nickname2=test_character["platforms"]["wechat"]["nickname"],
    )
    
    yield conv_id
    
    # 清理
    mongo_client.delete_one("conversations", {"_id": conv_id})


@pytest.fixture
def test_input_message(mongo_client, test_user, test_character):
    """创建测试输入消息"""
    message_id = str(uuid.uuid4())
    
    message_data = {
        "_id": message_id,
        "from_user": test_user["_id"],
        "to_user": test_character["_id"],
        "platform": "wechat",
        "message": "你好，这是一条测试消息",
        "status": "pending",
        "input_timestamp": int(time.time()),
        "retry_count": 0,
        "rollback_count": 0,
    }
    
    mongo_client.insert_one("inputmessages", message_data)
    yield message_data
    
    # 清理
    mongo_client.delete_one("inputmessages", {"_id": message_id})


class TestE2EMessageFlow:
    """端到端消息处理流程测试"""
    
    def test_read_message_from_queue(self, mongo_client, test_input_message, test_character):
        """测试从 MongoDB 队列获取消息"""
        # 从队列获取消息
        messages = read_top_inputmessages(
            to_user=test_character["_id"],
            status="pending",
            platform="wechat",
            limit=1
        )
        
        assert len(messages) > 0
        assert messages[0]["_id"] == test_input_message["_id"]
        assert messages[0]["status"] == "pending"
        assert messages[0]["message"] == "你好，这是一条测试消息"
        
        logger.info(f"✓ 成功从队列获取消息: {messages[0]['_id']}")
    
    def test_acquire_distributed_lock(self, mongo_client, test_conversation):
        """测试获取分布式锁"""
        lock_manager = MongoDBLockManager()
        
        # 获取锁
        lock_id = lock_manager.acquire_lock(
            "conversation",
            test_conversation,
            timeout=180
        )
        
        assert lock_id is not None
        logger.info(f"✓ 成功获取锁: lock_id={lock_id}")
        
        # 验证锁存在
        lock_doc = mongo_client.find_one("locks", {
            "resource_type": "conversation",
            "resource_id": f"conversation:{test_conversation}"
        })
        assert lock_doc is not None
        assert lock_doc["lock_id"] == lock_id
        
        # 释放锁
        released, _ = lock_manager.release_lock_safe(
            "conversation",
            test_conversation,
            lock_id
        )
        assert released
        logger.info("✓ 成功释放锁")
    
    def test_lock_prevents_concurrent_access(self, mongo_client, test_conversation):
        """测试锁机制防止并发访问"""
        lock_manager = MongoDBLockManager()
        
        # Worker 1 获取锁
        lock_id_1 = lock_manager.acquire_lock(
            "conversation",
            test_conversation,
            timeout=180
        )
        assert lock_id_1 is not None
        logger.info(f"✓ Worker 1 获取锁: {lock_id_1}")
        
        # Worker 2 尝试获取同一个锁（应该失败）
        lock_id_2 = lock_manager.acquire_lock(
            "conversation",
            test_conversation,
            timeout=180,
            max_wait=0.1
        )
        assert lock_id_2 is None
        logger.info("✓ Worker 2 无法获取锁（符合预期）")
        
        # Worker 1 释放锁
        lock_manager.release_lock_safe("conversation", test_conversation, lock_id_1)
        
        # Worker 2 再次尝试获取锁（应该成功）
        lock_id_3 = lock_manager.acquire_lock(
            "conversation",
            test_conversation,
            timeout=180
        )
        assert lock_id_3 is not None
        logger.info(f"✓ Worker 2 成功获取锁: {lock_id_3}")
        
        # 清理
        lock_manager.release_lock_safe("conversation", test_conversation, lock_id_3)
    
    def test_update_message_status_with_optimistic_lock(
        self, mongo_client, test_input_message
    ):
        """测试使用乐观锁更新消息状态"""
        message_id = test_input_message["_id"]
        
        # 更新状态从 pending 到 handled
        success = update_message_status_safe(message_id, "handled", "pending")
        assert success
        logger.info("✓ 成功更新消息状态（乐观锁）")
        
        # 验证状态已更新
        updated_msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert updated_msg["status"] == "handled"
        
        # 尝试再次更新（应该失败，因为状态已经不是 pending）
        success = update_message_status_safe(message_id, "failed", "pending")
        assert not success
        logger.info("✓ 乐观锁防止重复更新（符合预期）")
    
    def test_retry_mechanism(self, mongo_client, test_input_message):
        """测试消息重试机制"""
        message_id = test_input_message["_id"]
        
        # 第一次重试
        retry_count = increment_retry_count(message_id, "测试错误1")
        assert retry_count == 1
        logger.info(f"✓ 第1次重试，retry_count={retry_count}")
        
        # 第二次重试
        retry_count = increment_retry_count(message_id, "测试错误2")
        assert retry_count == 2
        logger.info(f"✓ 第2次重试，retry_count={retry_count}")
        
        # 第三次重试
        retry_count = increment_retry_count(message_id, "测试错误3")
        assert retry_count == 3
        logger.info(f"✓ 第3次重试，retry_count={retry_count}")
        
        # 验证错误信息已保存
        msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert msg["retry_count"] == 3
        assert "测试错误3" in msg.get("last_error", "")
    
    def test_complete_message_processing_flow(
        self, mongo_client, test_user, test_character, test_conversation, test_input_message
    ):
        """测试完整的消息处理流程"""
        lock_manager = MongoDBLockManager()
        message_id = test_input_message["_id"]
        
        # Step 1: 从队列获取消息
        messages = read_top_inputmessages(
            to_user=test_character["_id"],
            status="pending",
            platform="wechat",
            limit=1
        )
        assert len(messages) > 0
        logger.info("✓ Step 1: 从队列获取消息")
        
        # Step 2: 获取分布式锁
        lock_id = lock_manager.acquire_lock(
            "conversation",
            test_conversation,
            timeout=180
        )
        assert lock_id is not None
        logger.info(f"✓ Step 2: 获取锁 lock_id={lock_id}")
        
        try:
            # Step 3: 模拟消息处理（这里简化处理）
            # 在真实场景中，这里会调用 Agent 和 Workflow
            logger.info("✓ Step 3: 处理消息（模拟）")
            
            # Step 4: 保存处理结果到数据库
            # 更新会话历史
            conv_dao = ConversationDAO()
            conversation = conv_dao.get_conversation_by_id(test_conversation)
            
            # 添加输入消息到历史
            input_msg = {
                "role": "user",
                "message": test_input_message["message"],
                "timestamp": test_input_message["input_timestamp"]
            }
            conversation["conversation_info"]["chat_history"].append(input_msg)
            
            # 添加回复消息到历史
            response_msg = {
                "role": "assistant",
                "message": "这是测试回复",
                "timestamp": int(time.time())
            }
            conversation["conversation_info"]["chat_history"].append(response_msg)
            
            # 保存会话
            conv_dao.update_conversation_info(
                test_conversation,
                conversation["conversation_info"]
            )
            logger.info("✓ Step 4: 保存处理结果到数据库")
            
            # Step 5: 更新消息状态
            success = update_message_status_safe(message_id, "handled", "pending")
            assert success
            logger.info("✓ Step 5: 更新消息状态为 handled")
            
        finally:
            # Step 6: 释放锁
            released, _ = lock_manager.release_lock_safe(
                "conversation",
                test_conversation,
                lock_id
            )
            assert released
            logger.info("✓ Step 6: 释放锁")
        
        # 验证最终状态
        final_msg = mongo_client.find_one("inputmessages", {"_id": message_id})
        assert final_msg["status"] == "handled"
        
        final_conv = conv_dao.get_conversation_by_id(test_conversation)
        assert len(final_conv["conversation_info"]["chat_history"]) == 2
        
        logger.info("✅ 完整的端到端消息处理流程测试通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
