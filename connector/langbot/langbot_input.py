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
    """
    Get default character from config.

    Returns:
        Default character document or None
    """
    from conf.config import CONF

    user_dao = UserDAO()
    langbot_conf = CONF.get("langbot", {})
    default_alias = langbot_conf.get("default_character_alias", "qiaoyun")
    characters = user_dao.find_characters({"name": default_alias})
    return characters[0] if characters else None


def get_character_by_bot_uuid(bot_uuid: str):
    """
    Get character by bot_uuid from config.json bots mapping.

    Args:
        bot_uuid: The bot UUID from LangBot webhook payload

    Returns:
        Character document from MongoDB, or None if not found
    """
    from conf.config import CONF

    user_dao = UserDAO()
    langbot_conf = CONF.get("langbot", {})
    bots = langbot_conf.get("bots", {})

    # Find character by bot_uuid in bots config
    for bot_key, bot_config in bots.items():
        if bot_config.get("bot_uuid") == bot_uuid:
            character_name = bot_config.get("character")
            if character_name:
                characters = user_dao.find_characters({"name": character_name})
                if characters:
                    logger.info(f"Found character '{character_name}' for bot '{bot_key}'")
                    return characters[0]
            break

    # Fallback to default character
    logger.warning(
        f"bot_uuid '{bot_uuid}' not found in config, falling back to default character"
    )
    return get_default_character()


def get_or_create_user(adapter_name: str, sender_id: str, sender_name: str):
    """
    Find or create user based on LangBot platform info.

    使用 upsert 操作避免多线程竞态条件导致的重复用户创建。

    Args:
        adapter_name: LangBot adapter name (e.g., "telegram", "qq_official")
        sender_id: Sender ID from the platform
        sender_name: Sender display name

    Returns:
        User document from MongoDB
    """
    user_dao = UserDAO()
    platform_key = f"langbot_{adapter_name}"

    # 使用 upsert 避免竞态条件：多个请求同时创建同一用户
    user_data = {
        "is_character": False,
        "name": sender_name or f"User_{str(sender_id)[:8]}",
        "platforms": {
            platform_key: {
                "id": sender_id,
                "nickname": sender_name,
                "account": sender_id,
                "name": sender_name,
            }
        },
        "status": "normal",
        "user_info": {},
    }

    # upsert: 如果存在则返回现有用户，不存在则创建
    user_id = user_dao.upsert_user(
        query={f"platforms.{platform_key}.id": sender_id},
        user_data=user_data,
    )

    user = user_dao.get_user_by_id(user_id)
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
        logger.debug(f"Full payload: {payload}")

        # Only process message events
        if event_type not in ("bot.person_message", "bot.group_message"):
            return jsonify({"status": "ok", "skip_pipeline": True}), 200

        logger.info("Step 1: Converting webhook to std format")
        std = langbot_webhook_to_std(payload)
        if str(std.get("platform", "")).startswith("langbot_"):
            std["platform"] = "langbot"
        logger.info(
            f"Step 1 done: platform={std.get('platform')}, message={std.get('message', '')[:30]}"
        )

        data = payload.get("data", {})
        adapter_name = data.get("adapter_name", "")
        sender = data.get("sender", {}) or {}
        sender_id = sender.get("id", "")
        sender_name = sender.get("name", "")

        logger.info(
            f"Step 2: Getting character and user (adapter={adapter_name}, sender_id={sender_id})"
        )
        # resolve from_user and to_user
        # Get bot_uuid from converted message metadata
        bot_uuid = std.get("metadata", {}).get("langbot_bot_uuid", "")
        character = get_character_by_bot_uuid(bot_uuid)
        user = get_or_create_user(adapter_name, sender_id, sender_name)
        logger.info(
            f"Step 2 done: character={bool(character)}, user_id={user.get('_id') if user else None}"
        )

        if character:
            std["to_user"] = str(character.get("_id"))
        if user:
            std["from_user"] = str(user.get("_id"))

        logger.info(
            f"Step 3: Inserting into MongoDB (from_user={std.get('from_user')}, to_user={std.get('to_user')})"
        )
        # Insert into Mongo
        mongo = MongoDBBase()
        result = mongo.insert_one("inputmessages", std)
        logger.info(f"Step 3 done: inserted_id={result}")

        return jsonify({"status": "ok", "skip_pipeline": True}), 200

    except Exception as e:
        import traceback

        logger.error(f"Error handling LangBot webhook: {e}\n{traceback.format_exc()}")
        return jsonify({"status": "error"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=False)
