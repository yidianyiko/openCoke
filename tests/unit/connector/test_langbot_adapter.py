# -*- coding: utf-8 -*-
"""
Unit tests for LangBot Adapter (migrated)
"""

import pytest

from connector.adapters.langbot.langbot_adapter import LangBotAdapter
from connector.channel.types import MessageType, ChatType


class TestLangBotAdapter:
    """Test LangBot adapter message conversion."""

    def setup_method(self):
        """Create adapter instance for testing."""
        self.adapter = LangBotAdapter(
            bot_uuid="test-bot-uuid",
            adapter_name="telegram",
        )

    def test_channel_properties(self):
        """Test adapter channel properties."""
        assert self.adapter.channel_id == "langbot_telegram"
        assert "Telegram" in self.adapter.display_name
        assert "LangBot" in self.adapter.display_name
        assert self.adapter.delivery_mode.value == "polling"

    def test_capabilities(self):
        """Test adapter capabilities."""
        caps = self.adapter.capabilities
        assert MessageType.TEXT in caps.message_types
        assert MessageType.IMAGE in caps.message_types
        assert MessageType.VOICE in caps.message_types
        assert ChatType.PRIVATE in caps.chat_types
        assert ChatType.GROUP in caps.chat_types

    def test_to_standard_person_text(self):
        """Test converting person text message."""
        webhook_payload = {
            "uuid": "event-123",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "test-bot-uuid",
                "adapter_name": "telegram",
                "sender": {"id": "user-789", "name": "John Doe"},
                "message": [{"type": "Plain", "text": "Hello world"}],
                "timestamp": 1704153600,
            },
        }

        std_msg = self.adapter.to_standard(webhook_payload)

        assert std_msg.platform == "langbot_telegram"
        assert std_msg.chat_type == ChatType.PRIVATE
        assert std_msg.from_user == "user-789"
        assert std_msg.to_user == "user-789"
        assert std_msg.message_type == MessageType.TEXT
        assert std_msg.content == "Hello world"
        assert std_msg.metadata["langbot_adapter"] == "telegram"

    def test_to_standard_group_text(self):
        """Test converting group text message."""
        webhook_payload = {
            "uuid": "event-456",
            "event_type": "bot.group_message",
            "data": {
                "bot_uuid": "test-bot-uuid",
                "adapter_name": "telegram",
                "group": {"id": "group-123", "name": "Test Group"},
                "sender": {"id": "user-456", "name": "Alice"},
                "message": [{"type": "Plain", "text": "Hello group"}],
                "timestamp": 1704153700,
            },
        }

        std_msg = self.adapter.to_standard(webhook_payload)

        assert std_msg.chat_type == ChatType.GROUP
        assert std_msg.chatroom_id == "group-123"
        assert std_msg.content == "Hello group"
        assert std_msg.metadata["langbot_target_type"] == "group"

    def test_to_standard_image(self):
        """Test converting image message."""
        webhook_payload = {
            "uuid": "event-img",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "test-bot-uuid",
                "adapter_name": "telegram",
                "sender": {"id": "user-222", "name": "Carol"},
                "message": [{"type": "Image", "url": "https://example.com/image.jpg"}],
                "timestamp": 1704153900,
            },
        }

        std_msg = self.adapter.to_standard(webhook_payload)

        assert std_msg.message_type == MessageType.IMAGE
        assert std_msg.media_url == "https://example.com/image.jpg"

    def test_to_standard_voice(self):
        """Test converting voice message."""
        webhook_payload = {
            "uuid": "event-voice",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "test-bot-uuid",
                "adapter_name": "telegram",
                "sender": {"id": "user-333", "name": "Dave"},
                "message": [{"type": "Voice", "url": "https://example.com/voice.ogg"}],
                "timestamp": 1704154000,
            },
        }

        std_msg = self.adapter.to_standard(webhook_payload)

        assert std_msg.message_type == MessageType.VOICE
        assert std_msg.media_url == "https://example.com/voice.ogg"

    def test_from_standard_text(self):
        """Test converting standard text message to LangBot format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="langbot_telegram",
            to_user="user-456",
            message_type=MessageType.TEXT,
            content="Hello from Coke!",
            metadata={
                "langbot_bot_uuid": "test-bot-uuid",
                "langbot_target_type": "person",
                "langbot_target_id": "user-456",
            },
        )

        result = self.adapter.from_standard(std_msg)

        assert result["bot_uuid"] == "test-bot-uuid"
        assert result["target_type"] == "person"
        assert result["target_id"] == "user-456"

    def test_strip_mention_telegram(self):
        """Test stripping Telegram-style mention."""
        adapter = LangBotAdapter(bot_uuid="test", adapter_name="telegram")
        result = adapter.strip_mention("@bot_username hello world")
        assert "hello world" in result

    def test_strip_mention_feishu(self):
        """Test stripping Feishu-style mention."""
        adapter = LangBotAdapter(bot_uuid="test", adapter_name="feishu")
        result = adapter.strip_mention('<at userid="xxx">@user</at> hello')
        assert "hello" in result
