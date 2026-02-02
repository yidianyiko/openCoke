#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提醒管理脚本

功能：
1. 查询所有提醒（支持按状态筛选）
2. 删除指定提醒（按ID或关键词）
3. 人性化显示

使用方法：
    python scripts/manage_reminders.py                  # 交互式菜单
    python scripts/manage_reminders.py list             # 列出所有待触发提醒
    python scripts/manage_reminders.py list --all       # 列出所有提醒
    python scripts/manage_reminders.py list --status active  # 按状态筛选
    python scripts/manage_reminders.py delete <id>      # 删除指定ID的提醒
    python scripts/manage_reminders.py delete --keyword "关键词"  # 删除匹配关键词的提醒
"""

import sys

sys.path.append(".")

import argparse
from datetime import datetime, timedelta
from typing import List, Optional

from dao.reminder_dao import ReminderDAO
from util.time_util import format_time_friendly


# ANSI 颜色代码
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


def colorize(text: str, color: str) -> str:
    """给文本添加颜色"""
    return f"{color}{text}{Colors.ENDC}"


def format_status(status: str) -> str:
    """格式化状态显示"""
    status_map = {
        "active": ("✅ 待触发", Colors.GREEN),
        "triggered": ("🔔 已触发", Colors.BLUE),
        "completed": ("✓ 已完成", Colors.DIM),
    }
    display, color = status_map.get(status, (status, Colors.ENDC))
    return colorize(display, color)


def format_recurrence(recurrence: dict) -> str:
    """格式化周期显示"""
    if not recurrence or not recurrence.get("enabled"):
        return "单次"

    rec_type = recurrence.get("type", "")
    interval = recurrence.get("interval", 1)

    type_map = {
        "daily": "每天",
        "weekly": "每周",
        "monthly": "每月",
        "yearly": "每年",
        "hourly": "每小时",
        "interval": f"每{interval}分钟",
    }

    return colorize(type_map.get(rec_type, rec_type), Colors.CYAN)


def format_time(timestamp: Optional[int]) -> str:
    """格式化时间显示"""
    if not timestamp:
        return "未设置"

    try:
        friendly = format_time_friendly(timestamp)
        dt = datetime.fromtimestamp(timestamp)
        exact = dt.strftime("%Y-%m-%d %H:%M")

        # 判断是否已过期
        if timestamp < int(datetime.now().timestamp()):
            return colorize(f"⚠️  {friendly} ({exact})", Colors.RED)
        else:
            return f"{friendly} ({exact})"
    except (ValueError, OSError, TypeError):
        return str(timestamp)


def print_reminder_table(reminders: List[dict], show_user: bool = True):
    """以表格形式打印提醒列表"""
    if not reminders:
        print(colorize("\n📭 没有找到提醒\n", Colors.YELLOW))
        return

    print()
    print(colorize("=" * 100, Colors.HEADER))
    print(colorize(f"  共找到 {len(reminders)} 条提醒", Colors.BOLD))
    print(colorize("=" * 100, Colors.HEADER))

    for i, reminder in enumerate(reminders, 1):
        reminder_id = reminder.get("reminder_id", "N/A")
        title = reminder.get("title", "无标题")
        status = reminder.get("status", "unknown")
        trigger_time = reminder.get("next_trigger_time")
        user_id = reminder.get("user_id", "")
        recurrence = reminder.get("recurrence", {})

        print()
        print(
            colorize(f"[{i}] ", Colors.BOLD)
            + colorize(title, Colors.CYAN + Colors.BOLD)
        )
        print(f"    ID: {colorize(reminder_id, Colors.DIM)}")
        print(
            f"    状态: {format_status(status)}  |  周期: {format_recurrence(recurrence)}"
        )
        print(f"    触发时间: {format_time(trigger_time)}")

        if show_user and user_id:
            print(f"    用户: {colorize(user_id, Colors.DIM)}")

        print(colorize("    " + "-" * 80, Colors.DIM))

    print()


def list_reminders(
    status: Optional[str] = None, show_all: bool = False, user_id: Optional[str] = None
):
    """列出提醒"""
    dao = ReminderDAO()

    try:
        # 构建查询
        query = {}

        if user_id:
            query["user_id"] = user_id

        if status:
            query["status"] = status
        elif not show_all:
            # 默认只显示待触发的提醒
            query["status"] = "active"

        # 查询并排序
        reminders = list(dao.collection.find(query).sort("next_trigger_time", 1))

        # 统计信息
        if show_all:
            status_counts = {}
            for r in reminders:
                s = r.get("status", "unknown")
                status_counts[s] = status_counts.get(s, 0) + 1

            print(colorize("\n📊 状态统计:", Colors.BOLD))
            for s, count in sorted(status_counts.items()):
                print(f"    {format_status(s)}: {count}")

        print_reminder_table(reminders)

        return reminders

    finally:
        dao.close()


def delete_reminder_by_id(reminder_id: str, force: bool = False) -> bool:
    """通过ID删除提醒"""
    dao = ReminderDAO()

    try:
        reminder = dao.get_reminder_by_id(reminder_id)

        if not reminder:
            print(colorize(f"\n❌ 找不到ID为 {reminder_id} 的提醒\n", Colors.RED))
            return False

        title = reminder.get("title", "无标题")

        if not force:
            print(colorize("\n⚠️  即将删除提醒:", Colors.YELLOW))
            print(f"    标题: {title}")
            print(f"    ID: {reminder_id}")
            confirm = input("\n确认删除? (y/N): ").strip().lower()
            if confirm != "y":
                print(colorize("已取消删除", Colors.DIM))
                return False

        success = dao.delete_reminder(reminder_id)

        if success:
            print(colorize(f"\n✅ 已删除提醒: {title}\n", Colors.GREEN))
        else:
            print(colorize("\n❌ 删除失败\n", Colors.RED))

        return success

    finally:
        dao.close()


def reschedule_expired(reminder_ids: List[str] = None, dry_run: bool = True) -> int:
    """重新调度过期的提醒到最近的触发时间"""
    dao = ReminderDAO()

    try:
        now = datetime.now()
        now_ts = int(now.timestamp())

        # 查找过期的提醒
        if reminder_ids:
            query = {
                "reminder_id": {"$in": reminder_ids},
                "status": "active",
            }
        else:
            query = {
                "status": "active",
                "next_trigger_time": {"$lt": now_ts},
            }

        reminders = list(dao.collection.find(query).sort("next_trigger_time", 1))

        if not reminders:
            print(colorize("\n📭 没有找到需要重新调度的提醒\n", Colors.YELLOW))
            return 0

        print(
            colorize(f"\n🔄 找到 {len(reminders)} 条需要重新调度的提醒:", Colors.BOLD)
        )

        updates = []
        for reminder in reminders:
            reminder_id = reminder.get("reminder_id")
            title = reminder.get("title", "无标题")
            old_time = reminder.get("next_trigger_time")
            old_dt = datetime.fromtimestamp(old_time)

            # 计算新的触发时间：保持时分秒，调整到今天或明天
            new_dt = now.replace(
                hour=old_dt.hour, minute=old_dt.minute, second=0, microsecond=0
            )

            # 如果今天这个时间已过，改到明天
            if new_dt <= now:
                new_dt = new_dt + timedelta(days=1)

            new_time = int(new_dt.timestamp())

            updates.append(
                {
                    "reminder_id": reminder_id,
                    "title": title,
                    "old_time": old_time,
                    "new_time": new_time,
                }
            )

            old_friendly = format_time_friendly(old_time)
            new_friendly = format_time_friendly(new_time)
            old_exact = old_dt.strftime("%Y-%m-%d %H:%M")
            new_exact = new_dt.strftime("%Y-%m-%d %H:%M")

            print(f"\n  {colorize(title, Colors.CYAN)}")
            print(f"    {colorize('原时间:', Colors.RED)} {old_friendly} ({old_exact})")
            print(
                f"    {colorize('新时间:', Colors.GREEN)} {new_friendly} ({new_exact})"
            )

        print()

        if dry_run:
            print(colorize("⚠️  预览模式：不会实际修改", Colors.YELLOW))
            print("如需执行，请添加 --execute 参数\n")
            return 0

        # 执行更新
        updated = 0
        for update in updates:
            result = dao.collection.update_one(
                {"reminder_id": update["reminder_id"]},
                {
                    "$set": {
                        "next_trigger_time": update["new_time"],
                        "updated_at": now_ts,
                    }
                },
            )
            if result.modified_count > 0:
                updated += 1

        print(colorize(f"✅ 已更新 {updated} 条提醒\n", Colors.GREEN))
        return updated

    finally:
        dao.close()


def delete_by_keyword(keyword: str, dry_run: bool = True) -> int:
    """通过关键词删除提醒"""
    dao = ReminderDAO()

    try:
        # 查找匹配的提醒
        query = {"title": {"$regex": keyword, "$options": "i"}}

        reminders = list(dao.collection.find(query))

        if not reminders:
            print(
                colorize(
                    f'\n📭 没有找到或已经完成了包含 "{keyword}" 的提醒\n', Colors.YELLOW
                )
            )
            return 0

        print(
            colorize(
                f'\n🔍 找到 {len(reminders)} 条匹配 "{keyword}" 的提醒:', Colors.BOLD
            )
        )
        print_reminder_table(reminders)

        if dry_run:
            print(colorize("⚠️  预览模式：不会实际删除", Colors.YELLOW))
            print(
                f'如需删除，请运行: python scripts/manage_reminders.py delete --keyword "{keyword}" --execute\n'
            )
            return 0

        confirm = input(f"确认删除这 {len(reminders)} 条提醒? (y/N): ").strip().lower()
        if confirm != "y":
            print(colorize("已取消删除", Colors.DIM))
            return 0

        # 执行删除
        result = dao.collection.delete_many(query)
        deleted = result.deleted_count

        print(colorize(f"\n✅ 已删除 {deleted} 条提醒\n", Colors.GREEN))
        return deleted

    finally:
        dao.close()


def interactive_menu():
    """交互式菜单"""
    while True:
        print(colorize("\n" + "=" * 50, Colors.HEADER))
        print(colorize("       📋 提醒管理工具", Colors.BOLD + Colors.CYAN))
        print(colorize("=" * 50, Colors.HEADER))
        print()
        print("  1. 查看待触发的提醒")
        print("  2. 查看所有提醒")
        print("  3. 按状态筛选提醒")
        print("  4. 删除指定ID的提醒")
        print("  5. 按关键词删除提醒")
        print("  6. 重新调度过期提醒")
        print("  0. 退出")
        print()

        choice = input("请选择操作 [0-6]: ").strip()

        if choice == "0":
            print(colorize("\n👋 再见!\n", Colors.CYAN))
            break
        elif choice == "1":
            list_reminders()
        elif choice == "2":
            list_reminders(show_all=True)
        elif choice == "3":
            print("\n状态选项: active, triggered, completed")
            status = input("输入状态: ").strip()
            if status:
                list_reminders(status=status)
        elif choice == "4":
            reminder_id = input("\n输入提醒ID: ").strip()
            if reminder_id:
                delete_reminder_by_id(reminder_id)
        elif choice == "5":
            keyword = input("\n输入关键词: ").strip()
            if keyword:
                delete_by_keyword(keyword, dry_run=True)
                execute = input("\n是否执行删除? (y/N): ").strip().lower()
                if execute == "y":
                    delete_by_keyword(keyword, dry_run=False)
        elif choice == "6":
            reschedule_expired(dry_run=True)
            execute = input("\n是否执行更新? (y/N): ").strip().lower()
            if execute == "y":
                reschedule_expired(dry_run=False)
        else:
            print(colorize("无效选项，请重试", Colors.RED))


def main():
    parser = argparse.ArgumentParser(
        description="提醒管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scripts/manage_reminders.py                      # 交互式菜单
    python scripts/manage_reminders.py list                 # 列出待触发提醒
    python scripts/manage_reminders.py list --all           # 列出所有提醒
    python scripts/manage_reminders.py list --status active
    python scripts/manage_reminders.py delete abc123        # 删除指定ID
    python scripts/manage_reminders.py delete --keyword "关键词" --execute
    python scripts/manage_reminders.py reschedule           # 预览过期提醒重新调度
    python scripts/manage_reminders.py reschedule --execute # 执行重新调度
        """,
    )

    subparsers = parser.add_subparsers(dest="command")

    # list 子命令
    list_parser = subparsers.add_parser("list", help="列出提醒")
    list_parser.add_argument(
        "--all", "-a", action="store_true", help="显示所有状态的提醒"
    )
    list_parser.add_argument(
        "--status",
        "-s",
        help="按状态筛选 (active/triggered/completed)",
    )
    list_parser.add_argument("--user", "-u", help="按用户ID筛选")

    # delete 子命令
    delete_parser = subparsers.add_parser("delete", help="删除提醒")
    delete_parser.add_argument("id", nargs="?", help="要删除的提醒ID")
    delete_parser.add_argument("--keyword", "-k", help="按关键词删除")
    delete_parser.add_argument(
        "--execute", action="store_true", help="实际执行删除（非预览模式）"
    )
    delete_parser.add_argument(
        "--force", "-", action="store_true", help="强制删除，不提示确认"
    )

    # reschedule 子命令
    reschedule_parser = subparsers.add_parser("reschedule", help="重新调度过期提醒")
    reschedule_parser.add_argument(
        "ids",
        nargs="*",
        help="指定要重新调度的提醒ID（可选，不指定则处理所有过期提醒）",
    )
    reschedule_parser.add_argument(
        "--execute", action="store_true", help="实际执行更新（非预览模式）"
    )

    args = parser.parse_args()

    if args.command == "list":
        list_reminders(status=args.status, show_all=args.all, user_id=args.user)
    elif args.command == "delete":
        if args.keyword:
            delete_by_keyword(args.keyword, dry_run=not args.execute)
        elif args.id:
            delete_reminder_by_id(args.id, force=args.force)
        else:
            print(colorize("请指定要删除的提醒ID或使用 --keyword 选项", Colors.RED))
    elif args.command == "reschedule":
        reminder_ids = args.ids if args.ids else None
        reschedule_expired(reminder_ids=reminder_ids, dry_run=not args.execute)
    else:
        # 默认进入交互式菜单
        interactive_menu()


if __name__ == "__main__":
    main()
