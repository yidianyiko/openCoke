# -*- coding: utf-8 -*-
"""
提醒功能初始化脚本
"""
import sys

sys.path.append(".")

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from dao.reminder_dao import ReminderDAO


def init_reminder_feature():
    """初始化提醒功能"""
    logger.info("开始初始化提醒功能...")

    try:
        # 1. 创建 DAO 实例
        dao = ReminderDAO()

        # 2. 创建索引
        logger.info("创建数据库索引...")
        dao.create_indexes()

        # 3. 验证连接
        logger.info("验证数据库连接...")
        test_count = dao.collection.count_documents({})
        logger.info(f"当前提醒记录数: {test_count}")

        # 4. 关闭连接
        dao.close()

        logger.info("✅ 提醒功能初始化完成！")
        logger.info("")
        logger.info("下一步：")
        logger.info("1. 运行测试: python tests/test_reminder_feature.py")
        logger.info(
            "2. 启动后台处理器: python agent / runner/agent_background_handler.py"
        )
        logger.info("3. 查看使用指南: doc/reminder_usage_guide.md")

        return True

    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = init_reminder_feature()
    sys.exit(0 if success else 1)
