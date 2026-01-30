# -*- coding: utf-8 -*-
"""
Polling 模式适配器基类

适用于通过轮询 MongoDB 获取消息的平台（Ecloud、LangBot、Terminal）。
"""

from abc import abstractmethod
from typing import List, Dict, Any, Optional

from connector.channel.adapter import ChannelAdapter
from connector.channel.types import (
    DeliveryMode,
    ChannelCapabilities,
    StandardMessage,
    UserInfo,
)


class PollingAdapter(ChannelAdapter):
    """
    轮询模式适配器基类

    适用于：Ecloud (微信)、LangBot (Feishu/Telegram)、Terminal
    """

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.POLLING

    def __init__(self, poll_interval: float = 1.0):
        """
        初始化轮询适配器

        Args:
            poll_interval: 轮询间隔（秒）
        """
        self.poll_interval = poll_interval

    # ==================== 轮询特有方法 ====================

    @abstractmethod
    async def poll_messages(self) -> List[StandardMessage]:
        """
        轮询获取新消息

        Returns:
            List[StandardMessage]: 新消息列表
        """
        pass

    @abstractmethod
    async def poll_and_send(self) -> int:
        """
        轮询并发送待发消息

        Returns:
            int: 发送的消息数量
        """
        pass

    # ==================== 与现有系统集成 ====================

    async def input_handler(self):
        """兼容现有 BaseConnector.input_handler"""
        messages = await self.poll_messages()
        for msg in messages:
            await self._save_to_input_queue(msg)

    async def output_handler(self):
        """兼容现有 BaseConnector.output_handler"""
        await self.poll_and_send()

    async def _save_to_input_queue(self, message: StandardMessage):
        """保存消息到 MongoDB inputmessages"""
        from dao.mongo import MongoDBBase

        mongo = MongoDBBase()
        doc = {
            "input_timestamp": message.timestamp,
            "handled_timestamp": None,
            "status": "pending",
            "from_user": message.from_user_db_id,
            "platform": message.platform,
            "chatroom_name": message.chatroom_id,
            "to_user": message.to_user_db_id,
            "message_type": message.message_type.value,
            "message": message.content,
            "metadata": message.metadata,
        }
        mongo.insert_one("inputmessages", doc)

    # ==================== 输入/输出运行器 ====================

    async def input_runner(self):
        """输入轮询循环"""
        import asyncio

        while True:
            await asyncio.sleep(self.poll_interval)
            await self.input_handler()

    async def output_runner(self):
        """输出轮询循环"""
        import asyncio

        while True:
            await asyncio.sleep(self.poll_interval)
            await self.output_handler()

    async def runner(self):
        """同时运行输入和输出轮询"""
        import asyncio

        await asyncio.gather(self.input_runner(), self.output_runner())
