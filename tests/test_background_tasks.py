# -*- coding: utf-8 -*-
"""
后台任务测试

测试定时检查和触发提醒、主动消息的后台任务

Requirements:
- 定时检查到期提醒
- 触发提醒消息
- 触发主动消息
- 清理过期提醒
"""

import logging
import time
import uuid

import pytest

from agent.agno_agent.services.proactive_message_trigger_service import (
    ProactiveMessageTriggerService,
)
from dao.conversation_dao import ConversationDAO
from dao.mongo import MongoDBBase
from dao.reminder_dao import ReminderDAO
from dao.user_dao import UserDAO

logger = logging.getLogger(__name__)


@pytest.fixture
def test_user(mongo_client):
    """创建测试用户"""
    user_id = str(uuid.uuid4())
    user_data = {
        "_id": user_id,
        "is_character": False,
        "platforms": {
            "wechat": {
                "id": f"wxid_user_{user_id[:8]}",
                "nickname": "测试用户"
            }
        }
    }
    mongo_client.insert_one("users", user_data)
    yield user_data
    mongo_client.delete_one("users", {"_id": user_id})


@pytest.fixture
def test_character(mongo_client):
    """创建测试角色"""
    char_id = str(uuid.uuid4())
    char_data = {
        "_id": char_id,
        "is_character": True,
        "platforms": {
            "wechat": {
                "id": f"wxid_char_{char_id[:8]}",
                "nickname": "测试角色"
            }
        }
    }
    mongo_client.insert_one("users", char_data)
    yield char_data
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
    mongo_client.delete_one("conversations", {"_id": conv_id})


class TestBackgroundTasks:
    """后台任务测试"""
    
    def test_check_due_reminders(self, mongo_client, test_user):
        """测试检查到期的提醒"""
        reminder_dao = ReminderDAO()
        current_time = int(time.time())
        
        # 创建已到期的提醒
        due_reminder = {
            "user_id": test_user["_id"],
            "reminder_id": str(uuid.uuid4()),
            "title": "已到期提醒",
            "action_template": "记得已到期提醒",
            "next_trigger_time": current_time-60,  # 1分钟前
            "time_original": "1分钟前",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        reminder_dao.create_reminder(due_reminder)
        
        # 创建未到期的提醒
        future_reminder = {
            "user_id": test_user["_id"],
            "reminder_id": str(uuid.uuid4()),
            "title": "未到期提醒",
            "action_template": "记得未到期提醒",
            "next_trigger_time": current_time + 3600,  # 1小时后
            "time_original": "1小时后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        reminder_dao.create_reminder(future_reminder)
        
        # 查找到期的提醒
        due_reminders = reminder_dao.find_pending_reminders(current_time, time_window=120)
        
        # 验证只找到已到期的提醒
        due_ids = [r["reminder_id"] for r in due_reminders]
        assert due_reminder["reminder_id"] in due_ids
        assert future_reminder["reminder_id"] not in due_ids
        
        logger.info(f"✓ 找到 {len(due_reminders)} 个到期提醒")
        
        # 清理
        reminder_dao.delete_reminder(due_reminder["reminder_id"])
        reminder_dao.delete_reminder(future_reminder["reminder_id"])
        reminder_dao.close()
    
    def test_trigger_reminder_message(self, mongo_client, test_user, test_character, test_conversation):
        """测试触发提醒消息"""
        reminder_dao = ReminderDAO()
        current_time = int(time.time())
        
        # 创建到期的提醒
        reminder_id = str(uuid.uuid4())
        reminder_data = {
            "user_id": test_user["_id"],
            "character_id": test_character["_id"],
            "conversation_id": test_conversation,
            "reminder_id": reminder_id,
            "title": "测试提醒",
            "action_template": "记得测试提醒",
            "next_trigger_time": current_time-60,
            "time_original": "1分钟前",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        reminder_dao.create_reminder(reminder_data)
        
        # 模拟触发提醒
        # 1. 标记为已触发
        success = reminder_dao.mark_as_triggered(reminder_id)
        assert success
        logger.info("✓ 标记提醒为已触发")
        
        # 2. 创建提醒消息到输出队列
        output_message = {
            "_id": str(uuid.uuid4()),
            "conversation_id": test_conversation,
            "uid": test_user["_id"],
            "cid": test_character["_id"],
            "type": "text",
            "content": f"提醒：{reminder_data['title']}",
            "timestamp": current_time,
            "source": "reminder",
        }
        mongo_client.insert_one("outputmessages", output_message)
        logger.info("✓ 创建提醒消息到输出队列")
        
        # 验证提醒状态
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder["status"] == "triggered"
        assert reminder["triggered_count"] == 1
        
        # 验证输出消息
        output_msg = mongo_client.find_one("outputmessages", {"_id": output_message["_id"]})
        assert output_msg is not None
        assert output_msg["source"] == "reminder"
        
        # 清理
        mongo_client.delete_one("outputmessages", {"_id": output_message["_id"]})
        reminder_dao.delete_reminder(reminder_id)
        reminder_dao.close()
    
    def test_trigger_proactive_message(self, mongo_client, test_user, test_character, test_conversation):
        """测试触发主动消息"""
        conv_dao = ConversationDAO()
        current_time = int(time.time())
        
        # 设置会话的 future 信息（主动消息计划）
        conversation = conv_dao.get_conversation_by_id(test_conversation)
        conversation["conversation_info"]["future"] = {
            "timestamp": current_time-60,  # 1分钟前到期
            "action": "询问用户今天的学习进度",
            "proactive_times": 0,
            "status": "pending"
        }
        conv_dao.update_conversation_info(
            test_conversation,
            conversation["conversation_info"]
        )
        logger.info("✓ 设置主动消息计划")
        
        # 使用 ProactiveMessageTriggerService 检查并触发
        service = ProactiveMessageTriggerService()
        
        # 查找到期的会话
        due_conversations = service._get_due_conversations()
        
        # 验证找到了到期的会话
        due_conv_ids = [str(c.get("_id", "")) for c in due_conversations]
        assert test_conversation in due_conv_ids
        logger.info(f"✓ 找到 {len(due_conversations)} 个到期的主动消息会话")
        
        # 清理
        conversation["conversation_info"]["future"] = {
            "timestamp": None,
            "action": None,
            "proactive_times": 0,
            "status": "pending"
        }
        conv_dao.update_conversation_info(
            test_conversation,
            conversation["conversation_info"]
        )
    
    def test_recurring_reminder_reschedule(self, mongo_client, test_user):
        """测试周期性提醒的重新安排"""
        reminder_dao = ReminderDAO()
        current_time = int(time.time())
        reminder_id = str(uuid.uuid4())
        
        # 创建每日提醒
        reminder_data = {
            "user_id": test_user["_id"],
            "reminder_id": reminder_id,
            "title": "每日提醒",
            "action_template": "记得每日提醒",
            "next_trigger_time": current_time-60,  # 已到期
            "time_original": "每天9点",
            "timezone": "Asia/Shanghai",
            "recurrence": {
                "enabled": True,
                "type": "daily",
                "interval": 1,
                "max_count": 10
            },
            "status": "confirmed",
            "triggered_count": 0,
        }
        reminder_dao.create_reminder(reminder_data)
        
        # 模拟触发流程
        # 1. 标记为已触发
        reminder_dao.mark_as_triggered(reminder_id)
        
        # 2. 计算下次触发时间（24小时后）
        next_time = current_time + 86400
        
        # 3. 重新安排提醒
        success = reminder_dao.reschedule_reminder(reminder_id, next_time)
        assert success
        logger.info("✓ 重新安排周期性提醒")
        
        # 验证提醒已重新安排
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder["next_trigger_time"] == next_time
        assert reminder["status"] == "confirmed"  # 状态重置为 confirmed
        assert reminder["triggered_count"] == 1
        
        # 清理
        reminder_dao.delete_reminder(reminder_id)
        reminder_dao.close()
    
    def test_cleanup_completed_reminders(self, mongo_client, test_user):
        """测试清理已完成的提醒"""
        reminder_dao = ReminderDAO()
        current_time = int(time.time())
        
        # 创建已完成的提醒
        completed_reminder = {
            "user_id": test_user["_id"],
            "reminder_id": str(uuid.uuid4()),
            "title": "已完成提醒",
            "action_template": "记得已完成提醒",
            "next_trigger_time": current_time-3600,
            "time_original": "1小时前",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "completed",
        }
        reminder_dao.create_reminder(completed_reminder)
        
        # 创建有效提醒
        active_reminder = {
            "user_id": test_user["_id"],
            "reminder_id": str(uuid.uuid4()),
            "title": "有效提醒",
            "action_template": "记得有效提醒",
            "next_trigger_time": current_time + 3600,
            "time_original": "1小时后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        reminder_dao.create_reminder(active_reminder)
        
        # 查询所有提醒
        all_reminders = reminder_dao.find_reminders_by_user(test_user["_id"])
        assert len(all_reminders) == 2
        
        # 清理已完成的提醒（模拟后台任务）
        # 在真实场景中，这会是一个定时任务
        reminder_dao.delete_reminder(completed_reminder["reminder_id"])
        logger.info("✓ 清理已完成的提醒")
        
        # 验证只剩下有效提醒
        remaining = reminder_dao.find_reminders_by_user(
            test_user["_id"],
            status_list=["confirmed", "pending"]
        )
        assert len(remaining) == 1
        assert remaining[0]["reminder_id"] == active_reminder["reminder_id"]
        
        # 清理
        reminder_dao.delete_reminder(active_reminder["reminder_id"])
        reminder_dao.close()
    
    def test_proactive_message_limit(self, mongo_client, test_user, test_character, test_conversation):
        """测试主动消息次数限制"""
        conv_dao = ConversationDAO()
        current_time = int(time.time())
        
        # 设置已达到上限的主动消息
        conversation = conv_dao.get_conversation_by_id(test_conversation)
        conversation["conversation_info"]["future"] = {
            "timestamp": current_time-60,
            "action": "询问用户",
            "proactive_times": 2,  # 已达到上限
            "status": "pending"
        }
        conv_dao.update_conversation_info(
            test_conversation,
            conversation["conversation_info"]
        )
        
        # 使用 ProactiveMessageTriggerService 检查
        service = ProactiveMessageTriggerService()
        due_conversations = service._get_due_conversations()
        
        # 验证不会触发（因为已达到次数上限）
        due_conv_ids = [str(c.get("_id", "")) for c in due_conversations]
        assert test_conversation not in due_conv_ids
        logger.info("✓ 主动消息次数限制生效")
        
        # 清理
        conversation["conversation_info"]["future"] = {
            "timestamp": None,
            "action": None,
            "proactive_times": 0,
            "status": "pending"
        }
        conv_dao.update_conversation_info(
            test_conversation,
            conversation["conversation_info"]
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
