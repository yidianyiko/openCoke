#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理过期提醒的脚本

此脚本用于删除已经过了提醒时间但状态仍然是待提醒（confirmed或pending）的提醒任务。

使用方法：
    python scripts/cleanup_expired_reminders.py
"""

import sys
sys.path.append(".")

from datetime import datetime
from dao.reminder_dao import ReminderDAO


def cleanup_expired_reminders(dry_run=True):
    """清理过期的提醒"""
    dao = ReminderDAO()
    
    try:
        # 获取所有待提醒状态的提醒（confirmed 或 pending）
        query = {"status": {"$in": ["confirmed", "pending"]}}
        reminders = list(dao.collection.find(query))
        
        if not reminders:
            print("没有找到待提醒状态的提醒")
            return 0
        
        current_time = int(datetime.now().timestamp())
        expired_reminders = []
        
        # 查找已过期的提醒
        for reminder in reminders:
            trigger_time = reminder.get("next_trigger_time", 0)
            if trigger_time < current_time:
                expired_reminders.append(reminder)
        
        if not expired_reminders:
            print("没有找到过期的提醒")
            return 0
        
        print(f"{'[预览模式] ' if dry_run else ''}找到 {len(expired_reminders)} 个过期的提醒:")
        print("-" * 80)
        
        for i, reminder in enumerate(expired_reminders, 1):
            reminder_id = reminder.get("reminder_id", "N/A")
            user_id = reminder.get("user_id", "N/A")
            title = reminder.get("title", "无标题")
            status = reminder.get("status", "unknown")
            trigger_time = reminder.get("next_trigger_time", 0)
            
            # 格式化时间显示
            try:
                from util.time_util import format_time_friendly
                time_str = format_time_friendly(trigger_time)
                dt = datetime.fromtimestamp(trigger_time)
                exact_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                time_str = str(trigger_time)
                exact_time = str(trigger_time)
            
            print(f"[{i}] ID: {reminder_id}")
            print(f"    用户: {user_id}")
            print(f"    标题: {title}")
            print(f"    状态: {status}")
            print(f"    触发时间: {time_str} ({exact_time})")
            print(f"    已过期: {current_time - trigger_time} 秒")
            print()
        
        if dry_run:
            print(f"\n预览模式：将删除 {len(expired_reminders)} 个过期的提醒")
            print("如需执行删除，请运行: python scripts/cleanup_expired_reminders.py --execute")
        else:
            # 执行删除操作
            deleted_count = 0
            for reminder in expired_reminders:
                reminder_id = reminder.get("reminder_id")
                if dao.delete_reminder(reminder_id):
                    deleted_count += 1
                else:
                    print(f"删除失败: {reminder_id}")
            
            print(f"成功删除 {deleted_count} 个过期的提醒")
        
        return len(expired_reminders) if not dry_run else 0
        
    finally:
        dao.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="清理过期提醒")
    parser.add_argument("--execute", action="store_true", help="执行删除操作（默认为预览模式）")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("                   清理过期提醒工具")
    print("=" * 80)
    print("此工具将删除已经过了提醒时间但状态仍然是待提醒的提醒任务")
    print("注意：此脚本只处理状态为 confirmed 或 pending 的提醒")
    print()
    
    cleanup_expired_reminders(dry_run=not args.execute)


if __name__ == "__main__":
    main()