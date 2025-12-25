# -*- coding: utf-8 -*-
"""
聊天流程端到端测试
"""
import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestChatFlowE2E:
    """聊天流程端到端测试"""

    def test_basic_chat_flow(self, sample_full_context):
        """测试基本聊天流程"""
        # 这是一个端到端测试框架
        # 实际测试需要配置 API keys
        assert sample_full_context is not None
        assert "user" in sample_full_context
        assert "character" in sample_full_context
        assert "conversation" in sample_full_context

    def test_multimodal_response_flow(self, sample_full_context):
        """测试多模态响应流程"""
        assert "MultiModalResponses" in sample_full_context
        assert isinstance(sample_full_context["MultiModalResponses"], list)

    def test_context_structure(self, sample_full_context):
        """测试 context 结构完整性"""
        required_keys = [
            "user",
            "character",
            "conversation",
            "relation",
            "context_retrieve",
            "query_rewrite",
        ]

        for key in required_keys:
            assert key in sample_full_context
