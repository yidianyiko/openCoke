# -*- coding: utf-8 -*-
"""
提醒状态迁移脚本

阶段二状态重构：
- confirmed/pending -> active
- cancelled -> completed
- triggered 和 completed 保持不变

使用方法：
    # 预览模式（不执行实际迁移）
    python scripts/migrate_reminder_status.py --dry-run

    # 执行迁移
    python scripts/migrate_reminder_status.py

    # 回滚迁移
    python scripts/migrate_reminder_status.py --rollback
"""

import argparse
import sys
import time
from datetime import datetime

sys.path.append(".")

from pymongo import MongoClient

from conf.config import CONF
from util.log_util import get_logger

logger = get_logger(__name__)


def get_mongo_collection():
    """获取 MongoDB reminders 集合"""
    mongo_uri = (
        f"mongodb://{CONF['mongodb']['mongodb_ip']}:{CONF['mongodb']['mongodb_port']}/"
    )
    client = MongoClient(mongo_uri)
    db = client[CONF["mongodb"]["mongodb_name"]]
    return db.reminders, client


def migrate_status(dry_run: bool = False) -> dict:
    """
    执行状态迁移

    Args:
        dry_run: 是否为预览模式

    Returns:
        迁移结果统计
    """
    collection, client = get_mongo_collection()

    stats = {
        "confirmed_to_active": 0,
        "pending_to_active": 0,
        "cancelled_to_completed": 0,
        "total_migrated": 0,
        "errors": [],
    }

    try:
        # 1. confirmed -> active
        confirmed_count = collection.count_documents({"status": "confirmed"})
        stats["confirmed_to_active"] = confirmed_count
        logger.info(f"Found {confirmed_count} reminders with status='confirmed'")

        if not dry_run and confirmed_count > 0:
            result = collection.update_many(
                {"status": "confirmed"}, {"$set": {"status": "active"}}
            )
            logger.info(f"Migrated {result.modified_count} confirmed -> active")

        # 2. pending -> active
        pending_count = collection.count_documents({"status": "pending"})
        stats["pending_to_active"] = pending_count
        logger.info(f"Found {pending_count} reminders with status='pending'")

        if not dry_run and pending_count > 0:
            result = collection.update_many(
                {"status": "pending"}, {"$set": {"status": "active"}}
            )
            logger.info(f"Migrated {result.modified_count} pending -> active")

        # 3. cancelled -> completed
        cancelled_count = collection.count_documents({"status": "cancelled"})
        stats["cancelled_to_completed"] = cancelled_count
        logger.info(f"Found {cancelled_count} reminders with status='cancelled'")

        if not dry_run and cancelled_count > 0:
            result = collection.update_many(
                {"status": "cancelled"}, {"$set": {"status": "completed"}}
            )
            logger.info(f"Migrated {result.modified_count} cancelled -> completed")

        stats["total_migrated"] = (
            stats["confirmed_to_active"]
            + stats["pending_to_active"]
            + stats["cancelled_to_completed"]
        )

    except Exception as e:
        logger.error(f"Migration error: {e}")
        stats["errors"].append(str(e))
    finally:
        client.close()

    return stats


def rollback_status(dry_run: bool = False) -> dict:
    """
    回滚状态迁移（仅用于紧急情况）

    注意：这个回滚不是完美的，因为：
    - 无法区分原本是 confirmed 还是 pending 的 active
    - 无法区分原本是 cancelled 还是 completed 的 completed

    Args:
        dry_run: 是否为预览模式

    Returns:
        回滚结果统计
    """
    collection, client = get_mongo_collection()

    stats = {
        "active_to_confirmed": 0,
        "errors": [],
        "warning": "回滚不完美：无法区分原本是 confirmed 还是 pending",
    }

    try:
        # active -> confirmed（无法区分原本是 confirmed 还是 pending）
        active_count = collection.count_documents({"status": "active"})
        stats["active_to_confirmed"] = active_count
        logger.info(f"Found {active_count} reminders with status='active'")

        if not dry_run and active_count > 0:
            result = collection.update_many(
                {"status": "active"}, {"$set": {"status": "confirmed"}}
            )
            logger.info(f"Rolled back {result.modified_count} active -> confirmed")

    except Exception as e:
        logger.error(f"Rollback error: {e}")
        stats["errors"].append(str(e))
    finally:
        client.close()

    return stats


def verify_migration() -> dict:
    """
    验证迁移结果

    Returns:
        各状态的数量统计
    """
    collection, client = get_mongo_collection()

    try:
        stats = {
            "active": collection.count_documents({"status": "active"}),
            "triggered": collection.count_documents({"status": "triggered"}),
            "completed": collection.count_documents({"status": "completed"}),
            # 旧状态（迁移后应该为 0）
            "confirmed": collection.count_documents({"status": "confirmed"}),
            "pending": collection.count_documents({"status": "pending"}),
            "cancelled": collection.count_documents({"status": "cancelled"}),
        }
        return stats
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Reminder Status Migration Script")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview mode - don't execute actual migration",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback migration (use with caution)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify current status distribution",
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Reminder Status Migration Script")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")

    if args.verify:
        print("Verifying current status distribution...\n")
        stats = verify_migration()
        print("Current status counts:")
        print(f"  - active: {stats['active']}")
        print(f"  - triggered: {stats['triggered']}")
        print(f"  - completed: {stats['completed']}")
        print(f"  - confirmed (old): {stats['confirmed']}")
        print(f"  - pending (old): {stats['pending']}")
        print(f"  - cancelled (old): {stats['cancelled']}")

        old_total = stats["confirmed"] + stats["pending"] + stats["cancelled"]
        if old_total > 0:
            print(f"\n⚠️  Warning: {old_total} reminders still have old status values")
        else:
            print("\n✅ All reminders have been migrated to new status values")
        return

    if args.rollback:
        print("⚠️  ROLLBACK MODE - This will revert status changes\n")
        if args.dry_run:
            print("DRY RUN - No actual changes will be made\n")
        else:
            confirm = input("Are you sure you want to rollback? (yes/no): ")
            if confirm.lower() != "yes":
                print("Rollback cancelled")
                return

        stats = rollback_status(dry_run=args.dry_run)
        print(f"\nRollback {'preview' if args.dry_run else 'results'}:")
        print(f"  - active -> confirmed: {stats['active_to_confirmed']}")
        if stats.get("warning"):
            print(f"\n⚠️  {stats['warning']}")
        return

    # 正常迁移
    if args.dry_run:
        print("DRY RUN - No actual changes will be made\n")
    else:
        print("⚠️  This will modify the database. Make sure you have a backup!\n")
        confirm = input("Continue with migration? (yes/no): ")
        if confirm.lower() != "yes":
            print("Migration cancelled")
            return

    print("Starting migration...\n")
    stats = migrate_status(dry_run=args.dry_run)

    print(f"\nMigration {'preview' if args.dry_run else 'results'}:")
    print(f"  - confirmed -> active: {stats['confirmed_to_active']}")
    print(f"  - pending -> active: {stats['pending_to_active']}")
    print(f"  - cancelled -> completed: {stats['cancelled_to_completed']}")
    print(f"  - Total: {stats['total_migrated']}")

    if stats["errors"]:
        print(f"\n❌ Errors: {stats['errors']}")
    elif not args.dry_run:
        print("\n✅ Migration completed successfully")

    # 验证结果
    if not args.dry_run:
        print("\nVerifying migration results...")
        verify_stats = verify_migration()
        old_total = (
            verify_stats["confirmed"]
            + verify_stats["pending"]
            + verify_stats["cancelled"]
        )
        if old_total > 0:
            print(f"⚠️  Warning: {old_total} reminders still have old status values")
        else:
            print("✅ All reminders have been migrated")


if __name__ == "__main__":
    main()
