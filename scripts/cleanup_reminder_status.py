#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理提醒状态脚本

用于修复数据库中状态异常的提醒：
1. 将 status 为 "triggered" 且不是周期提醒的改为 "completed"
2. 统计各种状态的提醒数量
"""

import sys

sys.path.append(".")

import logging

from dao.reminder_dao import ReminderDAO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_reminder_status():
    """分析提醒状态分布"""
    dao = ReminderDAO()

    try:
        # 统计各种状态
        all_reminders = list(dao.collection.find({}))

        status_count = {}
        for reminder in all_reminders:
            status = reminder.get("status", "unknown")
            status_count[status] = status_count.get(status, 0) + 1

        logger.info("=" * 60)
        logger.info("提醒状态统计")
        logger.info("=" * 60)
        logger.info(f"总提醒数: {len(all_reminders)}")
        for status, count in sorted(status_count.items()):
            logger.info(f"  {status}: {count}")
        logger.info("")

        # 查找异常状态
        triggered_non_recurring = list(
            dao.collection.find({"status": "triggered", "recurrence.enabled": False})
        )

        logger.info(
            f"发现 {len(triggered_non_recurring)} 个状态为 'triggered' 的非周期提醒"
        )
        logger.info("这些提醒应该被标记为 'completed'")
        logger.info("")

        return len(triggered_non_recurring)

    finally:
        dao.close()


def cleanup_reminder_status(dry_run=True):
    """清理异常状态的提醒"""
    dao = ReminderDAO()

    try:
        # 查找需要清理的提醒
        triggered_non_recurring = list(
            dao.collection.find({"status": "triggered", "recurrence.enabled": False})
        )

        if len(triggered_non_recurring) == 0:
            logger.info("✓ 没有需要清理的提醒")
            return

        logger.info("=" * 60)
        logger.info(f"准备清理 {len(triggered_non_recurring)} 个提醒")
        logger.info("=" * 60)

        for reminder in triggered_non_recurring:
            logger.info(
                f" -{reminder.get('title')} (ID: {reminder.get('reminder_id')})"
            )

        logger.info("")

        if dry_run:
            logger.info("⚠️  DRY RUN 模式：不会实际修改数据")
            logger.info(
                "如需实际执行，请运行: python scripts/cleanup_reminder_status.py --execute"
            )
        else:
            # 执行清理
            result = dao.collection.update_many(
                {"status": "triggered", "recurrence.enabled": False},
                {"$set": {"status": "completed"}},
            )

            logger.info(f"✓ 已更新 {result.modified_count} 个提醒的状态为 'completed'")

    finally:
        dao.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="清理提醒状态")
    parser.add_argument(
        "--execute", action="store_true", help="实际执行清理（默认为 dry-run）"
    )
    args = parser.parse_args()

    try:
        # 分析状态
        count = analyze_reminder_status()

        # 清理异常状态
        if count > 0:
            cleanup_reminder_status(dry_run=not args.execute)

        logger.info("=" * 60)
        logger.info("✅ 完成")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ 执行失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
