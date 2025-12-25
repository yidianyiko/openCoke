#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并重复提醒的脚本

此脚本用于合并那些应该合并的提醒（同一用户同一时间但无相同关键词的提醒），只保留一个.

使用方法：
    python scripts/merge_duplicate_reminders.py [--dry-run]
"""

import sys

sys.path.append(".")

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
        exact = dt.strftime("%Y-%m-%d %H:%M:%S")
        return f"{friendly} ({exact})"
    except (ValueError, OSError, TypeError):
        return str(timestamp)


def extract_keywords(title):
    """从标题中提取关键词"""
    # 移除常见的停用词和标点符号
    stop_words = {
        "的",
        "了",
        "在",
        "是",
        "我",
        "你",
        "他",
        "她",
        "它",
        "们",
        "这",
        "那",
        "个",
        "些",
        "和",
        "与",
        "或",
        "但是",
        "然而",
        "因此",
        "所以",
        "然后",
        "接着",
        "最后",
    }

    # 简单的分词处理
    words = re.findall(r"[\w]+", title.lower())

    # 过滤停用词并返回关键词集合
    keywords = set(word for word in words if word not in stop_words and len(word) > 1)
    return keywords


def merge_duplicate_reminders(dry_run=True):
    """合并应该合并的提醒"""
    dao = ReminderDAO()

    try:
        # 获取将来会被触发的提醒（confirmed 或 pending 状态）
        query = {"status": {"$in": ["confirmed", "pending"]}}
        reminders = list(dao.collection.find(query))

        if not reminders:
            print("没有找到将来会被触发的提醒")
            return 0

        # 按用户ID分组
        user_reminders = defaultdict(list)
        for reminder in reminders:
            user_id = reminder.get("user_id")
            if user_id:
                user_reminders[user_id].append(reminder)

        # 记录需要合并的提醒
        merge_candidates = []  # 应该合并的提醒组

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

                    for i in range(len(group_keywords)):
                        for j in range(i + 1, len(group_keywords)):
                            _, keywords1 = group_keywords[i]
                            _, keywords2 = group_keywords[j]

                            # 计算关键词重叠
                            overlap = keywords1.intersection(keywords2)
                            if overlap:
                                has_overlap = True
                                break

                    # 如果没有关键词重叠，则应该合并
                    if not has_overlap:
                        merge_candidates.append((user_id, time_key, group))

        # 执行合并操作
        merged_count = 0

        if not merge_candidates:
            print("没有找到需要合并的提醒")
            return 0

        print(
            f"{'[预览模式] ' if dry_run else ''}找到 {len(merge_candidates)} 组需要合并的提醒:"
        )
        print("-" * 80)

        for i, (user_id, time_key, group) in enumerate(merge_candidates, 1):
            print(f"[{i}] 用户: {user_id}")
            print(f"    时间: {format_time(time_key)}")
            print(f"    数量: {len(group)} 个提醒")

            # 显示所有提醒
            for j, reminder in enumerate(group, 1):
                reminder_id = reminder.get("reminder_id", "N/A")
                title = reminder.get("title", "无标题")
                recurrence = reminder.get("recurrence", {})

                recurrence_str = (
                    "单次"
                    if not recurrence or not recurrence.get("enabled")
                    else recurrence.get("type", "周期")
                )

                print(f"      [{j}] ID: {reminder_id}")
                print(f"          标题: {title}")
                print(f"          类型: {recurrence_str}")

            # 确定保留哪个提醒（优先保留标题较长的，或者第一个）
            reminder_to_keep = group[0]
            max_title_length = len(reminder_to_keep.get("title", ""))

            for reminder in group:
                title_length = len(reminder.get("title", ""))
                if title_length > max_title_length:
                    max_title_length = title_length
                    reminder_to_keep = reminder

            # 显示将保留的提醒
            keep_id = reminder_to_keep.get("reminder_id", "N/A")
            keep_title = reminder_to_keep.get("title", "无标题")
            print(f"    → 保留: {keep_title} ({keep_id[:8]}...)")

            # 显示将删除的提醒
            reminders_to_delete = [
                r
                for r in group
                if r.get("reminder_id") != reminder_to_keep.get("reminder_id")
            ]
            if reminders_to_delete:
                print("    → 删除:")
                for reminder in reminders_to_delete:
                    del_id = reminder.get("reminder_id", "N/A")
                    del_title = reminder.get("title", "无标题")
                    print(f"        • {del_title} ({del_id[:8]}...)")

            # 执行删除操作（非预览模式）
            if not dry_run:
                success_count = 0
                for reminder in reminders_to_delete:
                    del_id = reminder.get("reminder_id")
                    if dao.delete_reminder(del_id):
                        success_count += 1
                    else:
                        print(f"        ❌ 删除失败: {del_id}")

                if success_count == len(reminders_to_delete):
                    print(f"    ✓ 成功合并 {success_count} 个提醒")
                    merged_count += success_count
                else:
                    print(
                        f"    ⚠️ 部分删除成功: {success_count}/{len(reminders_to_delete)}"
                    )

            print("-" * 80)

        if dry_run:
            print(
                f"\n预览模式：将合并 {len(merge_candidates)} 组提醒，共 {sum(len(group)-1 for _, _, group in merge_candidates)} 个提醒"
            )
            print(
                "如需执行合并，请运行: python scripts/merge_duplicate_reminders.py --execute"
            )
        else:
            print(f"\n成功合并 {merged_count} 个提醒")

        return merged_count if not dry_run else 0

    finally:
        dao.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="合并重复提醒")
    parser.add_argument(
        "--execute", action="store_true", help="执行合并操作（默认为预览模式）"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("                   合并重复提醒工具")
    print("=" * 80)
    print("此工具将合并那些应该合并的提醒（同一用户同一时间但无相同关键词的提醒）")
    print("规则：只保留一个提醒，优先保留标题较长的")
    print()

    merge_duplicate_reminders(dry_run=not args.execute)


if __name__ == "__main__":
    main()
