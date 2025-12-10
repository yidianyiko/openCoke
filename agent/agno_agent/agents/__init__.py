# -*- coding: utf-8 -*-
"""
Agno Agents Module

This module contains all pre-created Agno Agents for the chat system.
Agents are created at module level to avoid instantiation overhead on each call.

V2 架构：引入 OrchestratorAgent 作为调度中心

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import logging
from typing import Any, Dict

from agno.agent import Agent
from agno.models.deepseek import DeepSeek

from agent.agno_agent.schemas.query_rewrite_schema import QueryRewriteResponse
from agent.agno_agent.schemas.orchestrator_schema import OrchestratorResponse
from agent.agno_agent.schemas.chat_response_schema import ChatResponse
from agent.agno_agent.schemas.post_analyze_schema import PostAnalyzeResponse
from agent.agno_agent.tools.reminder_tools import reminder_tool
from agent.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
from agent.prompt.system_prompt import SYSTEMPROMPT_小说越狱
from agent.prompt.agent_instructions_prompt import (
    INSTRUCTIONS_REMINDER_DETECT,
    INSTRUCTIONS_CONTEXT_RETRIEVE,
    INSTRUCTIONS_ORCHESTRATOR,
)

logger = logging.getLogger(__name__)


# ========== 动态 instructions 函数 ==========

def get_query_rewrite_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 QueryRewrite 的 system prompt
    
    Args:
        session_state: 会话状态，包含动态数据
        
    Returns:
        渲染后的 system prompt
    """
    session_state = session_state or {}
    try:
        # 尝试使用 session_state 渲染模板
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        logger.warning(f"QueryRewrite Prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱
    except Exception as e:
        logger.error(f"QueryRewrite Prompt 渲染失败: {e}")
        return SYSTEMPROMPT_小说越狱


def get_chat_response_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 ChatResponse 的 system prompt
    
    Args:
        session_state: 会话状态，包含动态数据
        
    Returns:
        渲染后的 system prompt
    """
    session_state = session_state or {}
    try:
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        logger.warning(f"ChatResponse Prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱
    except Exception as e:
        logger.error(f"ChatResponse Prompt 渲染失败: {e}")
        return SYSTEMPROMPT_小说越狱


def get_post_analyze_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 PostAnalyze 的 system prompt
    
    Args:
        session_state: 会话状态，包含动态数据
        
    Returns:
        渲染后的 system prompt
    """
    session_state = session_state or {}
    try:
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        logger.warning(f"PostAnalyze Prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱
    except Exception as e:
        logger.error(f"PostAnalyze Prompt 渲染失败: {e}")
        return SYSTEMPROMPT_小说越狱


def get_reminder_detect_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 ReminderDetect 的 system prompt
    
    Args:
        session_state: 会话状态，包含动态数据
        
    Returns:
        渲染后的 system prompt
    """
    return INSTRUCTIONS_REMINDER_DETECT


def get_context_retrieve_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 ContextRetrieve 的 system prompt
    
    Args:
        session_state: 会话状态，包含动态数据
        
    Returns:
        渲染后的 system prompt
    """
    return INSTRUCTIONS_CONTEXT_RETRIEVE


def get_orchestrator_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 OrchestratorAgent 的 system prompt
    
    V2 架构核心：Orchestrator 负责语义理解 + 调度决策
    
    Args:
        session_state: 会话状态，包含动态数据
        
    Returns:
        渲染后的 system prompt
    """
    return INSTRUCTIONS_ORCHESTRATOR


# ========== 模块级预创建 Agent ==========

# QueryRewriteAgent - 问题重写，生成检索查询词
# Requirements: 4.1
query_rewrite_agent = Agent(
    id="query-rewrite-agent",
    name="QueryRewriteAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=SYSTEMPROMPT_小说越狱,
    output_schema=QueryRewriteResponse,
    markdown=False,
)

# ReminderDetectAgent - 提醒检测，识别提醒意图并创建提醒
# Requirements: 4.2
reminder_detect_agent = Agent(
    id="reminder-detect-agent",
    name="ReminderDetectAgent",
    model=DeepSeek(id="deepseek-chat"),
    tools=[reminder_tool],
    instructions=get_reminder_detect_instructions(),
    markdown=False,
)

# ContextRetrieveAgent - 上下文检索，根据问题重写结果检索相关上下文
# Requirements: 4.3
# 注意：V2 架构中此 Agent 已废弃，改为直接调用 context_retrieve_tool
context_retrieve_agent = Agent(
    id="context-retrieve-agent",
    name="ContextRetrieveAgent",
    model=DeepSeek(id="deepseek-chat"),
    tools=[context_retrieve_tool],
    instructions=get_context_retrieve_instructions(),
    markdown=False,
)

# OrchestratorAgent - V2 架构核心，语义理解 + 调度决策
# 职责：理解用户意图、生成检索参数、决定调用哪些 Tool/Agent
orchestrator_agent = Agent(
    id="orchestrator-agent",
    name="OrchestratorAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=get_orchestrator_instructions(),
    output_schema=OrchestratorResponse,
    markdown=False,
)

# ChatResponseAgent - 对话生成，基于角色人设生成多模态回复
# Requirements: 4.4
chat_response_agent = Agent(
    id="chat-response-agent",
    name="ChatResponseAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=SYSTEMPROMPT_小说越狱,
    output_schema=ChatResponse,
    markdown=False,
)

# PostAnalyzeAgent - 后处理分析，总结对话并更新用户/角色记忆
# Requirements: 4.4
post_analyze_agent = Agent(
    id="post-analyze-agent",
    name="PostAnalyzeAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=SYSTEMPROMPT_小说越狱,
    output_schema=PostAnalyzeResponse,
    markdown=False,
)


# ========== 导出 ==========

__all__ = [
    # 动态 instructions 函数
    "get_query_rewrite_instructions",
    "get_chat_response_instructions",
    "get_post_analyze_instructions",
    "get_reminder_detect_instructions",
    "get_context_retrieve_instructions",
    "get_orchestrator_instructions",
    # 预创建 Agent
    "query_rewrite_agent",
    "reminder_detect_agent",
    "context_retrieve_agent",
    "orchestrator_agent",  # V2 架构核心
    "chat_response_agent",
    "post_analyze_agent",
]
