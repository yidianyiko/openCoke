"""LangBot webhook input handler.

Receives webhook events from LangBot and inserts messages into MongoDB.
"""
import sys

sys.path.append(".")

from flask import Flask, jsonify, request

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
    characters = user_dao.find_characters({"name": default_alias})
    if characters:
        return characters[0]
    return None


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
            "is_character": False,
            "name": sender_name or f"User_{str(sender_id)[:8]}",
            "platforms": {
                platform_key: {
                    "account": sender_id,
                    "name": sender_name,
                }
            },
            "status": "normal",
            "user_info": {},
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
        payload = request.json or {}
        event_type = payload.get("event_type", "")
        logger.info(f"Received LangBot webhook: {event_type}")

        # Only process message events
        if event_type not in ("bot.person_message", "bot.group_message"):
            return jsonify({"status": "ok", "skip_pipeline": True}), 200

        std = langbot_webhook_to_std(payload)

        data = payload.get("data", {})
        adapter_name = data.get("adapter_name", "")
        sender = data.get("sender", {}) or {}
        sender_id = sender.get("id", "")
        sender_name = sender.get("name", "")

        # resolve from_user and to_user
        character = get_default_character()
        user = get_or_create_user(adapter_name, sender_id, sender_name)

        if character:
            std["to_user"] = str(character.get("_id"))
        if user:
            std["from_user"] = str(user.get("_id"))

        # Insert into Mongo
        mongo = MongoDBBase()
        mongo.insert_one("inputmessages", std)

        return jsonify({"status": "ok", "skip_pipeline": True}), 200

    except Exception as e:
        logger.error(f"Error handling LangBot webhook: {e}")
        return jsonify({"status": "error"}), 200


if __name__ == "__main__":
    # Simple dev server if needed
    app.run(host="0.0.0.0", port=8081, debug=True)
