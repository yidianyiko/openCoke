# -*- coding: utf-8 -*-
"""
查看数据库中的未来主动消息 (Future Proactive Messages)

用于查看当前数据库中配置了 future 主动消息的所有会话.

Usage:
    python scripts/check_future_messages.py [--all] [--pending] [--due] [--expired]

Options:
    --all       显示所有有 future 配置的会话（包括 timestamp 为 None 的）
    --pending   仅显示待发送的未来消息（timestamp 不为空且未到期）
    --due       仅显示已到期等待触发的消息
    --expired   仅显示已过期的消息（主动消息次数达到上限）
    无参数      默认显示所有有效的未来消息（timestamp 不为 None）
"""
import sys

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()

import argparse
import time
from datetime import datetime

from tabulate import tabulate

from dao.conversation_dao import ConversationDAO
from dao.user_dao import UserDAO


def format_timestamp(ts):
    """格式化时间戳为可读字符串"""
    if ts is None:
        return "未设置"
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def get_time_status(ts, status=None):
    """获取时间状态（已到期/待触发/已过期）"""
    # 如果 status 是 expired，优先显示
    if status == "expired":
        return "已过期(次数上限)"

    if ts is None:
        return "无计划"
    now = int(time.time())
    if ts <= now:
        diff = now - ts
        if diff < 60:
            return f"已到期 ({diff}秒前)"
        elif diff < 3600:
            return f"已到期 ({diff // 60}分钟前)"
        else:
            return f"已到期 ({diff // 3600}小时前)"
    else:
        diff = ts - now
        if diff < 60:
            return f"待触发 ({diff}秒后)"
        elif diff < 3600:
            return f"待触发 ({diff // 60}分钟后)"
        elif diff < 86400:
            return f"待触发 ({diff // 3600}小时后)"
        else:
            return f"待触发 ({diff // 86400}天后)"


def get_talker_names(talkers, user_dao):
    """获取会话参与者名称"""
    names = []
    for talker in talkers:
        talker_id = talker.get("id", "")
        nickname = talker.get("nickname", "未知")

        # 尝试从数据库获取更多信息
        try:
            user = user_dao.get_user_by_id(talker_id)
            if user:
                is_char = user.get("is_character", False)
                role = "角色" if is_char else "用户"
                name = (
                    user.get("platforms", {})
                    .get("wechat", {})
                    .get("nickname", nickname)
                )
                names.append(f"{name} ({role})")
            else:
                names.append(nickname)
        except Exception:
            names.append(nickname)
    return " <-> ".join(names)


def main():
    parser = argparse.ArgumentParser(description="查看数据库中的未来主动消息")
    parser.add_argument(
        "--all", action="store_true", help="显示所有有 future 配置的会话"
    )
    parser.add_argument("--pending", action="store_true", help="仅显示待发送的未来消息")
    parser.add_argument("--due", action="store_true", help="仅显示已到期等待触发的消息")
    parser.add_argument(
        "--expired",
        action="store_true",
        help="仅显示已过期的消息（主动消息次数达到上限）",
    )
    args = parser.parse_args()

    conversation_dao = ConversationDAO()
    user_dao = UserDAO()

    now = int(time.time())

    # 构建查询条件
    if args.all:
        # 显示所有有 future 字段的会话
        query = {
            "$or": [
                {"conversation_info.future.timestamp": {"$exists": True}},
                {"conversation_info.future.action": {"$exists": True}},
            ]
        }
        title = "所有配置了 future 的会话"
    elif args.pending:
        # 仅显示待发送的（timestamp > now）
        query = {
            "conversation_info.future.timestamp": {
                "$exists": True,
                "$ne": None,
                "$gt": now,
            }
        }
        title = "待发送的未来消息"
    elif args.due:
        # 仅显示已到期的（timestamp <= now 且未过期）
        query = {
            "conversation_info.future.timestamp": {
                "$exists": True,
                "$ne": None,
                "$lte": now,
            },
            "conversation_info.future.status": {"$ne": "expired"},
        }
        title = "已到期等待触发的消息"
    elif args.expired:
        # 仅显示已过期的
        query = {"conversation_info.future.status": "expired"}
        title = "已过期的主动消息（次数达到上限）"
    else:
        # 默认：显示所有有效的（timestamp 不为 None）
        query = {"conversation_info.future.timestamp": {"$exists": True, "$ne": None}}
        title = "有效的未来主动消息"

    print("\n" + "=" * 80)
    print(f" {title}")
    print(f" 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conversations = conversation_dao.find_conversations(query)

    if not conversations:
        print("\n  未找到符合条件的会话.\n")
        return

    print(f"\n  找到 {len(conversations)} 条记录:\n")

    # 准备表格数据
    table_data = []
    for conv in conversations:
        conv_id = str(conv.get("_id", ""))
        future = conv.get("conversation_info", {}).get("future", {})

        timestamp = future.get("timestamp")
        action = future.get("action", "无")
        proactive_times = future.get("proactive_times", 0)
        status = future.get("status", "pending")

        talkers = conv.get("talkers", [])
        participants = get_talker_names(talkers, user_dao)

        table_data.append(
            [
                conv_id[:12] + "...",  # 会话ID（截断）
                participants[:40] + "..." if len(participants) > 40 else participants,
                format_timestamp(timestamp),
                get_time_status(timestamp, status),
                (
                    action[:30] + "..."
                    if action and len(action) > 30
                    else (action or "无")
                ),
                proactive_times,
                status or "pending",
            ]
        )

    # 按时间排序
    table_data.sort(key=lambda x: x[2])

    headers = ["会话ID", "参与者", "计划时间", "时间状态", "行动", "主动次数", "状态"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    # 统计信息
    due_count = sum(
        1
        for conv in conversations
        if conv.get("conversation_info", {}).get("future", {}).get("timestamp")
        and conv["conversation_info"]["future"]["timestamp"] <= now
        and conv["conversation_info"]["future"].get("status") != "expired"
    )
    pending_count = sum(
        1
        for conv in conversations
        if conv.get("conversation_info", {}).get("future", {}).get("timestamp")
        and conv["conversation_info"]["future"]["timestamp"] > now
        and conv["conversation_info"]["future"].get("status") != "expired"
    )
    expired_count = sum(
        1
        for conv in conversations
        if conv.get("conversation_info", {}).get("future", {}).get("status")
        == "expired"
    )

    print(
        f"\n  统计: 已到期 {due_count} 条, 待触发 {pending_count} 条, 已过期 {expired_count} 条\n"
    )

    # 详细信息
    print("-" * 80)
    print(" 详细信息:")
    print("-" * 80)

    for i, conv in enumerate(conversations, 1):
        conv_id = str(conv.get("_id", ""))
        future = conv.get("conversation_info", {}).get("future", {})
        talkers = conv.get("talkers", [])

        print(f"\n [{i}] 会话 ID: {conv_id}")
        print(f"     参与者: {get_talker_names(talkers, user_dao)}")
        print(f"     计划时间: {format_timestamp(future.get('timestamp'))}")
        print(
            f"     时间状态: {get_time_status(future.get('timestamp'), future.get('status'))}"
        )
        print(f"     行动: {future.get('action', '无')}")
        print(f"     主动消息次数: {future.get('proactive_times', 0)}")
        print(f"     状态: {future.get('status', 'pending')}")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()
