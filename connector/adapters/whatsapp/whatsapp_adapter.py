# -*- coding: utf-8 -*-
"""
WhatsApp Cloud Adapter

使用 WhatsApp Cloud API (Meta Graph API) 实现消息收发。
"""

import hashlib
import hmac
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


class WhatsAppAdapter(WebhookAdapter):
    """
    WhatsApp Cloud API 适配器

    使用 Meta Graph API v18.0+
    文档: https://developers.facebook.com/docs/whatsapp/cloud-api
    """

    API_BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        verify_token: str,
        app_secret: Optional[str] = None,
        webhook_path: str = "/webhook/whatsapp",
    ):
        """
        初始化 WhatsApp 适配器

        Args:
            phone_number_id: WhatsApp Phone Number ID
            access_token: Meta Access Token
            verify_token: Webhook 验证令牌（自定义字符串）
            app_secret: App Secret（用于签名验证）
            webhook_path: Webhook 路径
        """
        config = WebhookConfig(
            webhook_path=webhook_path,
            verify_token=verify_token,
            app_secret=app_secret,
        )
        super().__init__(config)

        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._app_secret = app_secret
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def channel_id(self) -> str:
        return "whatsapp"

    @property
    def display_name(self) -> str:
        return "WhatsApp"

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
            ],
            chat_types=[ChatType.PRIVATE, ChatType.GROUP],
            supports_reply=True,
            supports_mention=False,  # WhatsApp 不支持 @提及
            supports_edit=False,
            supports_delete=False,
            max_text_length=4096,
            max_media_size_mb=100,
        )

    # ==================== Webhook 处理 ====================

    async def verify_webhook(
        self, mode: str, token: str, challenge: str
    ) -> Optional[str]:
        """
        验证 Webhook 订阅

        Args:
            mode: hub.mode (应为 "subscribe")
            token: hub.verify_token
            challenge: hub.challenge

        Returns:
            Optional[str]: 验证成功返回 challenge
        """
        if mode == "subscribe" and token == self.config.verify_token:
            logger.info("WhatsApp Webhook 验证成功")
            return challenge
        logger.warning(f"WhatsApp Webhook 验证失败: mode={mode}, token={token}")
        return None

    async def handle_webhook(self, payload: Dict[str, Any]) -> None:
        """
        处理 Webhook 推送

        Args:
            payload: Webhook 负载
        """
        try:
            # 解析消息
            messages = self._extract_messages(payload)
            for msg in messages:
                await self._emit_message(msg)
                logger.debug(
                    f"WhatsApp 收到消息: from={msg.from_user}, "
                    f"content={msg.content[:50]}"
                )
        except Exception as e:
            logger.error(f"WhatsApp Webhook 处理异常: {e}")

    def _extract_messages(self, payload: Dict[str, Any]) -> List[StandardMessage]:
        """
        从 Webhook 负载中提取消息

        Args:
            payload: Webhook 负载

        Returns:
            List[StandardMessage]: 标准消息列表
        """
        messages = []

        # 遍历 entry
        for entry in payload.get("entry", []):
            changes = entry.get("changes", [])
            for change in changes:
                if change.get("field") != "messages":
                    continue

                value = change.get("value", {})
                raw_messages = value.get("messages", [])

                for raw_msg in raw_messages:
                    # 跳过自己发送的消息
                    if raw_msg.get("from") == self._phone_number_id:
                        continue

                    std_msg = self.to_standard(raw_msg, value)
                    messages.append(std_msg)

        return messages

    # ==================== 消息转换 ====================

    def to_standard(
        self, raw_message: Dict[str, Any], metadata: Optional[Dict] = None
    ) -> StandardMessage:
        """
        WhatsApp 消息 → 标准消息格式

        Args:
            raw_message: WhatsApp message 对象
            metadata: 额外的元数据（如 phone_number_id）

        Returns:
            StandardMessage: 标准化消息
        """
        # 基本信息
        message_id = raw_message.get("id")
        from_user = raw_message.get("from")
        to_user = raw_message.get("to")
        timestamp = int(raw_message.get("timestamp", 0))

        # 确定会话类型
        chat_type = ChatType.GROUP if from_user.endswith("@g.us") else ChatType.PRIVATE

        # 提取消息内容
        message_type, content, media_url = self._extract_message_content(raw_message)

        # 构建标准消息
        std_msg = StandardMessage(
            message_id=message_id,
            platform=self.channel_id,
            chat_type=chat_type,
            from_user=from_user,
            to_user=to_user,
            message_type=message_type,
            content=content,
            media_url=media_url,
            timestamp=timestamp,
            metadata={
                "whatsapp_message_id": message_id,
                "whatsapp_from": from_user,
                "whatsapp_to": to_user,
                "raw_message": raw_message,
                **(metadata or {}),
            },
        )

        # 处理上下文（回复消息）
        context = raw_message.get("context", {})
        if context and "id" in context:
            std_msg.reply_to_id = context["id"]

        return std_msg

    def _extract_message_content(self, raw_message: Dict) -> tuple:
        """
        提取消息内容

        Returns:
            (message_type, content, media_url)
        """
        # 文本消息
        if "text" in raw_message:
            text_obj = raw_message["text"]
            return MessageType.TEXT, text_obj.get("body", ""), None

        # 图片消息
        if "image" in raw_message:
            image_obj = raw_message["image"]
            return (
                MessageType.IMAGE,
                image_obj.get("caption", "[图片]"),
                image_obj.get("id"),
            )

        # 音频消息
        if "audio" in raw_message:
            audio_obj = raw_message["audio"]
            return MessageType.VOICE, "[语音]", audio_obj.get("id")

        # 视频消息
        if "video" in raw_message:
            video_obj = raw_message["video"]
            return (
                MessageType.VIDEO,
                video_obj.get("caption", "[视频]"),
                video_obj.get("id"),
            )

        # 文档消息
        if "document" in raw_message:
            doc_obj = raw_message["document"]
            filename = doc_obj.get("filename", "[文件]")
            return MessageType.FILE, filename, doc_obj.get("id")

        # 位置消息
        if "location" in raw_message:
            loc = raw_message["location"]
            latitude = loc.get("latitude", 0)
            longitude = loc.get("longitude", 0)
            name = loc.get("name", "")
            content = (
                f"[位置] {name} ({latitude}, {longitude})"
                if name
                else f"[位置] ({latitude}, {longitude})"
            )
            return MessageType.LOCATION, content, None

        # 联系人消息
        if "contacts" in raw_message:
            contacts = raw_message["contacts"]
            if contacts:
                contact = contacts[0]
                name = contact.get("name", {}).get("formatted_name", "[联系人]")
                phones = contact.get("phones", [])
                if phones:
                    phone = phones[0].get("phone", "")
                    content = f"[联系人] {name}: {phone}"
                else:
                    content = f"[联系人] {name}"
                return MessageType.CONTACT, content, None

        # 默认
        return MessageType.TEXT, "[不支持的消息类型]", None

    def from_standard(self, message: StandardMessage) -> Dict[str, Any]:
        """
        标准消息格式 → WhatsApp 发送格式

        Args:
            message: 标准化消息

        Returns:
            Dict: WhatsApp API 参数
        """
        to_phone = message.to_user
        params = {"to": to_phone, "type": "text"}

        if message.message_type == MessageType.TEXT:
            params["text"] = {"body": message.content, "preview_url": False}

        elif message.message_type == MessageType.IMAGE:
            params["type"] = "image"
            if message.media_url:
                params["image"] = {"link": message.media_url}
            if message.content:
                params.get("image", {})["caption"] = message.content

        elif message.message_type == MessageType.VIDEO:
            params["type"] = "video"
            if message.media_url:
                params["video"] = {"link": message.media_url}
            if message.content:
                params.get("video", {})["caption"] = message.content

        elif message.message_type == MessageType.FILE:
            params["type"] = "document"
            if message.media_url:
                params["document"] = {"link": message.media_url}
            if message.content:
                params.get("document", {})["caption"] = message.content

        elif message.message_type == MessageType.LOCATION:
            params["type"] = "location"
            # 解析位置信息（需要从 metadata 或 content 中解析）
            params["location"] = {
                "latitude": 0,
                "longitude": 0,
                "name": message.content,
            }

        elif message.message_type == MessageType.CONTACT:
            params["type"] = "contacts"
            params["contacts"] = [{"name": {"formatted_name": message.content}}]

        else:
            # 默认文本
            params["text"] = {"body": message.content}

        # 处理回复
        if message.reply_to_id:
            # WhatsApp 使用 context 消息回复
            # 这里需要额外处理，暂时跳过
            pass

        return params

    # ==================== 消息发送 ====================

    async def send_message(self, message: StandardMessage) -> bool:
        """
        发送消息到 WhatsApp

        Args:
            message: 标准化消息

        Returns:
            bool: 是否发送成功
        """
        if not self._session:
            self._session = aiohttp.ClientSession()

        params = self.from_standard(message)
        url = f"{self.API_BASE_URL}/{self._phone_number_id}/messages"

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with self._session.post(
                url, headers=headers, data=json.dumps(params)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.debug(f"WhatsApp 消息发送成功: {message.content[:50]}")
                    return True
                else:
                    error_text = await resp.text()
                    logger.error(f"WhatsApp 消息发送失败: {resp.status}, {error_text}")
                    return False
        except Exception as e:
            logger.error(f"WhatsApp 发送消息异常: {e}")
            return False

    async def send_text(
        self, to_user: str, text: str, preview_url: bool = False
    ) -> bool:
        """
        发送文本消息

        Args:
            to_user: 接收者电话号码
            text: 文本内容
            preview_url: 是否生成链接预览

        Returns:
            bool: 是否发送成功
        """
        msg = StandardMessage(
            platform=self.channel_id,
            to_user=to_user,
            message_type=MessageType.TEXT,
            content=text,
        )
        return await self.send_message(msg)

    # ==================== 用户解析 ====================

    async def resolve_user(self, platform_user_id: str) -> Optional[UserInfo]:
        """
        解析 WhatsApp 用户信息

        Args:
            platform_user_id: WhatsApp 电话号码 ID

        Returns:
            UserInfo: 用户信息
        """
        # WhatsApp Cloud API 不提供直接获取用户信息的接口
        # 电话号码就是用户 ID
        return UserInfo(
            platform_user_id=platform_user_id,
            display_name=platform_user_id,
            metadata={"phone_number": platform_user_id},
        )

    # ==================== 签名验证 ====================

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        验证 Webhook 签名

        Args:
            payload: 原始请求体
            signature: X-Hub-Signature-256 头

        Returns:
            bool: 签名是否有效
        """
        if not self._app_secret:
            # 未配置 app_secret，跳过验证
            return True

        # 签名格式: sha256=<hex>
        if not signature.startswith("sha256="):
            return False

        expected_signature = signature.split("=")[1]

        # 计算 HMAC
        hmac_obj = hmac.new(self._app_secret.encode(), payload, hashlib.sha256)
        calculated = hmac_obj.hexdigest()

        # 使用 compare_digest 防止时序攻击
        return hmac.compare_digest(calculated, expected_signature)

    # ==================== 媒体处理 ====================

    async def get_media_url(self, media_id: str) -> Optional[str]:
        """
        获取媒体下载 URL

        Args:
            media_id: 媒体 ID

        Returns:
            Optional[str]: 媒体 URL（有时效性）
        """
        if not self._session:
            self._session = aiohttp.ClientSession()

        url = f"{self.API_BASE_URL}/{media_id}"
        headers = {"Authorization": f"Bearer {self._access_token}"}

        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("url")
                else:
                    logger.error(f"WhatsApp 获取媒体 URL 失败: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"WhatsApp 获取媒体 URL 异常: {e}")
            return None

    # ==================== 生命周期 ====================

    async def start(self):
        """启动适配器"""
        await super().start()
        self._session = aiohttp.ClientSession()
        logger.info("WhatsApp 适配器已启动")

    async def stop(self):
        """停止适配器"""
        await super().stop()
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("WhatsApp 适配器已停止")

    async def health_check(self) -> bool:
        """健康检查"""
        return self._running
