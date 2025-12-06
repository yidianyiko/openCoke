# -*- coding: utf-8 -*-
"""
Voice Tools for Agno Agent

This module provides voice processing capabilities:
- voice2text_tool: 语音转文字 (阿里云 ASR)
- text2voice_tool: 文字转语音 (MiniMax T2A)

Requirements: FR-004, FR-005, FR-051, FR-052, FR-053
"""

import logging
from typing import List, Tuple, Optional, Literal
from agno.tools import tool

logger = logging.getLogger(__name__)


@tool(description="将语音文件转换为文字，支持 silk 格式")
def voice2text_tool(file_path: str) -> dict:
    """
    语音转文字工具
    
    使用阿里云 ASR 实时语音识别将语音文件转换为文字。
    
    Args:
        file_path: 语音文件路径，支持 silk 格式
    
    Returns:
        dict: {
            "ok": bool,  # 是否成功
            "text": str,  # 识别出的文字
            "error": str  # 错误信息（如果失败）
        }
    """
    try:
        from framework.tool.voice2text.aliyun_asr import voice_to_text
        
        result = voice_to_text(file_path)
        
        if result is not None:
            return {
                "ok": True,
                "text": result
            }
        else:
            return {
                "ok": False,
                "text": "",
                "error": "语音识别超时或失败"
            }
    except Exception as e:
        logger.error(f"voice2text_tool error: {e}")
        return {
            "ok": False,
            "text": "",
            "error": str(e)
        }


@tool(description="将文字转换为语音消息，支持情感色彩")
def text2voice_tool(
    text: str,
    emotion: Literal["无", "高兴", "悲伤", "愤怒", "害怕", "惊讶", "厌恶", "魅惑"] = "无"
) -> dict:
    """
    文字转语音工具
    
    使用 MiniMax T2A 将文字转换为语音，支持多种情感色彩。
    
    Args:
        text: 要转换的文字内容
        emotion: 情感色彩，可选值：
            - "无": 无特殊情感（默认）
            - "高兴": 开心、愉快的语气
            - "悲伤": 难过、低落的语气
            - "愤怒": 生气、恼怒的语气
            - "害怕": 恐惧、紧张的语气
            - "惊讶": 惊奇、意外的语气
            - "厌恶": 反感、嫌弃的语气
            - "魅惑": 撩人、诱惑的语气
    
    Returns:
        dict: {
            "ok": bool,  # 是否成功
            "voice_messages": list,  # [(url, voice_length), ...] 语音文件URL和时长列表
            "error": str  # 错误信息（如果失败）
        }
    """
    try:
        from qiaoyun.tool.voice import qiaoyun_voice
        
        # 调用现有的语音合成函数
        voice_messages = qiaoyun_voice(text, emotion if emotion != "无" else None)
        
        if voice_messages:
            return {
                "ok": True,
                "voice_messages": [
                    {"url": url, "voice_length": length}
                    for url, length in voice_messages
                ]
            }
        else:
            return {
                "ok": False,
                "voice_messages": [],
                "error": "语音合成失败"
            }
    except Exception as e:
        logger.error(f"text2voice_tool error: {e}")
        return {
            "ok": False,
            "voice_messages": [],
            "error": str(e)
        }


__all__ = [
    "voice2text_tool",
    "text2voice_tool",
]
