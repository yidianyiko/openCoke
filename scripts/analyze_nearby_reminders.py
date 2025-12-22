#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析附近时间提醒的脚本

此脚本用于分析将来会被触发的提醒，查找时间非常接近的提醒（30秒内），
以确定是否还需要合并。

使用方法：
    python scripts/analyze_nearby_reminders.py
"""

import sys
sys.path.append(".")

from collections import defaultdict
from datetime import datetime
import re
from dao.reminder_dao import ReminderDAO
from util.time_util import format_time_friendly


def format_time(timestamp):
    """格式化时间显示"""
    if not timestamp:
        return "未设置"
    
    try:
        friendly = format_time_friendly(timestamp)
        dt = datetime.fromtimestamp(timestamp)
        exact = dt.strftime("%Y-%m-%d %H:%M:%S")
        return f"{friendly} ({exact})"
    except:
        return str(timestamp)


def extract_keywords(title):
    """从标题中提取关键词"""
    # 移除常见的停用词和标点符号
    stop_words = {'的', '了', '在', '是', '我', '你', '他', '她', '它', '们', '这', '那', '个', '些', '和', '与', '或', '但是', '然而', '因此', '所以', '然后', '接着', '最后'}
    
    # 简单的分词处理
    words = re.findall(r'[\w]+', title.lower())
    
    # 过滤停用词并返回关键词集合
    keywords = set(word for word in words if word not in stop_words and len(word) > 1)
    return keywords


def analyze_nearby_reminders():
    """分析时间附近的提醒"""
    dao = ReminderDAO()
    
    try:
        # 获取将来会被触发的提醒（confirmed 或 pending 状态）
        query = {"status": {"$in": ["confirmed", "pending"]}}
        reminders = list(dao.collection.find(query))
        
        if not reminders:
            print("没有找到将来会被触发的提醒")
            return
        
        # 按用户ID分组
        user_reminders = defaultdict(list)
        for reminder in reminders:
            user_id = reminder.get("user_id")
            if user_id:
                user_reminders[user_id].append(reminder)
        
        # 分析每个用户的提醒
        nearby_candidates = []   # 时间接近的提醒组（30秒内）
        
        for user_id, user_reminder_list in user_reminders.items():
            # 按时间排序
            sorted_reminders = sorted(user_reminder_list, key=lambda x: x.get("next_trigger_time", 0))
            
            # 查找时间接近的提醒（30秒内）
            for i in range(len(sorted_reminders)):
                current_reminder = sorted_reminders[i]
                current_time = current_reminder.get("next_trigger_time", 0)
                
                # 查找后续30秒内的提醒
                nearby_group = [current_reminder]
                for j in range(i+1, len(sorted_reminders)):
                    next_reminder = sorted_reminders[j]
                    next_time = next_reminder.get("next_trigger_time", 0)
                    
                    # 如果时间差在30秒内，则加入组
                    if next_time - current_time <= 30:
                        nearby_group.append(next_reminder)
                    else:
                        break
                
                # 如果有多个提醒且还不是已记录的组，则加入候选组
                if len(nearby_group) > 1:
                    # 检查是否已经记录过这个组
                    already_recorded = False
                    for recorded_group in nearby_candidates:
                        if set(recorded_group[2]) == set(nearby_group):
                            already_recorded = True
                            break
                    
                    if not already_recorded:
                        # 计算时间范围
                        min_time = min(r.get("next_trigger_time", 0) for r in nearby_group)
                        max_time = max(r.get("next_trigger_time", 0) for r in nearby_group)
                        time_diff = max_time - min_time
                        
                        nearby_candidates.append((user_id, min_time, max_time, time_diff, nearby_group))
        
        # 显示结果
        print("=" * 100)
        print("                          附近时间提醒分析报告")
        print("=" * 100)
        
        print(f"\n📊 总体统计:")
        print(f"  • 未来提醒总数: {len(reminders)}")
        print(f"  • 涉及用户数: {len(user_reminders)}")
        print(f"  • 时间接近组数: {len(nearby_candidates)} (30秒内)")
        
        # 显示时间接近的提醒
        if nearby_candidates:
            print(f"\n🟡 时间接近的提醒 (30秒内):")
            print("-" * 100)
            for i, (user_id, min_time, max_time, time_diff, group) in enumerate(nearby_candidates, 1):
                print(f"[{i}] 用户: {user_id}")
                print(f"    时间范围: {format_time(min_time)} - {format_time(max_time)}")
                print(f"    时间差: {time_diff} 秒")
                print(f"    数量: {len(group)} 个提醒")
                print("    详细信息:")
                
                # 按时间排序显示
                sorted_group = sorted(group, key=lambda x: x.get("next_trigger_time", 0))
                for j, reminder in enumerate(sorted_group, 1):
                    reminder_id = reminder.get("reminder_id", "N/A")
                    title = reminder.get("title", "无标题")
                    trigger_time = reminder.get("next_trigger_time", 0)
                    recurrence = reminder.get("recurrence", {})
                    
                    recurrence_str = "单次" if not recurrence or not recurrence.get("enabled") else recurrence.get("type", "周期")
                    
                    print(f"      [{j}] ID: {reminder_id}")
                    print(f"          标题: {title}")
                    print(f"          类型: {recurrence_str}")
                    print(f"          时间: {format_time(trigger_time)}")
                
                print("-" * 80)
        else:
            print(f"\n🟢 没有发现时间接近的提醒 (30秒内)")
        
        print("\n" + "=" * 100)
        print("                           分析完成")
        print("=" * 100)
        
    finally:
        dao.close()


def main():
    print("=" * 100)
    print("                   附近时间提醒分析工具")
    print("=" * 100)
    print("此工具将分析将来会被触发的提醒，查找时间非常接近的提醒（30秒内）")
    print("注意：此脚本仅用于分析，不会删除任何提醒\n")
    
    analyze_nearby_reminders()


if __name__ == "__main__":
    main()