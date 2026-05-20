# -*- coding: utf-8 -*-
"""
Agent background handler for non-reminder runtime work.

Reminder and follow-up execution now lives in the reminder runtime. This module
keeps only unrelated background maintenance work:

- hold-message recovery
"""

import sys

sys.path.append(".")
import time

from util.log_util import get_logger

logger = get_logger(__name__)

from dao.mongo import MongoDBBase

HOLD_TIMEOUT = 3600


async def background_handler():
    """后台任务主处理函数。"""
    await check_hold_messages()


async def check_hold_messages():
    """
     检查 hold 状态消息，超时时恢复为 pending

     解决问题：
    -P3: hold 状态消息无恢复机制
    -E3: hold 状态超时永久挂起
    """
    try:
        now = int(time.time())
        mongo_client = MongoDBBase()
        hold_messages = mongo_client.find_many("inputmessages", {"status": "hold"}, limit=100)

        if not hold_messages:
            return

        logger.info(f"[HOLD] 发现 {len(hold_messages)} 条 hold 状态消息")

        for msg in hold_messages:
            try:
                hold_started_at = msg.get("hold_started_at", now)
                is_timeout = (now - hold_started_at) > HOLD_TIMEOUT

                if is_timeout:
                    mongo_client.update_one(
                        "inputmessages",
                        {"_id": msg["_id"]},
                        {"$set": {"status": "pending", "hold_started_at": None}},
                    )
                    logger.info(f"[HOLD] 恢复 hold 消息: {msg['_id']}, reason=timeout")

            except Exception as exc:
                logger.error(f"[HOLD] 检查 hold 消息失败: {msg.get('_id')}, error={exc}")

    except Exception as exc:
        logger.error(f"[HOLD] check_hold_messages 异常: {exc}")
