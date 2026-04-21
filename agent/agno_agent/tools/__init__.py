# -*- coding: utf-8 -*-
"""
Agno Tools Module

Contains tool functions that can be called by Agents.

Tools:
- context_retrieve_tool: 向量检索（角色设定、用户资料、知识库）
- visible_reminder_tool: 可见提醒管理（CRUD）
- web_search_tool: 联网搜索（博查 Search API）
- voice2text_tool: 语音转文字
- text2voice_tool: 文字转语音
- image2text_tool: 图片识别
- image_send_tool: 图片发送
- image_generate_tool: 文生图
- photo_delete_tool: 照片删除
"""

from agent.agno_agent.tools.album_tools import photo_delete_tool
from agent.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
from agent.agno_agent.tools.deferred_action import visible_reminder_tool
from agent.agno_agent.tools.image_tools import (
    image2text_tool,
    image_generate_tool,
    image_send_tool,
)
from agent.agno_agent.tools.voice_tools import text2voice_tool, voice2text_tool
from agent.agno_agent.tools.web_search_tool import web_search_tool

__all__ = [
    # 核心 Tool
    "context_retrieve_tool",
    "visible_reminder_tool",
    "web_search_tool",
    # 语音 Tool
    "voice2text_tool",
    "text2voice_tool",
    # 图片 Tool
    "image2text_tool",
    "image_send_tool",
    "image_generate_tool",
    # 相册 Tool
    "photo_delete_tool",
]
