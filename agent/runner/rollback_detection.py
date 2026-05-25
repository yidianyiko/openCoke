# -*- coding: utf-8 -*-
"""
Rollback detection helpers for the agent runner.
"""

from entity.message import read_all_inputmessages


def _is_product_notification_message(message: dict) -> bool:
    metadata = message.get("metadata") or {}
    if not isinstance(metadata, dict):
        return False
    business_protocol = metadata.get("business_protocol")
    if not isinstance(business_protocol, dict):
        business_protocol = {}
    business_conversation_key = business_protocol.get(
        "business_conversation_key"
    ) or metadata.get("business_conversation_key")
    return str(business_conversation_key or "").startswith("product-notification:")


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

    input_messages = [
        message
        for message in input_messages
        if not _is_product_notification_message(message)
    ]

    return len(input_messages) > 0
