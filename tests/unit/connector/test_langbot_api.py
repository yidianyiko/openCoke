from unittest.mock import MagicMock, patch

import pytest


class TestLangBotAPI:
    """Test LangBot API client."""

    def test_send_message_success(self):
        """Test successful message sending."""
        from connector.langbot.langbot_api import LangBotAPI

        api = LangBotAPI(base_url="http://localhost:8080", api_key="lbk_test")

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"code": 0, "msg": "ok", "data": {"sent": True}},
            )

            result = api.send_message(
                bot_uuid="bot-123",
                target_type="person",
                target_id="user-456",
                message_chain=[{"type": "Plain", "text": "Hello"}],
            )

            assert result["code"] == 0
            assert result["data"]["sent"] is True
            mock_post.assert_called_once()

    def test_send_message_with_correct_headers(self):
        """Test that API key is sent in headers."""
        from connector.langbot.langbot_api import LangBotAPI

        api = LangBotAPI(base_url="http://localhost:8080", api_key="lbk_secret")

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"code": 0, "msg": "ok", "data": {"sent": True}},
            )

            api.send_message(
                bot_uuid="bot-123",
                target_type="group",
                target_id="group-789",
                message_chain=[{"type": "Plain", "text": "Hi group"}],
            )

            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["X-API-Key"] == "lbk_secret"
            assert call_kwargs["headers"]["Content-Type"] == "application/json"

    def test_send_message_correct_url(self):
        """Test that correct URL is constructed."""
        from connector.langbot.langbot_api import LangBotAPI

        api = LangBotAPI(base_url="http://langbot:8080", api_key="lbk_test")

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"code": 0, "msg": "ok", "data": {"sent": True}},
            )

            api.send_message(
                bot_uuid="my-bot-uuid",
                target_type="person",
                target_id="123",
                message_chain=[],
            )

            call_args = mock_post.call_args[0]
            assert (
                call_args[0]
                == "http://langbot:8080/api/v1/platform/bots/my-bot-uuid/send_message"
            )

    def test_send_message_error_handling(self):
        """Test error handling when API fails."""
        from connector.langbot.langbot_api import LangBotAPI

        api = LangBotAPI(base_url="http://localhost:8080", api_key="lbk_test")

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=500,
                json=lambda: {"code": 1, "msg": "error"},
            )

            result = api.send_message(
                bot_uuid="bot-123",
                target_type="person",
                target_id="user-456",
                message_chain=[],
            )

            assert result["code"] == 1
