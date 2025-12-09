# -*- coding: utf-8 -*-
"""
Agno Workflows Module

Contains Workflow classes for orchestrating multiple Agents.

V2 架构 Workflows:
- PrepareWorkflow: OrchestratorAgent + context_retrieve_tool + ReminderDetectAgent(按需)
- ChatWorkflow: ChatResponseAgent (Requirements: 5.2)
- PostAnalyzeWorkflow: PostAnalyzeAgent (Requirements: 5.3)
- FutureMessageWorkflow: 主动消息生成 (Requirements: FR-036, FR-038)

V2 架构改进:
- PrepareWorkflow 使用 OrchestratorAgent 作为调度中心
- context_retrieve_tool 直接函数调用，省去 2 次 LLM
- ReminderDetectAgent 按需调用，普通消息不触发
"""

from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow
from agent.agno_agent.workflows.chat_workflow import ChatWorkflow
from agent.agno_agent.workflows.post_analyze_workflow import PostAnalyzeWorkflow
from agent.agno_agent.workflows.future_message_workflow import FutureMessageWorkflow

__all__ = [
    "PrepareWorkflow",
    "ChatWorkflow",
    "PostAnalyzeWorkflow",
    "FutureMessageWorkflow",
]
