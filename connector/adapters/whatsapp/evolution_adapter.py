# -*- coding: utf-8 -*-
"""
Evolution API Adapter for WhatsApp

使用 Evolution API (基于 Baileys) 实现 WhatsApp 集成。
- 不需要 Meta 开发者 API
- 支持二维码登录
- 基于 WhatsApp Web 协议
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from connector.channel.types import (
    ChannelCapabilities,
    ChatType,
    DeliveryMode,
    MessageType,
    StandardMessage,
    UserInfo,
)
from connector.channel.webhook_adapter import WebhookAdapter, WebhookConfig
from util.log_util import get_logger

logger = get_logger(__name__)


class EvolutionAdapter(WebhookAdapter):
    """
    Evolution API 适配器

    Evolution API 是一个基于 Baileys 的 WhatsApp API 服务。
    - 使用 WhatsApp Web 协议（不需要 Meta 开发者账号）
    - 支持二维码登录
    - 提供 REST API 和 Webhook

    Evolution API 文档: https://doc.evolution-api.com/
    Baileys 仓库: https://github.com/WhiskeySockets/Baileys

    使用方式：
    1. 启动 Evolution API Docker 容器
    2. 配置 Coke 的 Evolution API 地址和 API Key
    3. Coke 提供 Webhook URL 接收消息
    4. 通过 REST API 发送消息
    """

    DEFAULT_API_BASE = "http://localhost:8080"

    def __init__(
        self,
        api_base: str,
        api_key: str,
        instance_name: str,
        webhook_url: str,
        webhook_path: str = "/webhook/whatsapp",
    ):
        """
        初始化 Evolution API 适配器

        Args:
            api_base: Evolution API 基础地址 (如 http://localhost:8080)
            api_key: Evolution API 密钥 (AUTHENTICATION_API_KEY)
            instance_name: 实例名称 (用于创建/连接 WhatsApp 实例)
            webhook_url: Coke 的 Webhook URL (Evolution API 将推送消息到此)
            webhook_path: Coke 接收 Webhook 的路径
        """
        config = WebhookConfig(webhook_path=webhook_path)
        super().__init__(config)

        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._instance_name = instance_name
        self._webhook_url = webhook_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            "Content-Type": "application/json",
            "apikey": self._api_key,
        }

    @property
    def channel_id(self) -> str:
        return "whatsapp"

    @property
    def display_name(self) -> str:
        return "WhatsApp (Evolution API)"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            message_types=[
                MessageType.TEXT,
                MessageType.IMAGE,
                MessageType.VOICE,
                MessageType.VIDEO,
                MessageType.FILE,
                MessageType.LOCATION,
                MessageType.CONTACT,
                MessageType.STICKER,
            ],
            chat_types=[ChatType.PRIVATE, ChatType.GROUP],
            supports_reply=True,
            supports_mention=True,  # WhatsApp 支持 @提及
            supports_edit=False,
            supports_delete=False,
            max_text_length=4096,
            max_media_size_mb=100,
        )

    # ==================== Evolution API 端点 ====================

    def _get_endpoint(self, path: str) -> str:
        """构建完整的 API 端点 URL"""
        return f"{self._api_base}/{path}"

    # ==================== 实例管理 ====================

    async def create_instance(self) -> Dict[str, Any]:
        """
        创建新的 WhatsApp 实例

        Returns:
            Dict: 实例信息 (包含 qrcode 用于扫码登录)
        """
        url = self._get_endpoint(f"instance/create")
        data = {
            "instanceName": self._instance_name,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
        }

        try:
            async with self._session.post(
                url, headers=self._headers, json=data
            ) as resp:
                if resp.status == 201:
                    result = await resp.json()
                    logger.info(f"Evolution API 实例创建成功: {self._instance_name}")
                    return result
                else:
                    error_text = await resp.text()
                    logger.error(f"创建实例失败: {resp.status}, {error_text}")
                    raise Exception(f"创建实例失败: {error_text}")
        except Exception as e:
            logger.error(f"创建实例异常: {e}")
            raise

    async def connect_instance(self) -> Dict[str, Any]:
        """
        连接到已存在的实例

        Returns:
            Dict: 连接状态和二维码 (如果需要重新扫码)
        """
        url = self._get_endpoint(
            f"instance/connect/{self._instance_name}"
        )

        try:
            async with self._session.get(url, headers=self._headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(f"Evolution API 连接成功: {self._instance_name}")
                    return result
                else:
                    error_text = await resp.text()
                    logger.error(f"连接实例失败: {resp.status}, {error_text}")
                    raise Exception(f"连接实例失败: {error_text}")
        except Exception as e:
            logger.error(f"连接实例异常: {e}")
            raise

    async def get_instance_status(self) -> Dict[str, Any]:
        """获取实例状态"""
        url = self._get_endpoint(
            f"instance/connectionState/{self._instance_name}"
        )

        try:
            async with self._session.get(url, headers=self._headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    # Evolution API v2 返回 {"instance": {"state": "open"}}
                    instance = result.get("instance", {})
                    if instance:
                        return {"state": instance.get("state", "unknown")}
                    return result
                return {"state": "unknown"}
        except Exception as e:
            logger.error(f"获取实例状态异常: {e}")
            return {"state": "error"}

    async def setup_webhook(self) -> bool:
        """
        配置 Evolution API 的 Webhook

        让 Evolution API 将消息推送到 Coke

        Returns:
            bool: 是否配置成功
        """
        url = self._get_endpoint(
            f"webhook/set/{self._instance_name}"
        )
        data = {
            "webhook": {
                "url": self._webhook_url,
                "enabled": True,
                "webhookByEvents": False,
                "events": [
                    "MESSAGES_UPSERT",
                    "MESSAGES_UPDATE",
                    "SEND_MESSAGE",
                    "CONNECTION_UPDATE",
                ],
            }
        }

        try:
            async with self._session.post(
                url, headers=self._headers, json=data
            ) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Evolution API Webhook 配置成功: {self._webhook_url}")
                    return True
                else:
                    error_text = await resp.text()
                    logger.error(f"Webhook 配置失败: {resp.status}, {error_text}")
                    return False
        except Exception as e:
            logger.error(f"Webhook 配置异常: {e}")
            return False

    # ==================== Webhook 处理 ====================

    async def verify_webhook(
        self, mode: str, token: str, challenge: str
    ) -> Optional[str]:
        """
        验证 Webhook 订阅

        Evolution API 不需要验证，直接返回成功
        """
        return challenge

    async def handle_webhook(self, payload: Dict[str, Any]) -> None:
        """
        处理 Evolution API Webhook 推送

        Args:
            payload: Webhook 负载 (Evolution API 格式)
        """
        try:
            event = payload.get("event", "")

            if event == "messages.upsert":
                await self._handle_message_upsert(payload)
            elif event == "connection.update":
                await self._handle_connection_update(payload)
            elif event == "send.message":
                # 消息发送确认，可以忽略
                pass
            else:
                logger.debug(f"未处理的 Webhook 事件: {event}")

        except Exception as e:
            logger.error(f"Evolution API Webhook 处理异常: {e}")

    async def _handle_message_upsert(self, payload: Dict[str, Any]):
        """处理消息接收事件"""
        data = payload.get("data", {})
        messages = data if isinstance(data, list) else [data]

        for msg_data in messages:
            # 跳过自己发送的消息
            key = msg_data.get("key", {})
            if key.get("fromMe", False):
                continue

            std_msg = self.to_standard(msg_data)
            await self._emit_message(std_msg)
            logger.debug(
                f"WhatsApp 收到消息: from={std_msg.from_user}, "
                f"content={std_msg.content[:50]}"
            )

    async def _handle_connection_update(self, payload: Dict[str, Any]):
        """处理连接状态更新"""
        data = payload.get("data", {})
        state = data.get("state", "")
        logger.info(f"Evolution API 连接状态更新: {state}")

    # ==================== 消息转换 ====================

    def to_standard(self, raw_message: Dict[str, Any]) -> StandardMessage:
        """
        Evolution API 消息 → 标准消息格式

        Args:
            raw_message: Evolution API message 对象

        Returns:
            StandardMessage: 标准化消息
        """
        # 基本信息
        message_id = raw_message.get("key", {}).get("id", "")
        key = raw_message.get("key", {})
        from_user = key.get("remoteJid", "")
        from_me = key.get("fromMe", False)
        participant = key.get("participant", "")

        timestamp = raw_message.get("messageTimestamp", 0)

        # 确定会话类型
        chat_type = ChatType.GROUP if from_user.endswith("@g.us") else ChatType.PRIVATE

        # 提取消息内容
        message_type, content, media_url = self._extract_message_content(raw_message)

        # 构建标准消息
        std_msg = StandardMessage(
            message_id=message_id,
            platform=self.channel_id,
            chat_type=chat_type,
            from_user=(
                participant
                if chat_type == ChatType.GROUP and participant
                else from_user
            ),
            to_user="" if from_me else "bot",
            message_type=message_type,
            content=content,
            media_url=media_url,
            timestamp=timestamp,
            chatroom_id=from_user if chat_type == ChatType.GROUP else None,
            metadata={
                "evolution_message_id": message_id,
                "evolution_remote_jid": from_user,
                "raw_message": raw_message,
            },
        )

        # 处理上下文（回复消息）
        # contextInfo 可能在 message 内部或直接在 raw_message
        message_obj = raw_message.get("message", {})
        context = message_obj.get("contextInfo") or raw_message.get("contextInfo")
        if context and "stanzaId" in context:
            std_msg.reply_to_id = context["stanzaId"]
            quoted_msg = context.get("quotedMessage", {})
            if quoted_msg:
                std_msg.reply_to_content = self._extract_quoted_content(quoted_msg)

        # 处理提及
        mentions = context.get("mentionedJid", []) if context else []
        if mentions:
            std_msg.metadata["mentions"] = mentions

        return std_msg

    def _extract_message_content(self, raw_message: Dict) -> tuple:
        """
        提取消息内容

        Returns:
            (message_type, content, media_url)
        """
        message = raw_message.get("message", {})

        # 协议类型消息
        if "protocolMessage" in message:
            proto = message["protocolMessage"]
            proto_type = proto.get("type", 0)
            if proto_type == 0:  # 消息撤回
                return MessageType.TEXT, "[消息已撤回]", None
            return MessageType.TEXT, f"[协议消息: {proto_type}]", None

        # 文本消息
        if "conversation" in message:
            return MessageType.TEXT, message["conversation"], None

        if "extendedTextMessage" in message:
            ext = message["extendedTextMessage"]
            text = ext.get("text", "")
            return MessageType.TEXT, text, None

        # 图片消息
        if "imageMessage" in message:
            img = message["imageMessage"]
            caption = img.get("caption", "[图片]")
            return MessageType.IMAGE, caption, None

        # 音频消息
        if "audioMessage" in message:
            return MessageType.VOICE, "[语音]", None

        # 视频消息
        if "videoMessage" in message:
            vid = message["videoMessage"]
            caption = vid.get("caption", "[视频]")
            return MessageType.VIDEO, caption, None

        # 文档消息
        if "documentMessage" in message:
            doc = message["documentMessage"]
            filename = doc.get("fileName", "[文件]")
            return MessageType.FILE, filename, None

        # 位置消息
        if "locationMessage" in message:
            loc = message["locationMessage"]
            latitude = loc.get("degreesLatitude", 0)
            longitude = loc.get("degreesLongitude", 0)
            name = loc.get("name", "")
            content = (
                f"[位置] {name} ({latitude}, {longitude})"
                if name
                else f"[位置] ({latitude}, {longitude})"
            )
            return MessageType.LOCATION, content, None

        # 联系人消息
        if "contactMessage" in message:
            contact = message["contactMessage"]
            name = contact.get("vname", contact.get("displayName", "[联系人]"))
            return MessageType.CONTACT, f"[联系人] {name}", None

        # 表情包
        if "stickerMessage" in message:
            return MessageType.STICKER, "[表情包]", None

        # 列表消息
        if "listMessage" in message:
            return MessageType.TEXT, "[列表消息]", None

        # 列表响应
        if "listResponseMessage" in message:
            resp = message["listResponseMessage"]
            title = resp.get("title", "")
            return MessageType.TEXT, f"[选择了: {title}]", None

        # 按钮响应
        if "buttonsResponseMessage" in message:
            resp = message["buttonsResponseMessage"]
            text = resp.get("selectedButtonId", "")
            return MessageType.TEXT, f"[按钮: {text}]", None

        # 反应消息
        if "reactionMessage" in message:
            react = message["reactionMessage"]
            emoji = react.get("text", "")
            return MessageType.TEXT, f"[反应: {emoji}]", None

        # 默认
        return MessageType.TEXT, "[不支持的消息类型]", None

    def _extract_quoted_content(self, quoted_msg: Dict) -> Optional[str]:
        """提取被引用消息的内容"""
        if "conversation" in quoted_msg:
            return quoted_msg["conversation"]
        if "extendedTextMessage" in quoted_msg:
            return quoted_msg["extendedTextMessage"].get("text", "")
        return None

    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → Evolution API 格式

        注意：Evolution API 使用 REST API 发送消息，不需要转换消息格式。
        此方法仅用于内部一致性检查。

        Args:
            message: 标准化消息

        Returns:
            Dict: 消息数据字典（用于调试/日志）
        """
        return {
            "to": message.to_user,
            "type": message.message_type.value,
            "content": message.content,
            "media_url": message.media_url,
            "reply_to_id": message.reply_to_id,
        }

    # ==================== 消息发送 ====================

    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到 WhatsApp

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        try:
            if message.message_type == MessageType.TEXT:
                return await self.send_text(message.to_user, message.content)
            elif message.message_type == MessageType.IMAGE:
                return await self.send_media(
                    message.to_user, "image", message.content, message.media_url
                )
            elif message.message_type == MessageType.VIDEO:
                return await self.send_media(
                    message.to_user, "video", message.content, message.media_url
                )
            elif message.message_type == MessageType.VOICE:
                return await self.send_audio(message.to_user, message.media_url)
            elif message.message_type == MessageType.FILE:
                return await self.send_media(
                    message.to_user, "document", message.content, message.media_url
                )
            elif message.message_type == MessageType.LOCATION:
                # 位置需要从 metadata 中解析
                return await self.send_location(
                    message.to_user,
                    message.metadata.get("latitude", 0),
                    message.metadata.get("longitude", 0),
                    message.content,
                )
            elif message.message_type == MessageType.CONTACT:
                return await self.send_contact(message.to_user, message.content)
            else:
                # 默认文本
                return await self.send_text(message.to_user, message.content)

        except Exception as e:
            logger.error(f"发送消息异常: {e}")
            return False

    async def send_text(self, to_user: str, text: str, delay: int = 1000) -> bool:
        """
        发送文本消息

        Args:
            to_user: 接收者 JID (如 8613800138000@s.whatsapp.net)
            text: 文本内容
            delay: 发送延迟 (毫秒)

        Returns:
            bool: 是否发送成功
        """
        url = self._get_endpoint(
            f"message/sendText/{self._instance_name}"
        )
        data = {
            "number": to_user,
            "text": text,
            "delay": delay,
        }

        try:
            async with self._session.post(
                url, headers=self._headers, json=data
            ) as resp:
                if resp.status == 200 or resp.status == 201:
                    logger.debug(f"WhatsApp 文本消息发送成功: {text[:50]}")
                    return True
                else:
                    error_text = await resp.text()
                    logger.error(f"文本消息发送失败: {resp.status}, {error_text}")
                    return False
        except Exception as e:
            logger.error(f"发送文本消息异常: {e}")
            return False

    async def send_media(
        self,
        to_user: str,
        media_type: str,
        caption: str,
        media_url: Optional[str],
        delay: int = 1000,
    ) -> bool:
        """
        发送媒体消息

        Args:
            to_user: 接收者 JID
            media_type: 媒体类型 (image/video/document)
            caption: 媒体描述
            media_url: 媒体 URL
            delay: 发送延迟

        Returns:
            bool: 是否发送成功
        """
        url = self._get_endpoint(
            f"message/sendMedia/{self._instance_name}"
        )
        data = {
            "number": to_user,
            "mediatype": media_type,
            "caption": caption or "",
            "delay": delay,
        }

        if media_url:
            data["mediaUrl"] = media_url

        try:
            async with self._session.post(
                url, headers=self._headers, json=data
            ) as resp:
                if resp.status == 200 or resp.status == 201:
                    logger.debug(f"WhatsApp 媒体消息发送成功: {media_type}")
                    return True
                else:
                    error_text = await resp.text()
                    logger.error(f"媒体消息发送失败: {resp.status}, {error_text}")
                    return False
        except Exception as e:
            logger.error(f"发送媒体消息异常: {e}")
            return False

    async def send_audio(
        self, to_user: str, audio_url: Optional[str], delay: int = 1000
    ) -> bool:
        """
        发送音频消息

        Args:
            to_user: 接收者 JID
            audio_url: 音频 URL
            delay: 发送延迟

        Returns:
            bool: 是否发送成功
        """
        url = self._get_endpoint(
            f"message/sendAudio/{self._instance_name}"
        )
        data = {
            "number": to_user,
            "delay": delay,
        }

        if audio_url:
            data["url"] = audio_url

        try:
            async with self._session.post(
                url, headers=self._headers, json=data
            ) as resp:
                if resp.status == 200 or resp.status == 201:
                    logger.debug("WhatsApp 音频消息发送成功")
                    return True
                else:
                    error_text = await resp.text()
                    logger.error(f"音频消息发送失败: {resp.status}, {error_text}")
                    return False
        except Exception as e:
            logger.error(f"发送音频消息异常: {e}")
            return False

    async def send_location(
        self,
        to_user: str,
        latitude: float,
        longitude: float,
        name: str,
        delay: int = 1000,
    ) -> bool:
        """
        发送位置消息

        Args:
            to_user: 接收者 JID
            latitude: 纬度
            longitude: 经度
            name: 位置名称
            delay: 发送延迟

        Returns:
            bool: 是否发送成功
        """
        url = self._get_endpoint(
            f"message/sendLocation/{self._instance_name}"
        )
        data = {
            "number": to_user,
            "latitude": latitude,
            "longitude": longitude,
            "name": name,
            "delay": delay,
        }

        try:
            async with self._session.post(
                url, headers=self._headers, json=data
            ) as resp:
                if resp.status == 200 or resp.status == 201:
                    logger.debug("WhatsApp 位置消息发送成功")
                    return True
                else:
                    error_text = await resp.text()
                    logger.error(f"位置消息发送失败: {resp.status}, {error_text}")
                    return False
        except Exception as e:
            logger.error(f"发送位置消息异常: {e}")
            return False

    async def send_contact(
        self, to_user: str, contact_info: str, delay: int = 1000
    ) -> bool:
        """
        发送联系人卡片

        Args:
            to_user: 接收者 JID
            contact_info: 联系人信息 (vCard 格式或 JSON)
            delay: 发送延迟

        Returns:
            bool: 是否发送成功
        """
        url = self._get_endpoint(
            f"message/sendContact/{self._instance_name}"
        )
        data = {
            "number": to_user,
            "contact": contact_info,
            "delay": delay,
        }

        try:
            async with self._session.post(
                url, headers=self._headers, json=data
            ) as resp:
                if resp.status == 200 or resp.status == 201:
                    logger.debug("WhatsApp 联系人消息发送成功")
                    return True
                else:
                    error_text = await resp.text()
                    logger.error(f"联系人消息发送失败: {resp.status}, {error_text}")
                    return False
        except Exception as e:
            logger.error(f"发送联系人消息异常: {e}")
            return False

    # ==================== 用户解析 ====================

    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析 WhatsApp 用户信息

        Args:
            platform_user_id: WhatsApp JID

        Returns:
            UserInfo: 用户信息
        """
        # JID 格式: 电话号码 + @s.whatsapp.net (个人) 或 @g.us (群组)
        display_name = platform_user_id.split("@")[0]
        return UserInfo(
            platform_user_id=platform_user_id,
            display_name=display_name,
            metadata={"jid": platform_user_id},
        )

    # ==================== 生命周期 ====================

    async def start(self):
        """启动适配器"""
        await super().start()
        self._session = aiohttp.ClientSession()

        # 检查实例连接状态
        try:
            status = await self.get_instance_status()
            state = status.get("state", "")

            if state in ["open", "connected"]:
                logger.info(f"Evolution API 实例已连接: {self._instance_name}")
            elif state in ["close", "connecting"]:
                logger.info(f"Evolution API 实例未连接，状态: {state}")
                # 尝试连接
                await self.connect_instance()
            else:
                logger.info(
                    f"Evolution API 实例不存在，尝试创建: {self._instance_name}"
                )
                await self.create_instance()

            # 配置 Webhook
            await self.setup_webhook()

        except Exception as e:
            logger.error(f"Evolution API 启动异常: {e}")

        logger.info("Evolution API 适配器已启动")

    async def stop(self):
        """停止适配器"""
        await super().stop()
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Evolution API 适配器已停止")

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            status = await self.get_instance_status()
            state = status.get("state", "")
            return state in ["open", "connected"]
        except Exception:
            return False
