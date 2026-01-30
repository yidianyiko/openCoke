# -*- coding: utf-8 -*-
"""
Unit tests for Ecloud Adapter (migrated)
"""

import pytest

from connector.adapters.ecloud.ecloud_adapter import EcloudAdapter
from connector.channel.types import MessageType, ChatType


class TestEcloudAdapter:
    """Test Ecloud adapter (WeChat) message conversion."""

    def setup_method(self):
        """Create adapter instance for testing."""
        self.adapter = EcloudAdapter(
            bot_wxid="wxid_bot123",
            bot_nickname="TestBot",
        )

    def test_channel_properties(self):
        """Test adapter channel properties."""
        assert self.adapter.channel_id == "wechat"
        assert "WeChat" in self.adapter.display_name
        assert "Ecloud" in self.adapter.display_name
        assert self.adapter.delivery_mode.value == "polling"

    def test_capabilities(self):
        """Test adapter capabilities."""
        caps = self.adapter.capabilities
        assert MessageType.TEXT in caps.message_types
        assert MessageType.IMAGE in caps.message_types
        assert MessageType.VOICE in caps.message_types
        assert MessageType.REFERENCE in caps.message_types
        assert ChatType.PRIVATE in caps.chat_types
        assert ChatType.GROUP in caps.chat_types
        assert caps.supports_mention is True

    def test_to_standard_private_text(self):
        """Test converting private text message."""
        ecloud_message = {
            "account": "15618861103",
            "data": {
                "content": "hello",
                "fromUser": "wxid_user123",
                "msgId": 1052001123,
                "newMsgId": 3166120021925175285,
                "sel": False,
                "timestamp": 1640594470,
                "toUser": "wxid_bot123",
                "wId": "12491ae9-62aa-4f7a-83e6-9db4e9f28e3c"
            },
            "messageType": "60001",
            "wcId": "wxid_bot123"
        }

        std_msg = self.adapter.to_standard(ecloud_message)

        assert std_msg.platform == "wechat"
        assert std_msg.chat_type == ChatType.PRIVATE
        assert std_msg.from_user == "wxid_user123"
        assert std_msg.to_user == "wxid_bot123"
        assert std_msg.message_type == MessageType.TEXT
        assert std_msg.content == "hello"
        assert std_msg.metadata["ecloud_msg_type"] == "60001"

    def test_to_standard_group_text(self):
        """Test converting group text message."""
        ecloud_message = {
            "account": "15618861103",
            "data": {
                "content": "hello group",
                "fromUser": "wxid_user456",
                "fromGroup": "123456789@chatroom",
                "msgId": 1052001124,
                "newMsgId": 3166120021925175286,
                "timestamp": 1640594471,
                "wId": "12491ae9-62aa-4f7a-83e6-9db4e9f28e3c"
            },
            "messageType": "80001",
        }

        std_msg = self.adapter.to_standard(ecloud_message)

        assert std_msg.chat_type == ChatType.GROUP
        assert std_msg.chatroom_id == "123456789@chatroom"
        assert std_msg.content == "hello group"

    def test_to_standard_reference(self):
        """Test converting reference message."""
        import xml.etree.ElementTree as ET

        xml_content = '''<?xml version="1.0"?>
<msg>
    <appmsg appid="" sdkver="0">
        <title>好的</title>
        <refermsg>
            <type>1</type>
            <displayname>李洛云</displayname>
            <content>这是引用的内容</content>
        </refermsg>
    </appmsg>
</msg>'''

        ecloud_message = {
            "data": {
                "toUser": "wxid_bot123",
                "msgId": 349799730,
                "newMsgId": 6288973548168670026,
                "wId": "ca9518dd-bec6-4421-b0f0-cbf81ecdb2f8",
                "fromUser": "wxid_user789",
                "title": "好的",
                "content": xml_content,
                "timestamp": 1748141489,
            },
            "messageType": "60014",
        }

        std_msg = self.adapter.to_standard(ecloud_message)

        assert std_msg.message_type == MessageType.REFERENCE
        assert std_msg.content == "好的"

    def test_is_mentioned_with_nickname(self):
        """Test mention detection with nickname."""
        from connector.channel.types import StandardMessage

        msg = StandardMessage(
            platform="wechat",
            content="@TestBot hello there",
        )

        result = self.adapter.is_mentioned(msg, "wxid_bot123")
        assert result is True

    def test_is_mentioned_with_atlist(self):
        """Test mention detection with atlist."""
        from connector.channel.types import StandardMessage

        msg = StandardMessage(
            platform="wechat",
            content="hello there",
            metadata={"atlist": ["wxid_bot123", "wxid_other"]},
        )

        result = self.adapter.is_mentioned(msg, "wxid_bot123")
        assert result is True

    def test_strip_mention(self):
        """Test stripping mention from text."""
        result = self.adapter.strip_mention("@TestBot hello world")
        assert result == "hello world"

    def test_from_standard_text(self):
        """Test converting standard text message to Ecloud format."""
        from connector.channel.types import StandardMessage

        std_msg = StandardMessage(
            platform="wechat",
            to_user="wxid_user123",
            message_type=MessageType.TEXT,
            content="Hello, user!",
        )

        result = self.adapter.from_standard(std_msg)

        assert result["content"] == "Hello, user!"
