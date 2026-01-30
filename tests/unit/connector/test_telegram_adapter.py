# -*- coding: utf-8 -*-
"""
Unit tests for Telegram Adapter
"""

import pytest

from connector.adapters.telegram.telegram_adapter import TelegramAdapter
from connector.channel.types import MessageType, ChatType


class TestTelegramAdapter:
    """Test Telegram adapter message conversion."""

    def setup_method(self):
        """Create adapter instance for testing."""
        self.adapter = TelegramAdapter(bot_token="123456:ABC-DEF")

    def test_channel_properties(self):
        """Test adapter channel properties."""
        assert self.adapter.channel_id == "telegram"
        assert self.adapter.display_name == "Telegram"
        assert self.adapter.delivery_mode.value == "gateway"

    def test_capabilities(self):
        """Test adapter capabilities."""
        caps = self.adapter.capabilities
        assert MessageType.TEXT in caps.message_types
        assert MessageType.IMAGE in caps.message_types
        assert MessageType.VOICE in caps.message_types
        assert ChatType.PRIVATE in caps.chat_types
        assert ChatType.GROUP in caps.chat_types
        assert caps.supports_mention is True
        assert caps.supports_reply is True
        assert caps.max_text_length == 4096

    def test_to_standard_text_private(self):
        """Test converting private text message."""
        telegram_message = {
            "message": {
                "message_id": 123,
                "from": {"id": 456, "first_name": "John", "username": "john_doe"},
                "chat": {"id": 456, "type": "private", "first_name": "John"},
                "date": 1704153600,
                "text": "Hello, bot!",
            }
        }

        std_msg = self.adapter.to_standard(telegram_message)

        assert std_msg.message_id == "123"
        assert std_msg.platform == "telegram"
        assert std_msg.chat_type == ChatType.PRIVATE
        assert std_msg.from_user == "456"
        assert std_msg.to_user == self.adapter._bot_id
        assert std_msg.chatroom_id is None
        assert std_msg.message_type == MessageType.TEXT
        assert std_msg.content == "Hello, bot!"

    def test_to_standard_group_text(self):
        """Test converting group text message."""
        telegram_message = {
            "message": {
                "message_id": 124,
                "from": {"id": 456, "first_name": "Alice"},
                "chat": {"id": -1001234567890, "type": "supergroup", "title": "Test Group"},
                "date": 1704153600,
                "text": "Hello group!",
            }
        }

        std_msg = self.adapter.to_standard(telegram_message)

        assert std_msg.chat_type == ChatType.GROUP
        assert std_msg.chatroom_id == "-1001234567890"
        assert std_msg.content == "Hello group!"

    def test_to_standard_photo(self):
        """Test converting photo message."""
        telegram_message = {
            "message": {
                "message_id": 125,
                "from": {"id": 789, "first_name": "Bob"},
                "chat": {"id": 789, "type": "private"},
                "photo": [
                    {"file_id": "small", "file_size": 1000},
                    {"file_id": "large", "file_size": 5000},
                ],
                "caption": "Nice photo!",
            }
        }

        std_msg = self.adapter.to_standard(telegram_message)

        assert std_msg.message_type == MessageType.IMAGE
        assert std_msg.content == "Nice photo!"
        assert std_msg.media_url == "large"

    def test_to_standard_voice(self):
        """Test converting voice message."""
        telegram_message = {
            "message": {
                "message_id": 126,
                "from": {"id": 999, "first_name": "Carol"},
                "chat": {"id": 999, "type": "private"},
                "voice": {"file_id": "voice123", "duration": 15},
            }
        }

        std_msg = self.adapter.to_standard(telegram_message)

        assert std_msg.message_type == MessageType.VOICE
        assert std_msg.content == "[语音 15秒]"
        assert std_msg.media_url == "voice123"

    def test_to_standard_video(self):
        """Test converting video message."""
        telegram_message = {
            "message": {
                "message_id": 127,
                "from": {"id": 111, "first_name": "Dave"},
                "chat": {"id": 111, "type": "private"},
                "video": {"file_id": "video123", "duration": 30},
                "caption": "Check this out",
            }
        }

        std_msg = self.adapter.to_standard(telegram_message)

        assert std_msg.message_type == MessageType.VIDEO
        assert std_msg.content == "Check this out"
        assert std_msg.media_url == "video123"

    def test_to_standard_sticker(self):
        """Test converting sticker message."""
        telegram_message = {
            "message": {
                "message_id": 128,
                "from": {"id": 222, "first_name": "Eve"},
                "chat": {"id": 222, "type": "private"},
                "sticker": {"file_id": "sticker123", "emoji": "😀"},
            }
        }

        std_msg = self.adapter.to_standard(telegram_message)

        assert std_msg.message_type == MessageType.STICKER
        assert std_msg.content == "[贴纸]"

    def test_to_standard_location(self):
        """Test converting location message."""
        telegram_message = {
            "message": {
                "message_id": 129,
                "from": {"id": 333, "first_name": "Frank"},
                "chat": {"id": 333, "type": "private"},
                "location": {"latitude": 40.7128, "longitude": -74.0060},
            }
        }

        std_msg = self.adapter.to_standard(telegram_message)

        assert std_msg.message_type == MessageType.LOCATION
        assert "40.7128" in std_msg.content
        assert "-74.006" in std_msg.content

    def test_to_standard_reply(self):
        """Test converting reply message."""
        telegram_message = {
            "message": {
                "message_id": 130,
                "from": {"id": 444, "first_name": "Grace"},
                "chat": {"id": 444, "type": "private"},
                "text": "Yes, I agree",
                "reply_to_message": {
                    "message_id": 129,
                    "text": "Do you agree?",
                },
            }
        }

        std_msg = self.adapter.to_standard(telegram_message)

        assert std_msg.content == "Yes, I agree"
        assert std_msg.reply_to_id == "129"
        assert std_msg.reply_to_content == "Do you agree?"

    def test_from_standard_text(self):
        """Test converting standard text message to Telegram format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="telegram",
            to_user="123456",
            message_type=MessageType.TEXT,
            content="Hello, user!",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["chat_id"] == "123456"
        assert result["text"] == "Hello, user!"
        assert result["method"] == "sendMessage"

    def test_from_standard_photo(self):
        """Test converting standard photo message to Telegram format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="telegram",
            to_user="123456",
            message_type=MessageType.IMAGE,
            content="Nice photo",
            media_url="file123",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["chat_id"] == "123456"
        assert result["photo"] == "file123"
        assert result["caption"] == "Nice photo"
        assert result["method"] == "sendPhoto"

    def test_from_standard_voice(self):
        """Test converting standard voice message to Telegram format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="telegram",
            to_user="123456",
            message_type=MessageType.VOICE,
            content="",
            media_url="voice123",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["voice"] == "voice123"
        assert result["method"] == "sendVoice"

    def test_strip_mention(self):
        """Test stripping mentions from text."""
        assert self.adapter.strip_mention("/start hello") == "hello"
        assert self.adapter.strip_mention("@bot_name how are you?") == "how are you?"
        assert self.adapter.strip_mention("/command  text  ") == "text"  # No leading spaces
        assert self.adapter.strip_mention("hello @bot_name") == "hello"

    def test_extract_bot_id(self):
        """Test bot ID extraction."""
        adapter = TelegramAdapter(bot_token="123456:ABC-DEF1234")
        assert adapter._bot_id == "123456"
