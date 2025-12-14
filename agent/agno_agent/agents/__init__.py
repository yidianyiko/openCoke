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
from agent.prompt.agent_instructions_prompt import (
    INSTRUCTIONS_REMINDER_DETECT,
    INSTRUCTIONS_ORCHESTRATOR,
    INSTRUCTIONS_QUERY_REWRITE,
    INSTRUCTIONS_CHAT_RESPONSE,
    INSTRUCTIONS_POST_ANALYZE,
)

logger = logging.getLogger(__name__)


# ========== 动态 instructions 函数 ==========

def get_query_rewrite_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 QueryRewrite 的 system prompt
    
    Args:
        session_state: 会话状态（预留用于未来扩展）
        
    Returns:
        问题重写的 instructions
    """
    return INSTRUCTIONS_QUERY_REWRITE


def get_chat_response_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 ChatResponse 的 system prompt
    
    Args:
        session_state: 会话状态（预留用于未来扩展）
        
    Returns:
        对话生成的 instructions
    """
    return INSTRUCTIONS_CHAT_RESPONSE


def get_post_analyze_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 PostAnalyze 的 system prompt
    
    Args:
        session_state: 会话状态（预留用于未来扩展）
        
    Returns:
        后处理分析的 instructions
    """
    return INSTRUCTIONS_POST_ANALYZE


def get_reminder_detect_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 ReminderDetect 的 system prompt
    
    Args:
        session_state: 会话状态，包含动态数据
        
    Returns:
        渲染后的 system prompt
    """
    return INSTRUCTIONS_REMINDER_DETECT



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


# ========== Model 层重试配置 ==========
# 解决问题：
# - P17: Agno Agent 未配置重试，API 限流直接失败
# - E4: LLM API 限流直接失败
# - E5: 网络临时故障直接失败

def create_deepseek_model(model_id: str = "deepseek-chat"):
    """
    创建带重试配置的 DeepSeek Model
    
    Args:
        model_id: 模型ID
        
    Returns:
        配置了重试的 DeepSeek 实例
    """
    return DeepSeek(
        id=model_id,
        # 重试配置：2次重试，指数退避
        # 注意：Agno 的 DeepSeek 继承自 OpenAI，支持 max_retries 参数
        max_retries=2,
    )


# ========== 模块级预创建 Agent ==========

# QueryRewriteAgent - 问题重写，生成检索查询词
# Requirements: 4.1
query_rewrite_agent = Agent(
    id="query-rewrite-agent",
    name="QueryRewriteAgent",
    model=create_deepseek_model(),
    instructions=INSTRUCTIONS_QUERY_REWRITE,
    output_schema=QueryRewriteResponse,
    markdown=False,
)

# ReminderDetectAgent - 提醒检测，识别提醒意图并创建提醒
# Requirements: 4.2
reminder_detect_agent = Agent(
    id="reminder-detect-agent",
    name="ReminderDetectAgent",
    model=create_deepseek_model(),
    tools=[reminder_tool],
    tool_call_limit=1,  # 限制只能调用一次工具，防止无限循环
    instructions=get_reminder_detect_instructions(),
    markdown=False,
)


# OrchestratorAgent - V2 架构核心，语义理解 + 调度决策
# 职责：理解用户意图、生成检索参数、决定调用哪些 Tool/Agent
orchestrator_agent = Agent(
    id="orchestrator-agent",
    name="OrchestratorAgent",
    model=create_deepseek_model(),
    instructions=get_orchestrator_instructions(),
    output_schema=OrchestratorResponse,
    markdown=False,
)

# ChatResponseAgent - 对话生成，基于角色人设生成多模态回复
# Requirements: 4.4
chat_response_agent = Agent(
    id="chat-response-agent",
    name="ChatResponseAgent",
    model=create_deepseek_model(),
    instructions=INSTRUCTIONS_CHAT_RESPONSE,
    output_schema=ChatResponse,
    markdown=False,
)

# PostAnalyzeAgent - 后处理分析，总结对话并更新用户/角色记忆
# Requirements: 4.4
post_analyze_agent = Agent(
    id="post-analyze-agent",
    name="PostAnalyzeAgent",
    model=create_deepseek_model(),
    instructions=INSTRUCTIONS_POST_ANALYZE,
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
    "get_orchestrator_instructions",
    # 预创建 Agent
    "query_rewrite_agent",
    "reminder_detect_agent",
    "orchestrator_agent",  # V2 架构核心
    "chat_response_agent",
    "post_analyze_agent",
]
