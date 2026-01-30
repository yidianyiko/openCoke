# -*- coding: utf-8 -*-
"""
Channel Adapter 统一接口层

提供多平台接入的统一接口，支持轮询和 Gateway 两种运行模式。
"""

from connector.channel.types import (
    MessageType,
    ChatType,
    DeliveryMode,
    ChannelCapabilities,
    StandardMessage,
    UserInfo,
)
from connector.channel.adapter import ChannelAdapter
from connector.channel.polling_adapter import PollingAdapter
from connector.channel.gateway_adapter import GatewayAdapter
from connector.channel.registry import ChannelRegistry, channel_registry

__all__ = [
    # Types
    "MessageType",
    "ChatType",
    "DeliveryMode",
    "ChannelCapabilities",
    "StandardMessage",
    "UserInfo",
    # Adapters
    "ChannelAdapter",
    "PollingAdapter",
    "GatewayAdapter",
    # Registry
    "ChannelRegistry",
    "channel_registry",
]
