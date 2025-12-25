#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析附近时间提醒的统一脚本

此脚本用于分析将来会被触发的提醒，查找时间非常接近的提醒，
以确定是否还需要合并.

使用方法：
    python scripts/analyze_nearby_reminders_unified.py --window 30    # 30秒内
    python scripts/analyze_nearby_reminders_unified.py --window 300   # 5分钟内
    python scripts/analyze_nearby_reminders_unified.py --window 1800  # 30分钟内
"""

import sys

sys.path.append(".")

import argparse
import re
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
        return f"{friendly} ({dt.strftime('%Y-%m-%d %H:%M:%S')})"
    except (ValueError, OSError, TypeError):
        return f"时间戳: {timestamp}"


def format_duration(seconds):
    """格式化时间差显示"""
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes}分{remaining_seconds}秒"
    else:
        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        return f"{hours}小时{remaining_minutes}分钟"


def analyze_nearby_reminders(window_seconds=30):
    """分析附近时间的提醒"""
    reminder_dao = ReminderDAO()

    # 获取所有未来的提醒
    all_reminders = reminder_dao.find_all_reminders()

    # 过滤出有效的未来提醒
    future_reminders = []
    current_time = int(datetime.now().timestamp())

    for reminder in all_reminders:
        next_trigger = reminder.get("next_trigger_time")
        if (
            next_trigger
            and next_trigger > current_time
            and reminder.get("status") in ["confirmed", "triggered"]
        ):
            future_reminders.append(reminder)

    # 按触发时间排序
    future_reminders.sort(key=lambda x: x.get("next_trigger_time", 0))

    print(f"总共找到 {len(future_reminders)} 个未来提醒")

    if not future_reminders:
        print("没有找到未来的提醒")
        return

    # 按用户分组分析
    user_reminders = defaultdict(list)
    for reminder in future_reminders:
        user_id = reminder.get("user_id")
        user_reminders[user_id].append(reminder)

    print(f"涉及 {len(user_reminders)} 个用户")

    # 分析每个用户的提醒
    all_nearby_groups = []

    for user_id, reminders in user_reminders.items():
        if len(reminders) < 2:
            continue

        # 查找时间接近的提醒组
        nearby_candidates = []
        processed_reminders = set()

        for i, reminder in enumerate(reminders):
            if reminder.get("reminder_id") in processed_reminders:
                continue

            current_time = reminder.get("next_trigger_time")
            if not current_time:
                continue

            # 查找后续指定时间窗口内的提醒
            nearby_group = [reminder]
            processed_reminders.add(reminder.get("reminder_id"))

            for j in range(i + 1, len(reminders)):
                next_reminder = reminders[j]
                next_time = next_reminder.get("next_trigger_time")

                if next_time and next_time-current_time <= window_seconds:
                    nearby_group.append(next_reminder)
                    processed_reminders.add(next_reminder.get("reminder_id"))
                else:
                    break

            if len(nearby_group) > 1:
                # 检查是否已经记录了相同的组
                is_duplicate = False
                for recorded_group in nearby_candidates:
                    if set(r.get("reminder_id") for r in recorded_group[4]) == set(
                        r.get("reminder_id") for r in nearby_group
                    ):
                        is_duplicate = True
                        break

                if not is_duplicate:
                    first_time = nearby_group[0].get("next_trigger_time")
                    last_time = nearby_group[-1].get("next_trigger_time")
                    time_span = last_time-first_time
                    nearby_candidates.append(
                        (user_id, first_time, last_time, time_span, nearby_group)
                    )

        all_nearby_groups.extend(nearby_candidates)

    # 生成报告
    window_desc = format_duration(window_seconds)
    print("\n" + "=" * 80)
    print(f"                          附近时间提醒分析报告 ({window_desc}内)")
    print("=" * 80)
    print(f"  • 分析时间窗口: {window_desc}")
    print(f"  • 总提醒数: {len(future_reminders)}")
    print(f"  • 用户数: {len(user_reminders)}")
    print(f"  • 时间接近组数: {len(all_nearby_groups)} ({window_desc}内)")

    if all_nearby_groups:
        print(f"\n🟡 时间接近的提醒 ({window_desc}内):")

        for i, (user_id, first_time, last_time, time_span, group) in enumerate(
            all_nearby_groups, 1
        ):
            print(f"\n  组 {i} (用户: {user_id[:8]}...):")
            print(f"    时间差: {format_duration(time_span)}")
            print(f"    提醒数量: {len(group)}")

            for j, reminder in enumerate(group):
                trigger_time = format_time(reminder.get("next_trigger_time"))
                title = reminder.get("title", "无标题")[:30]
                status = reminder.get("status", "unknown")
                reminder_type = reminder.get("type", "unknown")

                print(f"      {j + 1}. [{status}] {title}")
                print(f"         触发时间: {trigger_time}")
                print(f"         类型: {reminder_type}")
                print(f"         ID: {reminder.get('reminder_id', 'N/A')}")

        print("\n📊 统计信息:")
        print(f"  • 发现 {len(all_nearby_groups)} 个时间接近的提醒组")
        print(
            f"  • 总共涉及 {sum(len(group[4]) for group in all_nearby_groups)} 个提醒"
        )

        # 按时间差排序显示最接近的几组
        sorted_groups = sorted(all_nearby_groups, key=lambda x: x[3])
        print("\n🔥 最接近的 3 组:")
        for i, (user_id, first_time, last_time, time_span, group) in enumerate(
            sorted_groups[:3], 1
        ):
            print(
                f"  {i}. 时间差: {format_duration(time_span)} (用户: {user_id[:8]}..., {len(group)} 个提醒)"
            )
    else:
        print(f"\n🟢 没有发现时间接近的提醒 ({window_desc}内)")
        print("  所有提醒的时间间隔都超过了指定的时间窗口")

    print("\n" + "=" * 80)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="分析附近时间提醒的统一工具")
    parser.add_argument(
        "--window",
        "-w",
        type=int,
        default=30,
        help="时间窗口（秒），默认30秒。常用值：30(30秒), 300(5分钟), 1800(30分钟)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")

    args = parser.parse_args()

    print("=" * 80)
    print("                   附近时间提醒分析工具")
    print("=" * 80)
    window_desc = format_duration(args.window)
    print(f"此工具将分析将来会被触发的提醒，查找时间非常接近的提醒（{window_desc}内）")
    print("=" * 80)

    try:
        analyze_nearby_reminders(args.window)
    except Exception as e:
        print(f"❌ 分析过程中出现错误: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
