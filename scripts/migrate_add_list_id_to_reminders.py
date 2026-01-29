# -*- coding: utf-8 -*-
"""
Migration script: Add list_id field to existing reminders

执行时机：P0 上线前运行一次
执行方式：python scripts/migrate_add_list_id_to_reminders.py
"""

import sys

sys.path.append(".")

from dao.reminder_dao import ReminderDAO
from util.log_util import get_logger

logger = get_logger(__name__)


def migrate_add_list_id():
    """给所有现有 reminders 添加 list_id 字段"""
    dao = ReminderDAO()

    try:
        # 查询没有 list_id 字段的文档数量
        count_query = {"list_id": {"$exists": False}}
        count = dao.collection.count_documents(count_query)

        if count == 0:
            logger.info("No reminders need migration (all have list_id field)")
            return True

        logger.info(f"Found {count} reminders without list_id field")

        # 添加 list_id="inbox" 到所有缺少此字段的文档
        result = dao.collection.update_many(count_query, {"$set": {"list_id": "inbox"}})

        logger.info(f"Migration complete: {result.modified_count} reminders updated")

        # 验证迁移结果
        remaining = dao.collection.count_documents(count_query)
        if remaining > 0:
            logger.error(
                f"Migration incomplete: {remaining} reminders still missing list_id"
            )
            return False

        logger.info(
            "Migration verification passed: all reminders now have list_id field"
        )
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
    finally:
        dao.close()


if __name__ == "__main__":
    success = migrate_add_list_id()
    sys.exit(0 if success else 1)
