#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
删除特定用户所有提醒的脚本

此脚本用于删除指定用户的所有提醒任务。

使用方法：
    python scripts/delete_user_reminders.py
"""

import sys

sys.path.append(".")

from dao.reminder_dao import ReminderDAO


def delete_user_reminders(user_id, dry_run=True):
    """删除指定用户的所有提醒"""
    dao = ReminderDAO()

    try:
        # 查找指定用户的所有提醒
        query = {"user_id": user_id}
        reminders = list(dao.collection.find(query))

        if not reminders:
            print(f"用户 {user_id} 没有找到任何提醒")
            return 0

        print(
            f"{'[预览模式] ' if dry_run else ''}找到用户 {user_id} 的 {len(reminders)} 个提醒:"
        )
        print("-" * 80)

        for i, reminder in enumerate(reminders, 1):
            reminder_id = reminder.get("reminder_id", "N/A")
            title = reminder.get("title", "无标题")
            status = reminder.get("status", "unknown")
            trigger_time = reminder.get("next_trigger_time", 0)

            # 格式化时间显示
            try:
                from util.time_util import format_time_friendly

                time_str = format_time_friendly(trigger_time)
            except (ValueError, OSError, TypeError, ImportError):
                time_str = str(trigger_time)

            print(f"[{i}] ID: {reminder_id}")
            print(f"    标题: {title}")
            print(f"    状态: {status}")
            print(f"    触发时间: {time_str}")
            print()

        if dry_run:
            print(f"\n预览模式：将删除用户 {user_id} 的 {len(reminders)} 个提醒")
            print(
                f"如需执行删除，请运行: python scripts/delete_user_reminders.py --user {user_id} --execute"
            )
        else:
            # 执行删除操作
            deleted_count = 0
            for reminder in reminders:
                reminder_id = reminder.get("reminder_id")
                if dao.delete_reminder(reminder_id):
                    deleted_count += 1
                else:
                    print(f"删除失败: {reminder_id}")

            print(f"成功删除用户 {user_id} 的 {deleted_count} 个提醒")

        return len(reminders) if not dry_run else 0

    finally:
        dao.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="删除特定用户的所有提醒")
    parser.add_argument(
        "--user", type=str, help="用户ID", default="6945fc33f09e7d5a55ad9f29"
    )
    parser.add_argument(
        "--execute", action="store_true", help="执行删除操作（默认为预览模式）"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("                   删除用户提醒工具")
    print("=" * 80)
    print(f"此工具将删除用户 {args.user} 的所有提醒任务")
    print()

    delete_user_reminders(args.user, dry_run=not args.execute)


if __name__ == "__main__":
    main()
