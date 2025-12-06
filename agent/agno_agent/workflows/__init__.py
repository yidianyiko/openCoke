# -*- coding: utf-8 -*-
"""
Agno Workflows Module

Contains Workflow classes for orchestrating multiple Agents.

Workflows:
- PrepareWorkflow: QueryRewrite + ReminderDetect + ContextRetrieve (Requirements: 5.1)
- ChatWorkflow: ChatResponseAgent (Requirements: 5.2)
- PostAnalyzeWorkflow: PostAnalyzeAgent (Requirements: 5.3)
- FutureMessageWorkflow: 主动消息生成 (Requirements: FR-036, FR-038)
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
