"""LangBot HTTP API client."""
import requests

from util.log_util import get_logger

logger = get_logger(__name__)


class LangBotAPI:
    """LangBot HTTP API wrapper."""

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize LangBot API client.

        Args:
            base_url: LangBot server URL (e.g., "http://localhost:8080")
            api_key: LangBot API key (e.g., "lbk_xxx")
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def send_message(
        self,
        bot_uuid: str,
        target_type: str,
        target_id: str,
        message_chain: list,
    ) -> dict:
        """
        Send message to a user or group via LangBot.

        Args:
            bot_uuid: The bot's UUID in LangBot
            target_type: "person" or "group"
            target_id: Target user/group ID
            message_chain: List of message components, e.g., [{"type": "Plain", "text": "Hello"}]

        Returns:
            API response dict with "code", "msg", and "data" fields
        """
        url = f"{self.base_url}/api/v1/platform/bots/{bot_uuid}/send_message"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "target_type": target_type,
            "target_id": target_id,
            "message_chain": message_chain,
        }

        logger.info(f"Sending message to LangBot: {url}")
        logger.debug(f"Payload: {payload}")

        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        result = resp.json()

        logger.info(f"LangBot response: {result}")
        return result
