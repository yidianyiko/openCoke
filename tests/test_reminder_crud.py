# -*- coding: utf-8 -*-
"""
提醒 CRUD 操作测试

测试提醒的完整生命周期：创建、查询、修改、删除

Requirements:
- 批量创建提醒
- 查询提醒列表
- 删除提醒
- 修改提醒
"""

import logging
import time
import uuid

import pytest

from dao.reminder_dao import ReminderDAO

logger = logging.getLogger(__name__)


@pytest.fixture
def reminder_dao(mongo_client):
    """提供 ReminderDAO 实例"""
    dao = ReminderDAO()
    dao.create_indexes()
    yield dao
    dao.close()


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return f"test_user_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_reminders(reminder_dao, test_user_id):
    """测试后清理提醒"""
    yield
    # 清理所有测试提醒
    reminder_dao.delete_all_by_user(test_user_id)


class TestReminderCRUD:
    """提醒 CRUD 操作测试"""
    
    def test_create_single_reminder(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试创建单个提醒"""
        current_time = int(time.time())
        
        reminder_data = {
            "user_id": test_user_id,
            "reminder_id": str(uuid.uuid4()),
            "title": "测试提醒",
            "action_template": "记得测试提醒",
            "next_trigger_time": current_time + 3600,
            "time_original": "1小时后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        
        # 创建提醒
        inserted_id = reminder_dao.create_reminder(reminder_data)
        assert inserted_id is not None
        logger.info(f"✓ 创建提醒成功: {inserted_id}")
        
        # 验证提醒已创建
        reminder = reminder_dao.get_reminder_by_id(reminder_data["reminder_id"])
        assert reminder is not None
        assert reminder["title"] == "测试提醒"
        assert reminder["user_id"] == test_user_id
        assert reminder["status"] == "confirmed"
    
    def test_batch_create_reminders(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试批量创建提醒"""
        current_time = int(time.time())
        
        reminders = []
        for i in range(5):
            reminder_data = {
                "user_id": test_user_id,
                "reminder_id": str(uuid.uuid4()),
                "title": f"批量提醒{i+1}",
                "action_template": f"记得批量提醒{i+1}",
                "next_trigger_time": current_time + (i + 1) * 3600,
                "time_original": f"{i+1}小时后",
                "timezone": "Asia/Shanghai",
                "recurrence": {"enabled": False},
                "status": "confirmed",
            }
            reminders.append(reminder_data)
        
        # 批量创建
        created_ids = []
        for reminder in reminders:
            inserted_id = reminder_dao.create_reminder(reminder)
            created_ids.append(inserted_id)
        
        assert len(created_ids) == 5
        logger.info(f"✓ 批量创建 {len(created_ids)} 个提醒成功")
        
        # 验证所有提醒已创建
        user_reminders = reminder_dao.find_reminders_by_user(
            test_user_id,
            status_list=["confirmed", "pending"]
        )
        assert len(user_reminders) == 5
    
    def test_list_reminders(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试查询提醒列表"""
        current_time = int(time.time())
        
        # 创建多个不同状态的提醒
        statuses = ["confirmed", "pending", "triggered", "completed"]
        for i, status in enumerate(statuses):
            reminder_data = {
                "user_id": test_user_id,
                "reminder_id": str(uuid.uuid4()),
                "title": f"提醒{i+1}",
                "action_template": f"记得提醒{i+1}",
                "next_trigger_time": current_time + (i + 1) * 3600,
                "time_original": f"{i+1}小时后",
                "timezone": "Asia/Shanghai",
                "recurrence": {"enabled": False},
                "status": status,
            }
            reminder_dao.create_reminder(reminder_data)
        
        # 查询有效提醒（confirmed + pending）
        active_reminders = reminder_dao.find_reminders_by_user(
            test_user_id,
            status_list=["confirmed", "pending"]
        )
        assert len(active_reminders) == 2
        logger.info(f"✓ 查询到 {len(active_reminders)} 个有效提醒")
        
        # 查询所有提醒
        all_reminders = reminder_dao.find_reminders_by_user(test_user_id)
        assert len(all_reminders) == 4
        logger.info(f"✓ 查询到 {len(all_reminders)} 个所有状态提醒")
        
        # 查询特定状态
        triggered_reminders = reminder_dao.find_reminders_by_user(
            test_user_id,
            status="triggered"
        )
        assert len(triggered_reminders) == 1
        assert triggered_reminders[0]["status"] == "triggered"
    
    def test_update_reminder(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试修改提醒"""
        current_time = int(time.time())
        reminder_id = str(uuid.uuid4())
        
        # 创建提醒
        reminder_data = {
            "user_id": test_user_id,
            "reminder_id": reminder_id,
            "title": "原始标题",
            "action_template": "原始模板",
            "next_trigger_time": current_time + 3600,
            "time_original": "1小时后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        reminder_dao.create_reminder(reminder_data)
        
        # 修改标题
        success = reminder_dao.update_reminder(reminder_id, {"title": "新标题"})
        assert success
        logger.info("✓ 修改标题成功")
        
        # 验证修改
        updated = reminder_dao.get_reminder_by_id(reminder_id)
        assert updated["title"] == "新标题"
        
        # 修改时间
        new_time = current_time + 7200
        success = reminder_dao.update_reminder(
            reminder_id,
            {
                "next_trigger_time": new_time,
                "time_original": "2小时后"
            }
        )
        assert success
        logger.info("✓ 修改时间成功")
        
        # 验证修改
        updated = reminder_dao.get_reminder_by_id(reminder_id)
        assert updated["next_trigger_time"] == new_time
        assert updated["time_original"] == "2小时后"
    
    def test_delete_single_reminder(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试删除单个提醒"""
        reminder_id = str(uuid.uuid4())
        
        # 创建提醒
        reminder_data = {
            "user_id": test_user_id,
            "reminder_id": reminder_id,
            "title": "待删除提醒",
            "action_template": "记得待删除提醒",
            "next_trigger_time": int(time.time()) + 3600,
            "time_original": "1小时后",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        reminder_dao.create_reminder(reminder_data)
        
        # 验证提醒存在
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder is not None
        
        # 删除提醒
        success = reminder_dao.delete_reminder(reminder_id)
        assert success
        logger.info("✓ 删除提醒成功")
        
        # 验证提醒已删除
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder is None
    
    def test_delete_all_reminders(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试删除所有提醒"""
        current_time = int(time.time())
        
        # 创建多个提醒
        for i in range(3):
            reminder_data = {
                "user_id": test_user_id,
                "reminder_id": str(uuid.uuid4()),
                "title": f"提醒{i+1}",
                "action_template": f"记得提醒{i+1}",
                "next_trigger_time": current_time + (i + 1) * 3600,
                "time_original": f"{i+1}小时后",
                "timezone": "Asia/Shanghai",
                "recurrence": {"enabled": False},
                "status": "confirmed",
            }
            reminder_dao.create_reminder(reminder_data)
        
        # 验证提醒已创建
        reminders = reminder_dao.find_reminders_by_user(
            test_user_id,
            status_list=["confirmed", "pending"]
        )
        assert len(reminders) == 3
        
        # 删除所有提醒
        deleted_count = reminder_dao.delete_all_by_user(test_user_id)
        assert deleted_count == 3
        logger.info(f"✓ 删除所有提醒成功: {deleted_count} 个")
        
        # 验证提醒已删除
        reminders = reminder_dao.find_reminders_by_user(
            test_user_id,
            status_list=["confirmed", "pending"]
        )
        assert len(reminders) == 0
    
    def test_recurring_reminder(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试周期性提醒"""
        current_time = int(time.time())
        reminder_id = str(uuid.uuid4())
        
        # 创建每日提醒
        reminder_data = {
            "user_id": test_user_id,
            "reminder_id": reminder_id,
            "title": "每日提醒",
            "action_template": "记得每日提醒",
            "next_trigger_time": current_time + 3600,
            "time_original": "每天9点",
            "timezone": "Asia/Shanghai",
            "recurrence": {
                "enabled": True,
                "type": "daily",
                "interval": 1,
                "max_count": 10
            },
            "status": "confirmed",
        }
        reminder_dao.create_reminder(reminder_data)
        
        # 验证周期性配置
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder["recurrence"]["enabled"] is True
        assert reminder["recurrence"]["type"] == "daily"
        assert reminder["recurrence"]["max_count"] == 10
        logger.info("✓ 创建周期性提醒成功")
        
        # 模拟触发后重新安排
        next_time = current_time + 86400  # 24小时后
        success = reminder_dao.reschedule_reminder(reminder_id, next_time)
        assert success
        logger.info("✓ 重新安排提醒成功")
        
        # 验证时间已更新
        reminder = reminder_dao.get_reminder_by_id(reminder_id)
        assert reminder["next_trigger_time"] == next_time
        assert reminder["status"] == "confirmed"
    
    def test_find_pending_reminders(self, reminder_dao, test_user_id, cleanup_reminders):
        """测试查找待触发的提醒"""
        current_time = int(time.time())
        
        # 创建已到期的提醒
        past_reminder = {
            "user_id": test_user_id,
            "reminder_id": str(uuid.uuid4()),
            "title": "已到期提醒",
            "action_template": "记得已到期提醒",
            "next_trigger_time": current_time-60,  # 1分钟前
            "time_original": "1分钟前",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed",
        }
        reminder_dao.create_reminder(past_reminder)
        
        # 创建未到期的提醒
        future_reminder = {
            "user_id": test_user_id,
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
        
        # 查找待触发的提醒
        pending = reminder_dao.find_pending_reminders(current_time, time_window=120)
        
        # 应该只找到已到期的提醒
        pending_ids = [r["reminder_id"] for r in pending]
        assert past_reminder["reminder_id"] in pending_ids
        assert future_reminder["reminder_id"] not in pending_ids
        logger.info(f"✓ 找到 {len(pending)} 个待触发提醒")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
