#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查找重复提醒的脚本

此脚本用于查找具有相同用户ID和触发时间的提醒，但不会删除它们.
重复定义：同一用户、触发时间相差在5分钟内的提醒（内容不重要）.

使用方法：
    python scripts/find_duplicate_reminders.py
"""
import sys
sys.path.append(".")

from collections import defaultdict
from datetime import datetime
from dao.reminder_dao import ReminderDAO
from util.time_util import format_time_friendly


def format_time(timestamp):
    """格式化时间显示"""
    if not timestamp:
        return "未设置"
    
    try:
        friendly = format_time_friendly(timestamp)
        dt = datetime.fromtimestamp(timestamp)
        exact = dt.strftime("%Y-%m-%d %H:%M")
        return f"{friendly} ({exact})"
    except:
        return str(timestamp)


def find_duplicate_reminders():
    """查找重复的提醒"""
    dao = ReminderDAO()
    
    try:
        # 获取所有提醒
        reminders = list(dao.collection.find({}))
        
        if not reminders:
            print("没有找到任何提醒")
            return
        
        # 按用户ID分组
        user_reminders = defaultdict(list)
        for reminder in reminders:
            user_id = reminder.get("user_id")
            if user_id:
                user_reminders[user_id].append(reminder)
        
        # 查找每个用户的重复提醒
        duplicates = []
        for user_id, user_reminder_list in user_reminders.items():
            # 仅按时间分组（忽略标题）
            reminder_groups = defaultdict(list)
            
            for reminder in user_reminder_list:
                trigger_time = reminder.get("next_trigger_time", 0)
                status = reminder.get("status", "")
                
                # 将时间四舍五入到5分钟以内，用于分组
                time_key = round(trigger_time / 300) * 300 if trigger_time else 0
                
                # 仅使用时间作为键（忽略标题）
                key = time_key
                reminder_groups[key].append(reminder)
            
            # 查找有多个提醒的组
            for time_key, group in reminder_groups.items():
                if len(group) > 1:
                    # 进一步验证是否真的在5分钟内
                    times = [r.get("next_trigger_time", 0) for r in group]
                    min_time = min(times)
                    max_time = max(times)
                    
                    # 如果最大时间差超过5分钟，则不是重复提醒
                    if max_time - min_time <= 300:  # 5分钟 = 300秒
                        duplicates.append((user_id, time_key, group))        
        # 显示结果
        if not duplicates:
            print("没有找到重复的提醒")
            return
        
        print(f"找到 {len(duplicates)} 组重复提醒:\n")
        
        for i, (user_id, time_key, group) in enumerate(duplicates, 1):
            print(f"[{i}] 用户: {user_id}")
            print(f"    时间: {format_time(time_key)}")
            print(f"    数量: {len(group)} 个重复提醒")
            print("    详细信息:")
            
            for j, reminder in enumerate(group, 1):
                reminder_id = reminder.get("reminder_id", "N/A")
                title = reminder.get("title", "无标题")
                status = reminder.get("status", "unknown")
                trigger_time = reminder.get("next_trigger_time", 0)
                recurrence = reminder.get("recurrence", {})
                
                recurrence_str = "单次" if not recurrence or not recurrence.get("enabled") else recurrence.get("type", "周期")
                
                print(f"      [{j}] ID: {reminder_id}")
                print(f"          标题: {title}")
                print(f"          状态: {status}")
                print(f"          类型: {recurrence_str}")
                print(f"          时间: {format_time(trigger_time)}")
            
            print("-" * 60)            
        print(f"\n总共找到 {len(duplicates)} 组重复提醒")
        
    finally:
        dao.close()


def main():
    print("=" * 60)
    print("         查找重复提醒工具")
    print("=" * 60)
    print("此工具将查找具有相同用户ID和相似触发时间的提醒")
    print("重复定义：同一用户、触发时间相差在5分钟内（内容不重要）")
    print("注意：此脚本仅用于查找，不会删除任何提醒\n")
    
    find_duplicate_reminders()

if __name__ == "__main__":
    main()