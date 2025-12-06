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
from agent.prompt.system_prompt import SYSTEMPROMPT_小说越狱

logger = logging.getLogger(__name__)


# ========== 动态 instructions 函数 ==========

def get_future_query_rewrite_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染主动消息问题重写的 system prompt
    """
    session_state = session_state or {}
    try:
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        logger.warning(f"FutureQueryRewrite Prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱
    except Exception as e:
        logger.error(f"FutureQueryRewrite Prompt 渲染失败: {e}")
        return SYSTEMPROMPT_小说越狱


def get_future_message_chat_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染主动消息生成的 system prompt
    """
    session_state = session_state or {}
    try:
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        logger.warning(f"FutureMessageChat Prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱
    except Exception as e:
        logger.error(f"FutureMessageChat Prompt 渲染失败: {e}")
        return SYSTEMPROMPT_小说越狱


def get_future_context_retrieve_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染主动消息上下文检索的 system prompt
    """
    base_instructions = """你是一个上下文检索助手。你的任务是：
1. 根据问题重写结果，调用 context_retrieve_tool 检索相关上下文
2. 检索内容包括：角色全局设定、角色私有设定、用户资料、角色知识
3. 将检索结果整理后返回

请根据 query_rewrite 中的查询问题和关键词进行检索，特别关注与"规划行动"相关的内容。"""
    return base_instructions


# ========== 模块级预创建 Agent ==========

# FutureMessageQueryRewriteAgent - 主动消息的问题重写
# Requirements: FR-036
future_message_query_rewrite_agent = Agent(
    id="future-message-query-rewrite-agent",
    name="FutureMessageQueryRewriteAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=SYSTEMPROMPT_小说越狱,
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
    instructions=SYSTEMPROMPT_小说越狱,
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
