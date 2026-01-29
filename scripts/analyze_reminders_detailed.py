#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
详细分析重复提醒的脚本

此脚本用于详细分析提醒数据，区分真正重复和非重复的提醒.
重复定义：同一用户、触发时间相差在30秒内的提醒.

使用方法：
    python scripts/analyze_reminders_detailed.py
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
        exact = dt.strftime("%Y-%m-%d %H:%M:%S")
        return f"{friendly} ({exact})"
    except (ValueError, OSError, TypeError):
        return str(timestamp)


def analyze_reminders():
    """详细分析提醒数据"""
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

        # 分析每个用户的提醒
        exact_duplicates = []  # 完全相同时间的提醒
        near_duplicates = []  # 时间接近的提醒（30秒内）
        single_reminders = []  # 单独的提醒

        for user_id, user_reminder_list in user_reminders.items():
            # 按确切时间分组
            exact_time_groups = defaultdict(list)
            # 按近似时间分组（30秒内）
            near_time_groups = defaultdict(list)

            # 先按确切时间分组
            for reminder in user_reminder_list:
                trigger_time = reminder.get("next_trigger_time", 0)
                exact_time_groups[trigger_time].append(reminder)

            # 处理确切时间相同的提醒
            for time_key, group in exact_time_groups.items():
                if len(group) > 1:
                    exact_duplicates.append((user_id, time_key, group))
                else:
                    single_reminders.append((user_id, group[0]))

            # 按近似时间分组（30秒内）
            sorted_reminders = sorted(
                user_reminder_list, key=lambda x: x.get("next_trigger_time", 0)
            )
            for i, reminder in enumerate(sorted_reminders):
                trigger_time = reminder.get("next_trigger_time", 0)

                # 查找30秒内的其他提醒
                near_group = [reminder]
                for j in range(i + 1, len(sorted_reminders)):
                    other_reminder = sorted_reminders[j]
                    other_time = other_reminder.get("next_trigger_time", 0)
                    if other_time - trigger_time <= 30:  # 30秒内
                        near_group.append(other_reminder)
                    else:
                        break

                # 如果有多个提醒且不是确切重复的，则加入近似重复组
                if len(near_group) > 1:
                    # 检查是否已经是确切重复的
                    is_exact_duplicate = False
                    for _, _, exact_group in exact_duplicates:
                        if reminder in exact_group:
                            is_exact_duplicate = True
                            break

                    if not is_exact_duplicate:
                        near_duplicates.append((user_id, near_group))

        # 显示结果
        print("=" * 80)
        print("                          提醒数据分析报告")
        print("=" * 80)

        print("\n📊 总体统计:")
        print(f"  • 总提醒数: {len(reminders)}")
        print(f"  • 涉及用户数: {len(user_reminders)}")
        print(f"  • 完全重复组数: {len(exact_duplicates)}")
        print(f"  • 时间接近组数: {len(near_duplicates)}")
        print(f"  • 单独提醒数: {len(single_reminders)}")

        # 显示完全重复的提醒
        if exact_duplicates:
            print("\n🔴 完全重复提醒 (相同时间):")
            print("-" * 80)
            for i, (user_id, time_key, group) in enumerate(exact_duplicates, 1):
                print(f"[{i}] 用户: {user_id}")
                print(f"    时间: {format_time(time_key)}")
                print(f"    数量: {len(group)} 个提醒")
                print("    详细信息:")

                for j, reminder in enumerate(group, 1):
                    reminder_id = reminder.get("reminder_id", "N/A")
                    title = reminder.get("title", "无标题")
                    status = reminder.get("status", "unknown")
                    recurrence = reminder.get("recurrence", {})

                    recurrence_str = (
                        "单次"
                        if not recurrence or not recurrence.get("enabled")
                        else recurrence.get("type", "周期")
                    )

                    print(f"      [{j}] ID: {reminder_id}")
                    print(f"          标题: {title}")
                    print(f"          状态: {status}")
                    print(f"          类型: {recurrence_str}")

                print("-" * 60)

        # 显示时间接近的提醒
        if near_duplicates:
            print("\n🟡 时间接近提醒 (30秒内):")
            print("-" * 80)
            for i, (user_id, group) in enumerate(near_duplicates, 1):
                times = [r.get("next_trigger_time", 0) for r in group]
                min_time = min(times)
                max_time = max(times)

                print(f"[{i}] 用户: {user_id}")
                print(f"    时间范围: {format_time(min_time)}-{format_time(max_time)}")
                print(f"    时间差: {max_time-min_time} 秒")
                print(f"    数量: {len(group)} 个提醒")
                print("    详细信息:")

                # 按时间排序显示
                sorted_group = sorted(
                    group, key=lambda x: x.get("next_trigger_time", 0)
                )
                for j, reminder in enumerate(sorted_group, 1):
                    reminder_id = reminder.get("reminder_id", "N/A")
                    title = reminder.get("title", "无标题")
                    status = reminder.get("status", "unknown")
                    trigger_time = reminder.get("next_trigger_time", 0)
                    recurrence = reminder.get("recurrence", {})

                    recurrence_str = (
                        "单次"
                        if not recurrence or not recurrence.get("enabled")
                        else recurrence.get("type", "周期")
                    )

                    print(f"      [{j}] ID: {reminder_id}")
                    print(f"          标题: {title}")
                    print(f"          状态: {status}")
                    print(f"          类型: {recurrence_str}")
                    print(f"          时间: {format_time(trigger_time)}")

                print("-" * 60)

        # 显示单独的提醒（可选，如果数量太多就不显示）
        if len(single_reminders) <= 20 and single_reminders:
            print("\n🟢 单独提醒:")
            print("-" * 80)
            for i, (user_id, reminder) in enumerate(single_reminders[:20], 1):
                reminder_id = reminder.get("reminder_id", "N/A")
                title = reminder.get("title", "无标题")
                status = reminder.get("status", "unknown")
                trigger_time = reminder.get("next_trigger_time", 0)
                recurrence = reminder.get("recurrence", {})

                recurrence_str = (
                    "单次"
                    if not recurrence or not recurrence.get("enabled")
                    else recurrence.get("type", "周期")
                )

                print(f"[{i}] 用户: {user_id}")
                print(f"    ID: {reminder_id}")
                print(f"    标题: {title}")
                print(f"    状态: {status}")
                print(f"    类型: {recurrence_str}")
                print(f"    时间: {format_time(trigger_time)}")

        if len(single_reminders) > 20:
            print(f"\n🟢 单独提醒: {len(single_reminders)} 个 (太多了，不逐一显示)")

        print("\n" + "=" * 80)
        print("                           分析完成")
        print("=" * 80)

    finally:
        dao.close()


def main():
    print("=" * 80)
    print("                   详细提醒数据分析工具")
    print("=" * 80)
    print("此工具将详细分析提醒数据，区分完全重复和时间接近的提醒")
    print("重复定义：")
    print("  • 完全重复：同一用户、完全相同的时间")
    print("  • 时间接近：同一用户、触发时间相差在30秒内")
    print("注意：此脚本仅用于分析，不会删除任何提醒\n")

    analyze_reminders()


if __name__ == "__main__":
    main()
