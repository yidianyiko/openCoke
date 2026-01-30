# -*- coding: utf-8 -*-
"""
Channel Adapter 基类

定义所有平台适配器必须实现的统一接口。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from connector.channel.types import (
    ChannelCapabilities,
    ChatType,
    DeliveryMode,
    MessageType,
    StandardMessage,
    UserInfo,
)


class ChannelAdapter(ABC):
    """
    渠道适配器基类

    所有平台适配器都需要实现这个接口
    """

    # ==================== 基础属性 ====================

    @property
    @abstractmethod
    def channel_id(self) -> str:
        """
        渠道唯一标识

        示例: 'wechat', 'telegram', 'discord', 'slack'
        """
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """渠道显示名称"""
        pass

    @property
    @abstractmethod
    def delivery_mode(self) -> DeliveryMode:
        """消息投递模式: POLLING / GATEWAY / HYBRID"""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> ChannelCapabilities:
        """声明渠道支持的能力"""
        pass

    # ==================== 消息转换 ====================

    @abstractmethod
    def to_standard(self, raw_message: Dict[str, Any]) -> StandardMessage:
        """
        平台消息格式 → 标准消息格式

        Args:
            raw_message: 平台原始消息

        Returns:
            StandardMessage: 标准化消息
        """
        pass

    @abstractmethod
    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → 平台消息格式

        Args:
            message: 标准化消息

        Returns:
            Dict: 平台特定格式
        """
        pass

    # ==================== 消息发送 ====================

    @abstractmethod
    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到平台

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        pass

    async def send_text(self, to_user: str, text: str, **kwargs) -> bool:
        """便捷方法：发送文本消息"""
        msg = StandardMessage(
            platform=self.channel_id,
            to_user=to_user,
            message_type=MessageType.TEXT,
            content=text,
            **kwargs,
        )
        return await self.send_message(msg)

    async def send_media(
        self,
        to_user: str,
        media_type: MessageType,
        media_url: Optional[str] = None,
        media_data: Optional[bytes] = None,
        **kwargs,
    ) -> bool:
        """便捷方法：发送媒体消息"""
        msg = StandardMessage(
            platform=self.channel_id,
            to_user=to_user,
            message_type=media_type,
            media_url=media_url,
            media_data=media_data,
            **kwargs,
        )
        return await self.send_message(msg)

    # ==================== 用户解析 ====================

    @abstractmethod
    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析平台用户信息

        Args:
            platform_user_id: 平台用户 ID

        Returns:
            UserInfo: 用户信息，找不到返回 None
        """
        pass

    async def resolve_or_create_user(
        self, platform_user_id: str, default_name: Optional[str] = None
    ) -> UserInfo:
        """解析用户，不存在则创建"""
        user = await self.resolve_user(platform_user_id)
        if user:
            return user
        # 创建新用户（子类可覆盖）
        return UserInfo(
            platform_user_id=platform_user_id,
            display_name=default_name or platform_user_id,
        )

    # ==================== 群组支持（可选） ====================

    def is_mentioned(self, message: StandardMessage, bot_id: str) -> bool:
        """
        检测消息是否 @了机器人

        Args:
            message: 标准消息
            bot_id: 机器人的平台 ID

        Returns:
            bool: 是否被提及
        """
        return False

    def should_respond_in_group(
        self, message: StandardMessage, config: Dict[str, Any]
    ) -> bool:
        """
        群聊回复策略

        Args:
            message: 标准消息
            config: 配置（包含白名单、回复模式等）

        Returns:
            bool: 是否应该回复
        """
        return True

    def strip_mention(self, text: str) -> str:
        """
        去除文本中的 @提及

        Args:
            text: 原始文本

        Returns:
            str: 清理后的文本
        """
        return text

    # ==================== 生命周期（可选） ====================

    async def start(self):
        """启动适配器（如建立连接）"""
        pass

    async def stop(self):
        """停止适配器（如关闭连接）"""
        pass

    async def health_check(self) -> bool:
        """健康检查"""
        return True
