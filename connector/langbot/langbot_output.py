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
        mongo.replace_one("outputmessages", {"_id": message["_id"]}, message)

    except Exception:
        logger.error(traceback.format_exc())
        if "message" in locals() and message:
            message["status"] = "failed"
            message["handled_timestamp"] = int(time.time())
            mongo.replace_one("outputmessages", {"_id": message["_id"]}, message)


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

