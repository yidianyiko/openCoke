#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试提醒重复触发问题的修复

验证：
1. 提醒触发后状态正确更新为 "triggered"
2. 非周期提醒触发后状态更新为 "completed"
3. 周期提醒触发后状态更新为 "confirmed" 并设置下次触发时间
4. find_pending_reminders 不会查询到已触发的提醒
"""

import sys
sys.path.append(".")

import time
import logging
from dao.reminder_dao import ReminderDAO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_non_recurring_reminder():
    """测试非周期提醒的状态变化"""
    logger.info("=" * 60)
    logger.info("测试1: 非周期提醒状态变化")
    logger.info("=" * 60)
    
    dao = ReminderDAO()
    
    # 创建测试提醒
    now = int(time.time())
    test_reminder = {
        "user_id": "test_user_001",
        "character_id": "test_char_001",
        "conversation_id": "test_conv_001",
        "title": "测试非周期提醒",
        "action_template": "提醒：测试非周期提醒",
        "next_trigger_time": now - 10,  # 10秒前应该触发
        "time_original": "10秒前",
        "timezone": "Asia/Shanghai",
        "recurrence": {
            "enabled": False
        },
        "status": "confirmed"
    }
    
    reminder_id = dao.create_reminder(test_reminder)
    logger.info(f"✓ 创建提醒: {reminder_id}")
    
    # 查询待触发的提醒
    pending = dao.find_pending_reminders(now)
    logger.info(f"✓ 查询到 {len(pending)} 个待触发提醒")
    assert len(pending) >= 1, "应该能查询到刚创建的提醒"
    
    # 获取提醒详情
    reminder = dao.get_reminder_by_id(test_reminder["reminder_id"])
    logger.info(f"  状态: {reminder['status']}")
    assert reminder['status'] == 'confirmed', "初始状态应该是 confirmed"
    
    # 模拟触发：标记为已触发
    dao.mark_as_triggered(test_reminder["reminder_id"])
    logger.info("✓ 调用 mark_as_triggered()")
    
    # 检查状态
    reminder = dao.get_reminder_by_id(test_reminder["reminder_id"])
    logger.info(f"  状态: {reminder['status']}")
    assert reminder['status'] == 'triggered', "触发后状态应该是 triggered"
    
    # 再次查询待触发的提醒
    pending = dao.find_pending_reminders(now)
    has_this_reminder = any(r['reminder_id'] == test_reminder["reminder_id"] for r in pending)
    logger.info(f"✓ 再次查询待触发提醒: {len(pending)} 个")
    assert not has_this_reminder, "已触发的提醒不应该再被查询到"
    
    # 标记为完成
    dao.complete_reminder(test_reminder["reminder_id"])
    logger.info("✓ 调用 complete_reminder()")
    
    # 检查最终状态
    reminder = dao.get_reminder_by_id(test_reminder["reminder_id"])
    logger.info(f"  最终状态: {reminder['status']}")
    assert reminder['status'] == 'completed', "最终状态应该是 completed"
    
    # 清理
    dao.delete_reminder(test_reminder["reminder_id"])
    dao.close()
    
    logger.info("✅ 测试1通过：非周期提醒状态变化正确\n")


def test_recurring_reminder():
    """测试周期提醒的状态变化"""
    logger.info("=" * 60)
    logger.info("测试2: 周期提醒状态变化")
    logger.info("=" * 60)
    
    dao = ReminderDAO()
    
    # 创建测试周期提醒
    now = int(time.time())
    test_reminder = {
        "user_id": "test_user_002",
        "character_id": "test_char_002",
        "conversation_id": "test_conv_002",
        "title": "测试周期提醒",
        "action_template": "提醒：测试周期提醒",
        "next_trigger_time": now - 10,
        "time_original": "每天",
        "timezone": "Asia/Shanghai",
        "recurrence": {
            "enabled": True,
            "type": "daily",
            "interval": 1
        },
        "status": "confirmed"
    }
    
    reminder_id = dao.create_reminder(test_reminder)
    logger.info(f"✓ 创建周期提醒: {reminder_id}")
    
    # 查询待触发的提醒
    pending = dao.find_pending_reminders(now)
    logger.info(f"✓ 查询到 {len(pending)} 个待触发提醒")
    
    # 模拟触发
    dao.mark_as_triggered(test_reminder["reminder_id"])
    logger.info("✓ 调用 mark_as_triggered()")
    
    # 检查状态
    reminder = dao.get_reminder_by_id(test_reminder["reminder_id"])
    logger.info(f"  状态: {reminder['status']}")
    assert reminder['status'] == 'triggered', "触发后状态应该是 triggered"
    
    # 模拟重新调度
    next_time = now + 86400  # 明天
    dao.reschedule_reminder(test_reminder["reminder_id"], next_time)
    logger.info(f"✓ 调用 reschedule_reminder(next_time={next_time})")
    
    # 检查状态和下次触发时间
    reminder = dao.get_reminder_by_id(test_reminder["reminder_id"])
    logger.info(f"  状态: {reminder['status']}")
    logger.info(f"  下次触发时间: {reminder['next_trigger_time']}")
    assert reminder['status'] == 'confirmed', "重新调度后状态应该是 confirmed"
    assert reminder['next_trigger_time'] == next_time, "下次触发时间应该更新"
    
    # 确认不会被当前时间查询到
    pending = dao.find_pending_reminders(now)
    has_this_reminder = any(r['reminder_id'] == test_reminder["reminder_id"] for r in pending)
    logger.info(f"✓ 查询当前待触发提醒: {len(pending)} 个")
    assert not has_this_reminder, "重新调度的提醒不应该被当前时间查询到"
    
    # 清理
    dao.delete_reminder(test_reminder["reminder_id"])
    dao.close()
    
    logger.info("✅ 测试2通过：周期提醒状态变化正确\n")


def test_time_window():
    """测试时间窗口防止重复触发"""
    logger.info("=" * 60)
    logger.info("测试3: 时间窗口防止重复触发")
    logger.info("=" * 60)
    
    dao = ReminderDAO()
    
    # 创建多个不同时间的提醒
    now = int(time.time())
    test_reminders = []
    
    for i, offset in enumerate([5, 30, 90, 120]):  # 5秒、30秒、90秒、120秒前
        reminder = {
            "user_id": f"test_user_{i}",
            "character_id": "test_char",
            "conversation_id": f"test_conv_{i}",
            "title": f"测试提醒{i}",
            "action_template": f"提醒：测试提醒{i}",
            "next_trigger_time": now - offset,
            "time_original": f"{offset}秒前",
            "timezone": "Asia/Shanghai",
            "recurrence": {"enabled": False},
            "status": "confirmed"
        }
        dao.create_reminder(reminder)
        test_reminders.append(reminder)
        logger.info(f"✓ 创建提醒{i}: 触发时间为 {offset}秒前")
    
    # 使用默认60秒时间窗口查询
    pending = dao.find_pending_reminders(now, time_window=60)
    logger.info(f"✓ 60秒时间窗口查询到 {len(pending)} 个提醒")
    
    # 应该只查询到5秒和30秒前的提醒
    pending_ids = [r['reminder_id'] for r in pending]
    assert test_reminders[0]['reminder_id'] in pending_ids, "5秒前的应该被查询到"
    assert test_reminders[1]['reminder_id'] in pending_ids, "30秒前的应该被查询到"
    assert test_reminders[2]['reminder_id'] not in pending_ids, "90秒前的不应该被查询到"
    assert test_reminders[3]['reminder_id'] not in pending_ids, "120秒前的不应该被查询到"
    
    logger.info("  ✓ 5秒前的提醒: 被查询到")
    logger.info("  ✓ 30秒前的提醒: 被查询到")
    logger.info("  ✓ 90秒前的提醒: 未被查询到（超出窗口）")
    logger.info("  ✓ 120秒前的提醒: 未被查询到（超出窗口）")
    
    # 清理
    for reminder in test_reminders:
        dao.delete_reminder(reminder["reminder_id"])
    dao.close()
    
    logger.info("✅ 测试3通过：时间窗口正确限制查询范围\n")


if __name__ == "__main__":
    try:
        test_non_recurring_reminder()
        test_recurring_reminder()
        test_time_window()
        
        logger.info("=" * 60)
        logger.info("🎉 所有测试通过！提醒重复触发问题已修复")
        logger.info("=" * 60)
        
    except AssertionError as e:
        logger.error(f"❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
