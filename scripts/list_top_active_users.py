# -*- coding: utf-8 -*-
"""
列出最活跃用户脚本

列出最活跃的用户，显示微信号、昵称、最近活跃时间、创建时间。

Usage:
    python scripts/list_top_active_users.py [--top N]
"""
import sys

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()

import argparse
from datetime import datetime

from util.log_util import get_logger

logger = get_logger(__name__)

from bson import ObjectId

from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO


def format_timestamp(timestamp):
    """将时间戳格式化为可读日期"""
    if not timestamp:
        return "N/A"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, TypeError):
        return str(timestamp)


def get_user_creation_time(user_id):
    """从用户ID的ObjectId中提取创建时间"""
    try:
        obj_id = ObjectId(user_id)
        creation_time = obj_id.generation_time.timestamp()
        return creation_time
    except Exception:
        return None


def get_user_last_message_time(mongo_db, user_id):
    """获取用户最后一条消息的时间"""
    try:
        # 查找用户最晚的一条输入消息
        input_cursor = (
            mongo_db.db["inputmessages"]
            .find({"from_user": user_id})
            .sort("input_timestamp", -1)
            .limit(1)
        )
        input_msgs = list(input_cursor)
        input_msg = input_msgs[0] if input_msgs else None

        # 查找用户最晚的一条输出消息
        output_cursor = (
            mongo_db.db["outputmessages"]
            .find({"to_user": user_id})
            .sort("input_timestamp", -1)
            .limit(1)
        )
        output_msgs = list(output_cursor)
        output_msg = output_msgs[0] if output_msgs else None

        # 获取最晚的时间戳
        input_time = (
            input_msg.get("input_timestamp", -float("inf"))
            if input_msg
            else -float("inf")
        )
        output_time = (
            output_msg.get("input_timestamp", -float("inf"))
            if output_msg
            else -float("inf")
        )

        last_time = max(input_time, output_time)
        return last_time if last_time != -float("inf") else None
    except Exception:
        return None


def count_user_messages(mongo_db, user_id):
    """统计用户的消息数量"""
    # 统计用户作为发送者的输入消息数量
    input_count = mongo_db.count_documents("inputmessages", {"from_user": user_id})

    # 统计用户作为接收者的输出消息数量
    output_count = mongo_db.count_documents("outputmessages", {"to_user": user_id})

    return input_count, output_count


def list_top_active_users(top_n=50):
    """列出最活跃的用户"""
    logger.info(f"开始获取最活跃的 {top_n} 个用户...")

    # 创建DAO实例
    mongo_db = MongoDBBase()
    user_dao = UserDAO()

    try:
        # 获取所有非角色用户
        users = user_dao.find_users(query={"is_character": {"$ne": True}})

        if not users:
            logger.info("未找到任何用户")
            return

        total_users = len(users)
        logger.info(f"共找到 {total_users} 个用户，正在分析...")

        # 存储用户数据
        user_data = []

        for user in users:
            user_id = str(user.get("_id", "N/A"))

            # 获取微信相关信息
            platforms = user.get("platforms", {})
            wechat_info = (
                platforms.get("wechat", {}) if isinstance(platforms, dict) else {}
            )
            wechat_id = (
                wechat_info.get("id", "N/A")
                if isinstance(wechat_info, dict)
                else "N/A"
            )
            wechat_nickname = (
                wechat_info.get("nickname", "N/A")
                if isinstance(wechat_info, dict)
                else "N/A"
            )

            # 获取用户创建时间
            creation_time = get_user_creation_time(user_id)

            # 统计用户的消息数量
            input_count, output_count = count_user_messages(mongo_db, user_id)
            total_count = input_count + output_count

            # 获取用户最后一条消息的时间
            last_message_time = get_user_last_message_time(mongo_db, user_id)

            user_data.append(
                {
                    "user_id": user_id,
                    "wechat_id": wechat_id,
                    "nickname": wechat_nickname,
                    "input_count": input_count,
                    "output_count": output_count,
                    "total_count": total_count,
                    "last_active_time": last_message_time,
                    "creation_time": creation_time,
                }
            )

        # 按总消息数排序，获取前N名
        user_data.sort(key=lambda x: x["total_count"], reverse=True)
        top_users = user_data[:top_n]

        # 打印结果
        print("\n" + "=" * 140)
        print(f"最活跃的 {top_n} 个用户")
        print("=" * 140)
        print(
            "{:<4} {:<26} {:<20} {:<10} {:<10} {:<22} {:<22}".format(
                "排名",
                "微信号",
                "昵称",
                "输入消息",
                "输出消息",
                "最近活跃时间",
                "创建时间",
            )
        )
        print("-" * 140)

        for i, user in enumerate(top_users, 1):
            wechat_id = user["wechat_id"][:24] if user["wechat_id"] else "N/A"
            nickname = user["nickname"][:18] if user["nickname"] else "N/A"
            last_active_str = (
                format_timestamp(user["last_active_time"])
                if user["last_active_time"]
                else "N/A"
            )
            creation_str = (
                format_timestamp(user["creation_time"])
                if user["creation_time"]
                else "N/A"
            )

            print(
                "{:<4} {:<26} {:<20} {:<10} {:<10} {:<22} {:<22}".format(
                    i,
                    wechat_id,
                    nickname,
                    user["input_count"],
                    user["output_count"],
                    last_active_str,
                    creation_str,
                )
            )

        print("=" * 140)
        logger.info("分析完成")

    except Exception as e:
        logger.error(f"获取用户信息时发生错误: {e}")
        raise


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="列出最活跃的用户")
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="显示前N名最活跃用户（默认: 50）",
    )
    args = parser.parse_args()

    list_top_active_users(top_n=args.top)


if __name__ == "__main__":
    main()
