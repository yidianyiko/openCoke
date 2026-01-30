# -*- coding: utf-8 -*-
"""
Telegram Gateway Adapter

Gateway 模式的 Telegram 适配器，使用 python-telegram-bot 库。
支持实时消息接收和发送。
"""

from typing import Dict, Any, Optional, List
import asyncio

from connector.channel.gateway_adapter import GatewayAdapter
from connector.channel.types import (
    DeliveryMode,
    ChannelCapabilities,
    StandardMessage,
    UserInfo,
    MessageType,
    ChatType,
)

from util.log_util import get_logger

logger = get_logger(__name__)


class TelegramAdapter(GatewayAdapter):
    """
    Telegram Gateway 适配器

    使用 python-telegram-bot 库实现实时消息处理
    """

    # Telegram Bot API 基础 URL
    API_BASE_URL = "https://api.telegram.org/bot"

    def __init__(self, bot_token: str):
        """
        初始化 Telegram 适配器

        Args:
            bot_token: Telegram Bot Token (从 BotFather 获取)
        """
        super().__init__()
        self._bot_token = bot_token
        self._bot_id = self._extract_bot_id(bot_token)
        self._running = False
        self._polling_task: Optional[asyncio.Task] = None
        self._offset = 0  # 用于 getUpdates 的 offset

    @property
    def channel_id(self) -> str:
        return "telegram"

    @property
    def display_name(self) -> str:
        return "Telegram"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            message_types=[
                MessageType.TEXT,
                MessageType.IMAGE,
                MessageType.VOICE,
                MessageType.VIDEO,
                MessageType.STICKER,
                MessageType.LOCATION,
                MessageType.CONTACT,
            ],
            chat_types=[ChatType.PRIVATE, ChatType.GROUP],
            supports_mention=True,
            supports_reply=True,
            supports_edit=True,
            supports_delete=True,
            max_text_length=4096,
            max_media_size_mb=50,
        )

    @staticmethod
    def _extract_bot_id(bot_token: str) -> str:
        """从 bot token 中提取 bot ID"""
        try:
            return bot_token.split(":")[0]
        except (IndexError, AttributeError):
            return "unknown"

    # ==================== 连接管理 ====================

    async def connect(self):
        """
        建立与 Telegram 的连接

        使用 getUpdates (long polling) 方式获取消息
        """
        import aiohttp

        self._session = aiohttp.ClientSession()
        self._running = True
        logger.info("Telegram 适配器已连接 (使用 long polling)")

    async def disconnect(self):
        """断开连接"""
        self._running = False

        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, "_session") and self._session:
            await self._session.close()

        logger.info("Telegram 适配器已断开")

    # ==================== 消息接收 ====================

    async def start(self):
        """启动适配器，开始轮询消息"""
        await super().start()
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("Telegram 消息轮询已启动")

    async def _polling_loop(self):
        """消息轮询循环"""
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._process_update(update)
                    # 更新 offset
                    self._offset = update["update_id"] + 1
            except Exception as e:
                logger.error(f"Telegram 轮询异常: {e}")
                await asyncio.sleep(5)

    async def _get_updates(self) -> List[Dict]:
        """通过 getUpdates API 获取更新"""
        import aiohttp

        url = f"{self.API_BASE_URL}{self._bot_token}/getUpdates"
        params = {
            "offset": self._offset,
            "timeout": 30,  # long polling
        }

        try:
            async with self._session.get(url, params=params, timeout=35) as resp:
                result = await resp.json()
                if result.get("ok"):
                    return result.get("result", [])
                else:
                    logger.error(f"getUpdates 失败: {result.get('description')}")
                    return []
        except Exception as e:
            logger.error(f"getUpdates 请求失败: {e}")
            return []

    async def _process_update(self, update: Dict):
        """处理单个更新"""
        if "message" in update:
            message = update["message"]
            std_msg = self.to_standard({"message": message})
            await self._emit_message(std_msg)
        elif "edited_message" in update:
            message = update["edited_message"]
            std_msg = self.to_standard({"message": message, "edited": True})
            await self._emit_message(std_msg)
        elif "channel_post" in update:
            message = update["channel_post"]
            std_msg = self.to_standard({"message": message, "channel_post": True})
            await self._emit_message(std_msg)
        elif "edited_channel_post" in update:
            message = update["edited_channel_post"]
            std_msg = self.to_standard({
                "message": message,
                "edited": True,
                "channel_post": True,
            })
            await self._emit_message(std_msg)

    # ==================== 消息转换 ====================

    def to_standard(self, raw_message: Dict[str, Any]) -> StandardMessage:
        """
        Telegram 消息 → 标准消息格式

        Args:
            raw_message: Telegram update/message 对象

        Returns:
            StandardMessage: 标准化消息
        """
        message = raw_message.get("message", {})
        is_edited = raw_message.get("edited", False)
        is_channel_post = raw_message.get("channel_post", False)

        # 基本信息
        message_id = str(message.get("message_id", ""))
        from_user = message.get("from", {})
        chat = message.get("chat", {})

        # 确定会话类型
        chat_type = self._map_chat_type(chat.get("type", "private"))

        # 提取参与者信息
        from_user_id = str(from_user.get("id", ""))
        to_user_id = self._bot_id  # 接收者是 bot
        chatroom_id = None

        if chat_type == ChatType.GROUP:
            chatroom_id = str(chat.get("id", ""))
        elif chat_type == ChatType.CHANNEL:
            chatroom_id = str(chat.get("id", ""))

        # 提取消息内容
        message_type, content, media_url = self._extract_message_content(message)

        # 构建标准消息
        std_msg = StandardMessage(
            message_id=message_id,
            platform=self.channel_id,
            chat_type=chat_type,
            from_user=from_user_id,
            to_user=to_user_id,
            chatroom_id=chatroom_id,
            message_type=message_type,
            content=content,
            media_url=media_url,
            metadata={
                "telegram_message_id": message_id,
                "telegram_from_user": from_user,
                "telegram_chat": chat,
                "edited": is_edited,
                "channel_post": is_channel_post,
                "reply_to_message": message.get("reply_to_message"),
            },
        )

        # 处理回复消息
        if "reply_to_message" in message:
            reply_to = message["reply_to_message"]
            std_msg.reply_to_id = str(reply_to.get("message_id", ""))
            std_msg.reply_to_content = self._extract_text_from_message(reply_to)

        return std_msg

    def _map_chat_type(self, telegram_type: str) -> ChatType:
        """映射 Telegram 聊天类型到标准类型"""
        mapping = {
            "private": ChatType.PRIVATE,
            "group": ChatType.GROUP,
            "supergroup": ChatType.GROUP,
            "channel": ChatType.CHANNEL,
        }
        return mapping.get(telegram_type, ChatType.PRIVATE)

    def _extract_message_content(self, message: Dict) -> tuple:
        """
        提取消息内容

        Returns:
            (message_type, content, media_url)
        """
        # 文本消息
        if "text" in message:
            return MessageType.TEXT, message["text"], None

        # 图片消息
        if "photo" in message:
            photos = message["photo"]
            if photos:
                largest_photo = photos[-1]  # 获取最大尺寸
                return (
                    MessageType.IMAGE,
                    message.get("caption", "[图片]"),
                    largest_photo.get("file_id"),
                )

        # 语音消息
        if "voice" in message:
            voice = message["voice"]
            return (
                MessageType.VOICE,
                f"[语音 {voice.get('duration', 0)}秒]",
                voice.get("file_id"),
            )

        # 视频消息
        if "video" in message:
            video = message["video"]
            return (
                MessageType.VIDEO,
                message.get("caption", "[视频]"),
                video.get("file_id"),
            )

        # 贴纸
        if "sticker" in message:
            sticker = message["sticker"]
            return (
                MessageType.STICKER,
                "[贴纸]",
                sticker.get("file_id"),
            )

        # 位置
        if "location" in message:
            location = message["location"]
            return (
                MessageType.LOCATION,
                f"{location.get('latitude')}, {location.get('longitude')}",
                None,
            )

        # 联系人
        if "contact" in message:
            contact = message["contact"]
            return (
                MessageType.CONTACT,
                f"{contact.get('first_name', '')} {contact.get('phone_number', '')}",
                None,
            )

        # 文档
        if "document" in message:
            document = message["document"]
            return (
                MessageType.FILE,
                message.get("caption", f"[文件: {document.get('file_name', '')}]"),
                document.get("file_id"),
            )

        # 默认
        return MessageType.TEXT, "[不支持的消息类型]", None

    def _extract_text_from_message(self, message: Dict) -> str:
        """从消息中提取文本"""
        if "text" in message:
            return message["text"]
        if "caption" in message:
            return message["caption"]
        return "[非文本消息]"

    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → Telegram 发送格式

        Args:
            message: 标准化消息

        Returns:
            Dict: Telegram sendXXX API 参数
        """
        chat_id = message.chatroom_id or message.to_user
        params = {"chat_id": chat_id}

        if message.message_type == MessageType.TEXT:
            params["text"] = message.content
            params["method"] = "sendMessage"

        elif message.message_type == MessageType.IMAGE:
            params["photo"] = message.media_url
            if message.content:
                params["caption"] = message.content
            params["method"] = "sendPhoto"

        elif message.message_type == MessageType.VOICE:
            params["voice"] = message.media_url
            params["method"] = "sendVoice"

        elif message.message_type == MessageType.VIDEO:
            params["video"] = message.media_url
            if message.content:
                params["caption"] = message.content
            params["method"] = "sendVideo"

        elif message.message_type == MessageType.FILE:
            params["document"] = message.media_url
            if message.content:
                params["caption"] = message.content
            params["method"] = "sendDocument"

        else:
            # 默认发送文本
            params["text"] = message.content
            params["method"] = "sendMessage"

        # 处理回复
        if message.reply_to_id and message.metadata.get("telegram_message_id"):
            params["reply_to_message_id"] = message.reply_to_id

        return params

    # ==================== 消息发送 ====================

    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到 Telegram

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        import aiohttp

        params = self.from_standard(message)
        method = params.pop("method", "sendMessage")
        url = f"{self.API_BASE_URL}{self._bot_token}/{method}"

        try:
            async with self._session.post(url, json=params, timeout=30) as resp:
                result = await resp.json()
                if result.get("ok"):
                    logger.debug(f"Telegram 消息发送成功: {message.content[:50]}")
                    return True
                else:
                    logger.error(f"Telegram 消息发送失败: {result.get('description')}")
                    return False
        except Exception as e:
            logger.error(f"Telegram 发送消息异常: {e}")
            return False

    # ==================== 用户解析 ====================

    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析 Telegram 用户信息

        Args:
            platform_user_id: Telegram user ID

        Returns:
            UserInfo: 用户信息
        """
        # Telegram getChat API
        import aiohttp

        url = f"{self.API_BASE_URL}{self._bot_token}/getChat"

        try:
            async with self._session.get(url, params={"chat_id": platform_user_id}) as resp:
                result = await resp.json()
                if result.get("ok"):
                    chat_info = result.get("result", {})
                    return UserInfo(
                        platform_user_id=str(chat_info.get("id", "")),
                        display_name=chat_info.get("first_name", ""),
                        username=chat_info.get("username"),
                        metadata={"telegram_chat_info": chat_info},
                    )
        except Exception as e:
            logger.error(f"Telegram 获取用户信息失败: {e}")

        return None

    # ==================== 群组支持 ====================

    def is_mentioned(self, message: StandardMessage, bot_id: str) -> bool:
        """
        检测消息是否 @了机器人

        Args:
            message: 标准消息
            bot_id: 机器人的平台 ID

        Returns:
            bool: 是否被提及
        """
        # Telegram 的 entities 中包含 mention 信息
        entities = message.metadata.get("telegram_message", {}).get("entities", [])

        for entity in entities:
            if entity.get("type") == "mention":
                # 检查是否是 @bot_username
                return True
            if entity.get("type") == "bot_command":
                return True

        # 检查文本中是否有 @bot_username
        text = message.content or ""
        return f"@{bot_id}" in text

    def strip_mention(self, text: str) -> str:
        """
        去除文本中的 @提及

        Args:
            text: 原始文本

        Returns:
            str: 清理后的文本
        """
        import re

        # 移除 /command 开头
        text = re.sub(r"^/\w+\s*", "", text)

        # 移除 @username 提及
        text = re.sub(r"@\w+\s*", "", text)

        return text.strip()

    # ==================== 健康检查 ====================

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._connected:
            return False

        try:
            import aiohttp

            url = f"{self.API_BASE_URL}{self._bot_token}/getMe"
            async with self._session.get(url, timeout=10) as resp:
                result = await resp.json()
                return result.get("ok", False)
        except Exception:
            return False
