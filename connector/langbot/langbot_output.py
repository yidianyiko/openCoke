"""LangBot output handler.

Polls MongoDB for pending messages and sends them via appropriate API:
- For Feishu/Lark: Direct Feishu API (LangBot Lark adapter doesn't support send_message)
- For other platforms: LangBot Service API

路由信息获取优先级：
1. 从用户的 platforms 配置获取（与 ecloud 一致）
2. 回退到 metadata（兼容旧消息）
"""

import sys

sys.path.append(".")

import asyncio
import time
import traceback

from conf.config import CONF
from connector.langbot.feishu_api import FeishuAPI
from connector.langbot.langbot_adapter import std_to_langbot_message
from connector.langbot.langbot_api import LangBotAPI
from connector.langbot.telegram_api import TelegramAPI
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)


def get_langbot_api() -> LangBotAPI:
    """Get configured LangBot API client."""
    langbot_conf = CONF.get("langbot", {})
    return LangBotAPI(
        base_url=langbot_conf.get("base_url", "http://localhost:8080"),
        api_key=langbot_conf.get("api_key", ""),
    )


def get_feishu_api(app_id: str, app_secret: str) -> FeishuAPI:
    """Get Feishu API client."""
    return FeishuAPI(app_id=app_id, app_secret=app_secret)


def get_telegram_api(bot_token: str) -> TelegramAPI:
    """Get Telegram API client."""
    return TelegramAPI(bot_token=bot_token)


async def output_handler():
    """
    Process one pending output message.

    Finds a pending message for langbot platform and sends it via appropriate API.
    路由信息从用户的 platforms 配置获取，与 ecloud 保持一致。
    """
    mongo = MongoDBBase()
    user_dao = UserDAO()

    try:
        now = int(time.time())
        # Support all langbot_* platforms (langbot_telegram, langbot_qq, etc.)
        message = mongo.find_one(
            "outputmessages",
            {
                "platform": {"$regex": r"^langbot_"},
                "status": "pending",
                "expect_output_timestamp": {"$lte": now},
            },
        )

        if message is None:
            return

        logger.info(f"Sending LangBot message: {message.get('message', '')[:50]}")
        logger.debug(f"Full message: {message}")

        # 获取目标用户信息（与 ecloud 一致的方式）
        user = user_dao.get_user_by_id(message.get("to_user"))
        if user is None:
            raise Exception(f"User not found: {message.get('to_user')}")

        # 从 platform 字段获取平台信息（如 langbot_feishu, langbot_telegram）
        platform = message.get("platform", "")

        # 从用户的 platforms 配置获取路由信息
        user_platform_info = user.get("platforms", {}).get(platform, {})

        # 构建 metadata，优先使用用户配置，回退到消息自带的 metadata
        metadata = message.get("metadata", {})

        # 从 platform 提取 adapter 名称（langbot_feishu -> feishu）
        adapter = (
            platform.replace("langbot_", "")
            if platform.startswith("langbot_")
            else metadata.get("langbot_adapter", "")
        )

        # Route to appropriate API based on adapter
        if adapter.lower() in ("lark", "larkadapter", "feishu"):
            # Use direct Feishu API
            await send_via_feishu_api(message, user_platform_info, metadata)
        elif adapter.lower() in ("telegram", "telegramadapter"):
            # Use direct Telegram API (LangBot's send_message is not implemented)
            await send_via_telegram_api(message, user_platform_info, metadata)
        else:
            # Use LangBot Service API
            await send_via_langbot_api(message, user_platform_info, metadata)

        # Update status
        now = int(time.time())
        if message.get("status") == "handled":
            message["handled_timestamp"] = now
            mongo.replace_one("outputmessages", {"_id": message["_id"]}, message)

    except Exception:
        logger.error(traceback.format_exc())
        if "message" in locals() and message:
            message["status"] = "failed"
            message["handled_timestamp"] = int(time.time())
            mongo.replace_one("outputmessages", {"_id": message["_id"]}, message)


async def send_via_feishu_api(message: dict, user_platform_info: dict, metadata: dict):
    """
    Send message via direct Feishu API.

    Args:
        message: Output message document
        user_platform_info: 用户的平台配置信息（从 user.platforms.langbot_feishu 获取）
        metadata: Message metadata（回退用）
    """
    try:
        # Get Feishu credentials from config
        langbot_conf = CONF.get("langbot", {})
        feishu_conf = langbot_conf.get("feishu", {})

        feishu_app_id = feishu_conf.get("app_id")
        feishu_app_secret = feishu_conf.get("app_secret")

        if not feishu_app_id or not feishu_app_secret:
            raise ValueError(
                "Feishu credentials not configured in config.json under langbot.feishu"
            )

        feishu_api = get_feishu_api(feishu_app_id, feishu_app_secret)

        # 判断是群聊还是私聊
        chatroom_name = message.get("chatroom_name")
        if chatroom_name:
            # 群聊：target_id 是群 ID
            target_id = chatroom_name
            target_type = "chat_id"
            logger.info(f"Feishu group message, target_id: {target_id}")
        else:
            # 私聊：target_id 从用户配置获取
            target_id = user_platform_info.get("id") or metadata.get(
                "langbot_target_id"
            )
            target_type = "open_id"
            if not target_id:
                raise ValueError(
                    "Cannot determine target_id: not found in user platforms or metadata"
                )
            logger.info(
                f"Feishu private message, target_id: {target_id} "
                f"(from {'user_platforms' if user_platform_info.get('id') else 'metadata'})"
            )

        # Send message
        result = feishu_api.send_message(
            target_id=target_id,
            text=message.get("message", ""),
            target_type=target_type,
        )

        if result.get("code") == 0:
            message["status"] = "handled"
            logger.info(f"Feishu API success: {result.get('msg')}")
        else:
            message["status"] = "failed"
            message["error"] = result.get("msg", "Unknown error")
            logger.error(f"Feishu API failed: {result}")

    except Exception as e:
        message["status"] = "failed"
        message["error"] = str(e)
        logger.error(f"Error sending via Feishu API: {e}")
        raise


async def send_via_telegram_api(message: dict, user_platform_info: dict, metadata: dict):
    """
    Send message via direct Telegram Bot API.

    Args:
        message: Output message document
        user_platform_info: User's platform config (from user.platforms.langbot_TelegramAdapter)
        metadata: Message metadata (fallback)
    """
    try:
        # Get Telegram credentials from config
        langbot_conf = CONF.get("langbot", {})
        telegram_conf = langbot_conf.get("telegram", {})

        bot_token = telegram_conf.get("bot_token")

        if not bot_token:
            raise ValueError(
                "Telegram bot_token not configured in config.json under langbot.telegram"
            )

        telegram_api = get_telegram_api(bot_token)

        # Get target chat_id
        chatroom_name = message.get("chatroom_name")
        if chatroom_name:
            # Group chat
            chat_id = chatroom_name
            logger.info(f"Telegram group message, chat_id: {chat_id}")
        else:
            # Private chat: get from user platforms or metadata
            chat_id = user_platform_info.get("id") or metadata.get("langbot_target_id")
            if not chat_id:
                raise ValueError(
                    "Cannot determine chat_id: not found in user platforms or metadata"
                )
            logger.info(
                f"Telegram private message, chat_id: {chat_id} "
                f"(from {'user_platforms' if user_platform_info.get('id') else 'metadata'})"
            )

        # Determine parse_mode from config
        parse_mode = telegram_conf.get("parse_mode")  # Optional: "MarkdownV2" or None

        # Send message
        result = telegram_api.send_message(
            chat_id=chat_id,
            text=message.get("message", ""),
            parse_mode=parse_mode,
        )

        logger.info(f"Telegram send result: {result}")

        # Update status based on response
        if result.get("ok"):
            message["status"] = "handled"
        else:
            message["status"] = "failed"
            message["error"] = result.get("description", "Unknown error")

    except Exception as e:
        message["status"] = "failed"
        message["error"] = str(e)
        logger.error(f"Error sending via Telegram API: {e}")
        raise


async def send_via_langbot_api(message: dict, user_platform_info: dict, metadata: dict):
    """
    Send message via LangBot Service API.

    Args:
        message: Output message document
        user_platform_info: 用户的平台配置信息
        metadata: Message metadata（回退用）
    """
    langbot_api = get_langbot_api()

    # 判断是群聊还是私聊
    chatroom_name = message.get("chatroom_name")
    if chatroom_name:
        # 群聊：target_id 是群 ID
        target_id = chatroom_name
        target_type = "group"
        logger.info(f"LangBot group message, target_id: {target_id}")
    else:
        # 私聊：target_id 从用户配置获取
        target_id = user_platform_info.get("id") or metadata.get("langbot_target_id")
        target_type = "person"
        if not target_id:
            raise ValueError(
                "Cannot determine target_id: not found in user platforms or metadata"
            )
        logger.info(
            f"LangBot private message, target_id: {target_id} "
            f"(from {'user_platforms' if user_platform_info.get('id') else 'metadata'})"
        )

    bot_uuid = metadata.get("langbot_bot_uuid", "")

    # Build message chain
    message_type = message.get("message_type", "text")
    message_content = message.get("message", "")

    if message_type == "text":
        message_chain = [{"type": "Plain", "text": message_content}]
    elif message_type == "image":
        message_chain = [{"type": "Image", "url": metadata.get("url", "")}]
    elif message_type == "voice":
        message_chain = [{"type": "Voice", "url": metadata.get("url", "")}]
    else:
        message_chain = [{"type": "Plain", "text": message_content}]

    # Send via LangBot API
    result = langbot_api.send_message(
        bot_uuid=bot_uuid,
        target_type=target_type,
        target_id=target_id,
        message_chain=message_chain,
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
