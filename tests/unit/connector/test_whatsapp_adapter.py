# -*- coding: utf-8 -*-
"""
Unit tests for WhatsApp Adapter
"""

import pytest

from connector.adapters.whatsapp.whatsapp_adapter import WhatsAppAdapter
from connector.channel.types import ChatType, MessageType, StandardMessage


class TestWhatsAppAdapter:
    """Test WhatsApp adapter message conversion."""

    def setup_method(self):
        """Create adapter instance for testing."""
        self.adapter = WhatsAppAdapter(
            phone_number_id="test_phone_id",
            access_token="test_access_token",
            verify_token="test_verify_token",
        )

    def test_channel_properties(self):
        """Test adapter channel properties."""
        assert self.adapter.channel_id == "whatsapp"
        assert self.adapter.display_name == "WhatsApp"

    def test_capabilities(self):
        """Test adapter capabilities."""
        caps = self.adapter.capabilities
        assert MessageType.TEXT in caps.message_types
        assert MessageType.IMAGE in caps.message_types
        assert MessageType.VOICE in caps.message_types
        assert MessageType.VIDEO in caps.message_types
        assert MessageType.FILE in caps.message_types
        assert MessageType.LOCATION in caps.message_types
        assert MessageType.CONTACT in caps.message_types
        assert ChatType.PRIVATE in caps.chat_types
        assert ChatType.GROUP in caps.chat_types
        assert caps.supports_reply is True
        assert caps.supports_mention is False
        assert caps.max_text_length == 4096

    def test_to_standard_text_message(self):
        """Test converting private text message."""
        whatsapp_message = {
            "id": "wamid.msg123",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567890",
            "text": {"body": "Hello, bot!"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_id == "wamid.msg123"
        assert std_msg.platform == "whatsapp"
        assert std_msg.chat_type == ChatType.PRIVATE
        assert std_msg.from_user == "15551234567"
        assert std_msg.to_user == "15559876543"
        assert std_msg.message_type == MessageType.TEXT
        assert std_msg.content == "Hello, bot!"
        assert std_msg.timestamp == 1234567890

    def test_to_standard_group_message(self):
        """Test converting group text message."""
        whatsapp_message = {
            "id": "wamid.msg124",
            "from": "15551234567@s.whatsapp.net",  # 私聊格式
            "to": "15559876543",
            "timestamp": "1234567891",
            "text": {"body": "Hello group!"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.chat_type == ChatType.PRIVATE  # s.whatsapp.net 是私聊

    def test_to_standard_group_message_with_g_us(self):
        """Test converting group text message with @g.us suffix."""
        whatsapp_message = {
            "id": "wamid.msg125",
            "from": "15551234567@g.us",  # 群聊格式
            "to": "15559876543",
            "timestamp": "1234567892",
            "text": {"body": "Hello group!"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.chat_type == ChatType.GROUP

    def test_to_standard_image_message(self):
        """Test converting image message."""
        whatsapp_message = {
            "id": "wamid.msg126",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567893",
            "image": {"id": "media123", "caption": "Nice photo!"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.IMAGE
        assert std_msg.content == "Nice photo!"
        assert std_msg.media_url == "media123"

    def test_to_standard_image_without_caption(self):
        """Test converting image message without caption."""
        whatsapp_message = {
            "id": "wamid.msg127",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567894",
            "image": {"id": "media124"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.IMAGE
        assert std_msg.content == "[图片]"

    def test_to_standard_video_message(self):
        """Test converting video message."""
        whatsapp_message = {
            "id": "wamid.msg128",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567895",
            "video": {"id": "media125", "caption": "Check this"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.VIDEO
        assert std_msg.content == "Check this"
        assert std_msg.media_url == "media125"

    def test_to_standard_audio_message(self):
        """Test converting audio message."""
        whatsapp_message = {
            "id": "wamid.msg129",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567896",
            "audio": {"id": "media126"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.VOICE
        assert std_msg.content == "[语音]"
        assert std_msg.media_url == "media126"

    def test_to_standard_document_message(self):
        """Test converting document message."""
        whatsapp_message = {
            "id": "wamid.msg130",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567897",
            "document": {"id": "media127", "filename": "report.pdf"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.FILE
        assert std_msg.content == "report.pdf"
        assert std_msg.media_url == "media127"

    def test_to_standard_location_message(self):
        """Test converting location message."""
        whatsapp_message = {
            "id": "wamid.msg131",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567898",
            "location": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "name": "San Francisco",
            },
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.LOCATION
        assert "San Francisco" in std_msg.content
        assert "37.7749" in std_msg.content
        assert "-122.4194" in std_msg.content

    def test_to_standard_location_message_without_name(self):
        """Test converting location message without name."""
        whatsapp_message = {
            "id": "wamid.msg132",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567899",
            "location": {"latitude": 40.7128, "longitude": -74.0060},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.LOCATION
        assert "[位置]" in std_msg.content

    def test_to_standard_contact_message(self):
        """Test converting contact message."""
        whatsapp_message = {
            "id": "wamid.msg133",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567900",
            "contacts": [
                {
                    "name": {"formatted_name": "John Doe"},
                    "phones": [{"phone": "+15551112222"}],
                }
            ],
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.CONTACT
        assert "John Doe" in std_msg.content
        assert "+15551112222" in std_msg.content

    def test_to_standard_contact_message_without_phone(self):
        """Test converting contact message without phone."""
        whatsapp_message = {
            "id": "wamid.msg134",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567901",
            "contacts": [{"name": {"formatted_name": "Jane Doe"}}],
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.message_type == MessageType.CONTACT
        assert "Jane Doe" in std_msg.content

    def test_to_standard_with_reply_context(self):
        """Test converting message with reply context."""
        whatsapp_message = {
            "id": "wamid.msg135",
            "from": "15551234567",
            "to": "15559876543",
            "timestamp": "1234567902",
            "text": {"body": "Yes, I agree"},
            "context": {"id": "wamid.msg130"},
        }

        std_msg = self.adapter.to_standard(whatsapp_message)

        assert std_msg.reply_to_id == "wamid.msg130"
        assert std_msg.content == "Yes, I agree"

    def test_from_standard_text_message(self):
        """Test converting standard text message to WhatsApp format."""
        std_msg = StandardMessage(
            platform="whatsapp",
            to_user="15551234567",
            message_type=MessageType.TEXT,
            content="Hello, WhatsApp!",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["to"] == "15551234567"
        assert result["type"] == "text"
        assert result["text"]["body"] == "Hello, WhatsApp!"

    def test_from_standard_image_message(self):
        """Test converting standard image message to WhatsApp format."""
        std_msg = StandardMessage(
            platform="whatsapp",
            to_user="15551234567",
            message_type=MessageType.IMAGE,
            content="Nice image",
            media_url="https://example.com/image.jpg",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["to"] == "15551234567"
        assert result["type"] == "image"
        assert result["image"]["link"] == "https://example.com/image.jpg"
        assert result["image"]["caption"] == "Nice image"

    def test_from_standard_video_message(self):
        """Test converting standard video message to WhatsApp format."""
        std_msg = StandardMessage(
            platform="whatsapp",
            to_user="15551234567",
            message_type=MessageType.VIDEO,
            content="Check this",
            media_url="https://example.com/video.mp4",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["type"] == "video"
        assert result["video"]["link"] == "https://example.com/video.mp4"

    def test_from_standard_file_message(self):
        """Test converting standard file message to WhatsApp format."""
        std_msg = StandardMessage(
            platform="whatsapp",
            to_user="15551234567",
            message_type=MessageType.FILE,
            content="Report",
            media_url="https://example.com/file.pdf",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["type"] == "document"
        assert result["document"]["link"] == "https://example.com/file.pdf"

    @pytest.mark.asyncio
    async def test_verify_webhook_success(self):
        """Test successful webhook verification."""
        result = await self.adapter.verify_webhook(
            "subscribe", "test_verify_token", "challenge123"
        )
        assert result == "challenge123"

    @pytest.mark.asyncio
    async def test_verify_webhook_wrong_mode(self):
        """Test webhook verification with wrong mode."""
        result = await self.adapter.verify_webhook(
            "unsubscribe", "test_verify_token", "challenge123"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_webhook_wrong_token(self):
        """Test webhook verification with wrong token."""
        result = await self.adapter.verify_webhook(
            "subscribe", "wrong_token", "challenge123"
        )
        assert result is None

    def test_webhook_path(self):
        """Test webhook path property."""
        assert self.adapter.webhook_path == "/webhook/whatsapp"

    def test_verify_signature(self):
        """Test signature verification."""
        import hmac
        import hashlib

        # 测试正确的签名
        app_secret = "test_secret"
        payload = b'{"test": "data"}'
        signature = "sha256=" + hmac.new(
            app_secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        # 设置 app_secret
        self.adapter._app_secret = app_secret
        assert self.adapter.verify_signature(payload, signature) is True

    def test_verify_signature_invalid(self):
        """Test invalid signature verification."""
        payload = b'{"test": "data"}'
        signature = "sha256=invalid"

        self.adapter._app_secret = "test_secret"
        assert self.adapter.verify_signature(payload, signature) is False

    def test_verify_signature_no_secret(self):
        """Test signature verification without app_secret (should pass)."""
        payload = b'{"test": "data"}'
        signature = "sha256=invalid"

        # 不设置 app_secret，应该跳过验证
        self.adapter._app_secret = None
        assert self.adapter.verify_signature(payload, signature) is True
