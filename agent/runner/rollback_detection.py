# -*- coding: utf-8 -*-
"""
Rollback detection helpers for the agent runner.
"""

from entity.message import read_all_inputmessages


def is_new_message_coming_in(u_id, c_id, platform, current_message_ids: list = None):
    """
    检测是否有新消息到达（排除当前正在处理的消息）

    Args:
        u_id: 用户ID
        c_id: 角色ID
        platform: 平台
        current_message_ids: 当前正在处理的消息ID列表（字符串格式）

    Returns:
        bool: 是否有新消息
    """
    input_messages = read_all_inputmessages(u_id, c_id, platform, "pending")

    # 排除当前正在处理的消息
    if current_message_ids:
        current_ids_set = set(current_message_ids)
        input_messages = [
            m for m in input_messages if str(m.get("_id", "")) not in current_ids_set
        ]

    return len(input_messages) > 0


def merge_pending_messages(current_messages: list, new_messages: list) -> list:
    """合并待处理消息"""
    seen_ids = set()
    merged = []
    for msg in current_messages + new_messages:
        msg_id = str(msg.get("_id", ""))
        if msg_id and msg_id not in seen_ids:
            seen_ids.add(msg_id)
            merged.append(msg)
        elif not msg_id:
            merged.append(msg)
    merged.sort(key=lambda x: x.get("timestamp", 0))
    return merged
