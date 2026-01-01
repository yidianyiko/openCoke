# -*- coding: utf-8 -*-
"""
Agno Workflows Module

Contains Workflow classes for orchestrating multiple Agents.

V2 架构 Workflows:
- PrepareWorkflow: OrchestratorAgent + context_retrieve_tool + ReminderDetectAgent(按需)
- StreamingChatWorkflow: ChatResponseAgent with streaming support (Requirements: 5.2)
- PostAnalyzeWorkflow: PostAnalyzeAgent (Requirements: 5.3)

V2 架构改进:
- PrepareWorkflow 使用 OrchestratorAgent 作为调度中心
- context_retrieve_tool 直接函数调用，省去 2 次 LLM
- ReminderDetectAgent 按需调用，普通消息不触发
- StreamingChatWorkflow 支持流式输出，提升用户体验
"""

from agent.agno_agent.workflows.chat_workflow_streaming import StreamingChatWorkflow
from agent.agno_agent.workflows.post_analyze_workflow import PostAnalyzeWorkflow
from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

__all__ = [
    "PrepareWorkflow",
    "StreamingChatWorkflow",
    "PostAnalyzeWorkflow",
]
