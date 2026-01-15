"""LangBot output handler.

Polls MongoDB for pending messages and sends them via appropriate API:
- For Feishu/Lark: Direct Feishu API (LangBot Lark adapter doesn't support send_message)
- For other platforms: LangBot Service API
"""
import sys

sys.path.append(".")

import asyncio
import time
import traceback

from conf.config import CONF
from connector.langbot.langbot_adapter import std_to_langbot_message
from connector.langbot.langbot_api import LangBotAPI
from connector.langbot.feishu_api import FeishuAPI
from dao.mongo import MongoDBBase
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


async def output_handler():
    """
    Process one pending output message.

    Finds a pending message for langbot platform and sends it via appropriate API.
    """
    mongo = MongoDBBase()

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

        metadata = message.get("metadata", {})
        adapter = metadata.get("langbot_adapter", "")

        # Check if this is a Feishu/Lark message
        if adapter.lower() in ("lark", "larkadapter"):
            # Use direct Feishu API
            await send_via_feishu_api(message, metadata)
        else:
            # Use LangBot Service API
            await send_via_langbot_api(message)

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


async def send_via_feishu_api(message: dict, metadata: dict):
    """
    Send message via direct Feishu API.

    Args:
        message: Output message document
        metadata: Message metadata containing Feishu credentials
    """
    try:
        # Get Feishu credentials from metadata or config
        langbot_conf = CONF.get("langbot", {})
        feishu_app_id = metadata.get("feishu_app_id") or langbot_conf.get("feishu_app_id")
        feishu_app_secret = metadata.get("feishu_app_secret") or langbot_conf.get("feishu_app_secret")

        # Fall back to bot_uuid's credentials if not in metadata
        if not feishu_app_id or not feishu_app_secret:
            # Need to get from bot config - for now use hardcoded values or config
            # In production, should fetch from LangBot database or config
            feishu_app_id = "cli_a9e2c9da8cf85cd4"
            feishu_app_secret = "w8xxkD4CrIKO6blg25tTbbMfoGQ3oRFi"

        feishu_api = get_feishu_api(feishu_app_id, feishu_app_secret)

        target_id = metadata.get("langbot_target_id")
        if not target_id:
            raise ValueError("langbot_target_id not found in metadata")

        # Send message
        result = feishu_api.send_message(
            target_id=target_id,
            text=message.get("message", ""),
            target_type="open_id"
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


async def send_via_langbot_api(message: dict):
    """
    Send message via LangBot Service API.

    Args:
        message: Output message document
    """
    langbot_api = get_langbot_api()

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
