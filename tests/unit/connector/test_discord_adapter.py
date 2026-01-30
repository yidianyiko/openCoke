# -*- coding: utf-8 -*-
"""
Unit tests for Discord Adapter
"""

import pytest

from connector.adapters.discord.discord_adapter import DiscordAdapter
from connector.channel.types import MessageType, ChatType


class TestDiscordAdapter:
    """Test Discord adapter message conversion."""

    def setup_method(self):
        """Create adapter instance for testing."""
        self.adapter = DiscordAdapter(bot_token="test_bot_token")

    def test_channel_properties(self):
        """Test adapter channel properties."""
        assert self.adapter.channel_id == "discord"
        assert self.adapter.display_name == "Discord"
        # Note: _connected may be False if not started

    def test_capabilities(self):
        """Test adapter capabilities."""
        caps = self.adapter.capabilities
        assert MessageType.TEXT in caps.message_types
        assert MessageType.IMAGE in caps.message_types
        assert MessageType.STICKER in caps.message_types
        assert ChatType.PRIVATE in caps.chat_types
        assert ChatType.GROUP in caps.chat_types
        assert ChatType.CHANNEL in caps.chat_types
        assert caps.supports_mention is True
        assert caps.supports_reply is True
        assert caps.supports_reaction is True
        assert caps.supports_thread is True
        assert caps.max_text_length == 2000

    def test_to_standard_private_text(self):
        """Test converting private text message."""
        discord_message = {
            "message": {
                "id": "msg123",
                "author": {"id": "user456", "username": "john_doe", "global_name": "John"},
                "channel_id": "channel789",
                "content": "Hello, bot!",
                "type": 0,  # DEFAULT
            }
        }

        std_msg = self.adapter.to_standard(discord_message)

        assert std_msg.message_id == "msg123"
        assert std_msg.platform == "discord"
        assert std_msg.chat_type == ChatType.PRIVATE
        assert std_msg.from_user == "user456"
        assert std_msg.to_user == "channel789"
        assert std_msg.chatroom_id is None
        assert std_msg.message_type == MessageType.TEXT
        assert std_msg.content == "Hello, bot!"

    def test_to_standard_channel_text(self):
        """Test converting channel text message."""
        discord_message = {
            "message": {
                "id": "msg124",
                "author": {"id": "user456", "username": "alice"},
                "channel_id": "channel789",
                "guild_id": "guild123",
                "content": "Hello channel!",
                "type": 0,
            }
        }

        std_msg = self.adapter.to_standard(discord_message)

        assert std_msg.chat_type == ChatType.CHANNEL
        assert std_msg.chatroom_id == "guild123"
        assert std_msg.content == "Hello channel!"

    def test_to_standard_with_attachment_image(self):
        """Test converting message with image attachment."""
        discord_message = {
            "message": {
                "id": "msg125",
                "author": {"id": "user789", "username": "bob"},
                "channel_id": "channel456",
                "content": "Check this image",
                "attachments": [
                    {
                        "id": "att123",
                        "filename": "photo.jpg",
                        "content_type": "image/jpeg",
                        "url": "https://cdn.discordapp.com/attachments/photo.jpg",
                    }
                ],
            }
        }

        std_msg = self.adapter.to_standard(discord_message)

        assert std_msg.message_type == MessageType.IMAGE
        assert std_msg.content == "Check this image"
        assert "photo.jpg" in std_msg.media_url

    def test_to_standard_with_attachment_video(self):
        """Test converting message with video attachment."""
        discord_message = {
            "message": {
                "id": "msg126",
                "author": {"id": "user999", "username": "carol"},
                "channel_id": "channel789",
                "content": "",
                "attachments": [
                    {
                        "id": "att456",
                        "filename": "video.mp4",
                        "content_type": "video/mp4",
                        "url": "https://cdn.discordapp.com/attachments/video.mp4",
                    }
                ],
            }
        }

        std_msg = self.adapter.to_standard(discord_message)

        assert std_msg.message_type == MessageType.VIDEO
        assert std_msg.media_url == "https://cdn.discordapp.com/attachments/video.mp4"

    def test_to_standard_with_sticker(self):
        """Test converting message with sticker."""
        discord_message = {
            "message": {
                "id": "msg127",
                "author": {"id": "user111", "username": "dave"},
                "channel_id": "channel999",
                "content": "",
                "stickers": [
                    {"id": "sticker123", "name": "thumbs_up", "url": "https://cdn.discordapp.com/stickers/123.png"}
                ],
            }
        }

        std_msg = self.adapter.to_standard(discord_message)

        assert std_msg.message_type == MessageType.STICKER
        assert std_msg.content == "[贴纸]"

    def test_to_standard_with_mention(self):
        """Test converting message with bot mention."""
        discord_message = {
            "message": {
                "id": "msg128",
                "author": {"id": "user222", "username": "eve"},
                "channel_id": "channel111",
                "content": "<@bot123> hello there",
                "mentions": [{"id": "bot123", "username": "TestBot"}],
                "mention_everyone": False,
            }
        }

        std_msg = self.adapter.to_standard(discord_message)

        assert std_msg.content == "<@bot123> hello there"
        assert std_msg.metadata["mentions"] == [{"id": "bot123", "username": "TestBot"}]

    def test_to_standard_with_reply(self):
        """Test converting message with reply reference."""
        discord_message = {
            "message": {
                "id": "msg129",
                "author": {"id": "user333", "username": "frank"},
                "channel_id": "channel222",
                "content": "Yes, I agree",
                "referenced_message": {
                    "id": "msg128",
                    "content": "Do you agree?",
                },
            }
        }

        std_msg = self.adapter.to_standard(discord_message)

        assert std_msg.content == "Yes, I agree"
        assert std_msg.reply_to_id == "msg128"
        assert std_msg.reply_to_content == "Do you agree?"

    def test_from_standard_text(self):
        """Test converting standard text message to Discord format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="discord",
            to_user="channel123",
            message_type=MessageType.TEXT,
            content="Hello, Discord!",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["content"] == "Hello, Discord!"

    def test_from_standard_text_with_reply(self):
        """Test converting standard message with reply to Discord format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="discord",
            to_user="channel123",
            message_type=MessageType.TEXT,
            content="Yes, agreed",
            reply_to_id="msg456",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["content"] == "Yes, agreed"
        assert result["message_reference"]["message_id"] == "msg456"

    def test_from_standard_image(self):
        """Test converting standard image message to Discord format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="discord",
            to_user="channel123",
            message_type=MessageType.IMAGE,
            content="Nice image",
            media_url="https://example.com/image.jpg",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["content"] == "Nice image"
        assert len(result["embeds"]) == 1
        assert result["embeds"][0]["image"]["url"] == "https://example.com/image.jpg"

    def test_strip_mention(self):
        """Test stripping Discord mentions from text."""
        # User mention <@id> or <@!id>
        assert self.adapter.strip_mention("<@123456789> hello") == "hello"
        assert self.adapter.strip_mention("<@!987654321> hi there") == "hi there"

        # Role mention <@&id>
        assert self.adapter.strip_mention("<@&333333> announcement") == "announcement"

        # Channel mention <#id>
        assert self.adapter.strip_mention("check <#111222>") == "check"

        # Multiple mentions
        assert self.adapter.strip_mention("<@123> <@!456> hello world") == "hello world"
