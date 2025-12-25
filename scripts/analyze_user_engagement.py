# -*- coding: utf-8 -*-
"""
用户参与度分析脚本

分析用户注册后的活跃持续时间、留存模式和生命周期模式。

Usage:
    python scripts/analyze_user_engagement.py
"""
import sys

sys.path.append(".")

import argparse
import logging
from datetime import datetime, timedelta
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
            input_msg.get("input_timestamp", -float("in"))
            if input_msg
            else -float("in")
        )
        output_time = (
            output_msg.get("input_timestamp", -float("in"))
            if output_msg
            else -float("in")
        )

        last_time = max(input_time, output_time)
        return last_time if last_time != -float("in") else None
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


def categorize_user_engagement(total_messages):
    """根据总消息数对用户参与度进行分类"""
    if total_messages == 0:
        return "Non - active"
    elif total_messages < 5:
        return "One - time"
    elif total_messages < 20:
        return "Occasional"
    elif total_messages < 100:
        return "Regular"
    else:
        return "Highly Active"


def calculate_average_usage(user_data, current_time):
    """计算每个用户的平均日、周、月调用量"""
    for user in user_data:
        # 计算用户活跃周期
        if user["first_message_time"] and user["last_message_time"]:
            active_duration_days = (
                user["last_message_time"] - user["first_message_time"]
            )/86400
            # 至少活跃1天才能计算平均值
            if active_duration_days >= 1:
                # 计算平均每日调用量
                user["avg_daily_usage"] = user["total_count"] / active_duration_days

                # 计算平均每周调用量
                active_duration_weeks = active_duration_days/7
                user["avg_weekly_usage"] = (
                    user["total_count"] / active_duration_weeks
                    if active_duration_weeks > 0
                    else 0
                )

                # 计算平均每月调用量
                active_duration_months = (
                    active_duration_days/30
                )  # 简化按30天一个月计算
                user["avg_monthly_usage"] = (
                    user["total_count"]/active_duration_months
                    if active_duration_months > 0
                    else 0
                )
            else:
                user["avg_daily_usage"] = user["total_count"]
                user["avg_weekly_usage"] = user["total_count"] * 7
                user["avg_monthly_usage"] = user["total_count"] * 30
        else:
            # 如果没有明确的活动时间范围，默认为0
            user["avg_daily_usage"] = 0
            user["avg_weekly_usage"] = 0
            user["avg_monthly_usage"] = 0

    return user_data


def analyze_user_engagement():
    """分析用户参与度"""
    logger.info("开始分析用户参与度...")

    # 创建DAO实例
    mongo_db = MongoDBBase()
    user_dao = UserDAO()

    try:
        # 获取所有用户
        users = user_dao.find_users()

        if not users:
            logger.info("未找到任何用户")
            return

        total_users = len(users)
        logger.info(f"共找到 {total_users} 个用户")

        # 存储用户数据用于分析
        user_data = []

        import time

        current_time = time.time()

        for user in users:
            user_id = str(user.get("_id", "N/A"))
            user_name = user.get("name", "N/A")

            # 获取用户创建时间
            creation_time = get_user_creation_time(user_id)

            # 统计用户的消息数量
            input_count, output_count = count_user_messages(mongo_db, user_id)
            total_count = input_count + output_count

            # 获取用户第一条和最后一条消息的时间
            first_message_time = get_user_first_message_time(mongo_db, user_id)
            last_message_time = get_user_last_message_time(mongo_db, user_id)

            # 计算参与度分类
            engagement_category = categorize_user_engagement(total_count)

            user_data.append(
                {
                    "user_id": user_id,
                    "name": user_name,
                    "creation_time": creation_time,
                    "input_count": input_count,
                    "output_count": output_count,
                    "total_count": total_count,
                    "first_message_time": first_message_time,
                    "last_message_time": last_message_time,
                    "engagement_category": engagement_category,
                    "avg_daily_usage": 0,
                    "avg_weekly_usage": 0,
                    "avg_monthly_usage": 0,
                }
            )

        # 计算平均使用量
        user_data = calculate_average_usage(user_data, current_time)

        # 显示所有用户的基本信息
        print("\n" + "=" * 160)
        print("所有用户基本信息")
        print("=" * 160)
        print(
            "{:<24} {:<20} {:<20} {:<20} {:<20} {:<10} {:<10} {:<10} {:<10} {:<10} {:<10}".format(
                "用户ID",
                "用户名",
                "创建时间",
                "首次活动时间",
                "最后活动时间",
                "输入消息",
                "输出消息",
                "总计",
                "日均",
                "周均",
                "月均",
            )
        )
        print("-" * 160)

        for user in user_data:
            creation_time_str = (
                format_timestamp(user["creation_time"])
                if user["creation_time"]
                else "N/A"
            )
            first_message_str = (
                format_timestamp(user["first_message_time"])
                if user["first_message_time"]
                else "N/A"
            )
            last_message_str = (
                format_timestamp(user["last_message_time"])
                if user["last_message_time"]
                else "N/A"
            )

            print(
                "{:<24} {:<20} {:<20} {:<20} {:<20} {:<10} {:<10} {:<10} {:<10.2f} {:<10.2f} {:<10.2f}".format(
                    user["user_id"][:24],
                    user["name"][:20],
                    creation_time_str[:20],
                    first_message_str[:20],
                    last_message_str[:20],
                    user["input_count"],
                    user["output_count"],
                    user["total_count"],
                    user["avg_daily_usage"],
                    user["avg_weekly_usage"],
                    user["avg_monthly_usage"],
                )
            )

        # 分析1: 日增长趋势分析
        print("\n" + "=" * 100)
        print("日增长趋势分析")
        print("=" * 100)

        # 按日期统计新用户注册数
        daily_registration = {}
        daily_activity = {}

        for user in user_data:
            # 统计每日注册用户数
            if user["creation_time"]:
                creation_date = datetime.fromtimestamp(user["creation_time"]).date()
                daily_registration[creation_date] = (
                    daily_registration.get(creation_date, 0) + 1
                )

            # 统计每日活跃用户数
            if user["last_message_time"]:
                last_activity_date = datetime.fromtimestamp(
                    user["last_message_time"]
                ).date()
                daily_activity[last_activity_date] = (
                    daily_activity.get(last_activity_date, 0) + 1
                )

        # 显示最近14天的增长趋势
        from datetime import timedelta

        today = datetime.now().date()
        print("最近14天用户注册趋势:")
        print("日期         | 新注册用户 | 活跃用户")
        print("-------------|-----------|----------")
        for i in range(13, -1, -1):  # 从13天前到今天
            date = today - timedelta(days=i)
            registrations = daily_registration.get(date, 0)
            active_users = daily_activity.get(date, 0)
            print(f"{date} | {registrations:10} | {active_users:8}")

        # 分析2: 用户留存模式
        print("\n" + "=" * 100)
        print("用户留存模式分析")
        print("=" * 100)

        # 统计各类用户数量
        category_counts = {}
        for user in user_data:
            category = user["engagement_category"]
            category_counts[category] = category_counts.get(category, 0) + 1

        single_session_users = category_counts.get("One - time", 0)
        ongoing_engagement_users = (
            category_counts.get("Occasional", 0)
            + category_counts.get("Regular", 0)
            + category_counts.get("Highly Active", 0)
        )
        non_active_users = category_counts.get("Non - active", 0)

        print(
            f"从未使用服务的用户 (Non - active): {non_active_users} ({non_active_users/total_users * 100:.2f}%)"
        )
        print(
            f"一次性用户 (One - time): {single_session_users} ({single_session_users/total_users * 100:.2f}%)"
        )
        print(
            f"持续参与用户 (Occasional/Regular/Highly Active): {ongoing_engagement_users} ({ongoing_engagement_users/total_users * 100:.2f}%)"
        )

        print("\n用户参与度详细分类:")
        for category, count in category_counts.items():
            print(f"  {category}: {count} ({count/total_users * 100:.2f}%)")

        # 分析3: 基于注册时间的用户生命周期模式
        print("\n" + "=" * 100)
        print("基于注册时间的用户生命周期分析")
        print("=" * 100)

        # 按注册周分组用户
        users_by_registration_week = {}
        for user in user_data:
            if user["creation_time"]:
                creation_date = datetime.fromtimestamp(user["creation_time"]).date()
                # 计算是第几周注册的（相对于今天）
                days_since_creation = (today - creation_date).days
                week_since_creation = days_since_creation // 7
                # 确保不会出现负数周
                week_key = max(0, week_since_creation)
                if week_key not in users_by_registration_week:
                    users_by_registration_week[week_key] = []
                users_by_registration_week[week_key].append(user)

        print("按注册周分组的用户活跃度分析:")
        print("注册周 | 注册用户数 | 活跃用户数 | 活跃率 | 说明")
        print(
            "-------|------------|------------|--------|----------------------------------"
        )
        for week in sorted(users_by_registration_week.keys()):
            registered_users = len(users_by_registration_week[week])
            # 统计这一批用户中有多少最近仍在活跃
            active_users = 0
            for user in users_by_registration_week[week]:
                # 如果用户在过去7天内有活动，则认为是活跃的
                if user["last_message_time"]:
                    days_since_last_activity = (
                        current_time - user["last_message_time"]
                    ) / 86400
                    if days_since_last_activity <= 7:  # 一周内有活动
                        active_users += 1

            active_rate = (
                (active_users/registered_users * 100) if registered_users > 0 else 0
            )
            week_label = "本周" if week == 0 else f"{week}周前"
            explanation = "当前仍活跃用户占比（最近7天内有活动）"
            print(
                f"{week_label:6} | {registered_users:10} | {active_users:10} | {active_rate:6.1f}% | {explanation}"
            )

        print("\n说明：活跃率 = 最近7天内有活动的用户数/该时间段注册的总用户数")
        print("     这反映了不同时间段注册用户的当前留存情况")

        # 分析4: 不同注册时期的用户留存情况
        print("\n" + "=" * 100)
        print("不同注册时期的用户留存分析")
        print("=" * 100)

        # 定义时间分段
        time_segments = {
            "最近1周": 7,
            "1 - 2周前": 14,
            "2 - 4周前": 28,
            "1 - 2个月前": 60,
            "2 - 3个月前": 90,
            "3个月前": 91,  # 91天及以上
        }

        segment_stats = {}
        for segment, days in time_segments.items():
            segment_stats[segment] = {"registered": 0, "active": 0}

        for user in user_data:
            if user["creation_time"]:
                days_since_creation = (current_time - user["creation_time"])/86400
                # 归类到对应的时间段
                if days_since_creation <= 7:
                    segment = "最近1周"
                elif days_since_creation <= 14:
                    segment = "1 - 2周前"
                elif days_since_creation <= 28:
                    segment = "2 - 4周前"
                elif days_since_creation <= 60:
                    segment = "1 - 2个月前"
                elif days_since_creation <= 90:
                    segment = "2 - 3个月前"
                else:
                    segment = "3个月前"

                segment_stats[segment]["registered"] += 1
                # 检查用户最近是否活跃（最近7天内有活动）
                if user["last_message_time"]:
                    days_since_last_activity = (
                        current_time - user["last_message_time"]
                    )/86400
                    if days_since_last_activity <= 7:
                        segment_stats[segment]["active"] += 1

        print("不同注册时期的用户留存情况:")
        print("注册时期     | 注册用户数 | 近期活跃用户数 | 留存率 | 说明")
        print(
            "-------------|------------|----------------|--------|----------------------------------"
        )
        for segment, stats in segment_stats.items():
            registered = stats["registered"]
            active = stats["active"]
            retention_rate = (active/registered * 100) if registered > 0 else 0
            print(
                f"{segment:12} | {registered:10} | {active:14} | {retention_rate:6.1f}% | 最近7天内有活动的用户占比"
            )

        print(
            "\n说明：留存率 = 不同时间段注册用户中，当前仍活跃的用户比例（最近7天内有活动）"
        )
        print("     例如：'1 - 2周前'注册的用户中，有47.4%在最近7天内仍有活动")

        # 分析5: 平均使用量统计
        print("\n" + "=" * 100)
        print("用户平均使用量统计")
        print("=" * 100)

        # 过滤掉没有活动记录的用户
        active_users = [u for u in user_data if u["total_count"] > 0]

        if active_users:
            avg_daily = sum(u["avg_daily_usage"] for u in active_users)/len(
                active_users
            )
            avg_weekly = sum(u["avg_weekly_usage"] for u in active_users)/len(
                active_users
            )
            avg_monthly = sum(u["avg_monthly_usage"] for u in active_users)/len(
                active_users
            )

            print(f"所有活跃用户的平均日调用量: {avg_daily:.2f}")
            print(f"所有活跃用户的平均周调用量: {avg_weekly:.2f}")
            print(f"所有活跃用户的平均月调用量: {avg_monthly:.2f}")

            # 按参与度分类显示平均使用量
            print("\n按参与度分类的平均使用量:")
            categories = {}
            for user in active_users:
                category = user["engagement_category"]
                if category not in categories:
                    categories[category] = []
                categories[category].append(user)

            for category, users in categories.items():
                avg_daily_cat = sum(u["avg_daily_usage"] for u in users)/len(users)
                avg_weekly_cat = sum(u["avg_weekly_usage"] for u in users)/len(users)
                avg_monthly_cat = sum(u["avg_monthly_usage"] for u in users)/len(
                    users
                )
                print(
                    f"  {category}: 日均 {avg_daily_cat:.2f}, 周均 {avg_weekly_cat:.2f}, 月均 {avg_monthly_cat:.2f}"
                )
        else:
            print("没有活跃用户数据可供统计")

        print("=" * 100)
        logger.info("用户参与度分析完成")

    except Exception as e:
        logger.error(f"分析过程中发生错误: {e}")
        raise


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="分析用户参与度模式")
    parser.parse_args()  # 解析参数但不存储（当前未使用）

    analyze_user_engagement()


if __name__ == "__main__":
    main()
