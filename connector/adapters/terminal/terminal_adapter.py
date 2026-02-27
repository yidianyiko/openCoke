# -*- coding: utf-8 -*-
"""
Terminal Adapter - 迁移版本

Polling 模式的终端适配器，用于测试和本地开发。
"""

import asyncio
from typing import Any, Dict, List, Optional

from connector.channel.polling_adapter import PollingAdapter
from connector.channel.types import (
    ChannelCapabilities,
    ChatType,
    MessageType,
    StandardMessage,
    UserInfo,
)
from util.log_util import get_logger

logger = get_logger(__name__)


class TerminalAdapter(PollingAdapter):
    """
    Terminal 适配器

    用于测试和本地开发，通过 MongoDB 轮询收发消息
    """

    def __init__(
        self,
        user_id: str,
        character_id: str,
        poll_interval: float = 0.5,
    ):
        """
        初始化 Terminal 适配器

        Args:
            user_id: 测试用户 ID
            character_id: 测试角色 ID
            poll_interval: 轮询间隔（秒）
        """
        super().__init__(poll_interval=poll_interval)
        self._user_id = user_id
        self._character_id = character_id

    @property
    def channel_id(self) -> str:
        return "terminal"

    @property
    def display_name(self) -> str:
        return "Terminal"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            message_types=[MessageType.TEXT],
            chat_types=[ChatType.PRIVATE],
            supports_mention=False,
            supports_reply=False,
            max_text_length=4096,
            max_media_size_mb=0,
        )

    # ==================== 消息转换 ====================

    def to_standard(self, raw_message: Dict[str, Any]) -> StandardMessage:
        """
        MongoDB inputmessage → 标准消息格式

        Args:
            raw_message: MongoDB inputmessage 文档

        Returns:
            StandardMessage: 标准化消息
        """
        return StandardMessage(
            message_id=str(raw_message.get("_id", "")),
            platform=self.channel_id,
            chat_type=ChatType.PRIVATE,
            from_user=raw_message.get("from_user", ""),
            from_user_db_id=raw_message.get("from_user"),
            to_user=raw_message.get("to_user", ""),
            to_user_db_id=raw_message.get("to_user"),
            message_type=MessageType.TEXT,
            content=raw_message.get("message", ""),
            metadata=raw_message.get("metadata", {}),
            timestamp=raw_message.get("input_timestamp", 0),
        )

    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → MongoDB outputmessage 格式

        Args:
            message: 标准化消息

        Returns:
            Dict: MongoDB outputmessage 格式
        """
        return {
            "platform": self.channel_id,
            "from_user": message.from_user_db_id or self._character_id,
            "to_user": message.to_user_db_id or self._user_id,
            "chatroom_name": message.chatroom_id,
            "message_type": message.message_type.value,
            "message": message.content,
            "metadata": message.metadata,
        }

    # ==================== 消息发送 ====================

    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到 outputmessages

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        from entity.message import save_outputmessage
        from util.time_util import get_current_timestamp

        output_msg = self.from_standard(message)
        output_msg["status"] = "pending"
        output_msg["expect_output_timestamp"] = get_current_timestamp()
        output_msg["create_timestamp"] = get_current_timestamp()

        try:
            save_outputmessage(output_msg)
            logger.debug(f"Terminal 消息已发送: {message.content[:50]}")
            return True
        except Exception as e:
            logger.error(f"Terminal 发送消息失败: {e}")
            return False

    # ==================== 用户解析 ====================

    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析用户信息

        Args:
            platform_user_id: MongoDB 用户 ID

        Returns:
            UserInfo: 用户信息
        """
        from dao.user_dao import UserDAO

        user_dao = UserDAO()
        user = user_dao.get_user_by_id(platform_user_id)

        if user:
            wechat_info = user.get("platforms", {}).get("wechat", {})
            return UserInfo(
                platform_user_id=platform_user_id,
                db_user_id=str(user.get("_id")),
                display_name=wechat_info.get("nickname", user.get("name", "")),
                metadata={"terminal_user": user},
            )

        return None

    # ==================== 轮询特有方法 ====================

    async def poll_messages(self) -> List[StandardMessage]:
        """
        轮询获取新消息

        从 inputmessages 读取待处理消息

        Returns:
            List[StandardMessage]: 新消息列表
        """
        from entity.message import read_top_inputmessages

        messages = read_top_inputmessages(
            to_user=self._character_id,
            status="pending",
            platform=self.channel_id,
            limit=10,
        )

        return [self.to_standard(msg) for msg in messages]

    async def poll_and_send(self) -> int:
        """
        轮询并发送待发消息

        从 outputmessages 读取并发送（终端模式下发送只是写入 outputmessages）

        Returns:
            int: 发送的消息数量
        """
        # Terminal 模式下，消息由 terminal_chat.py 直接从 outputmessages 读取
        # 这里只返回 0
        return 0
