"""Telegram Bot API client for sending messages directly.

This bypasses LangBot's Service API since Telegram adapter doesn't implement send_message.
"""

import requests
from typing import Dict, Any
from util.log_util import get_logger

logger = get_logger(__name__)


class TelegramAPI:
    """Direct Telegram Bot API client."""

    BASE_URL = "https://api.telegram.org/bot"

    def __init__(self, bot_token: str):
        """
        Initialize Telegram API client.

        Args:
            bot_token: Telegram bot token from BotFather
        """
        self.bot_token = bot_token

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = None,
    ) -> Dict[str, Any]:
        """
        Send text message via Telegram Bot API.

        Args:
            chat_id: Target chat ID (user or group)
            text: Message text
            parse_mode: Optional parse mode ("MarkdownV2" or "HTML")

        Returns:
            Response from Telegram API with structure:
            - ok: bool
            - result: message object (if ok)
            - description: error message (if not ok)
        """
        url = f"{self.BASE_URL}{self.bot_token}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            resp = requests.post(url, json=payload, timeout=30)
            result = resp.json()

            if result.get("ok"):
                logger.info(f"Telegram API success: message sent to {chat_id}")
            else:
                logger.error(
                    f"Telegram API failed: {result.get('description', 'Unknown error')}"
                )

            return result

        except requests.RequestException as e:
            logger.error(f"Telegram API request failed: {e}")
            return {"ok": False, "description": str(e)}
