# -*- coding: utf-8 -*-
"""
LangBot Adapter - 迁移版本

Polling 模式的 LangBot 适配器，封装现有的 LangBot 适配器逻辑。
支持 Feishu、Telegram 等平台。
"""

from typing import Dict, Any, List, Optional
import asyncio

from connector.channel.polling_adapter import PollingAdapter
from connector.channel.types import (
    ChannelCapabilities,
    StandardMessage,
    UserInfo,
    MessageType,
    ChatType,
)
from connector.langbot import langbot_adapter as legacy_adapter
from connector.langbot import langbot_output

from util.log_util import get_logger

logger = get_logger(__name__)


# LangBot 消息类型映射
LANGBOT_MESSAGE_TYPE_MAP = {
    "Plain": MessageType.TEXT,
    "Image": MessageType.IMAGE,
    "Voice": MessageType.VOICE,
    "At": MessageType.TEXT,
    "Face": MessageType.STICKER,
}


class LangBotAdapter(PollingAdapter):
    """
    LangBot 适配器

    封装现有 LangBot 适配器逻辑，实现统一的 PollingAdapter 接口
    支持 Feishu、Telegram 等平台
    """

    def __init__(
        self,
        bot_uuid: str,
        adapter_name: str,
        poll_interval: float = 1.0,
    ):
        """
        初始化 LangBot 适配器

        Args:
            bot_uuid: LangBot bot UUID
            adapter_name: LangBot adapter 名称 (telegram, feishu, qq_official 等)
            poll_interval: 轮询间隔（秒）
        """
        super().__init__(poll_interval=poll_interval)
        self._bot_uuid = bot_uuid
        self._adapter_name = adapter_name
        # platform 格式为 langbot_{adapter_name}
        self._platform = f"langbot_{adapter_name}"

    @property
    def channel_id(self) -> str:
        return self._platform

    @property
    def display_name(self) -> str:
        # 返回友好的平台名称
        name_map = {
            "telegram": "Telegram (LangBot)",
            "feishu": "Feishu (LangBot)",
            "qq_official": "QQ Official (LangBot)",
        }
        return name_map.get(self._adapter_name, f"{self._adapter_name.title()} (LangBot)")

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            message_types=[
                MessageType.TEXT,
                MessageType.IMAGE,
                MessageType.VOICE,
                MessageType.STICKER,
            ],
            chat_types=[ChatType.PRIVATE, ChatType.GROUP],
            supports_mention=True,
            supports_reply=True,
            max_text_length=4096,
            max_media_size_mb=20,
        )

    # ==================== 消息转换 ====================

    def to_standard(self, raw_message: Dict[str, Any]) -> StandardMessage:
        """
        LangBot webhook → 标准消息格式

        Args:
            raw_message: LangBot webhook payload

        Returns:
            StandardMessage: 标准化消息
        """
        # 使用旧版转换函数
        legacy_std = legacy_adapter.langbot_webhook_to_std(raw_message)

        event_type = raw_message.get("event_type", "")
        data = raw_message.get("data", {})

        # 判断是否群消息
        is_group = event_type == "bot.group_message"
        group_data = data.get("group", {})
        chatroom_id = group_data.get("id") if is_group else None

        # 提取发送者信息
        sender = data.get("sender", {})
        sender_id = sender.get("id", "")
        sender_name = sender.get("name", "")

        # 提取消息内容
        message_parts = data.get("message", [])
        message_type, message_content, extra_metadata = self._extract_message_content(
            message_parts
        )

        # 构建标准消息
        std_msg = StandardMessage(
            message_id=raw_message.get("uuid", ""),
            platform=self._platform,
            chat_type=ChatType.GROUP if is_group else ChatType.PRIVATE,
            from_user=sender_id,
            to_user=sender_id,  # LangBot 回复时 target 是原发送者
            chatroom_id=chatroom_id,
            message_type=message_type,
            content=message_content,
            media_url=extra_metadata.get("url"),
            metadata={
                "langbot_adapter": self._adapter_name,
                "langbot_bot_uuid": self._bot_uuid,
                "langbot_sender_id": sender_id,
                "langbot_sender_name": sender_name,
                "langbot_target_id": sender_id,
                "langbot_target_type": "group" if is_group else "person",
                "langbot_event_uuid": raw_message.get("uuid", ""),
                **extra_metadata,
            },
            timestamp=data.get("timestamp", 0),
        )

        if is_group:
            std_msg.metadata["langbot_group_id"] = group_data.get("id", "")
            std_msg.metadata["langbot_group_name"] = group_data.get("name", "")

        return std_msg

    def _extract_message_content(self, message_parts: List[Dict]) -> tuple:
        """
        提取消息内容

        Returns:
            (message_type, message_content, extra_metadata)
        """
        if not message_parts:
            return MessageType.TEXT, "", {}

        text_parts = []
        extra_metadata = {}
        detected_type = MessageType.TEXT

        for part in message_parts:
            part_type = part.get("type", "")

            if part_type == "Plain":
                text_parts.append(part.get("text", ""))
            elif part_type == "Image":
                detected_type = MessageType.IMAGE
                extra_metadata["url"] = part.get("url", "")
            elif part_type == "Voice":
                detected_type = MessageType.VOICE
                extra_metadata["url"] = part.get("url", "")

        message_content = "".join(text_parts)

        return detected_type, message_content, extra_metadata

    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → LangBot 发送格式

        Args:
            message: 标准化消息

        Returns:
            Dict: LangBot Send API 格式
        """
        # 构建旧版标准消息格式
        legacy_msg = {
            "message_type": message.message_type.value,
            "message": message.content,
            "metadata": message.metadata.copy(),
        }

        # 使用旧版转换函数
        return legacy_adapter.std_to_langbot_message(legacy_msg)

    # ==================== 消息发送 ====================

    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到 LangBot

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        langbot_msg = self.from_standard(message)

        try:
            if message.message_type == MessageType.TEXT:
                result = langbot_output.send_text(
                    langbot_msg.get("bot_uuid", self._bot_uuid),
                    langbot_msg.get("target_type", "person"),
                    langbot_msg.get("target_id", ""),
                    langbot_msg.get("message_chain", []),
                )
            elif message.message_type == MessageType.IMAGE:
                result = langbot_output.send_image(
                    langbot_msg.get("bot_uuid", self._bot_uuid),
                    langbot_msg.get("target_type", "person"),
                    langbot_msg.get("target_id", ""),
                    message.metadata.get("url", ""),
                )
            elif message.message_type == MessageType.VOICE:
                result = langbot_output.send_voice(
                    langbot_msg.get("bot_uuid", self._bot_uuid),
                    langbot_msg.get("target_type", "person"),
                    langbot_msg.get("target_id", ""),
                    message.metadata.get("url", ""),
                )
            else:
                logger.warning(f"不支持的消息类型: {message.message_type}")
                return False

            return result
        except Exception as e:
            logger.error(f"LangBot 发送消息失败: {e}")
            return False

    # ==================== 用户解析 ====================

    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析平台用户信息

        Args:
            platform_user_id: 平台用户 ID

        Returns:
            UserInfo: 用户信息
        """
        # LangBot 可能从 webhook 中获取用户信息
        return UserInfo(
            platform_user_id=platform_user_id,
            display_name=platform_user_id,
            metadata={"source": "langbot", "adapter": self._adapter_name},
        )

    # ==================== 群组支持 ====================

    def is_mentioned(self, message: StandardMessage, bot_id: str) -> bool:
        """
        检测消息是否 @了机器人

        LangBot @消息格式因平台而异：
        - Telegram: @bot_username
        - Feishu: @at_user_id

        Args:
            message: 标准消息
            bot_id: 机器人的平台 ID

        Returns:
            bool: 是否被提及
        """
        content = message.content or ""

        # Telegram 风格
        if self._adapter_name == "telegram":
            return f"@{bot_id}" in content

        # Feishu 风格 - 检查 metadata 中的 at_list
        at_list = message.metadata.get("at_list", [])
        return bot_id in at_list

    def strip_mention(self, text: str) -> str:
        """
        去除文本中的 @提及

        Args:
            text: 原始文本

        Returns:
            str: 清理后的文本
        """
        import re

        # Telegram @username
        text = re.sub(r"@\w+\s*", "", text)

        # Feishu @at (xml 格式)
        text = re.sub(r"<at userid=\"[^\"]+\">@[^<]+</at>", "", text)

        return text.strip()

    # ==================== 轮询特有方法 ====================

    async def poll_messages(self) -> List[StandardMessage]:
        """
        轮询获取新消息

        LangBot 通过 webhook 推送到 MongoDB，这里从 inputmessages 读取

        Returns:
            List[StandardMessage]: 新消息列表
        """
        # 实际消息由 LangBot webhook 写入 MongoDB
        # 这里返回空列表，由 input_handler 直接处理
        return []

    async def poll_and_send(self) -> int:
        """
        轮询并发送待发消息

        从 outputmessages 读取并发送

        Returns:
            int: 发送的消息数量
        """
        from dao.mongo import MongoDBBase
        from entity.message import update_outputmessage_status
        from util.time_util import get_current_timestamp

        mongo = MongoDBBase()
        now = get_current_timestamp()

        # 查找待发送的消息
        messages = mongo.find_many(
            "outputmessages",
            {
                "platform": self._platform,
                "status": "pending",
                "expect_output_timestamp": {"$lte": now},
            },
        )

        sent_count = 0
        for msg in messages:
            # 转换为标准消息
            std_msg = StandardMessage(
                platform=msg.get("platform", self._platform),
                to_user=msg.get("to_user", ""),
                chatroom_id=msg.get("chatroom_name"),
                message_type=MessageType(msg.get("message_type", "text")),
                content=msg.get("message", ""),
                metadata=msg.get("metadata", {}),
            )

            # 发送消息
            success = await self.send_message(std_msg)
            if success:
                update_outputmessage_status(msg["_id"], "handled", now)
                sent_count += 1
            else:
                update_outputmessage_status(msg["_id"], "failed", now)

        return sent_count
