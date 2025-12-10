#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中的提醒数据

用法：
python check_reminders.py
"""

import sys
sys.path.append(".")

import logging
from dao.reminder_dao import ReminderDAO
from dao.mongo import MongoDBBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_reminders():
    """检查提醒数据"""
    
    # 获取用户
    mongo = MongoDBBase()
    admin_user_name = "不辣的皮皮"
    users = mongo.find_many("users", {"platforms.wechat.nickname": admin_user_name})
    
    if not users:
        logger.error(f"未找到用户: {admin_user_name}")
        return
    
    user = users[0]
    user_id = str(user["_id"])
    logger.info(f"用户: {user.get('name')} (ID: {user_id})")
    
    # 查询提醒
    reminder_dao = ReminderDAO()
    
    # 查询所有提醒
    all_reminders = reminder_dao.find_reminders_by_user(user_id)
    logger.info(f"\n总提醒数: {len(all_reminders)}")
    
    # 按状态统计
    status_count = {}
    for reminder in all_reminders:
        status = reminder.get("status", "unknown")
        status_count[status] = status_count.get(status, 0) + 1
    
    logger.info(f"\n按状态统计:")
    for status, count in status_count.items():
        logger.info(f"  {status}: {count}")
    
    # 查询 confirmed 状态的提醒
    confirmed_reminders = reminder_dao.find_reminders_by_user(user_id, status="confirmed")
    logger.info(f"\nconfirmed 状态提醒数: {len(confirmed_reminders)}")
    
    # 显示前 10 个 confirmed 提醒
    logger.info(f"\n前 10 个 confirmed 提醒:")
    for i, reminder in enumerate(confirmed_reminders[:10]):
        logger.info(f"  {i+1}. {reminder.get('title')} - {reminder.get('trigger_time')} - {reminder.get('reminder_id')}")
    
    # 检查是否有重复的提醒
    title_count = {}
    for reminder in confirmed_reminders:
        title = reminder.get("title", "")
        title_count[title] = title_count.get(title, 0) + 1
    
    logger.info(f"\n重复的提醒标题:")
    for title, count in sorted(title_count.items(), key=lambda x: x[1], reverse=True):
        if count > 1:
            logger.info(f"  {title}: {count} 次")
    
    reminder_dao.close()

if __name__ == "__main__":
    check_reminders()
