# -*- coding: utf-8 -*-
"""
计算LLM调用频率和费用估算脚本

用于统计数据库中的用户数量以及各用户的对话调用次数，从而计算LLM调用频率。

Usage:
    python scripts/calculate_llm_usage.py [--detailed]
"""
import sys

sys.path.append(".")

import argparse
import logging
from datetime import datetime
from logging import getLogger

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = getLogger(__name__)
from dao.conversation_dao import ConversationDAO
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
        from bson import ObjectId

        # 从字符串ID创建ObjectId
        obj_id = ObjectId(user_id)
        # 获取创建时间
        creation_time = obj_id.generation_time.timestamp()
        return creation_time
    except Exception:
        return None


def get_user_first_message_time(mongo_db, user_id):
    """获取用户第一条消息的时间"""
    try:
        # 查找用户最早的一条输入消息
        input_cursor = (
            mongo_db.db["inputmessages"]
            .find({"from_user": user_id})
            .sort("input_timestamp", 1)
            .limit(1)
        )
        input_msgs = list(input_cursor)
        input_msg = input_msgs[0] if input_msgs else None

        # 查找用户最早的一条输出消息
        output_cursor = (
            mongo_db.db["outputmessages"]
            .find({"to_user": user_id})
            .sort("input_timestamp", 1)
            .limit(1)
        )
        output_msgs = list(output_cursor)
        output_msg = output_msgs[0] if output_msgs else None

        # 获取最早的时间戳
        input_time = (
            input_msg.get("input_timestamp", float("in")) if input_msg else float("in")
        )
        output_time = (
            output_msg.get("input_timestamp", float("in"))
            if output_msg
            else float("in")
        )

        first_time = min(input_time, output_time)
        return first_time if first_time != float("in") else None
    except Exception:
        # 如果出现异常，返回None
        return None


def count_user_messages(mongo_db, user_id):
    """统计用户的消息数量"""
    # 统计用户作为发送者的输入消息数量
    input_count = mongo_db.count_documents("inputmessages", {"from_user": user_id})

    # 统计用户作为接收者的输出消息数量
    output_count = mongo_db.count_documents("outputmessages", {"to_user": user_id})

    return input_count, output_count


def count_conversation_messages(mongo_db, conversation_id):
    """统计会话中的消息数量"""
    # 统计会话中的输入消息数量
    input_count = mongo_db.count_documents(
        "inputmessages", {"conversation_id": conversation_id}
    )

    # 统计会话中的输出消息数量
    output_count = mongo_db.count_documents(
        "outputmessages", {"conversation_id": conversation_id}
    )

    return input_count, output_count


def main():
    """主函数：统计用户数量和对话调用次数"""
    parser = argparse.ArgumentParser(description="统计用户数量和对话调用次数")
    parser.add_argument("--detailed", action="store_true", help="显示详细信息")
    parser.parse_args()  # 解析参数但不存储（当前未使用）

    logger.info("开始统计LLM调用频率...")

    # 创建DAO实例
    mongo_db = MongoDBBase()
    user_dao = UserDAO()
    _conversation_dao = ConversationDAO()  # 保留以备将来使用

    try:
        # 获取所有用户
        users = user_dao.find_users()

        if not users:
            logger.info("未找到任何用户")
            return

        total_users = len(users)
        logger.info(f"共找到 {total_users} 个用户")

        # 统计每个用户的消息数量
        user_stats = []
        total_input_messages = 0
        total_output_messages = 0
        total_input_messages_filtered = 0  # 过滤后的输入消息总数
        total_output_messages_filtered = 0  # 过滤后的输出消息总数
        filtered_user_count = 0  # 过滤后的用户数

        import time

        current_time = time.time()

        for user in users:
            user_id = str(user.get("_id", "N/A"))
            user_name = user.get("name", "N/A")

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

            # 获取用户创建时间
            creation_time = get_user_creation_time(user_id)

            # 统计用户的消息数量
            input_count, output_count = count_user_messages(mongo_db, user_id)
            total_count = input_count + output_count

            # 获取用户第一条消息的时间
            first_message_time = get_user_first_message_time(mongo_db, user_id)

            # 计算用户活跃天数
            active_days = 0
            active_weeks = 0
            if first_message_time:
                active_seconds = current_time - first_message_time
                active_days = max(1, active_seconds / (24 * 3600))  # 至少为1天
                active_weeks = max(1, active_days / 7)  # 至少为1周

            # 计算日均和周均调用次数
            daily_avg = total_count/active_days if active_days > 0 else 0
            weekly_avg = total_count/active_weeks if active_weeks > 0 else 0

            total_input_messages += input_count
            total_output_messages += output_count

            user_stats.append(
                {
                    "user_id": user_id,
                    "name": user_name,
                    "wechat_nickname": wechat_nickname,
                    "creation_time": creation_time,
                    "input_count": input_count,
                    "output_count": output_count,
                    "total_count": total_count,
                    "first_message_time": first_message_time,
                    "active_days": active_days,
                    "active_weeks": active_weeks,
                    "daily_avg": daily_avg,
                    "weekly_avg": weekly_avg,
                }
            )
            # 如果用户总调用次数大于等于10，则计入过滤后的统计数据
            if total_count >= 10:
                total_input_messages_filtered += input_count
                total_output_messages_filtered += output_count
                filtered_user_count += 1

        # 按总消息数排序
        user_stats.sort(key=lambda x: x["total_count"], reverse=True)

        # 计算平均调用次数（所有用户）
        avg_total_calls = (
            (total_input_messages + total_output_messages) / total_users
            if total_users > 0
            else 0
        )
        avg_input_calls = total_input_messages / total_users if total_users > 0 else 0
        avg_output_calls = total_output_messages / total_users if total_users > 0 else 0

        # 计算平均调用次数（过滤后用户）
        avg_total_calls_filtered = (
            (total_input_messages_filtered + total_output_messages_filtered)
           /filtered_user_count
            if filtered_user_count > 0
            else 0
        )
        avg_input_calls_filtered = (
            total_input_messages_filtered/filtered_user_count
            if filtered_user_count > 0
            else 0
        )
        avg_output_calls_filtered = (
            total_output_messages_filtered/filtered_user_count
            if filtered_user_count > 0
            else 0
        )

        # 显示统计结果
        print("\n" + "=" * 140)
        print("LLM调用频率统计报告")
        print("=" * 140)
        print(f"统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"总用户数: {total_users}")
        print(f"总输入消息数: {total_input_messages}")
        print(f"总输出消息数: {total_output_messages}")
        print(f"总消息数: {total_input_messages + total_output_messages}")
        print(f"平均每用户总调用次数: {avg_total_calls:.2f}")
        print(f"平均每用户输入调用次数: {avg_input_calls:.2f}")
        print(f"平均每用户输出调用次数: {avg_output_calls:.2f}")
        print("-" * 140)
        print(f"过滤后用户数(调用次数>=10): {filtered_user_count}")
        print(f"过滤后总输入消息数: {total_input_messages_filtered}")
        print(f"过滤后总输出消息数: {total_output_messages_filtered}")
        print(
            f"过滤后总消息数: {total_input_messages_filtered + total_output_messages_filtered}"
        )
        print(f"过滤后平均每用户总调用次数: {avg_total_calls_filtered:.2f}")
        print(f"过滤后平均每用户输入调用次数: {avg_input_calls_filtered:.2f}")
        print(f"过滤后平均每用户输出调用次数: {avg_output_calls_filtered:.2f}")
        print("=" * 140)

        # 显示所有用户信息（按要求列出所有用户）
        print("\n所有用户详细统计:")
        print(
            "{:<24} {:<20} {:<20} {:<20} {:<10} {:<10} {:<10} {:<12} {:<12} {:<12}".format(
                "用户ID",
                "用户名",
                "微信昵称",
                "创建时间",
                "输入消息",
                "输出消息",
                "总计",
                "日均",
                "周均",
                "活跃天数",
            )
        )
        print("-" * 160)

        for stat in user_stats:
            # 格式化活跃天数
            active_days_str = (
                f"{stat['active_days']:.1f}" if stat["active_days"] > 0 else "N/A"
            )
            # 格式化创建时间
            creation_time_str = (
                format_timestamp(stat["creation_time"])
                if stat["creation_time"]
                else "N/A"
            )

            print(
                "{:<24} {:<20} {:<20} {:<20} {:<10} {:<10} {:<10} {:<12.2f} {:<12.2f} {:<12}".format(
                    stat["user_id"][:24],
                    stat["name"][:20],
                    stat["wechat_nickname"][:20],
                    creation_time_str[:20],
                    stat["input_count"],
                    stat["output_count"],
                    stat["total_count"],
                    stat["daily_avg"],
                    stat["weekly_avg"],
                    active_days_str,
                )
            )

        print("=" * 140)

        # 估算费用（这里只是一个示例，实际费用需要根据使用的模型和定价来计算）
        print("\n费用估算参考:")
        print("- 假设每次LLM调用平均消耗 1,000 tokens")
        print("- 假设每百万tokens费用为 $0.50")
        total_tokens = (total_input_messages + total_output_messages) * 1000
        total_tokens_filtered = (
            total_input_messages_filtered + total_output_messages_filtered
        ) * 1000
        estimated_cost = (total_tokens / 1000000) * 0.50
        estimated_cost_filtered = (total_tokens_filtered/1000000) * 0.50
        print(f"- 总token消耗估算: {total_tokens:,}")
        print(f"- 总预估费用: ${estimated_cost:.2f}")
        print(f"- 过滤后token消耗估算: {total_tokens_filtered:,}")
        print(f"- 过滤后预估费用: ${estimated_cost_filtered:.2f}")
        print("=" * 140)

        logger.info("LLM调用频率统计完成")

    except Exception as e:
        logger.error(f"统计过程中发生错误: {e}")
        raise


if __name__ == "__main__":
    main()
