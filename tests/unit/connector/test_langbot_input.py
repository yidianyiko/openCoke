from unittest.mock import MagicMock, patch

import pytest


class TestLangbotWebhookHandler:
    """Test LangBot webhook input handler."""

    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        from connector.langbot.langbot_input import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def mock_mongo(self):
        """Mock MongoDB operations."""
        with patch("connector.langbot.langbot_input.MongoDBBase") as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance

    @pytest.fixture
    def mock_user_dao(self):
        """Mock UserDAO operations."""
        with patch("connector.langbot.langbot_input.UserDAO") as mock:
            instance = MagicMock()
            mock.return_value = instance
            # Return existing user by default
            instance.find_by_platform.return_value = {
                "_id": "user-mongo-id",
                "name": "Test User",
            }
            yield instance

    @pytest.fixture
    def mock_character(self):
        """Mock character lookup."""
        with patch("connector.langbot.langbot_input.get_default_character") as mock:
            mock.return_value = {"_id": "char-mongo-id", "name": "qiaoyun"}
            yield mock

    def test_webhook_returns_skip_pipeline(
        self, client, mock_mongo, mock_user_dao, mock_character
    ):
        """Test that webhook returns skip_pipeline: true."""
        payload = {
            "uuid": "event-123",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "bot-456",
                "adapter_name": "telegram",
                "sender": {"id": "user-789", "name": "John"},
                "message": [{"type": "Plain", "text": "Hello"}],
                "timestamp": 1704153600,
            },
        }

        response = client.post(
            "/langbot/webhook",
            json=payload,
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["skip_pipeline"] is True

    def test_webhook_inserts_message_to_mongo(
        self, client, mock_mongo, mock_user_dao, mock_character
    ):
        """Test that webhook inserts message into inputmessages."""
        payload = {
            "uuid": "event-123",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "bot-456",
                "adapter_name": "telegram",
                "sender": {"id": "user-789", "name": "John"},
                "message": [{"type": "Plain", "text": "Hello"}],
                "timestamp": 1704153600,
            },
        }

        client.post("/langbot/webhook", json=payload, content_type="application/json")

        mock_mongo.insert_one.assert_called_once()
        call_args = mock_mongo.insert_one.call_args
        assert call_args[0][0] == "inputmessages"
        inserted_doc = call_args[0][1]
        assert inserted_doc["platform"] == "langbot"
        assert inserted_doc["message"] == "Hello"

    def test_webhook_ignores_unknown_event_type(
        self, client, mock_mongo, mock_user_dao, mock_character
    ):
        """Test that unknown event types are ignored."""
        payload = {
            "uuid": "event-123",
            "event_type": "bot.unknown_event",
            "data": {},
        }

        response = client.post(
            "/langbot/webhook", json=payload, content_type="application/json"
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["skip_pipeline"] is True
        mock_mongo.insert_one.assert_not_called()
