# -*- coding: utf-8 -*-
"""
渠道注册中心

统一管理所有渠道适配器的单例注册中心。
"""

from typing import Dict, List, Optional

from connector.channel.adapter import ChannelAdapter
from connector.channel.polling_adapter import PollingAdapter
from connector.channel.gateway_adapter import GatewayAdapter
from connector.channel.types import DeliveryMode


class ChannelRegistry:
    """
    渠道注册中心

    统一管理所有渠道适配器
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters: Dict[str, ChannelAdapter] = {}
        return cls._instance

    def register(self, adapter: ChannelAdapter):
        """
        注册适配器

        Args:
            adapter: 渠道适配器实例
        """
        self._adapters[adapter.channel_id] = adapter

    def unregister(self, channel_id: str):
        """
        注销适配器

        Args:
            channel_id: 渠道 ID
        """
        if channel_id in self._adapters:
            del self._adapters[channel_id]

    def get(self, channel_id: str) -> Optional[ChannelAdapter]:
        """
        获取适配器

        Args:
            channel_id: 渠道 ID

        Returns:
            ChannelAdapter: 适配器实例，不存在返回 None
        """
        return self._adapters.get(channel_id)

    def list_all(self) -> List[ChannelAdapter]:
        """
        列出所有适配器

        Returns:
            List[ChannelAdapter]: 所有已注册的适配器
        """
        return list(self._adapters.values())

    def list_by_mode(self, mode: DeliveryMode) -> List[ChannelAdapter]:
        """
        按投递模式列出适配器

        Args:
            mode: 投递模式

        Returns:
            List[ChannelAdapter]: 指定模式的所有适配器
        """
        return [a for a in self._adapters.values() if a.delivery_mode == mode]

    def list_polling(self) -> List[PollingAdapter]:
        """
        列出所有轮询模式适配器

        Returns:
            List[PollingAdapter]: 所有轮询模式适配器
        """
        return [
            a for a in self._adapters.values() if isinstance(a, PollingAdapter)
        ]

    def list_gateway(self) -> List[GatewayAdapter]:
        """
        列出所有 Gateway 模式适配器

        Returns:
            List[GatewayAdapter]: 所有 Gateway 模式适配器
        """
        return [
            a for a in self._adapters.values() if isinstance(a, GatewayAdapter)
        ]

    def clear(self):
        """清空所有适配器（主要用于测试）"""
        self._adapters.clear()

    def __len__(self) -> int:
        """返回已注册适配器数量"""
        return len(self._adapters)

    def __contains__(self, channel_id: str) -> bool:
        """检查渠道是否已注册"""
        return channel_id in self._adapters


# 全局单例
channel_registry = ChannelRegistry()
