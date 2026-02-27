# -*- coding: utf-8 -*-
"""
Webhook 模式适配器基类

适用于通过 Webhook 推送消息的平台（WhatsApp、Facebook Messenger、Line 等）。
"""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from connector.channel.adapter import ChannelAdapter
from connector.channel.types import (
    ChannelCapabilities,
    DeliveryMode,
    StandardMessage,
    UserInfo,
)


@dataclass
class WebhookConfig:
    """Webhook 配置"""

    webhook_path: str = "/webhook"
    verify_token: Optional[str] = None  # 用于 Webhook 验证
    app_secret: Optional[str] = None  # 用于签名验证


class WebhookAdapter(ChannelAdapter):
    """
    Webhook 模式适配器基类

    适用于：WhatsApp、Facebook Messenger、Line 等平台
    """

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.WEBHOOK

    def __init__(self, config: Optional[WebhookConfig] = None):
        """
        初始化 Webhook 适配器

        Args:
            config: Webhook 配置
        """
        self.config = config or WebhookConfig()
        self._message_handler: Optional[
            Callable[[StandardMessage], Awaitable[None]]
        ] = None
        self._running = False

    # ==================== 连接管理 ====================

    @abstractmethod
    async def verify_webhook(
        self, mode: str, token: str, challenge: str
    ) -> Optional[str]:
        """
        验证 Webhook 订阅

        Args:
            mode: 订阅模式
            token: 验证令牌
            challenge: 质询字符串

        Returns:
            Optional[str]: 验证成功返回 challenge，失败返回 None
        """
        pass

    @abstractmethod
    async def handle_webhook(self, payload: Dict[str, Any]) -> None:
        """
        处理 Webhook 推送

        Args:
            payload: Webhook 负载
        """
        pass

    @property
    def webhook_path(self) -> str:
        """Webhook 路径"""
        return self.config.webhook_path

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

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
        self._running = True

    async def stop(self):
        """停止适配器"""
        self._running = False

    async def health_check(self) -> bool:
        """健康检查"""
        return self._running
