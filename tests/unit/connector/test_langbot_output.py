import pytest
from unittest.mock import patch, MagicMock


class TestLangbotOutputHandler:
    """Test LangBot output handler."""

    @pytest.fixture
    def mock_mongo(self):
        """Mock MongoDB operations."""
        with patch("connector.langbot.langbot_output.MongoDBBase") as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance

    @pytest.fixture
    def mock_langbot_api(self):
        """Mock LangBot API."""
        with patch("connector.langbot.langbot_output.LangBotAPI") as mock:
            instance = MagicMock()
            mock.return_value = instance
            instance.send_message.return_value = {"code": 0, "msg": "ok", "data": {"sent": True}}
            yield instance

    @pytest.mark.asyncio
    async def test_output_handler_sends_pending_message(self, mock_mongo, mock_langbot_api):
        """Test that pending messages are sent via LangBot API."""
        from connector.langbot.langbot_output import output_handler

        pending_message = {
            "_id": "msg-123",
            "platform": "langbot",
            "status": "pending",
            "message_type": "text",
            "message": "Hello from Coke!",
            "metadata": {
                "langbot_bot_uuid": "bot-456",
                "langbot_target_id": "user-789",
                "langbot_target_type": "person",
            },
        }
        mock_mongo.find_one.return_value = pending_message

        await output_handler()

        mock_langbot_api.send_message.assert_called_once_with(
            bot_uuid="bot-456",
            target_type="person",
            target_id="user-789",
            message_chain=[{"type": "Plain", "text": "Hello from Coke!"}],
        )

    @pytest.mark.asyncio
    async def test_output_handler_updates_status_to_handled(self, mock_mongo, mock_langbot_api):
        """Test that message status is updated to handled after sending."""
        from connector.langbot.langbot_output import output_handler

        pending_message = {
            "_id": "msg-123",
            "platform": "langbot",
            "status": "pending",
            "message_type": "text",
            "message": "Test message",
            "metadata": {
                "langbot_bot_uuid": "bot-456",
                "langbot_target_id": "user-789",
                "langbot_target_type": "person",
            },
        }
        mock_mongo.find_one.return_value = pending_message

        await output_handler()

        # Verify replace_one was called with status = "handled"
        mock_mongo.replace_one.assert_called_once()
        call_args = mock_mongo.replace_one.call_args
        updated_doc = call_args[0][2]
        assert updated_doc["status"] == "handled"

    @pytest.mark.asyncio
    async def test_output_handler_no_pending_message(self, mock_mongo, mock_langbot_api):
        """Test that nothing happens when no pending messages."""
        from connector.langbot.langbot_output import output_handler

        mock_mongo.find_one.return_value = None

        await output_handler()

        mock_langbot_api.send_message.assert_not_called()
        mock_mongo.replace_one.assert_not_called()

