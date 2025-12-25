# -*- coding: utf-8 -*-
"""
connector/base_connector.py 单元测试
"""
import asyncio

import pytest


class TestBaseConnector:
    """测试基础连接器"""

    @pytest.mark.asyncio
    async def test_init(self):
        """测试初始化"""
        from connector.base_connector import BaseConnector

        connector = BaseConnector(loop_time=1)
        assert connector.loop_time == 1

    @pytest.mark.asyncio
    async def test_custom_loop_time(self):
        """测试自定义循环时间"""
        from connector.base_connector import BaseConnector

        connector = BaseConnector(loop_time=5)
        assert connector.loop_time == 5

    @pytest.mark.asyncio
    async def test_input_handler_exists(self):
        """测试 input_handler 方法存在"""
        from connector.base_connector import BaseConnector

        connector = BaseConnector()
        assert hasattr(connector, "input_handler")
        assert callable(connector.input_handler)

    @pytest.mark.asyncio
    async def test_output_handler_exists(self):
        """测试 output_handler 方法存在"""
        from connector.base_connector import BaseConnector

        connector = BaseConnector()
        assert hasattr(connector, "output_handler")
        assert callable(connector.output_handler)

    @pytest.mark.asyncio
    async def test_handlers_are_coroutines(self):
        """测试 handlers 是协程"""
        from connector.base_connector import BaseConnector

        connector = BaseConnector()
        assert asyncio.iscoroutinefunction(connector.input_handler)
        assert asyncio.iscoroutinefunction(connector.output_handler)
