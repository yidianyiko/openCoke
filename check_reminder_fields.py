#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查提醒的字段

用法：
python check_reminder_fields.py
"""

import sys
sys.path.append(".")

import logging
from dao.reminder_dao import ReminderDAO
from dao.mongo import MongoDBBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_reminder_fields():
    """检查提醒字段"""
    
    # 获取用户
    mongo = MongoDBBase()
    admin_user_name = "不辣的皮皮"
    users = mongo.find_many("users", {"platforms.wechat.nickname": admin_user_name})
    
    if not users:
        logger.error(f"未找到用户: {admin_user_name}")
        return
    
    user = users[0]
    user_id = str(user["_id"])
    
    # 查询提醒
    reminder_dao = ReminderDAO()
    confirmed_reminders = reminder_dao.find_reminders_by_user(user_id, status="confirmed")
    
    if not confirmed_reminders:
        logger.error("没有找到 confirmed 提醒")
        return
    
    # 查看第一个提醒的所有字段
    first_reminder = confirmed_reminders[0]
    logger.info(f"\n第一个提醒的所有字段:")
    for key, value in first_reminder.items():
        logger.info(f"  {key}: {value}")
    
    # 统计字段出现情况
    logger.info(f"\n字段统计 (共 {len(confirmed_reminders)} 个提醒):")
    field_count = {}
    for reminder in confirmed_reminders:
        for key in reminder.keys():
            field_count[key] = field_count.get(key, 0) + 1
    
    for key, count in sorted(field_count.items()):
        logger.info(f"  {key}: {count}/{len(confirmed_reminders)}")
    
    # 检查 trigger_time 和 next_trigger_time
    logger.info(f"\n检查时间字段:")
    has_trigger_time = 0
    has_next_trigger_time = 0
    trigger_time_none = 0
    next_trigger_time_none = 0
    
    for reminder in confirmed_reminders:
        if "trigger_time" in reminder:
            has_trigger_time += 1
            if reminder["trigger_time"] is None:
                trigger_time_none += 1
        
        if "next_trigger_time" in reminder:
            has_next_trigger_time += 1
            if reminder["next_trigger_time"] is None:
                next_trigger_time_none += 1
    
    logger.info(f"  有 trigger_time 字段: {has_trigger_time}/{len(confirmed_reminders)}")
    logger.info(f"  trigger_time 为 None: {trigger_time_none}/{has_trigger_time}")
    logger.info(f"  有 next_trigger_time 字段: {has_next_trigger_time}/{len(confirmed_reminders)}")
    logger.info(f"  next_trigger_time 为 None: {next_trigger_time_none}/{has_next_trigger_time}")
    
    reminder_dao.close()

if __name__ == "__main__":
    check_reminder_fields()
