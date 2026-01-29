#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
取消所有过时的主动消息

此脚本用于将所有过时的未来主动消息设置为过期状态，以避免继续发送过时的主动消息
"""

import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

sys.path.append(".")

from dao.conversation_dao import ConversationDAO


def update_outdated_future_messages_to_expired(
    conversation_dao: ConversationDAO,
) -> Dict[str, int]:
    """
    将所有过时的未来主动消息设置为过期状态

    Args:
        conversation_dao: ConversationDAO实例

    Returns:
        Dict[str, int]: 更新结果统计
    """
    now = int(time.time())

    # 查询所有有未来消息配置的会话
    query = {
        "$or": [
            {"conversation_info.future.timestamp": {"$exists": True}},
            {"conversation_info.future.action": {"$exists": True}},
        ]
    }

    conversations = conversation_dao.find_conversations(query)

    updated_count = 0
    processed_count = 0

    for conv in conversations:
        conv_id = str(conv.get("_id", ""))
        future = conv.get("conversation_info", {}).get("future", {})

        # 检查是否存在future配置
        if future:
            timestamp = future.get("timestamp")
            status = future.get("status", "pending")

            # 如果时间戳存在且已过期（小于当前时间）且状态不是已过期，则更新为过期
            should_update = False
            if timestamp and timestamp < now and status != "expired":
                should_update = True
            elif status == "pending" and timestamp is None:
                # 如果没有时间戳但状态是pending，也标记为过期
                should_update = True

            if should_update:
                # 设置为过期状态
                updated_future = {
                    "timestamp": None,
                    "action": future.get("action"),
                    "proactive_times": future.get("proactive_times", 0),
                    "status": "expired",
                }

                # 更新会话
                update_data = {"conversation_info.future": updated_future}
                success = conversation_dao.update_conversation(conv_id, update_data)

                if success:
                    updated_count += 1
                    print(
                        f"会话 {conv_id}: Future消息已设置为过期状态 (原计划时间: {datetime.fromtimestamp(timestamp) if timestamp else '未设置'}, 原状态: {status})"
                    )
                else:
                    print(f"会话 {conv_id}: 更新失败")

                processed_count += 1
            else:
                # 检查是否已经是过期状态但可能需要清理
                if status == "expired":
                    processed_count += 1  # 计入处理数量但不更新

    return {"processed": processed_count, "updated": updated_count}


def main():
    """主函数"""
    print("🔧 批量取消所有过时的主动消息")
    print("=" * 60)

    # 初始化数据库连接
    conversation_dao = ConversationDAO()

    try:
        # 更新所有过时的未来主动消息为过期状态
        results = update_outdated_future_messages_to_expired(conversation_dao)

        print(
            f"\n✅ 完成! 检查了 {results['processed']} 个会话，更新了 {results['updated']} 个会话的主动消息状态为过期"
        )

    finally:
        conversation_dao.close()


if __name__ == "__main__":
    main()
