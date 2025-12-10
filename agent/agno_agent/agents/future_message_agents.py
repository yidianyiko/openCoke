# -*- coding: utf-8 -*-
"""
主动消息（Future Message）Agent 定义

包含主动消息相关的 Agent：
- future_message_query_rewrite_agent: 主动消息的问题重写
- future_message_chat_agent: 主动消息生成

Requirements: FR-036, FR-038
"""

import logging
from typing import Any, Dict

from agno.agent import Agent
from agno.models.deepseek import DeepSeek

from agent.agno_agent.schemas.query_rewrite_schema import QueryRewriteResponse
from agent.agno_agent.schemas.future_message_schema import FutureMessageResponse
from agent.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
from agent.prompt.agent_instructions_prompt import (
    INSTRUCTIONS_FUTURE_CONTEXT_RETRIEVE,
    INSTRUCTIONS_FUTURE_QUERY_REWRITE,
    INSTRUCTIONS_FUTURE_MESSAGE_CHAT,
)

logger = logging.getLogger(__name__)


# ========== 动态 instructions 函数 ==========

def get_future_query_rewrite_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染主动消息问题重写的 system prompt
    
    Args:
        session_state: 会话状态（预留用于未来扩展）
        
    Returns:
        主动消息问题重写的 instructions
    """
    return INSTRUCTIONS_FUTURE_QUERY_REWRITE


def get_future_message_chat_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染主动消息生成的 system prompt
    
    Args:
        session_state: 会话状态（预留用于未来扩展）
        
    Returns:
        主动消息生成的 instructions
    """
    return INSTRUCTIONS_FUTURE_MESSAGE_CHAT


def get_future_context_retrieve_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染主动消息上下文检索的 system prompt
    """
    return INSTRUCTIONS_FUTURE_CONTEXT_RETRIEVE


# ========== 模块级预创建 Agent ==========

# FutureMessageQueryRewriteAgent - 主动消息的问题重写
# Requirements: FR-036
future_message_query_rewrite_agent = Agent(
    id="future-message-query-rewrite-agent",
    name="FutureMessageQueryRewriteAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=INSTRUCTIONS_FUTURE_QUERY_REWRITE,
    output_schema=QueryRewriteResponse,
    markdown=False,
)

# FutureMessageContextRetrieveAgent - 主动消息的上下文检索
# Requirements: FR-036
future_message_context_retrieve_agent = Agent(
    id="future-message-context-retrieve-agent",
    name="FutureMessageContextRetrieveAgent",
    model=DeepSeek(id="deepseek-chat"),
    tools=[context_retrieve_tool],
    instructions=get_future_context_retrieve_instructions(),
    markdown=False,
)

# FutureMessageChatAgent - 主动消息生成
# Requirements: FR-038
future_message_chat_agent = Agent(
    id="future-message-chat-agent",
    name="FutureMessageChatAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=INSTRUCTIONS_FUTURE_MESSAGE_CHAT,
    output_schema=FutureMessageResponse,
    markdown=False,
)


# ========== 导出 ==========

__all__ = [
    # 动态 instructions 函数
    "get_future_query_rewrite_instructions",
    "get_future_message_chat_instructions",
    "get_future_context_retrieve_instructions",
    # 预创建 Agent
    "future_message_query_rewrite_agent",
    "future_message_context_retrieve_agent",
    "future_message_chat_agent",
]
