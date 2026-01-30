# -*- coding: utf-8 -*-
"""
Ecloud Adapter (WeChat) - 迁移版本

Polling 模式的微信适配器，封装现有的 Ecloud 适配器逻辑。
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
from connector.ecloud import ecloud_adapter as legacy_adapter
from connector.ecloud import ecloud_output
from util.log_util import get_logger

logger = get_logger(__name__)


# 消息类型映射
MESSAGE_TYPE_MAP = {
    "60001": MessageType.TEXT,  # 私聊文本
    "80001": MessageType.TEXT,  # 群聊文本
    "60002": MessageType.IMAGE,  # 私聊图片
    "80002": MessageType.IMAGE,  # 群聊图片
    "60004": MessageType.VOICE,  # 私聊语音
    "80004": MessageType.VOICE,  # 群聊语音
    "60014": MessageType.REFERENCE,  # 私聊引用
    "80014": MessageType.REFERENCE,  # 群聊引用
}


class EcloudAdapter(PollingAdapter):
    """
    Ecloud 微信适配器

    封装现有 Ecloud 适配器逻辑，实现统一的 PollingAdapter 接口
    """

    def __init__(
        self,
        bot_wxid: str,
        bot_nickname: str,
        poll_interval: float = 1.0,
        group_chat_config: Optional[Dict] = None,
    ):
        """
        初始化 Ecloud 适配器

        Args:
            bot_wxid: 机器人的微信 ID
            bot_nickname: 机器人的昵称
            poll_interval: 轮询间隔（秒）
            group_chat_config: 群聊配置
        """
        super().__init__(poll_interval=poll_interval)
        self._bot_wxid = bot_wxid
        self._bot_nickname = bot_nickname
        self._group_chat_config = group_chat_config or {}

    @property
    def channel_id(self) -> str:
        return "wechat"

    @property
    def display_name(self) -> str:
        return "WeChat (Ecloud)"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            message_types=[
                MessageType.TEXT,
                MessageType.IMAGE,
                MessageType.VOICE,
                MessageType.REFERENCE,
            ],
            chat_types=[ChatType.PRIVATE, ChatType.GROUP],
            supports_mention=True,
            supports_reply=True,
            max_text_length=4096,
            max_media_size_mb=25,
        )

    # ==================== 消息转换 ====================

    def to_standard(self, raw_message: Dict[str, Any]) -> StandardMessage:
        """
        Ecloud 消息 → 标准消息格式

        Args:
            raw_message: Ecloud 消息对象

        Returns:
            StandardMessage: 标准化消息
        """
        # 先使用旧版转换函数
        legacy_std = legacy_adapter.ecloud_message_to_std(raw_message)
        if not legacy_std:
            return StandardMessage(platform=self.channel_id, content="")

        # 判断是否群消息
        is_group = legacy_adapter.is_group_message(raw_message)
        group_id = raw_message["data"].get("fromGroup") if is_group else None

        # 提取消息类型
        msg_type_str = raw_message.get("messageType", "")
        message_type = MESSAGE_TYPE_MAP.get(msg_type_str, MessageType.TEXT)

        # 提取参与者信息
        from_user = raw_message["data"].get("fromUser", "")
        to_user = raw_message["data"].get("toUser", "")

        # 构建标准消息
        std_msg = StandardMessage(
            message_id=str(raw_message["data"].get("newMsgId", "")),
            platform=self.channel_id,
            chat_type=ChatType.GROUP if is_group else ChatType.PRIVATE,
            from_user=from_user,
            to_user=to_user,
            chatroom_id=group_id,
            message_type=message_type,
            content=legacy_std.get("message", ""),
            metadata={
                "ecloud_message_id": raw_message["data"].get("msgId"),
                "ecloud_new_msg_id": raw_message["data"].get("newMsgId"),
                "ecloud_wid": raw_message["data"].get("wId"),
                "ecloud_msg_type": msg_type_str,
                **legacy_std.get("metadata", {}),
            },
            timestamp=raw_message["data"].get("timestamp", 0),
        )

        # 处理引用消息
        if message_type == MessageType.REFERENCE:
            ref_metadata = legacy_std.get("metadata", {}).get("reference", {})
            if ref_metadata:
                std_msg.reply_to_content = (
                    f"{ref_metadata.get('user', '')}: {ref_metadata.get('text', '')}"
                )

        return std_msg

    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → Ecloud 发送格式

        Args:
            message: 标准化消息

        Returns:
            Dict: Ecloud 输出格式
        """
        # 构建旧版标准消息格式
        legacy_msg = {
            "message_type": message.message_type.value,
            "message": message.content,
            "metadata": message.metadata.copy(),
        }

        # 使用旧版转换函数
        return legacy_adapter.std_to_ecloud_message(legacy_msg)

    # ==================== 消息发送 ====================

    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到 Ecloud

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        ecloud_msg = self.from_standard(message)

        try:
            # 获取 wId
            w_id = message.metadata.get("ecloud_wid", "")
            to_user = message.chatroom_id or message.to_user

            if message.message_type == MessageType.TEXT:
                result = ecloud_output.send_text(to_user, ecloud_msg.get("content", ""))
            elif message.message_type == MessageType.VOICE:
                result = ecloud_output.send_voice(
                    to_user,
                    ecloud_msg.get("content", ""),
                    ecloud_msg.get("length", 0),
                )
            elif message.message_type == MessageType.IMAGE:
                result = ecloud_output.send_image(
                    to_user, ecloud_msg.get("content", "")
                )
            else:
                logger.warning(f"不支持的消息类型: {message.message_type}")
                return False

            return result
        except Exception as e:
            logger.error(f"Ecloud 发送消息失败: {e}")
            return False

    # ==================== 用户解析 ====================

    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析微信用户信息

        Args:
            platform_user_id: 微信用户 ID (wxid)

        Returns:
            UserInfo: 用户信息
        """
        # Ecloud 不提供用户信息查询 API，返回基础信息
        return UserInfo(
            platform_user_id=platform_user_id,
            display_name=platform_user_id,
            metadata={"source": "ecloud"},
        )

    # ==================== 群组支持 ====================

    def is_mentioned(self, message: StandardMessage, bot_id: str) -> bool:
        """
        检测消息是否 @了机器人

        Args:
            message: 标准消息
            bot_id: 机器人的微信 ID

        Returns:
            bool: 是否被提及
        """
        content = message.content or ""
        atlist = message.metadata.get("atlist", [])

        return legacy_adapter.is_mention_bot(
            content, self._bot_wxid, self._bot_nickname, atlist
        )

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
        if message.chat_type != ChatType.GROUP:
            return True

        # 构建旧版格式的 data
        raw_data = {
            "fromGroup": message.chatroom_id,
            "content": message.content,
            "atlist": message.metadata.get("atlist", []),
        }
        raw_message = {"data": raw_data}

        return legacy_adapter.should_respond_to_group_message(
            raw_message,
            config or self._group_chat_config,
            self._bot_wxid,
            self._bot_nickname,
        )

    def strip_mention(self, text: str) -> str:
        """
        去除文本中的 @提及

        Args:
            text: 原始文本

        Returns:
            str: 清理后的文本
        """
        # 移除 @昵称 格式
        mention_pattern = f"@{self._bot_nickname}"
        if mention_pattern in text:
            text = text.replace(mention_pattern, "").strip()
        return text

    # ==================== 轮询特有方法 ====================

    async def poll_messages(self) -> List[StandardMessage]:
        """
        轮询获取新消息

        Ecloud 通过 webhook 推送到 MongoDB，这里从 inputmessages 读取

        Returns:
            List[StandardMessage]: 新消息列表
        """
        # 实际消息由 Ecloud webhook 写入 MongoDB
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
                "platform": self.channel_id,
                "status": "pending",
                "expect_output_timestamp": {"$lte": now},
            },
        )

        sent_count = 0
        for msg in messages:
            # 转换为标准消息
            std_msg = StandardMessage(
                platform=msg.get("platform", self.channel_id),
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
