# -*- coding: utf-8 -*-
"""
打印所有用户信息脚本

用于打印数据库中的所有用户信息.

Usage:
    python scripts/print_all_users.py
"""
import sys

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()

import logging
from logging import getLogger

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = getLogger(__name__)

from dao.user_dao import UserDAO


def main():
    """主函数：打印所有用户信息"""
    logger.info("开始获取所有用户信息...")

    # 创建UserDAO实例
    user_dao = UserDAO()

    try:
        # 获取所有用户
        users = user_dao.find_users()

        if not users:
            logger.info("未找到任何用户")
            return

        logger.info(f"共找到 {len(users)} 个用户:")
        print(
            "\n{:<24} {:<15} {:<20} {:<20} {:<10}".format(
                "用户ID", "是否为角色", "用户名", "微信昵称", "状态"
            )
        )
        print("-" * 90)

        for user in users:
            user_id = str(user.get("_id", "N/A"))[:24]
            is_character = "是" if user.get("is_character", False) else "否"
            name = user.get("name", "N/A")[:20]

            # 获取微信相关信息
            platforms = user.get("platforms", {})
            wechat_info = (
                platforms.get("wechat", {}) if isinstance(platforms, dict) else {}
            )
            wechat_nickname = (
                wechat_info.get("nickname", "N/A")
                if isinstance(wechat_info, dict)
                else "N/A"
            )
            wechat_nickname = wechat_nickname[:20]

            status = user.get("status", "N/A")[:10]

            print(
                "{:<24} {:<15} {:<20} {:<20} {:<10}".format(
                    user_id, is_character, name, wechat_nickname, status
                )
            )

        logger.info("用户信息打印完成")

    except Exception as e:
        logger.error(f"获取用户信息时发生错误: {e}")
        raise


if __name__ == "__main__":
    main()
