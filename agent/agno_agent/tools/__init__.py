# -*- coding: utf-8 -*-
"""
Agno Tools Module

Contains tool functions that can be called by Agents.

Tools:
- context_retrieve_tool: 向量检索（角色设定、用户资料、知识库）
- reminder_tool: 提醒管理（CRUD）
- voice2text_tool: 语音转文字
- text2voice_tool: 文字转语音
- image2text_tool: 图片识别
- image_send_tool: 图片发送
- image_generate_tool: 文生图
- moments_tool: 朋友圈发布
- photo_delete_tool: 照片删除
"""

from agent.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
from agent.agno_agent.tools.reminder_tools import reminder_tool
from agent.agno_agent.tools.voice_tools import voice2text_tool, text2voice_tool
from agent.agno_agent.tools.image_tools import image2text_tool, image_send_tool, image_generate_tool
from agent.agno_agent.tools.album_tools import moments_tool, photo_delete_tool

__all__ = [
    # 核心 Tool
    "context_retrieve_tool",
    "reminder_tool",
    # 语音 Tool
    "voice2text_tool",
    "text2voice_tool",
    # 图片 Tool
    "image2text_tool",
    "image_send_tool",
    "image_generate_tool",
    # 相册 Tool
    "moments_tool",
    "photo_delete_tool",
]
