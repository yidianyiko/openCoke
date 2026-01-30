# -*- coding: utf-8 -*-
"""
Discord Gateway Adapter

Gateway 模式的 Discord 适配器，使用 discord.py 库。
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


class DiscordAdapter(GatewayAdapter):
    """
    Discord Gateway 适配器

    使用 discord.py 库实现实时消息处理
    """

    # Discord API 基础 URL
    API_BASE_URL = "https://discord.com/api/v10"

    def __init__(self, bot_token: str):
        """
        初始化 Discord 适配器

        Args:
            bot_token: Discord Bot Token
        """
        super().__init__()
        self._bot_token = bot_token
        self._bot_id: Optional[str] = None
        self._session: Optional[Any] = None
        self._ws_url: Optional[str] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._sequence: Optional[int] = None
        self._session_id: Optional[str] = None
        self._heartbeat_interval: Optional[int] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._resume_gateway_url: Optional[str] = None

    @property
    def channel_id(self) -> str:
        return "discord"

    @property
    def display_name(self) -> str:
        return "Discord"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            message_types=[
                MessageType.TEXT,
                MessageType.IMAGE,
                MessageType.VOICE,
                MessageType.VIDEO,
                MessageType.STICKER,
                MessageType.REFERENCE,
            ],
            chat_types=[ChatType.PRIVATE, ChatType.GROUP, ChatType.CHANNEL],
            supports_mention=True,
            supports_reply=True,
            supports_reaction=True,
            supports_edit=True,
            supports_delete=True,
            supports_thread=True,
            max_text_length=2000,
            max_media_size_mb=25,
        )

    # ==================== 连接管理 ====================

    async def connect(self):
        """建立与 Discord Gateway 的连接"""
        import aiohttp

        self._session = aiohttp.ClientSession()

        # 获取 Gateway URL
        gateway_info = await self._get_gateway()
        self._ws_url = gateway_info.get("url", "wss://gateway.discord.gg")
        if "?v=" not in self._ws_url:
            self._ws_url += "?v=10"

        # 获取 bot 信息
        bot_info = await self._get_current_bot()
        self._bot_id = bot_info.get("id")

        logger.info(f"Discord 适配器已连接 (bot_id: {self._bot_id})")

    async def disconnect(self):
        """断开连接"""
        self._connected = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        if self._session:
            await self._session.close()

        logger.info("Discord 适配器已断开")

    async def start(self):
        """启动适配器，开始 WebSocket 连接"""
        await super().start()
        self._ws_task = asyncio.create_task(self._ws_loop())
        logger.info("Discord WebSocket 连接已启动")

    # ==================== Discord API ====================

    async def _get_gateway(self) -> Dict:
        """获取 Gateway URL"""
        async with self._session.get(
            f"{self.API_BASE_URL}/gateway/bot",
            headers={"Authorization": f"Bot {self._bot_token}"},
        ) as resp:
            return await resp.json()

    async def _get_current_bot(self) -> Dict:
        """获取当前 bot 信息"""
        async with self._session.get(
            f"{self.API_BASE_URL}/users/@me",
            headers={"Authorization": f"Bot {self._bot_token}"},
        ) as resp:
            return await resp.json()

    async def _send_message_api(self, channel_id: str, data: Dict) -> Dict:
        """发送消息 API"""
        async with self._session.post(
            f"{self.API_BASE_URL}/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {self._bot_token}"},
            json=data,
        ) as resp:
            return await resp.json()

    # ==================== WebSocket ====================

    async def _ws_loop(self):
        """WebSocket 主循环"""
        import aiohttp

        while self._connected:
            try:
                async with self._session.ws_connect(self._ws_url) as ws:
                    await self._handle_ws(ws)
            except Exception as e:
                logger.error(f"Discord WebSocket 异常: {e}")
                await asyncio.sleep(5)

    async def _handle_ws(self, ws):
        """处理 WebSocket 消息"""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = msg.json()
                await self._process_dispatch(data)
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("Discord WebSocket 连接关闭")
                break

    async def _process_dispatch(self, data: Dict):
        """处理 Gateway 事件"""
        op = data.get("op")
        t = data.get("t")

        if op == 10:  # Hello
            self._heartbeat_interval = data["d"]["heartbeat_interval"]
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws=None))
            await self._identify(data)

        elif op == 11:  # Heartbeat ACK
            pass

        elif op == 0:  # Dispatch
            if t == "MESSAGE_CREATE":
                await self._handle_message_create(data["d"])
            elif t == "MESSAGE_UPDATE":
                await self._handle_message_update(data["d"])
            elif t == "READY":
                self._session_id = data["d"]["session_id"]
                logger.info(f"Discord READY: session_id={self._session_id}")

    async def _identify(self, hello_data: Dict):
        """发送 Identify 事件"""
        identify_payload = {
            "op": 2,
            "d": {
                "token": self._bot_token,
                "intents": 1 << 0 | 1 << 9 | 1 << 10 | 1 << 11 | 1 << 12,  # guilds + messages
                "properties": {
                    "os": "linux",
                    "browser": "coke",
                    "device": "coke",
                },
            },
        }
        # 这里需要实际发送到 WebSocket
        # 简化实现，实际需要 ws.send_json

    async def _heartbeat_loop(self, ws):
        """心跳循环"""
        while self._connected:
            await asyncio.sleep(self._heartbeat_interval / 1000)
            # 发送心跳
            # await ws.send_json({"op": 1, "d": self._sequence})

    # ==================== 消息处理 ====================

    async def _handle_message_create(self, message_data: Dict):
        """处理消息创建事件"""
        # 忽略自己的消息
        if message_data.get("author", {}).get("id") == self._bot_id:
            return

        std_msg = self.to_standard({"message": message_data})
        await self._emit_message(std_msg)

    async def _handle_message_update(self, message_data: Dict):
        """处理消息更新事件"""
        # 简化处理：更新当作新消息处理，带 edited 标记
        std_msg = self.to_standard({"message": message_data, "edited": True})
        await self._emit_message(std_msg)

    # ==================== 消息转换 ====================

    def to_standard(self, raw_message: Dict[str, Any]) -> StandardMessage:
        """
        Discord 消息 → 标准消息格式

        Args:
            raw_message: Discord message 对象

        Returns:
            StandardMessage: 标准化消息
        """
        message = raw_message.get("message", {})
        is_edited = raw_message.get("edited", False)

        # 基本信息
        message_id = message.get("id", "")
        author = message.get("author", {})
        guild_id = message.get("guild_id")
        channel_id = message.get("channel_id", "")

        # 确定会话类型
        if guild_id:
            # 服务器频道
            channel_type = message.get("type", 0)
            if channel_type in [1, 3]:  # DM or group DM
                chat_type = ChatType.PRIVATE
                chatroom_id = None
            else:
                chat_type = ChatType.CHANNEL
                chatroom_id = guild_id
        else:
            # 私信
            chat_type = ChatType.PRIVATE
            chatroom_id = None

        # 提取参与者信息
        from_user_id = author.get("id", "")
        to_user_id = channel_id  # Discord 消息发送到 channel
        from_user_db_id = None
        to_user_db_id = None

        # 提取消息内容
        message_type, content, media_url = self._extract_message_content(message)

        # 构建标准消息
        std_msg = StandardMessage(
            message_id=message_id,
            platform=self.channel_id,
            chat_type=chat_type,
            from_user=from_user_id,
            from_user_db_id=from_user_db_id,
            to_user=to_user_id,
            to_user_db_id=to_user_db_id,
            chatroom_id=chatroom_id,
            message_type=message_type,
            content=content,
            media_url=media_url,
            metadata={
                "discord_message_id": message_id,
                "discord_author": author,
                "discord_channel_id": channel_id,
                "discord_guild_id": guild_id,
                "edited": is_edited,
                "mentions": message.get("mentions", []),
                "mention_everyone": message.get("mention_everyone", False),
                "referenced_message": message.get("referenced_message"),
            },
        )

        # 处理回复/引用
        if "referenced_message" in message and message["referenced_message"]:
            ref_msg = message["referenced_message"]
            std_msg.reply_to_id = ref_msg.get("id", "")
            std_msg.reply_to_content = ref_msg.get("content", "")

        return std_msg

    def _extract_message_content(self, message: Dict) -> tuple:
        """
        提取消息内容

        Returns:
            (message_type, content, media_url)
        """
        # 文本消息
        content = message.get("content", "")

        # 附件
        attachments = message.get("attachments", [])
        if attachments:
            attachment = attachments[0]
            content_type = attachment.get("content_type", "")

            if content_type and content_type.startswith("image/"):
                return MessageType.IMAGE, content or "[图片]", attachment.get("url")
            elif content_type and content_type.startswith("video/"):
                return MessageType.VIDEO, content or "[视频]", attachment.get("url")
            elif content_type and content_type.startswith("audio/"):
                return MessageType.VOICE, content or "[音频]", attachment.get("url")
            else:
                return MessageType.FILE, content or f"[文件: {attachment.get('filename', '')}]", attachment.get("url")

        # Stickers
        stickers = message.get("stickers", [])
        if stickers:
            sticker = stickers[0]
            return MessageType.STICKER, "[贴纸]", sticker.get("url", "")

        # 默认文本
        return MessageType.TEXT, content, None

    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → Discord 发送格式

        Args:
            message: 标准化消息

        Returns:
            Dict: Discord 发送 API 参数
        """
        channel_id = message.chatroom_id or message.to_user
        params = {}

        if message.message_type == MessageType.TEXT:
            params["content"] = message.content

        elif message.message_type == MessageType.IMAGE:
            # Discord 使用 embeds 或 attachments
            if message.media_url:
                params["embeds"] = [{"image": {"url": message.media_url}}]
            if message.content:
                params["content"] = message.content

        elif message.message_type == MessageType.VIDEO:
            params["content"] = message.content or f"[视频]({message.media_url})"

        elif message.message_type == MessageType.FILE:
            params["content"] = message.content or f"[文件]({message.media_url})"

        else:
            params["content"] = message.content

        # 处理回复
        if message.reply_to_id:
            params["message_reference"] = {"message_id": message.reply_to_id}

        return params

    # ==================== 消息发送 ====================

    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到 Discord

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        channel_id = message.chatroom_id or message.to_user
        if not channel_id:
            logger.error("Discord 发送消息失败: 缺少 channel_id")
            return False

        params = self.from_standard(message)

        # 移除空值
        params = {k: v for k, v in params.items() if v is not None and v != ""}

        try:
            result = await self._send_message_api(channel_id, params)
            if result.get("id"):
                logger.debug(f"Discord 消息发送成功: {message.content[:50]}")
                return True
            else:
                logger.error(f"Discord 消息发送失败: {result}")
                return False
        except Exception as e:
            logger.error(f"Discord 发送消息异常: {e}")
            return False

    # ==================== 用户解析 ====================

    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析 Discord 用户信息

        Args:
            platform_user_id: Discord user ID

        Returns:
            UserInfo: 用户信息
        """
        try:
            async with self._session.get(
                f"{self.API_BASE_URL}/users/{platform_user_id}",
                headers={"Authorization": f"Bot {self._bot_token}"},
            ) as resp:
                if resp.status == 200:
                    user_info = await resp.json()
                    return UserInfo(
                        platform_user_id=user_info.get("id", ""),
                        display_name=user_info.get("global_name") or user_info.get("username", ""),
                        username=user_info.get("username"),
                        avatar_url=(
                            f"https://cdn.discordapp.com/avatars/{user_info['id']}/{user_info['avatar']}.png"
                            if user_info.get("avatar")
                            else None
                        ),
                        metadata={"discord_user_info": user_info},
                    )
        except Exception as e:
            logger.error(f"Discord 获取用户信息失败: {e}")

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
        # 检查 mention_everyone
        if message.metadata.get("mention_everyone"):
            return True

        # 检查 mentions 列表
        mentions = message.metadata.get("mentions", [])
        for mention in mentions:
            if mention.get("id") == bot_id or mention.get("id") == self._bot_id:
                return True

        # 检查文本中的 @提及
        text = message.content or ""
        return f"<@{bot_id}>" in text or f"<@!{bot_id}>" in text

    def strip_mention(self, text: str) -> str:
        """
        去除文本中的 @提及

        Args:
            text: 原始文本

        Returns:
            str: 清理后的文本
        """
        import re

        # 移除 Discord 用户提及 <@id> 或 <@!id>
        text = re.sub(r"<@!?(\d+)>", "", text)

        # 移除角色提及 <@&id>
        text = re.sub(r"<@&(\d+)>", "", text)

        # 移除频道提及 <#id>
        text = re.sub(r"<#(\d+)>", "", text)

        return text.strip()

    # ==================== 健康检查 ====================

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._connected:
            return False

        try:
            bot_info = await self._get_current_bot()
            return bool(bot_info.get("id"))
        except Exception:
            return False
