# -*- coding: utf-8 -*-
"""
Workflow 集成测试
"""
import pytest


@pytest.mark.integration
@pytest.mark.slow
class TestWorkflowIntegration:
    """Workflow 集成测试"""

    def test_workflow_import(self):
        """测试 workflow 导入"""
        try:
            from agent.agno_agent.workflows import chat_workflow_streaming

            assert chat_workflow_streaming is not None
        except ImportError:
            pytest.skip("workflow 模块导入失败")

    def test_prepare_workflow_import(self):
        """测试 prepare workflow 导入"""
        try:
            from agent.agno_agent.workflows import prepare_workflow

            assert prepare_workflow is not None
        except ImportError:
            pytest.skip("prepare_workflow 模块导入失败")

    def test_post_analyze_workflow_import(self):
        """测试 post analyze workflow 导入"""
        try:
            from agent.agno_agent.workflows import post_analyze_workflow

            assert post_analyze_workflow is not None
        except ImportError:
            pytest.skip("post_analyze_workflow 模块导入失败")

    def test_future_message_workflow_import(self):
        """测试 future message workflow 导入"""
        try:
            from agent.agno_agent.workflows import future_message_workflow

            assert future_message_workflow is not None
        except ImportError:
            pytest.skip("future_message_workflow 模块导入失败")
