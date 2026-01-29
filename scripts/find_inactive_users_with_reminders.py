#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查找指定天数内未发送消息但仍有未触发提醒的用户

此脚本用于查找满足以下条件的用户：
1. 最后发送消息时间在指定天数前或更早
2. 仍有状态为"active"的未触发提醒
"""

import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.append(".")

from dao.mongo import MongoDBBase
from dao.reminder_dao import ReminderDAO
from dao.user_dao import UserDAO


def get_user_last_message_time(mongo_db: MongoDBBase, user_id: str) -> Optional[float]:
    """获取用户最后一条输入消息的时间"""
    try:
        cursor = (
            mongo_db.db["inputmessages"]
            .find({"from_user": user_id})
            .sort("input_timestamp", -1)
            .limit(1)
        )
        msgs = list(cursor)
        if msgs:
            return msgs[0].get("input_timestamp")
    except Exception as e:
        print(f"获取用户 {user_id} 最后消息时间时出错: {e}")
        pass
    return None


def find_inactive_users_with_reminders(days_threshold: int = 7) -> List[Dict]:
    """
    查找指定天数内未发送消息但仍有未触发提醒的用户

    Args:
        days_threshold: 天数阈值，默认为7天

    Returns:
        List[Dict]: 包含用户信息和提醒信息的列表
    """
    print(f"正在查找{days_threshold}天内未发送消息但仍有未触发提醒的用户...")

    # 计算时间阈值
    threshold_time = datetime.now() - timedelta(days=days_threshold)
    threshold_timestamp = int(threshold_time.timestamp())

    # 初始化数据库连接
    mongo_db = MongoDBBase()
    reminder_dao = ReminderDAO()
    user_dao = UserDAO()

    try:
        # 获取所有非角色用户
        users = user_dao.find_users(query={"is_character": {"$ne": True}})
        print(f"总共找到 {len(users)} 个用户")

        result = []

        for user in users:
            user_id = str(user.get("_id", ""))
            if not user_id:
                continue

            # 获取用户最后消息时间
            last_msg_time = get_user_last_message_time(mongo_db, user_id)

            # 检查用户是否超过指定天数未发送消息
            if last_msg_time is None or last_msg_time <= threshold_timestamp:
                # 获取用户的所有活动提醒
                active_reminders = reminder_dao.find_reminders_by_user(
                    user_id=user_id, status="active"
                )

                if active_reminders:
                    user_info = {
                        "user_id": user_id,
                        "name": user.get("name", "N/A"),
                        "last_message_time": last_msg_time,
                        "last_message_friendly": (
                            datetime.fromtimestamp(last_msg_time).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                            if last_msg_time
                            else "N/A"
                        ),
                        "days_since_last_message": (
                            (time.time() - last_msg_time) / (24 * 3600)
                            if last_msg_time
                            else float("inf")
                        ),
                        "active_reminder_count": len(active_reminders),
                        "active_reminders": active_reminders,
                    }
                    result.append(user_info)

        return result

    finally:
        mongo_db.close()
        reminder_dao.close()


def print_results(results: List[Dict], days_threshold: int = 7):
    """打印结果"""
    if not results:
        print(f"\n✅ 没有找到{days_threshold}天内未发送消息但仍有未触发提醒的用户")
        return

    print(
        f"\n⚠️  发现 {len(results)} 个用户{days_threshold}天内未发送消息但仍有未触发提醒："
    )
    print("=" * 120)

    for i, user_info in enumerate(results, 1):
        print(f"\n[{i}] 用户信息:")
        print(f"     用户ID: {user_info['user_id']}")
        print(f"     用户名: {user_info['name']}")
        print(
            f"     最后消息时间: {user_info['last_message_friendly']} ({user_info['days_since_last_message']:.1f}天前)"
        )
        print(f"     活跃提醒数量: {user_info['active_reminder_count']}")

        print(f"     活跃提醒详情:")
        for j, reminder in enumerate(user_info["active_reminders"], 1):
            title = reminder.get("title", "无标题")
            next_trigger_time = reminder.get("next_trigger_time")
            trigger_time_friendly = (
                datetime.fromtimestamp(next_trigger_time).strftime("%Y-%m-%d %H:%M:%S")
                if next_trigger_time
                else "N/A"
            )
            reminder_id = reminder.get("reminder_id", "N/A")
            print(
                f"       [{j}] {title} (ID: {reminder_id}, 触发时间: {trigger_time_friendly})"
            )

        print("-" * 120)


import argparse


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="查找指定天数内未发送消息但仍有未触发提醒的用户"
    )
    parser.add_argument("--days", type=int, default=5, help="天数阈值，默认为5天")
    args = parser.parse_args()

    print(f"🔍 查找{args.days}天内未发送消息但仍有未触发提醒的用户")
    print("=" * 60)

    results = find_inactive_users_with_reminders(days_threshold=args.days)
    print_results(results, days_threshold=args.days)


if __name__ == "__main__":
    main()
