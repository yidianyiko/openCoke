# -*- coding: utf-8 -*-
"""
Unit tests for Evolution API Adapter (WhatsApp via Baileys)
"""

import pytest

from connector.adapters.whatsapp.evolution_adapter import EvolutionAdapter
from connector.channel.types import ChatType, MessageType, StandardMessage


class TestEvolutionAdapter:
    """Test Evolution API adapter message conversion."""

    def setup_method(self):
        """Create adapter instance for testing."""
        self.adapter = EvolutionAdapter(
            api_base="http://localhost:8080",
            api_key="test_api_key",
            instance_name="test_instance",
            webhook_url="http://localhost:8081/webhook/whatsapp",
        )

    def test_channel_properties(self):
        """Test adapter channel properties."""
        assert self.adapter.channel_id == "whatsapp"
        assert "Evolution API" in self.adapter.display_name
        assert "WhatsApp" in self.adapter.display_name

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
        assert MessageType.STICKER in caps.message_types
        assert ChatType.PRIVATE in caps.chat_types
        assert ChatType.GROUP in caps.chat_types
        assert caps.supports_reply is True
        assert caps.supports_mention is True  # Evolution API supports mentions
        assert caps.max_text_length == 4096

    def test_api_endpoint_construction(self):
        """Test API endpoint URL construction."""
        assert self.adapter._get_endpoint("v1/test") == "http://localhost:8080/v1/test"
        assert (
            self.adapter._get_endpoint("v1/instance/create")
            == "http://localhost:8080/v1/instance/create"
        )

    def test_to_standard_text_message_conversation(self):
        """Test converting private text message with conversation field."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"conversation": "Hello, bot!"},
            "messageTimestamp": 1234567890,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_id == "3EB0XXXX"
        assert std_msg.platform == "whatsapp"
        assert std_msg.chat_type == ChatType.PRIVATE
        assert std_msg.from_user == "15551234567@s.whatsapp.net"
        assert std_msg.message_type == MessageType.TEXT
        assert std_msg.content == "Hello, bot!"
        assert std_msg.timestamp == 1234567890

    def test_to_standard_text_message_extended(self):
        """Test converting text message with extendedTextMessage."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "extendedTextMessage": {
                    "text": "This is an extended message",
                }
            },
            "messageTimestamp": 1234567891,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.TEXT
        assert std_msg.content == "This is an extended message"

    def test_to_standard_group_message(self):
        """Test converting group message (@g.us suffix)."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567-1234567@g.us",  # 群聊
                "fromMe": False,
                "participant": "15551234567@s.whatsapp.net",
            },
            "message": {"conversation": "Hello group!"},
            "messageTimestamp": 1234567892,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.chat_type == ChatType.GROUP
        assert std_msg.from_user == "15551234567@s.whatsapp.net"
        assert std_msg.chatroom_id == "15551234567-1234567@g.us"

    def test_to_standard_image_message(self):
        """Test converting image message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "imageMessage": {
                    "caption": "Nice photo!",
                    "url": "https://example.com/image.jpg",
                }
            },
            "messageTimestamp": 1234567893,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.IMAGE
        assert std_msg.content == "Nice photo!"

    def test_to_standard_image_without_caption(self):
        """Test converting image message without caption."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"imageMessage": {}},
            "messageTimestamp": 1234567894,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.IMAGE
        assert std_msg.content == "[图片]"

    def test_to_standard_video_message(self):
        """Test converting video message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "videoMessage": {
                    "caption": "Check this",
                }
            },
            "messageTimestamp": 1234567895,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.VIDEO
        assert std_msg.content == "Check this"

    def test_to_standard_audio_message(self):
        """Test converting audio message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"audioMessage": {}},
            "messageTimestamp": 1234567896,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.VOICE
        assert std_msg.content == "[语音]"

    def test_to_standard_document_message(self):
        """Test converting document message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "documentMessage": {
                    "fileName": "report.pdf",
                }
            },
            "messageTimestamp": 1234567897,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.FILE
        assert std_msg.content == "report.pdf"

    def test_to_standard_location_message(self):
        """Test converting location message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "locationMessage": {
                    "degreesLatitude": 37.7749,
                    "degreesLongitude": -122.4194,
                    "name": "San Francisco",
                }
            },
            "messageTimestamp": 1234567898,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.LOCATION
        assert "San Francisco" in std_msg.content
        assert "37.7749" in std_msg.content
        assert "-122.4194" in std_msg.content

    def test_to_standard_location_message_without_name(self):
        """Test converting location message without name."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "locationMessage": {
                    "degreesLatitude": 40.7128,
                    "degreesLongitude": -74.0060,
                }
            },
            "messageTimestamp": 1234567899,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.LOCATION
        assert "[位置]" in std_msg.content

    def test_to_standard_contact_message(self):
        """Test converting contact message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "contactMessage": {
                    "displayName": "John Doe",
                }
            },
            "messageTimestamp": 1234567900,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.CONTACT
        assert "John Doe" in std_msg.content

    def test_to_standard_sticker_message(self):
        """Test converting sticker message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"stickerMessage": {}},
            "messageTimestamp": 1234567901,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.STICKER
        assert std_msg.content == "[表情包]"

    def test_to_standard_protocol_message_revoke(self):
        """Test converting protocol message (message revoke)."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "protocolMessage": {
                    "type": 0,  # REVOKE
                }
            },
            "messageTimestamp": 1234567902,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.TEXT
        assert "撤回" in std_msg.content

    def test_to_standard_with_reply_context(self):
        """Test converting message with reply context."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "conversation": "Yes, I agree",
                "contextInfo": {
                    "stanzaId": "3EB0YYYY",
                    "quotedMessage": {
                        "conversation": "Do you agree?",
                    },
                },
            },
            "messageTimestamp": 1234567903,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.reply_to_id == "3EB0YYYY"
        assert std_msg.reply_to_content == "Do you agree?"
        assert std_msg.content == "Yes, I agree"

    def test_to_standard_with_mentions(self):
        """Test converting message with mentions."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "extendedTextMessage": {
                    "text": "Hello everyone!",
                }
            },
            "messageTimestamp": 1234567904,
        }

        # Add mentions via context
        evolution_message["message"]["contextInfo"] = {
            "mentionedJid": [
                "15559998888@s.whatsapp.net",
                "15557776666@s.whatsapp.net",
            ]
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert "mentions" in std_msg.metadata
        assert len(std_msg.metadata["mentions"]) == 2

    def test_to_standard_button_response(self):
        """Test converting button response message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "buttonsResponseMessage": {
                    "selectedButtonId": "option_1",
                }
            },
            "messageTimestamp": 1234567905,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.TEXT
        assert "option_1" in std_msg.content

    def test_to_standard_list_response(self):
        """Test converting list response message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "listResponseMessage": {
                    "title": "Option A",
                }
            },
            "messageTimestamp": 1234567906,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.TEXT
        assert "Option A" in std_msg.content

    def test_to_standard_reaction_message(self):
        """Test converting reaction message."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "reactionMessage": {
                    "text": "👍",
                }
            },
            "messageTimestamp": 1234567907,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.TEXT
        assert "👍" in std_msg.content

    def test_to_standard_unknown_message_type(self):
        """Test converting unknown message type."""
        evolution_message = {
            "key": {
                "id": "3EB0XXXX",
                "remoteJid": "15551234567@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {},
            "messageTimestamp": 1234567908,
        }

        std_msg = self.adapter.to_standard(evolution_message)

        assert std_msg.message_type == MessageType.TEXT
        assert "不支持" in std_msg.content

    def test_extract_quoted_content_conversation(self):
        """Test extracting quoted message content from conversation."""
        quoted_msg = {"conversation": "Original message"}
        content = self.adapter._extract_quoted_content(quoted_msg)
        assert content == "Original message"

    def test_extract_quoted_content_extended(self):
        """Test extracting quoted message content from extended text."""
        quoted_msg = {
            "extendedTextMessage": {
                "text": "Extended original",
            }
        }
        content = self.adapter._extract_quoted_content(quoted_msg)
        assert content == "Extended original"

    def test_extract_quoted_content_none(self):
        """Test extracting quoted content when none exists."""
        quoted_msg = {}
        content = self.adapter._extract_quoted_content(quoted_msg)
        assert content is None

    @pytest.mark.asyncio
    async def test_verify_webhook_always_pass(self):
        """Test webhook verification (always returns challenge)."""
        result = await self.adapter.verify_webhook(
            "subscribe", "any_token", "challenge123"
        )
        assert result == "challenge123"

    def test_webhook_path(self):
        """Test webhook path property."""
        assert self.adapter.webhook_path == "/webhook/whatsapp"

    def test_default_api_base(self):
        """Test default API base URL."""
        adapter = EvolutionAdapter(
            api_base="http://custom:9090",
            api_key="test",
            instance_name="test",
            webhook_url="http://test",
        )
        assert adapter._api_base == "http://custom:9090"

    def test_headers_construction(self):
        """Test HTTP headers include API key."""
        assert "apikey" in self.adapter._headers
        assert self.adapter._headers["apikey"] == "test_api_key"
        assert self.adapter._headers["Content-Type"] == "application/json"
