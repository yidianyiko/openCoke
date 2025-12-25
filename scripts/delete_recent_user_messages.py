# -*- coding: utf-8 -*-
"""
删除指定用户最近历史消息脚本

用于删除指定用户最近的10条历史消息.

Usage:
    python scripts/delete_recent_user_messages.py --user - id USER_ID [--count COUNT]
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
    """主函数：删除指定用户最近的10条历史消息"""
    parser = argparse.ArgumentParser(description="删除指定用户最近的历史消息")
    parser.add_argument("--user - id", required=True, help="用户ID")
    parser.add_argument(
        "--count", type=int, default=10, help="要删除的消息数量（默认10条）"
    )
    args = parser.parse_args()

    logger.info(f"开始删除用户 {args.user_id} 的最近 {args.count} 条消息...")

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
        # 使用聚合管道按时间戳排序并限制数量
        input_pipeline = [
            {"$match": {"from_user": args.user_id}},
            {"$sort": {"input_timestamp": -1}},
            {"$limit": args.count},
        ]
        input_messages = mongo.aggregate("inputmessages", input_pipeline)

        # 查询用户的输出消息（作为接收者），按时间倒序排列
        output_pipeline = [
            {"$match": {"to_user": args.user_id}},
            {"$sort": {"input_timestamp": -1}},
            {"$limit": args.count},
        ]
        output_messages = mongo.aggregate("outputmessages", output_pipeline)

        # 合并消息并再次排序，确保我们处理的是最新的消息
        all_messages = input_messages + output_messages
        all_messages.sort(key=lambda x: x.get("input_timestamp", 0), reverse=True)
        all_messages = all_messages[: args.count]

        if not all_messages:
            logger.info(f"用户 {user_name} ({args.user_id}) 没有找到任何消息")
            return

        logger.info(f"找到 {len(all_messages)} 条最新消息，准备删除...")

        # 显示将要删除的消息
        print(
            f"\n将要删除用户 {user_name} ({args.user_id}) 的 {len(all_messages)} 条最新消息:"
        )
        print("=" * 100)
        print(
            "{:<24} {:<20} {:<10} {:<20} {:<15} {:<30}".format(
                "消息ID", "时间", "方向", "消息类型", "状态", "消息内容"
            )
        )
        print("-" * 100)

        message_ids_to_delete = []
        for msg in all_messages:
            message_id = str(msg.get("_id", "N/A"))
            timestamp = format_timestamp(msg.get("input_timestamp"))
            direction = "发送" if "from_user" in msg else "接收"
            message_type = (msg.get("message_type", "N/A") or "N/A")[:20]
            status = (msg.get("status", "N/A") or "N/A")[:15]
            message_content = (msg.get("message", "") or "")[:30].replace("\n", " ")

            collection_name = (
                "inputmessages" if "from_user" in msg else "outputmessages"
            )
            message_ids_to_delete.append((message_id, collection_name))

            print(
                "{:<24} {:<20} {:<10} {:<20} {:<15} {:<30}".format(
                    message_id[:24],
                    timestamp,
                    direction,
                    message_type,
                    status,
                    message_content,
                )
            )
        print("=" * 100)

        # 确认删除
        confirm = input(f"\n确认删除这 {len(all_messages)} 条消息吗？(y/N): ")
        if confirm.lower() != "y":
            logger.info("用户取消删除操作")
            return

        # 执行删除
        deleted_count = 0
        for message_id, collection_name in message_ids_to_delete:
            try:
                from bson import ObjectId

                result = mongo.delete_one(
                    collection_name, {"_id": ObjectId(message_id)}
                )
                if result > 0:
                    deleted_count += 1
                    logger.info(f"成功删除消息 {message_id}")
                else:
                    logger.warning(f"未能删除消息 {message_id}")
            except Exception as e:
                logger.error(f"删除消息 {message_id} 时发生错误: {e}")
        logger.info(
            f"删除操作完成，成功删除 {deleted_count}/{len(all_messages)} 条消息"
        )

    except Exception as e:
        logger.error(f"删除用户消息时发生错误: {e}")
        raise


if __name__ == "__main__":
    main()
