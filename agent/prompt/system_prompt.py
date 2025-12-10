# -*- coding: utf-8 -*-
"""
System Prompt Module (DEPRECATED)

本文件已废弃。所有 Agent Instructions 已迁移至 agent_instructions_prompt.py

历史原因：
- SYSTEMPROMPT_小说越狱 原本是一个通用的 JSON 格式说明
- 命名不规范，内容过于通用，不适合作为具体 Agent 的 instructions
- 已被更具体、更清晰的 instructions 替代

迁移说明：
- QueryRewriteAgent -> INSTRUCTIONS_QUERY_REWRITE
- ChatResponseAgent -> INSTRUCTIONS_CHAT_RESPONSE
- PostAnalyzeAgent -> INSTRUCTIONS_POST_ANALYZE
- FutureMessageQueryRewriteAgent -> INSTRUCTIONS_FUTURE_QUERY_REWRITE
- FutureMessageChatAgent -> INSTRUCTIONS_FUTURE_MESSAGE_CHAT

请使用 agent_instructions_prompt.py 中的新定义。
"""

# 保留此文件以避免破坏可能的外部引用
# 如果确认没有外部依赖，可以删除此文件