# LangBot Multi-Platform Gateway Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate LangBot as a platform gateway to support QQ, Telegram, Discord, and other messaging platforms while maintaining the existing ecloud connector for WeChat.

**Architecture:** LangBot handles all platform protocols and forwards messages to Coke via webhook. Coke receives messages, processes them through the existing Agent Core, and sends responses back via LangBot's Send Message API. Both ecloud and LangBot connectors run in parallel, routing via the `platform` field in MongoDB.

**Tech Stack:** Python 3.12+, Flask (webhook receiver), asyncio (output polling), requests (LangBot API), MongoDB

---

## Background

### Current Architecture
```
ecloud (WeChat) → MongoDB.inputmessages → Agent Core → MongoDB.outputmessages → ecloud
```

### Target Architecture
```
ecloud (WeChat)  ─┬→ MongoDB.inputmessages → Agent Core → MongoDB.outputmessages ─┬→ ecloud
LangBot (多平台) ─┘                                                                └→ LangBot
```

### LangBot Webhook Format
```json
{
    "uuid": "event-uuid",
    "event_type": "bot.person_message",
    "data": {
        "bot_uuid": "bot-uuid",
        "adapter_name": "telegram",
        "sender": {"id": "123456", "name": "User"},
        "message": [{"type": "Plain", "text": "Hello"}],
        "timestamp": 1704153600
    }
}
```

### LangBot Send Message API
```
POST /api/v1/platform/bots/{bot_uuid}/send_message
Headers: X-API-Key: lbk_xxx
Body: {"target_type": "person", "target_id": "123456", "message_chain": [...]}
```

---

## Task 1: Create LangBot Connector Directory Structure

**Files:**
- Create: `connector/langbot/__init__.py`

**Step 1: Create directory and init file**

```bash
mkdir -p connector/langbot
```

**Step 2: Create __init__.py**

```python
# connector/langbot/__init__.py
"""LangBot multi-platform connector for Coke."""
```

**Step 3: Commit**

```bash
git add connector/langbot/__init__.py
git commit -m "chore(langbot): create langbot connector directory"
```

---

## Task 2: Implement LangBot API Client

**Files:**
- Create: `connector/langbot/langbot_api.py`
- Test: `tests/unit/connector/test_langbot_api.py`

**Step 1: Write the failing test**

```python
# tests/unit/connector/test_langbot_api.py
import pytest
from unittest.mock import patch, MagicMock


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
            assert call_args[0] == "http://langbot:8080/api/v1/platform/bots/my-bot-uuid/send_message"

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/connector/test_langbot_api.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'connector.langbot.langbot_api'"

**Step 3: Write minimal implementation**

```python
# connector/langbot/langbot_api.py
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/connector/test_langbot_api.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add connector/langbot/langbot_api.py tests/unit/connector/test_langbot_api.py
git commit -m "feat(langbot): add LangBot API client with send_message support"
```

---

## Task 3: Implement LangBot Adapter (Webhook to Standard Format)

**Files:**
- Create: `connector/langbot/langbot_adapter.py`
- Test: `tests/unit/connector/test_langbot_adapter.py`

**Step 1: Write the failing test**

```python
# tests/unit/connector/test_langbot_adapter.py
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/connector/test_langbot_adapter.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# connector/langbot/langbot_adapter.py
"""LangBot message format adapter.

Converts between LangBot webhook format and Coke standard message format.
"""
from util.log_util import get_logger

logger = get_logger(__name__)


def langbot_webhook_to_std(webhook_payload: dict) -> dict:
    """
    Convert LangBot webhook payload to Coke standard message format.

    Args:
        webhook_payload: LangBot webhook event payload

    Returns:
        Coke standard inputmessage format
    """
    event_type = webhook_payload.get("event_type", "")
    data = webhook_payload.get("data", {})

    # Extract common fields
    bot_uuid = data.get("bot_uuid", "")
    adapter_name = data.get("adapter_name", "")
    sender = data.get("sender", {})
    sender_id = sender.get("id", "")
    sender_name = sender.get("name", "")
    timestamp = data.get("timestamp", 0)
    message_parts = data.get("message", [])

    # Determine if group or person message
    is_group = event_type == "bot.group_message"
    group_data = data.get("group", {})
    chatroom_name = group_data.get("id") if is_group else None

    # Extract message content and type
    message_type, message_content, extra_metadata = _extract_message_content(message_parts)

    # Build metadata
    metadata = {
        "langbot_adapter": adapter_name,
        "langbot_bot_uuid": bot_uuid,
        "langbot_sender_id": sender_id,
        "langbot_sender_name": sender_name,
        "langbot_target_type": "group" if is_group else "person",
        "langbot_event_uuid": webhook_payload.get("uuid", ""),
    }

    if is_group:
        metadata["langbot_group_id"] = group_data.get("id", "")
        metadata["langbot_group_name"] = group_data.get("name", "")

    # Merge extra metadata (e.g., image URL)
    metadata.update(extra_metadata)

    return {
        "input_timestamp": timestamp,
        "handled_timestamp": None,
        "status": "pending",
        "platform": "langbot",
        "chatroom_name": chatroom_name,
        "message_type": message_type,
        "message": message_content,
        "metadata": metadata,
    }


def _extract_message_content(message_parts: list) -> tuple[str, str, dict]:
    """
    Extract message type, content, and extra metadata from message parts.

    Args:
        message_parts: List of message components from LangBot

    Returns:
        Tuple of (message_type, message_content, extra_metadata)
    """
    if not message_parts:
        return "text", "", {}

    # Collect all text parts
    text_parts = []
    extra_metadata = {}
    detected_type = "text"

    for part in message_parts:
        part_type = part.get("type", "")

        if part_type == "Plain":
            text_parts.append(part.get("text", ""))
        elif part_type == "Image":
            detected_type = "image"
            extra_metadata["url"] = part.get("url", "")
        elif part_type == "Voice":
            detected_type = "voice"
            extra_metadata["url"] = part.get("url", "")
        # Add more types as needed

    message_content = "".join(text_parts)

    return detected_type, message_content, extra_metadata


def std_to_langbot_message(outputmessage: dict) -> dict:
    """
    Convert Coke standard outputmessage to LangBot Send API format.

    Args:
        outputmessage: Coke standard outputmessage

    Returns:
        Dict with bot_uuid, target_type, target_id, message_chain
    """
    metadata = outputmessage.get("metadata", {})
    message_type = outputmessage.get("message_type", "text")
    message_content = outputmessage.get("message", "")

    # Build message chain based on type
    if message_type == "text":
        message_chain = [{"type": "Plain", "text": message_content}]
    elif message_type == "image":
        message_chain = [{"type": "Image", "url": metadata.get("url", "")}]
    elif message_type == "voice":
        message_chain = [{"type": "Voice", "url": metadata.get("url", "")}]
    else:
        # Fallback to text
        message_chain = [{"type": "Plain", "text": message_content}]

    return {
        "bot_uuid": metadata.get("langbot_bot_uuid", ""),
        "target_type": metadata.get("langbot_target_type", "person"),
        "target_id": metadata.get("langbot_target_id", ""),
        "message_chain": message_chain,
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/connector/test_langbot_adapter.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add connector/langbot/langbot_adapter.py tests/unit/connector/test_langbot_adapter.py
git commit -m "feat(langbot): add message format adapter for webhook and send API"
```

---

## Task 4: Implement LangBot Webhook Input Handler

**Files:**
- Create: `connector/langbot/langbot_input.py`
- Test: `tests/unit/connector/test_langbot_input.py`

**Step 1: Write the failing test**

```python
# tests/unit/connector/test_langbot_input.py
import pytest
from unittest.mock import patch, MagicMock


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

    def test_webhook_returns_skip_pipeline(self, client, mock_mongo, mock_user_dao, mock_character):
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

    def test_webhook_inserts_message_to_mongo(self, client, mock_mongo, mock_user_dao, mock_character):
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

    def test_webhook_ignores_unknown_event_type(self, client, mock_mongo, mock_user_dao, mock_character):
        """Test that unknown event types are ignored."""
        payload = {
            "uuid": "event-123",
            "event_type": "bot.unknown_event",
            "data": {},
        }

        response = client.post("/langbot/webhook", json=payload, content_type="application/json")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["skip_pipeline"] is True
        mock_mongo.insert_one.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/connector/test_langbot_input.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# connector/langbot/langbot_input.py
"""LangBot webhook input handler.

Receives webhook events from LangBot and inserts messages into MongoDB.
"""
import sys

sys.path.append(".")

from flask import Flask, request, jsonify

from connector.langbot.langbot_adapter import langbot_webhook_to_std
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)

app = Flask(__name__)


def get_default_character():
    """Get the default character for LangBot messages."""
    from conf.config import CONF

    user_dao = UserDAO()
    default_alias = CONF.get("langbot", {}).get("default_character_alias", "qiaoyun")
    character = user_dao.get_user_by_name(default_alias)
    return character


def get_or_create_user(adapter_name: str, sender_id: str, sender_name: str):
    """
    Find or create user based on LangBot platform info.

    Args:
        adapter_name: LangBot adapter name (e.g., "telegram", "qq_official")
        sender_id: Sender ID from the platform
        sender_name: Sender display name

    Returns:
        User document from MongoDB
    """
    user_dao = UserDAO()
    platform_key = f"langbot_{adapter_name}"

    # Try to find existing user
    user = user_dao.find_by_platform(platform_key, sender_id)

    if user is None:
        # Create new user
        logger.info(f"Creating new user for {platform_key}:{sender_id}")
        user = {
            "name": sender_name or f"User_{sender_id[:8]}",
            "platforms": {
                platform_key: {
                    "account": sender_id,
                    "name": sender_name,
                }
            },
        }
        user_id = user_dao.create_user(user)
        user["_id"] = user_id

    return user


@app.route("/langbot/webhook", methods=["POST"])
def webhook_handler():
    """
    Handle LangBot webhook events.

    Receives message events, converts to standard format, and inserts into MongoDB.
    Always returns skip_pipeline: true to prevent LangBot from processing with its AI.
    """
    try:
        payload = request.json
        logger.info(f"Received LangBot webhook: {payload.get('event_type')}")
        logger.debug(f"Payload: {payload}")

        event_type = payload.get("event_type", "")

        # Only process message events
        if event_type not in ["bot.person_message", "bot.group_message"]:
            logger.info(f"Ignoring event type: {event_type}")
            return jsonify({"status": "ok", "skip_pipeline": True})

        # Convert to standard format
        std_message = langbot_webhook_to_std(payload)

        # Get or create user
        data = payload.get("data", {})
        adapter_name = data.get("adapter_name", "unknown")
        sender = data.get("sender", {})
        sender_id = sender.get("id", "")
        sender_name = sender.get("name", "")

        user = get_or_create_user(adapter_name, sender_id, sender_name)
        character = get_default_character()

        if character is None:
            logger.error("Default character not found")
            return jsonify({"status": "error", "message": "character not found", "skip_pipeline": True})

        # Add user and character IDs
        std_message["from_user"] = str(character["_id"])  # Bot receives from character perspective
        std_message["to_user"] = str(user["_id"])

        # For response routing, we need to store the target info
        std_message["metadata"]["langbot_target_id"] = sender_id
        if event_type == "bot.group_message":
            group = data.get("group", {})
            std_message["metadata"]["langbot_target_id"] = group.get("id", sender_id)

        # Insert into MongoDB
        mongo = MongoDBBase()
        mongo.insert_one("inputmessages", std_message)
        logger.info(f"Inserted message into inputmessages: {std_message.get('message', '')[:50]}")

        return jsonify({"status": "ok", "skip_pipeline": True})

    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e), "skip_pipeline": True})


def run_langbot_input(host: str = "0.0.0.0", port: int = 8081):
    """Run the Flask webhook server."""
    logger.info(f"Starting LangBot webhook server on {host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_langbot_input()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/connector/test_langbot_input.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add connector/langbot/langbot_input.py tests/unit/connector/test_langbot_input.py
git commit -m "feat(langbot): add webhook input handler for receiving messages"
```

---

## Task 5: Implement LangBot Output Handler

**Files:**
- Create: `connector/langbot/langbot_output.py`
- Test: `tests/unit/connector/test_langbot_output.py`

**Step 1: Write the failing test**

```python
# tests/unit/connector/test_langbot_output.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/connector/test_langbot_output.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# connector/langbot/langbot_output.py
"""LangBot output handler.

Polls MongoDB for pending messages and sends them via LangBot API.
"""
import sys

sys.path.append(".")

import asyncio
import time
import traceback

from conf.config import CONF
from connector.langbot.langbot_adapter import std_to_langbot_message
from connector.langbot.langbot_api import LangBotAPI
from dao.mongo import MongoDBBase
from entity.message import save_outputmessage
from util.log_util import get_logger

logger = get_logger(__name__)


def get_langbot_api() -> LangBotAPI:
    """Get configured LangBot API client."""
    langbot_conf = CONF.get("langbot", {})
    return LangBotAPI(
        base_url=langbot_conf.get("base_url", "http://localhost:8080"),
        api_key=langbot_conf.get("api_key", ""),
    )


async def output_handler():
    """
    Process one pending output message.

    Finds a pending message for langbot platform and sends it via LangBot API.
    """
    mongo = MongoDBBase()
    langbot_api = get_langbot_api()

    try:
        now = int(time.time())
        message = mongo.find_one(
            "outputmessages",
            {
                "platform": "langbot",
                "status": "pending",
                "expect_output_timestamp": {"$lte": now},
            },
        )

        if message is None:
            return

        logger.info(f"Sending LangBot message: {message.get('message', '')[:50]}")
        logger.debug(f"Full message: {message}")

        # Convert to LangBot format
        langbot_msg = std_to_langbot_message(message)

        # Send via LangBot API
        result = langbot_api.send_message(
            bot_uuid=langbot_msg["bot_uuid"],
            target_type=langbot_msg["target_type"],
            target_id=langbot_msg["target_id"],
            message_chain=langbot_msg["message_chain"],
        )

        logger.info(f"LangBot send result: {result}")

        # Update status
        now = int(time.time())
        if result.get("code") == 0:
            message["status"] = "handled"
        else:
            message["status"] = "failed"
            message["error"] = result.get("msg", "Unknown error")

        message["handled_timestamp"] = now
        save_outputmessage(message)

    except Exception:
        logger.error(traceback.format_exc())
        if message:
            message["status"] = "failed"
            message["handled_timestamp"] = int(time.time())
            save_outputmessage(message)


async def run_langbot_output():
    """Run the output handler loop."""
    logger.info("Starting LangBot output handler")
    while True:
        await asyncio.sleep(1)
        await output_handler()


async def main():
    """Main entry point."""
    await asyncio.gather(run_langbot_output())


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/connector/test_langbot_output.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add connector/langbot/langbot_output.py tests/unit/connector/test_langbot_output.py
git commit -m "feat(langbot): add output handler for sending messages via LangBot API"
```

---

## Task 6: Create LangBot Startup Script

**Files:**
- Create: `connector/langbot/langbot_start.sh`

**Step 1: Create the startup script**

```bash
#!/bin/bash
# connector/langbot/langbot_start.sh
# Startup script for LangBot connector

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

LOG_FILE="$SCRIPT_DIR/langbot.log"

echo "Starting LangBot connector..."
echo "Log file: $LOG_FILE"

# Start input handler (Flask webhook server)
python -u connector/langbot/langbot_input.py >> "$LOG_FILE" 2>&1 &
INPUT_PID=$!
echo "Started langbot_input.py with PID $INPUT_PID"

# Start output handler (async polling)
python -u connector/langbot/langbot_output.py >> "$LOG_FILE" 2>&1 &
OUTPUT_PID=$!
echo "Started langbot_output.py with PID $OUTPUT_PID"

echo "LangBot connector started"
echo "Input PID: $INPUT_PID, Output PID: $OUTPUT_PID"

wait
```

**Step 2: Make executable**

```bash
chmod +x connector/langbot/langbot_start.sh
```

**Step 3: Commit**

```bash
git add connector/langbot/langbot_start.sh
git commit -m "chore(langbot): add startup script for langbot connector"
```

---

## Task 7: Add LangBot Configuration

**Files:**
- Modify: `conf/config.json` (add langbot section)

**Step 1: Document the required configuration**

Add the following section to `conf/config.json`:

```json
{
    "langbot": {
        "enabled": true,
        "base_url": "http://langbot-server:8080",
        "api_key": "lbk_your_api_key_here",
        "webhook_port": 8081,
        "default_character_alias": "qiaoyun"
    }
}
```

**Step 2: Commit documentation update**

```bash
git add conf/config.json
git commit -m "docs(config): add langbot configuration section"
```

---

## Task 8: Update Main Startup Script

**Files:**
- Modify: `start.sh`

**Step 1: Add LangBot connector to start.sh**

Add the following lines after the ecloud connector startup:

```bash
# LangBot Connector (multi-platform)
if [ -f connector/langbot/langbot_start.sh ]; then
    bash connector/langbot/langbot_start.sh &
fi
```

**Step 2: Commit**

```bash
git add start.sh
git commit -m "chore(startup): add langbot connector to main startup script"
```

---

## Task 9: Integration Test with Mock LangBot

**Files:**
- Create: `tests/integration/test_langbot_integration.py`

**Step 1: Write integration test**

```python
# tests/integration/test_langbot_integration.py
"""Integration tests for LangBot connector."""
import pytest
import time
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestLangbotIntegration:
    """End-to-end integration tests for LangBot connector."""

    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        from connector.langbot.langbot_input import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def mock_deps(self):
        """Mock all external dependencies."""
        with patch("connector.langbot.langbot_input.MongoDBBase") as mongo_mock, \
             patch("connector.langbot.langbot_input.UserDAO") as user_dao_mock, \
             patch("connector.langbot.langbot_input.get_default_character") as char_mock:

            mongo_instance = MagicMock()
            mongo_mock.return_value = mongo_instance

            user_dao_instance = MagicMock()
            user_dao_mock.return_value = user_dao_instance
            user_dao_instance.find_by_platform.return_value = {
                "_id": "user-123",
                "name": "Test User",
            }

            char_mock.return_value = {"_id": "char-456", "name": "qiaoyun"}

            yield {
                "mongo": mongo_instance,
                "user_dao": user_dao_instance,
                "character": char_mock,
            }

    def test_full_message_flow(self, client, mock_deps):
        """Test complete message flow from webhook to MongoDB."""
        # Simulate Telegram message via LangBot webhook
        payload = {
            "uuid": "event-integration-test",
            "event_type": "bot.person_message",
            "data": {
                "bot_uuid": "test-bot-uuid",
                "adapter_name": "telegram",
                "sender": {"id": "tg-user-123", "name": "Integration Tester"},
                "message": [{"type": "Plain", "text": "Integration test message"}],
                "timestamp": int(time.time()),
            },
        }

        response = client.post("/langbot/webhook", json=payload, content_type="application/json")

        # Verify response
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["skip_pipeline"] is True

        # Verify MongoDB insertion
        mock_deps["mongo"].insert_one.assert_called_once()
        call_args = mock_deps["mongo"].insert_one.call_args[0]
        assert call_args[0] == "inputmessages"

        inserted_msg = call_args[1]
        assert inserted_msg["platform"] == "langbot"
        assert inserted_msg["message"] == "Integration test message"
        assert inserted_msg["metadata"]["langbot_adapter"] == "telegram"
```

**Step 2: Run integration test**

Run: `pytest tests/integration/test_langbot_integration.py -v -m integration`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_langbot_integration.py
git commit -m "test(langbot): add integration tests for langbot connector"
```

---

## Task 10: Final Verification and Documentation

**Files:**
- Update: `doc/plans/2026-01-02-langbot-gateway-design.md` (mark Phase 1 complete)

**Step 1: Run all LangBot tests**

```bash
pytest tests/unit/connector/test_langbot*.py tests/integration/test_langbot*.py -v
```

Expected: All tests PASS

**Step 2: Verify file structure**

```bash
ls -la connector/langbot/
```

Expected output:
```
__init__.py
langbot_api.py
langbot_adapter.py
langbot_input.py
langbot_output.py
langbot_start.sh
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(langbot): complete Phase 1 MVP implementation

- LangBot API client for sending messages
- Message adapter for webhook/send format conversion
- Webhook input handler (Flask)
- Output handler (async polling)
- Startup script
- Unit and integration tests

Ready for LangBot deployment and platform configuration."
```

---

## Summary

### Files Created
| File | Purpose |
|------|---------|
| `connector/langbot/__init__.py` | Package init |
| `connector/langbot/langbot_api.py` | LangBot HTTP API client |
| `connector/langbot/langbot_adapter.py` | Message format conversion |
| `connector/langbot/langbot_input.py` | Webhook receiver (Flask) |
| `connector/langbot/langbot_output.py` | Message sender (async polling) |
| `connector/langbot/langbot_start.sh` | Startup script |
| `tests/unit/connector/test_langbot_api.py` | API client tests |
| `tests/unit/connector/test_langbot_adapter.py` | Adapter tests |
| `tests/unit/connector/test_langbot_input.py` | Input handler tests |
| `tests/unit/connector/test_langbot_output.py` | Output handler tests |
| `tests/integration/test_langbot_integration.py` | Integration tests |

### Next Steps (Phase 2)
1. Deploy LangBot (Docker)
2. Configure one platform (recommend Telegram for easy testing)
3. Configure webhook URL pointing to Coke server
4. End-to-end testing with real messages
