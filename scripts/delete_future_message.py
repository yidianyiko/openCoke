# -*- coding: utf-8 -*-
"""
删除指定会话的未来主动消息

Usage:
    python scripts/delete_future_message.py <conversation_id> [conversation_id2 ...]

Examples:
    # 删除单个会话的未来消息
    python scripts/delete_future_message.py 69417b04f9e76ec1580d9284

    # 删除多个会话的未来消息
    python scripts/delete_future_message.py 69417b04f9e76ec1580d9284 692c14aaa58e1cd8e0750f45
"""
import sys

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()

import argparse
from datetime import datetime

from dao.conversation_dao import ConversationDAO


def format_timestamp(ts):
    """格式化时间戳"""
    if ts is None:
        return "未设置"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def get_talker_names(talkers):
    """获取参与者名称"""
    return " <-> ".join([t.get("nickname", "未知") for t in talkers])


def delete_future_message(
    conv_id: str, conversation_dao: ConversationDAO, show_detail: bool = True
):
    """
    删除指定会话的未来主动消息

    Args:
        conv_id: 会话ID
        conversation_dao: ConversationDAO 实例
        show_detail: 是否显示详细信息

    Returns:
        bool: 是否成功
    """
    # 获取会话信息
    conv = conversation_dao.get_conversation_by_id(conv_id)

    if not conv:
        print(f"  ✗ 未找到会话: {conv_id}")
        return False

    talkers = get_talker_names(conv.get("talkers", []))
    future = conv.get("conversation_info", {}).get("future", {})

    if show_detail:
        print(f"\n  会话ID: {conv_id}")
        print(f"  参与者: {talkers}")
        print(f"  计划时间: {format_timestamp(future.get('timestamp'))}")
        print(f"  行动: {future.get('action', '无')}")
        print(f"  主动次数: {future.get('proactive_times', 0)}")

    # 检查是否有未来消息
    if not future.get("timestamp") and not future.get("action"):
        print("  ⚠ 该会话没有配置未来主动消息")
        return False

    # 执行删除
    result = conversation_dao.update_conversation(
        conv_id,
        {
            "conversation_info.future.timestamp": None,
            "conversation_info.future.action": None,
        },
    )

    if result:
        print("  ✓ 已删除未来主动消息")
    else:
        print("  ✗ 删除失败")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="删除指定会话的未来主动消息",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/delete_future_message.py 69417b04f9e76ec1580d9284
    python scripts/delete_future_message.py 69417b04f9e76ec1580d9284 692c14aaa58e1cd8e0750f45
        """,
    )
    parser.add_argument(
        "conversation_ids", nargs="+", help="要删除未来消息的会话ID（支持多个）"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="安静模式，不显示详细信息"
    )
    parser.add_argument("-y", "--yes", action="store_true", help="跳过确认直接删除")

    args = parser.parse_args()

    conversation_dao = ConversationDAO()

    print("\n" + "=" * 60)
    print(" 删除未来主动消息")
    print("=" * 60)

    # 先显示要删除的会话
    if not args.quiet:
        print(f"\n将删除以下 {len(args.conversation_ids)} 个会话的未来主动消息:")
        for conv_id in args.conversation_ids:
            conv = conversation_dao.get_conversation_by_id(conv_id)
            if conv:
                talkers = get_talker_names(conv.get("talkers", []))
                future = conv.get("conversation_info", {}).get("future", {})
                print(f"\n  - {conv_id[:16]}...")
                print(f"    参与者: {talkers}")
                print(f"    行动: {future.get('action', '无')[:40]}...")
            else:
                print(f"\n  - {conv_id} (未找到)")

    # 确认
    if not args.yes:
        confirm = input("\n确认删除? (y/N): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    # 执行删除
    print("\n" + "-" * 60)
    success_count = 0
    fail_count = 0

    for conv_id in args.conversation_ids:
        if delete_future_message(conv_id, conversation_dao, show_detail=not args.quiet):
            success_count += 1
        else:
            fail_count += 1

    print("\n" + "=" * 60)
    print(f" 完成: 成功 {success_count} 条, 失败 {fail_count} 条")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
