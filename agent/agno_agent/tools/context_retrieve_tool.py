# -*- coding: utf-8 -*-
"""Context Retrieve Tool adapter for Agno Agent."""

from __future__ import annotations

from agent.agno_agent.capabilities.context_retrieve import ContextRetrieveCapabilityPort


def context_retrieve_tool(
    character_setting_query: str = "",
    character_setting_keywords: str = "",
    user_profile_query: str = "",
    user_profile_keywords: str = "",
    character_knowledge_query: str = "",
    character_knowledge_keywords: str = "",
    chat_history_query: str = "",
    chat_history_keywords: str = "",
    character_id: str = "",
    user_id: str = "",
) -> dict:
    """
    向量检索工具，检索角色全局设定、角色私有设定、用户资料、角色知识、相关历史对话
    """
    result = ContextRetrieveCapabilityPort().run(
        "",
        None,
        {
            "character_setting_query": character_setting_query,
            "character_setting_keywords": character_setting_keywords,
            "user_profile_query": user_profile_query,
            "user_profile_keywords": user_profile_keywords,
            "character_knowledge_query": character_knowledge_query,
            "character_knowledge_keywords": character_knowledge_keywords,
            "chat_history_query": chat_history_query,
            "chat_history_keywords": chat_history_keywords,
            "character_id": character_id,
            "user_id": user_id,
        },
    )
    return dict(result.content)
