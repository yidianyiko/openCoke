# -*- coding: utf-8 -*-
"""
Message history and retrieval storage helpers for the agent runner.
"""

import copy
from concurrent.futures import ThreadPoolExecutor

from agent.runner.identity import get_agent_entity_id
from util.log_util import get_logger

logger = get_logger(__name__)

# Thread pool for background embedding storage
_embedding_executor = ThreadPoolExecutor(max_workers=4)


def store_messages_for_retrieval_sync(context: dict, resp_messages: list):
    """
    Store messages as embeddings for future retrieval (sync, runs in background thread).
    """
    from util.embedding_util import store_chat_message

    character_id = get_agent_entity_id(context.get("character"))
    user_id = get_agent_entity_id(context.get("user"))

    try:
        # Store user's input messages
        input_messages = (
            context.get("conversation", {})
            .get("conversation_info", {})
            .get("input_messages", [])
        )
        for msg in input_messages:
            message_content = msg.get("message", "")
            if message_content:
                store_chat_message(
                    message=message_content,
                    from_user=msg.get("from_user", ""),
                    to_user=msg.get("to_user", ""),
                    character_id=character_id,
                    user_id=user_id,
                    timestamp=msg.get("input_timestamp", 0),
                    message_type=msg.get("message_type", "text"),
                )

        # Store character's responses
        for msg in resp_messages:
            message_content = msg.get("message", "")
            if message_content:
                store_chat_message(
                    message=message_content,
                    from_user=character_id,
                    to_user=user_id,
                    character_id=character_id,
                    user_id=user_id,
                    timestamp=msg.get("expect_output_timestamp", 0),
                    message_type=msg.get("message_type", "text"),
                )

        logger.debug(
            f"Stored {len(input_messages) + len(resp_messages)} messages for semantic retrieval"
        )
    except Exception as e:
        logger.warning(f"Failed to store messages for retrieval: {e}")


def store_messages_background(context: dict, resp_messages: list):
    """Submit message storage to background thread pool.

    BUG-008 fix: Use deep copy to prevent concurrent modification of context
    while the background thread is accessing it.
    """
    # Deep copy to avoid race condition with concurrent context modifications
    context_copy = copy.deepcopy(context)
    resp_messages_copy = copy.deepcopy(resp_messages)
    _embedding_executor.submit(
        store_messages_for_retrieval_sync, context_copy, resp_messages_copy
    )


def extract_recent_chat_history(chat_history: list, limit: int = 6) -> str:
    """
    从聊天历史中提取最近的对话（包括用户和角色的消息）
    用于主动消息/提醒消息场景，避免传入过长的历史对话

    Args:
        chat_history: 聊天历史列表
        limit: 提取的消息数量（默认6条，约3轮对话）

    Returns:
        格式化的最近对话字符串
    """
    if not chat_history:
        return "（无历史消息）"

    # 取最近的 limit 条消息
    recent_messages = (
        chat_history[-limit:] if len(chat_history) > limit else chat_history
    )

    if not recent_messages:
        return "（无历史消息）"

    # 格式化输出，保持与原始 chat_history_str 类似的格式
    result_lines = []
    for msg in recent_messages:
        msg_from = msg.get("from_nickname", "") or msg.get("from", "")
        msg_content = msg.get("message", "") or msg.get("content", "")
        msg_time = msg.get("time_str", "")
        msg_type = msg.get("message_type", "text")

        if msg_content:
            # 截断过长的消息
            if len(msg_content) > 150:
                msg_content = msg_content[:150] + "..."

            if msg_time:
                result_lines.append(
                    f"（{msg_time} {msg_from}发来了{msg_type}消息）{msg_content}"
                )
            else:
                result_lines.append(f"（{msg_from}发来了{msg_type}消息）{msg_content}")

    return "\n".join(result_lines)
