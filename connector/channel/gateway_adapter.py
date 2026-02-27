# -*- coding: utf-8 -*-
"""
Gateway 模式适配器基类

适用于通过实时 Gateway 推送消息的平台（Discord、Slack、WhatsApp 等）。
"""

from abc import abstractmethod
from typing import Awaitable, Callable, Optional

from connector.channel.adapter import ChannelAdapter
from connector.channel.types import (
    ChannelCapabilities,
    DeliveryMode,
    StandardMessage,
    UserInfo,
)


class GatewayAdapter(ChannelAdapter):
    """
    Gateway 模式适配器基类

    适用于：Discord、Slack、WhatsApp、Signal 等新增平台
    """

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.GATEWAY

    def __init__(self):
        """初始化 Gateway 适配器"""
        self._message_handler: Optional[
            Callable[[StandardMessage], Awaitable[None]]
        ] = None
        self._connected = False

    # ==================== 连接管理 ====================

    @abstractmethod
    async def connect(self):
        """建立与平台的连接（如 WebSocket）"""
        pass

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected

    # ==================== 消息流 ====================

    def on_message(self, handler: Callable[[StandardMessage], Awaitable[None]]):
        """
        注册消息处理回调

        Args:
            handler: 异步回调函数，接收 StandardMessage
        """
        self._message_handler = handler

    async def _emit_message(self, message: StandardMessage):
        """内部方法：触发消息处理"""
        if self._message_handler:
            await self._message_handler(message)

    # ==================== 生命周期 ====================

    async def start(self):
        """启动适配器"""
        await self.connect()
        self._connected = True

    async def stop(self):
        """停止适配器"""
        await self.disconnect()
        self._connected = False

    async def health_check(self) -> bool:
        """健康检查"""
        return self._connected
