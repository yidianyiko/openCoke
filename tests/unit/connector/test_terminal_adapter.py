# -*- coding: utf-8 -*-
"""
Unit tests for Terminal Adapter (migrated)
"""

import pytest

from connector.adapters.terminal.terminal_adapter import TerminalAdapter
from connector.channel.types import MessageType, ChatType


class TestTerminalAdapter:
    """Test Terminal adapter message conversion."""

    def setup_method(self):
        """Create adapter instance for testing."""
        self.adapter = TerminalAdapter(
            user_id="test-user-id",
            character_id="test-character-id",
        )

    def test_channel_properties(self):
        """Test adapter channel properties."""
        assert self.adapter.channel_id == "terminal"
        assert self.adapter.display_name == "Terminal"
        assert self.adapter.delivery_mode.value == "polling"

    def test_capabilities(self):
        """Test adapter capabilities."""
        caps = self.adapter.capabilities
        assert MessageType.TEXT in caps.message_types
        assert ChatType.PRIVATE in caps.chat_types
        assert caps.supports_mention is False
        assert caps.supports_reply is False

    def test_to_standard(self):
        """Test converting MongoDB inputmessage to standard format."""
        inputmessage = {
            "_id": "msg-id-123",
            "input_timestamp": 1704153600,
            "status": "pending",
            "from_user": "test-user-id",
            "to_user": "test-character-id",
            "platform": "terminal",
            "chatroom_name": None,
            "message_type": "text",
            "message": "Hello, terminal!",
            "metadata": {},
        }

        std_msg = self.adapter.to_standard(inputmessage)

        assert std_msg.message_id == "msg-id-123"
        assert std_msg.platform == "terminal"
        assert std_msg.chat_type == ChatType.PRIVATE
        assert std_msg.from_user == "test-user-id"
        assert std_msg.to_user == "test-character-id"
        assert std_msg.message_type == MessageType.TEXT
        assert std_msg.content == "Hello, terminal!"
        assert std_msg.timestamp == 1704153600

    def test_from_standard(self):
        """Test converting standard message to MongoDB outputmessage format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="terminal",
            from_user="test-character-id",
            from_user_db_id="test-character-id",
            to_user="test-user-id",
            to_user_db_id="test-user-id",
            message_type=MessageType.TEXT,
            content="Hello from terminal!",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["platform"] == "terminal"
        assert result["from_user"] == "test-character-id"
        assert result["to_user"] == "test-user-id"
        assert result["message_type"] == "text"
        assert result["message"] == "Hello from terminal!"
