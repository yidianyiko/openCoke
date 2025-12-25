# -*- coding: utf-8 -*-
"""
查询指定用户的历史消息脚本

用于查询指定用户的历史消息，默认按时间倒序显示最近的消息.

Usage:
    python scripts/query_user_messages.py --user - id USER_ID [--limit LIMIT] [--recent]
"""
import sys

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()

import argparse
import logging
from datetime import datetime
from logging import getLogger

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = getLogger(__name__)

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


def main():
    """主函数：查询指定用户的历史消息"""
    parser = argparse.ArgumentParser(description="查询指定用户的历史消息")
    parser.add_argument("--user - id", required=True, help="用户ID")
    parser.add_argument(
        "--limit", type=int, default=20, help="返回消息数量限制（默认20条）"
    )
    parser.add_argument(
        "--recent",
        action="store_true",
        help="按时间倒序排列，显示最近的消息（默认是按时间倒序）",
    )
    args = parser.parse_args()

    logger.info(f"开始查询用户 {args.user_id} 的历史消息...")

    # 创建DAO实例
    mongo = MongoDBBase()
    user_dao = UserDAO()

    try:
        # 验证用户是否存在
        user = user_dao.get_user_by_id(args.user_id)
        if not user:
            logger.error(f"用户 {args.user_id} 不存在")
            return

        user_name = user.get("name", "N/A")
        logger.info(f"找到用户: {user_name}")

        # 查询用户的输入消息（作为发送者），按时间倒序排列
        input_pipeline = [
            {"$match": {"from_user": args.user_id}},
            {"$sort": {"input_timestamp": -1}},
            {"$limit": args.limit},
        ]
        input_messages = mongo.aggregate("inputmessages", input_pipeline)

        # 查询用户的输出消息（作为接收者），按时间倒序排列
        output_pipeline = [
            {"$match": {"to_user": args.user_id}},
            {"$sort": {"input_timestamp": -1}},
            {"$limit": args.limit},
        ]
        output_messages = mongo.aggregate("outputmessages", output_pipeline)

        # 合并并排序消息
        all_messages = []

        for msg in input_messages:
            msg["direction"] = "发送"
            all_messages.append(msg)

        for msg in output_messages:
            msg["direction"] = "接收"
            all_messages.append(msg)

        # 按时间戳排序（最新的在前）
        all_messages.sort(key=lambda x: x.get("input_timestamp", 0), reverse=True)

        # 限制数量
        all_messages = all_messages[: args.limit]

        if not all_messages:
            logger.info(f"用户 {user_name} ({args.user_id}) 没有找到任何消息")
            return

        logger.info(f"找到 {len(all_messages)} 条消息:")
        print(f"\n用户 {user_name} ({args.user_id}) 的消息历史:")
        print("=" * 100)
        print(
            "{:<20} {:<10} {:<20} {:<15} {:<30}".format(
                "时间", "方向", "消息类型", "状态", "消息内容"
            )
        )
        print("-" * 100)

        for msg in all_messages:
            timestamp = format_timestamp(msg.get("input_timestamp"))
            direction = msg.get("direction", "N/A")
            message_type = (msg.get("message_type", "N/A") or "N/A")[:20]
            status = (msg.get("status", "N/A") or "N/A")[:15]
            message_content = (msg.get("message", "") or "")[:30].replace("\n", " ")

            print(
                "{:<20} {:<10} {:<20} {:<15} {:<30}".format(
                    timestamp, direction, message_type, status, message_content
                )
            )

        print("=" * 100)
        logger.info("消息查询完成")

    except Exception as e:
        logger.error(f"查询用户消息时发生错误: {e}")
        raise


if __name__ == "__main__":
    main()
