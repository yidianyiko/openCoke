import pytest


class TestLangbotWebhookToStd:
    """Test LangBot webhook to standard message format conversion."""

    def test_person_message_text(self):
        """Test converting personal text message."""
        from connector.langbot.langbot_adapter import langbot_webhook_to_std

        webhook_payload = {
            "uuid": "event-123",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "bot-uuid-456",
                "adapter_name": "telegram",
                "sender": {"id": "user-789", "name": "John Doe"},
                "message": [{"type": "Plain", "text": "Hello world"}],
                "timestamp": 1704153600,
            },
        }

        result = langbot_webhook_to_std(webhook_payload)

        assert result["platform"] == "langbot"
        assert result["message_type"] == "text"
        assert result["message"] == "Hello world"
        assert result["input_timestamp"] == 1704153600
        assert result["status"] == "pending"
        assert result["chatroom_name"] is None
        assert result["metadata"]["langbot_adapter"] == "telegram"
        assert result["metadata"]["langbot_bot_uuid"] == "bot-uuid-456"
        assert result["metadata"]["langbot_sender_id"] == "user-789"
        assert result["metadata"]["langbot_sender_name"] == "John Doe"
        assert result["metadata"]["langbot_target_type"] == "person"

    def test_group_message_text(self):
        """Test converting group text message."""
        from connector.langbot.langbot_adapter import langbot_webhook_to_std

        webhook_payload = {
            "uuid": "event-456",
            "event_type": "bot.group_message",
            "data": {
                "bot_uuid": "bot-uuid-789",
                "adapter_name": "qq_official",
                "group": {"id": "group-123", "name": "Test Group"},
                "sender": {"id": "user-456", "name": "Alice"},
                "message": [{"type": "Plain", "text": "Hello group"}],
                "timestamp": 1704153700,
            },
        }

        result = langbot_webhook_to_std(webhook_payload)

        assert result["platform"] == "langbot"
        assert result["message_type"] == "text"
        assert result["message"] == "Hello group"
        assert result["chatroom_name"] == "group-123"
        assert result["metadata"]["langbot_group_id"] == "group-123"
        assert result["metadata"]["langbot_group_name"] == "Test Group"
        assert result["metadata"]["langbot_target_type"] == "group"

    def test_multiple_message_parts(self):
        """Test converting message with multiple Plain parts."""
        from connector.langbot.langbot_adapter import langbot_webhook_to_std

        webhook_payload = {
            "uuid": "event-789",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "bot-123",
                "adapter_name": "discord",
                "sender": {"id": "user-111", "name": "Bob"},
                "message": [
                    {"type": "Plain", "text": "Hello "},
                    {"type": "Plain", "text": "world!"},
                ],
                "timestamp": 1704153800,
            },
        }

        result = langbot_webhook_to_std(webhook_payload)

        assert result["message"] == "Hello world!"

    def test_image_message(self):
        """Test converting image message."""
        from connector.langbot.langbot_adapter import langbot_webhook_to_std

        webhook_payload = {
            "uuid": "event-img",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "bot-123",
                "adapter_name": "telegram",
                "sender": {"id": "user-222", "name": "Carol"},
                "message": [{"type": "Image", "url": "https://example.com/image.jpg"}],
                "timestamp": 1704153900,
            },
        }

        result = langbot_webhook_to_std(webhook_payload)

        assert result["message_type"] == "image"
        assert result["metadata"]["url"] == "https://example.com/image.jpg"


class TestStdToLangbotMessage:
    """Test standard message format to LangBot Send API format conversion."""

    def test_text_message(self):
        """Test converting text message for sending."""
        from connector.langbot.langbot_adapter import std_to_langbot_message

        outputmessage = {
            "message_type": "text",
            "message": "Hello from Coke!",
            "metadata": {
                "langbot_bot_uuid": "bot-123",
                "langbot_target_id": "user-456",
                "langbot_target_type": "person",
            },
        }

        result = std_to_langbot_message(outputmessage)

        assert result["bot_uuid"] == "bot-123"
        assert result["target_type"] == "person"
        assert result["target_id"] == "user-456"
        assert result["message_chain"] == [{"type": "Plain", "text": "Hello from Coke!"}]

    def test_group_message(self):
        """Test converting group message for sending."""
        from connector.langbot.langbot_adapter import std_to_langbot_message

        outputmessage = {
            "message_type": "text",
            "message": "Hello group!",
            "metadata": {
                "langbot_bot_uuid": "bot-789",
                "langbot_target_id": "group-123",
                "langbot_target_type": "group",
            },
        }

        result = std_to_langbot_message(outputmessage)

        assert result["target_type"] == "group"
        assert result["target_id"] == "group-123"

