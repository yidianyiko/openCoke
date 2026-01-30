# -*- coding: utf-8 -*-
"""
Unit tests for Channel Adapter Types
"""

from dataclasses import asdict

import pytest

from connector.channel.types import (
    ChannelCapabilities,
    ChatType,
    DeliveryMode,
    MessageType,
    StandardMessage,
    UserInfo,
)


class TestMessageType:
    """Test MessageType enum."""

    def test_message_type_values(self):
        """Test MessageType enum values."""
        assert MessageType.TEXT.value == "text"
        assert MessageType.IMAGE.value == "image"
        assert MessageType.VOICE.value == "voice"
        assert MessageType.VIDEO.value == "video"
        assert MessageType.FILE.value == "file"
        assert MessageType.REFERENCE.value == "reference"
        assert MessageType.STICKER.value == "sticker"
        assert MessageType.LOCATION.value == "location"
        assert MessageType.CONTACT.value == "contact"


class TestChatType:
    """Test ChatType enum."""

    def test_chat_type_values(self):
        """Test ChatType enum values."""
        assert ChatType.PRIVATE.value == "private"
        assert ChatType.GROUP.value == "group"
        assert ChatType.CHANNEL.value == "channel"


class TestDeliveryMode:
    """Test DeliveryMode enum."""

    def test_delivery_mode_values(self):
        """Test DeliveryMode enum values."""
        assert DeliveryMode.POLLING.value == "polling"
        assert DeliveryMode.GATEWAY.value == "gateway"
        assert DeliveryMode.HYBRID.value == "hybrid"


class TestChannelCapabilities:
    """Test ChannelCapabilities dataclass."""

    def test_default_capabilities(self):
        """Test default capabilities."""
        caps = ChannelCapabilities()
        assert caps.message_types == [MessageType.TEXT]
        assert caps.chat_types == [ChatType.PRIVATE]
        assert caps.supports_mention is False
        assert caps.supports_reply is False
        assert caps.supports_reaction is False
        assert caps.supports_edit is False
        assert caps.supports_delete is False
        assert caps.supports_thread is False
        assert caps.supports_media_upload is False
        assert caps.max_text_length == 4096
        assert caps.max_media_size_mb == 10

    def test_custom_capabilities(self):
        """Test custom capabilities."""
        caps = ChannelCapabilities(
            message_types=[MessageType.TEXT, MessageType.IMAGE, MessageType.VOICE],
            chat_types=[ChatType.PRIVATE, ChatType.GROUP],
            supports_mention=True,
            supports_reply=True,
            supports_reaction=True,
            max_text_length=2000,
        )
        assert len(caps.message_types) == 3
        assert MessageType.TEXT in caps.message_types
        assert MessageType.IMAGE in caps.message_types
        assert MessageType.VOICE in caps.message_types
        assert len(caps.chat_types) == 2
        assert caps.supports_mention is True
        assert caps.supports_reply is True
        assert caps.supports_reaction is True
        assert caps.max_text_length == 2000


class TestStandardMessage:
    """Test StandardMessage dataclass."""

    def test_default_message(self):
        """Test default message values."""
        msg = StandardMessage()
        assert msg.message_id is None
        assert msg.platform == ""
        assert msg.chat_type == ChatType.PRIVATE
        assert msg.from_user == ""
        assert msg.from_user_db_id is None
        assert msg.to_user == ""
        assert msg.to_user_db_id is None
        assert msg.chatroom_id is None
        assert msg.message_type == MessageType.TEXT
        assert msg.content == ""
        assert msg.media_url is None
        assert msg.media_data is None
        assert msg.reply_to_id is None
        assert msg.reply_to_content is None
        assert msg.metadata == {}
        assert msg.timestamp == 0
        assert msg.status == "pending"

    def test_text_message(self):
        """Test creating a text message."""
        msg = StandardMessage(
            message_id="msg-123",
            platform="telegram",
            chat_type=ChatType.PRIVATE,
            from_user="user-456",
            to_user="bot-789",
            message_type=MessageType.TEXT,
            content="Hello, world!",
            timestamp=1704153600,
        )
        assert msg.message_id == "msg-123"
        assert msg.platform == "telegram"
        assert msg.chat_type == ChatType.PRIVATE
        assert msg.from_user == "user-456"
        assert msg.to_user == "bot-789"
        assert msg.message_type == MessageType.TEXT
        assert msg.content == "Hello, world!"
        assert msg.timestamp == 1704153600

    def test_group_message(self):
        """Test creating a group message."""
        msg = StandardMessage(
            platform="discord",
            chat_type=ChatType.GROUP,
            from_user="user-123",
            to_user="bot-456",
            chatroom_id="guild-789",
            message_type=MessageType.TEXT,
            content="@bot hello",
            metadata={"mention": True},
        )
        assert msg.platform == "discord"
        assert msg.chat_type == ChatType.GROUP
        assert msg.chatroom_id == "guild-789"
        assert msg.metadata == {"mention": True}

    def test_media_message(self):
        """Test creating a media message."""
        msg = StandardMessage(
            platform="whatsapp",
            from_user="user-123",
            to_user="bot-456",
            message_type=MessageType.IMAGE,
            content="Photo",
            media_url="https://example.com/image.jpg",
        )
        assert msg.message_type == MessageType.IMAGE
        assert msg.content == "Photo"
        assert msg.media_url == "https://example.com/image.jpg"

    def test_reply_message(self):
        """Test creating a reply message."""
        msg = StandardMessage(
            platform="slack",
            from_user="user-123",
            to_user="bot-456",
            message_type=MessageType.TEXT,
            content="Yes, agreed",
            reply_to_id="msg-789",
            reply_to_content="Do you agree?",
        )
        assert msg.reply_to_id == "msg-789"
        assert msg.reply_to_content == "Do you agree?"


class TestUserInfo:
    """Test UserInfo dataclass."""

    def test_default_user_info(self):
        """Test default user info."""
        user = UserInfo(platform_user_id="user-123")
        assert user.platform_user_id == "user-123"
        assert user.db_user_id is None
        assert user.display_name is None
        assert user.username is None
        assert user.avatar_url is None
        assert user.metadata == {}

    def test_full_user_info(self):
        """Test full user info."""
        user = UserInfo(
            platform_user_id="user-456",
            db_user_id="mongo-789",
            display_name="John Doe",
            username="johndoe",
            avatar_url="https://example.com/avatar.jpg",
            metadata={"role": "admin"},
        )
        assert user.platform_user_id == "user-456"
        assert user.db_user_id == "mongo-789"
        assert user.display_name == "John Doe"
        assert user.username == "johndoe"
        assert user.avatar_url == "https://example.com/avatar.jpg"
        assert user.metadata == {"role": "admin"}
