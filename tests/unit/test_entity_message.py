# -*- coding: utf-8 -*-
"""
entity/message.py 单元测试
"""
import pytest


class TestMessageEntity:
    """测试消息实体"""

    def test_text_message_structure(self, sample_text_message):
        """测试文本消息结构"""
        assert "type" in sample_text_message
        assert sample_text_message["type"] == "text"
        assert "content" in sample_text_message
        assert "timestamp" in sample_text_message

    def test_voice_message_structure(self, sample_voice_message):
        """测试语音消息结构"""
        assert "type" in sample_voice_message
        assert sample_voice_message["type"] == "voice"
        assert "content" in sample_voice_message
        assert "duration" in sample_voice_message

    def test_message_timestamp(self, sample_text_message):
        """测试消息时间戳"""
        import time

        timestamp = sample_text_message["timestamp"]
        assert isinstance(timestamp, int)
        assert timestamp > 0
        # 时间戳应该接近当前时间
        assert abs(timestamp - int(time.time())) < 10

    def test_message_sender(self, sample_text_message):
        """测试消息发送者"""
        assert "sender" in sample_text_message
        assert isinstance(sample_text_message["sender"], str)
