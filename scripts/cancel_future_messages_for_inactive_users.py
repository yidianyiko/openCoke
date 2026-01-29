#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
取消为不活跃用户设置的主动消息

此脚本用于将指定用户的未来主动消息设置为过期状态，以避免继续向不活跃用户发送主动消息
"""

import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

sys.path.append(".")

from dao.conversation_dao import ConversationDAO
from dao.user_dao import UserDAO


def get_conversations_by_user_ids(
    user_ids: List[str], conversation_dao: ConversationDAO
) -> List[Dict]:
    """
    根据用户ID列表获取相关会话

    Args:
        user_ids: 用户ID列表
        conversation_dao: ConversationDAO实例

    Returns:
        List[Dict]: 匹配的会话列表
    """
    # 构建查询条件，查找包含这些用户ID的会话
    query = {"talkers.id": {"$in": user_ids}}

    conversations = conversation_dao.find_conversations(query)
    return conversations


def update_future_messages_to_expired(
    conversations: List[Dict], conversation_dao: ConversationDAO
) -> Dict[str, int]:
    """
    将会话中的未来主动消息设置为过期状态

    Args:
        conversations: 会话列表
        conversation_dao: ConversationDAO实例

    Returns:
        Dict[str, int]: 更新结果统计
    """
    updated_count = 0
    processed_count = 0

    for conv in conversations:
        conv_id = str(conv.get("_id", ""))
        future = conv.get("conversation_info", {}).get("future", {})

        # 检查是否存在future配置
        if future:
            # 设置为过期状态
            updated_future = {
                "timestamp": None,
                "action": None,
                "proactive_times": future.get("proactive_times", 0),
                "status": "expired",
            }

            # 更新会话
            update_data = {"conversation_info.future": updated_future}
            success = conversation_dao.update_conversation(conv_id, update_data)

            if success:
                updated_count += 1
                print(f"会话 {conv_id}: Future消息已设置为过期状态")
            else:
                print(f"会话 {conv_id}: 更新失败")

            processed_count += 1

    return {"processed": processed_count, "updated": updated_count}


def main():
    """主函数"""
    print("🔧 批量取消不活跃用户的主动消息")
    print("=" * 60)

    # 之前处理的不活跃用户ID列表
    inactive_user_ids = [
        "69416b65d31213c1ef437583",  # 4.6天前，13个提醒
        "69417b04d31213c1ef4375ae",  # 16.4天前，1个提醒
        "694381d07a8fcefce10c8ce3",  # 15.6天前，3个提醒
        "6943f2d7709458dc324a9fe3",  # 18.2天前，1个提醒
        "6944fec4f09e7d5a55ad9ad3",  # 10.5天前，1个提醒
        "69457aa4f09e7d5a55ad9e5d",  # 4.4天前，4个提醒
        "69460b98f09e7d5a55ad9f81",  # 11.1天前，5个提醒
        "694cd15275b94ddc9ff2fb39",  # 5.0天前，1个提醒
        "694cee7875b94ddc9ff2fbe1",  # 7.2天前，1个提醒
        "6950953332a0608514a93047",  # 7.5天前，1个提醒
    ]

    print(f"总共需要处理 {len(inactive_user_ids)} 个不活跃用户")

    # 初始化数据库连接
    conversation_dao = ConversationDAO()

    try:
        # 获取与这些用户相关的会话
        conversations = get_conversations_by_user_ids(
            inactive_user_ids, conversation_dao
        )

        print(f"找到 {len(conversations)} 个相关会话")

        if conversations:
            # 更新会话中的未来主动消息为过期状态
            results = update_future_messages_to_expired(conversations, conversation_dao)

            print(
                f"\n✅ 完成! 处理了 {results['processed']} 个会话，更新了 {results['updated']} 个会话的主动消息状态为过期"
            )
        else:
            print("\n未找到相关会话")

    finally:
        conversation_dao.close()


if __name__ == "__main__":
    main()
