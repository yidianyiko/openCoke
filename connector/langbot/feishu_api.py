"""Feishu (Lark) API client for sending messages directly.

This bypasses LangBot's Service API since Lark adapter doesn't implement send_message.
"""

import json
import time
from typing import Any, Dict, List, Optional

import requests

from util.log_util import get_logger

logger = get_logger(__name__)


class FeishuAPI:
    """Direct Feishu API client."""

    def __init__(self, app_id: str, app_secret: str):
        """
        Initialize Feishu API client.

        Args:
            app_id: Feishu app ID
            app_secret: Feishu app secret
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self._tenant_access_token: Optional[str] = None
        self._token_expire_at: int = 0

    def get_tenant_access_token(self) -> str:
        """
        Get or refresh tenant access token.

        Returns:
            Tenant access token
        """
        # 如果 token 还有 5 分钟以上有效期，直接返回
        if self._tenant_access_token and time.time() < self._tenant_access_token - 300:
            return self._tenant_access_token

        # 获取新的 token
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}

        resp = requests.post(url, json=payload)
        result = resp.json()

        if result.get("code") != 0:
            raise Exception(f"Failed to get tenant_access_token: {result}")

        self._tenant_access_token = result.get("tenant_access_token")
        expire = result.get("expire", 7200)
        self._token_expire_at = int(time.time()) + expire

        logger.info("Refreshed Feishu tenant_access_token")
        return self._tenant_access_token

    def send_message(
        self, target_id: str, text: str, target_type: str = "open_id"
    ) -> Dict[str, Any]:
        """
        Send text message to Feishu.

        Args:
            target_id: Target user/group ID
            text: Message text
            target_type: ID type (open_id, union_id, user_id, chat_id)

        Returns:
            Response from Feishu API
        """
        token = self.get_tenant_access_token()

        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={target_type}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # 构建飞书消息格式
        content = json.dumps({"text": text})

        payload = {"receive_id": target_id, "msg_type": "text", "content": content}

        resp = requests.post(url, headers=headers, json=payload)
        result = resp.json()

        logger.info(
            f"Feishu API response: code={result.get('code')}, msg={result.get('msg')}"
        )

        return result

    def send_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Send multiple messages.

        Args:
            messages: List of dicts with 'target_id' and 'text' keys

        Returns:
            List of responses
        """
        results = []
        for msg in messages:
            try:
                result = self.send_message(target_id=msg["target_id"], text=msg["text"])
                results.append(result)
                time.sleep(0.5)  # Avoid rate limiting
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                results.append({"code": -1, "msg": str(e)})
        return results
