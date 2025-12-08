# -*- coding: utf-8 -*-
"""
Agno Agents Module

This module contains all pre-created Agno Agents for the chat system.
Agents are created at module level to avoid instantiation overhead on each call.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import logging
from typing import Any, Dict

from agno.agent import Agent
from agno.models.deepseek import DeepSeek

from agent.agno_agent.schemas.query_rewrite_schema import QueryRewriteResponse
from agent.agno_agent.schemas.chat_response_schema import ChatResponse
from agent.agno_agent.schemas.post_analyze_schema import PostAnalyzeResponse
from agent.agno_agent.tools.reminder_tools import reminder_tool
from agent.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
from agent.prompt.system_prompt import SYSTEMPROMPT_小说越狱

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
    base_instructions = """你是一个提醒检测助手。你的唯一任务是检测用户消息中是否包含提醒意图，如果有则调用 reminder_tool 创建提醒。

## 检测规则
当用户消息包含以下关键词时，必须调用 reminder_tool：
- "提醒我"、"帮我提醒"、"记得提醒"
- "设个提醒"、"设置提醒"、"创建提醒"
- "别忘了提醒"、"到时候提醒"
- "闹钟"、"定时"

## 调用方式
检测到提醒意图后，调用 reminder_tool 并提供：
- action: "create"
- title: 从用户消息中提取的提醒事项，如"开会"、"喝水"、"休息"
- trigger_time: 触发时间，支持以下两种格式：
  1. 绝对时间格式（推荐）："xxxx年xx月xx日xx时xx分"，如"2025年12月08日15时00分"
  2. 相对时间格式："X分钟后"、"X小时后"、"X天后"、"明天"、"后天"、"下周"

## 时间解析规则
你必须将用户的时间表达解析为上述支持的格式：
- "下午3点" -> 解析为绝对时间，如"2025年12月08日15时00分"
- "晚上8点" -> 解析为绝对时间，如"2025年12月08日20时00分"
- "明天早上9点" -> 解析为绝对时间，如"2025年12月09日09时00分"
- "30分钟后" -> 直接使用"30分钟后"
- "每天早上9点" -> 解析为最近一次的绝对时间，如"2025年12月09日09时00分"

## 示例
- 用户说"明天早上9点提醒我开会" -> 调用 reminder_tool(action="create", title="开会", trigger_time="2025年12月09日09时00分")
- 用户说"30分钟后提醒我喝水" -> 调用 reminder_tool(action="create", title="喝水", trigger_time="30分钟后")
- 用户说"下午3点提醒我休息" -> 调用 reminder_tool(action="create", title="休息", trigger_time="2025年12月08日15时00分")

## 注意
- 如果用户消息不包含提醒意图，不要调用任何工具
- 不需要回复任何文字，只需要判断是否调用工具
- 绝对不要使用"下午3点"、"晚上8点"、"23:00"等不支持的格式，必须转换为绝对时间格式"""
    return base_instructions


def get_context_retrieve_instructions(session_state: Dict[str, Any] = None) -> str:
    """
    动态渲染 ContextRetrieve 的 system prompt
    
    Args:
        session_state: 会话状态，包含动态数据
        
    Returns:
        渲染后的 system prompt
    """
    base_instructions = """你是一个上下文检索助手。你的任务是：
1. 根据问题重写结果，调用 context_retrieve_tool 检索相关上下文
2. 检索内容包括：角色全局设定、角色私有设定、用户资料、角色知识
3. 将检索结果整理后返回

请根据 query_rewrite 中的查询问题和关键词进行检索。"""
    return base_instructions


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
context_retrieve_agent = Agent(
    id="context-retrieve-agent",
    name="ContextRetrieveAgent",
    model=DeepSeek(id="deepseek-chat"),
    tools=[context_retrieve_tool],
    instructions=get_context_retrieve_instructions(),
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
    # 预创建 Agent
    "query_rewrite_agent",
    "reminder_detect_agent",
    "context_retrieve_agent",
    "chat_response_agent",
    "post_analyze_agent",
]
