#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析未来重复提醒的脚本

此脚本用于分析将来会被触发的提醒，区分真正重复和需要合并的提醒。
重复定义：
1. 只分析状态为 confirmed 或 pending 的提醒（将来会被触发）
2. 时间完全重复的提醒，如果有相同关键词则为重复设置，否则为需要合并

使用方法：
    python scripts/analyze_future_duplicates.py
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


def analyze_future_duplicates():
    """分析未来的重复提醒"""
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
        actual_duplicates = []  # 真正重复设置的提醒（有相同关键词）
        merge_candidates = []   # 应该合并的提醒（无相同关键词）
        single_reminders = []   # 单独的提醒
        
        for user_id, user_reminder_list in user_reminders.items():
            # 按确切时间分组
            exact_time_groups = defaultdict(list)
            
            # 先按确切时间分组
            for reminder in user_reminder_list:
                trigger_time = reminder.get("next_trigger_time", 0)
                exact_time_groups[trigger_time].append(reminder)
            
            # 处理确切时间相同的提醒
            for time_key, group in exact_time_groups.items():
                if len(group) > 1:
                    # 检查是否有相同关键词
                    group_keywords = []
                    for reminder in group:
                        title = reminder.get("title", "")
                        keywords = extract_keywords(title)
                        group_keywords.append((reminder, keywords))
                    
                    # 检查关键词重叠
                    has_overlap = False
                    overlap_pairs = []
                    
                    for i in range(len(group_keywords)):
                        for j in range(i+1, len(group_keywords)):
                            reminder1, keywords1 = group_keywords[i]
                            reminder2, keywords2 = group_keywords[j]
                            
                            # 计算关键词重叠
                            overlap = keywords1.intersection(keywords2)
                            if overlap:
                                has_overlap = True
                                overlap_pairs.append((reminder1, reminder2, overlap))
                    
                    # 根据关键词重叠情况分类
                    if has_overlap:
                        actual_duplicates.append((user_id, time_key, group, overlap_pairs))
                    else:
                        merge_candidates.append((user_id, time_key, group))
                else:
                    single_reminders.append((user_id, group[0]))
        
        # 显示结果
        print("=" * 100)
        print("                          未来重复提醒分析报告")
        print("=" * 100)
        
        print(f"\n📊 总体统计:")
        print(f"  • 未来提醒总数: {len(reminders)}")
        print(f"  • 涉及用户数: {len(user_reminders)}")
        print(f"  • 真正重复组数: {len(actual_duplicates)} (有相同关键词)")
        print(f"  • 应合并组数: {len(merge_candidates)} (无相同关键词)")
        print(f"  • 单独提醒数: {len(single_reminders)}")
        
        # 显示真正重复的提醒（有相同关键词）
        if actual_duplicates:
            print(f"\n🔴 真正重复提醒 (有相同关键词):")
            print("-" * 100)
            for i, (user_id, time_key, group, overlap_pairs) in enumerate(actual_duplicates, 1):
                print(f"[{i}] 用户: {user_id}")
                print(f"    时间: {format_time(time_key)}")
                print(f"    数量: {len(group)} 个提醒")
                print("    重复详情:")
                
                for j, (reminder1, reminder2, overlap) in enumerate(overlap_pairs, 1):
                    title1 = reminder1.get("title", "无标题")
                    title2 = reminder2.get("title", "无标题")
                    id1 = reminder1.get("reminder_id", "N/A")[:8]
                    id2 = reminder2.get("reminder_id", "N/A")[:8]
                    
                    print(f"      重复对 {j}:")
                    print(f"        • 「{title1}」({id1}...)")
                    print(f"        • 「{title2}」({id2}...)")
                    print(f"        • 共同关键词: {', '.join(overlap)}")
                
                print("    所有提醒:")
                for j, reminder in enumerate(group, 1):
                    reminder_id = reminder.get("reminder_id", "N/A")
                    title = reminder.get("title", "无标题")
                    recurrence = reminder.get("recurrence", {})
                    
                    recurrence_str = "单次" if not recurrence or not recurrence.get("enabled") else recurrence.get("type", "周期")
                    
                    print(f"      [{j}] ID: {reminder_id}")
                    print(f"          标题: {title}")
                    print(f"          类型: {recurrence_str}")
                
                print("-" * 80)
        
        # 显示应该合并的提醒（无相同关键词）
        if merge_candidates:
            print(f"\n🟡 应该合并的提醒 (无相同关键词):")
            print("-" * 100)
            for i, (user_id, time_key, group) in enumerate(merge_candidates, 1):
                print(f"[{i}] 用户: {user_id}")
                print(f"    时间: {format_time(time_key)}")
                print(f"    数量: {len(group)} 个提醒")
                print("    详细信息:")
                
                for j, reminder in enumerate(group, 1):
                    reminder_id = reminder.get("reminder_id", "N/A")
                    title = reminder.get("title", "无标题")
                    recurrence = reminder.get("recurrence", {})
                    
                    recurrence_str = "单次" if not recurrence or not recurrence.get("enabled") else recurrence.get("type", "周期")
                    
                    print(f"      [{j}] ID: {reminder_id}")
                    print(f"          标题: {title}")
                    print(f"          类型: {recurrence_str}")
                
                print("-" * 80)
        
        # 显示单独的提醒（可选）
        if len(single_reminders) <= 20 and single_reminders:
            print(f"\n🟢 单独提醒:")
            print("-" * 100)
            for i, (user_id, reminder) in enumerate(single_reminders[:20], 1):
                reminder_id = reminder.get("reminder_id", "N/A")
                title = reminder.get("title", "无标题")
                trigger_time = reminder.get("next_trigger_time", 0)
                recurrence = reminder.get("recurrence", {})
                
                recurrence_str = "单次" if not recurrence or not recurrence.get("enabled") else recurrence.get("type", "周期")
                
                print(f"[{i}] 用户: {user_id}")
                print(f"    ID: {reminder_id}")
                print(f"    标题: {title}")
                print(f"    类型: {recurrence_str}")
                print(f"    时间: {format_time(trigger_time)}")
        
        if len(single_reminders) > 20:
            print(f"\n🟢 单独提醒: {len(single_reminders)} 个 (太多了，不逐一显示)")
        
        print("\n" + "=" * 100)
        print("                           分析完成")
        print("=" * 100)
        
    finally:
        dao.close()


def main():
    print("=" * 100)
    print("                   未来重复提醒分析工具")
    print("=" * 100)
    print("此工具将分析将来会被触发的提醒，区分真正重复和需要合并的提醒")
    print("分析规则：")
    print("  1. 只分析状态为 confirmed 或 pending 的提醒（将来会被触发）")
    print("  2. 时间完全重复的提醒：")
    print("     • 有相同关键词 → 真正重复设置")
    print("     • 无相同关键词 → 应该合并")
    print("注意：此脚本仅用于分析，不会删除任何提醒\n")
    
    analyze_future_duplicates()


if __name__ == "__main__":
    main()