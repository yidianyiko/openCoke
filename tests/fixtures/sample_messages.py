# -*- coding: utf-8 -*-
"""
标准测试消息数据
"""
import time
from datetime import datetime


def get_text_message(content="测试消息"):
    """文本消息"""
    return {
        "type": "text",
        "content": content,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_voice_message(content="语音内容", duration=5):
    """语音消息"""
    return {
        "type": "voice",
        "content": content,
        "duration": duration,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_image_message(url="https://example.com/image.jpg"):
    """图片消息"""
    return {
        "type": "image",
        "url": url,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_multimodal_response():
    """多模态响应"""
    return [
        {"type": "text", "content": "这是文本回复"},
        {"type": "voice", "content": "这是语音回复", "emotion": "高兴"},
    ]


def get_chat_history(length=5):
    """生成聊天历史"""
    history = []
    for i in range(length):
        if i % 2 == 0:
            history.append({"role": "user", "content": f"用户消息 {i+1}"})
        else:
            history.append({"role": "assistant", "content": f"助手回复 {i+1}"})
    return history
