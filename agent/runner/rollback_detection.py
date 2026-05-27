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


def _request_response_event_key(message: dict) -> str | None:
    metadata = message.get("metadata") or {}
    if not isinstance(metadata, dict) or metadata.get("source") != "clawscale":
        return None
    business_protocol = metadata.get("business_protocol")
    if not isinstance(business_protocol, dict):
        business_protocol = {}
    delivery_mode = business_protocol.get("delivery_mode") or metadata.get(
        "delivery_mode"
    )
    if delivery_mode != "request_response":
        return None
    stable_id = business_protocol.get("causal_inbound_event_id") or metadata.get(
        "causal_inbound_event_id"
    )
    stable_id = (
        stable_id
        or business_protocol.get("sync_reply_token")
        or metadata.get("sync_reply_token")
    )
    stable_id = stable_id or message.get("_id")
    return str(stable_id) if stable_id else None


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
    input_messages = read_all_inputmessages(
        u_id, c_id, platform, None if current_message_ids else "pending"
    )

    # 排除当前正在处理的消息
    current_latest = None
    if current_message_ids:
        current_ids_set = set(current_message_ids)
        current_messages = [
            m for m in input_messages if str(m.get("_id", "")) in current_ids_set
        ]
        current_latest = _latest_message_position(current_messages)
        input_messages = [
            m for m in input_messages if str(m.get("_id", "")) not in current_ids_set
        ]
    else:
        input_messages = [
            m for m in input_messages if m.get("status", "pending") == "pending"
        ]

    input_messages = [
        message
        for message in input_messages
        if not _is_product_notification_message(message)
    ]
    if current_message_ids and any(
        _request_response_event_key(message) for message in current_messages
    ):
        input_messages = [
            message
            for message in input_messages
            if _request_response_event_key(message) is None
        ]
    if current_latest is not None:
        input_messages = [
            message
            for message in input_messages
            if _message_position(message) > current_latest
        ]

    return len(input_messages) > 0


def _latest_message_position(messages: list[dict]) -> tuple[int, str] | None:
    positions = [_message_position(message) for message in messages]
    return max(positions) if positions else None


def _message_position(message: dict) -> tuple[int, str]:
    try:
        timestamp = int(message.get("input_timestamp") or 0)
    except (TypeError, ValueError):
        timestamp = 0
    return (timestamp, str(message.get("_id", "")))
