# -*- coding: utf-8 -*-
"""
Agent background handler for non-deferred runtime work.

Deferred reminder and follow-up execution now lives in the deferred-actions
runtime. This module keeps only unrelated background maintenance work:

- relationship decay
- hold-message recovery
"""

import sys

sys.path.append(".")
import time

from util.log_util import get_logger

logger = get_logger(__name__)

from agent.runner.identity import is_mongo_object_id, is_synthetic_coke_account_id
from conf.config import CONF
from dao.conversation_dao import ConversationDAO
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO

# ========== 配置 ==========
target_user_alias = CONF.get("default_character_alias", "coke")
typing_speed = 2.2
max_conversation_round = 50
descrease_frequency = 30240  # 多少秒降低一次关系数值
proactive_frequency = 5338  # legacy constant kept for compatibility

# ========== 懒加载 DAO ==========
conversation_dao = None
user_dao = None
mongo = None

# ========== 配置常量 ==========
HOLD_TIMEOUT = 3600  # hold 超时时间（1小时）


def _get_conversation_dao():
    global conversation_dao
    if conversation_dao is None:
        conversation_dao = ConversationDAO()
    return conversation_dao


def _get_user_dao():
    global user_dao
    if user_dao is None:
        user_dao = UserDAO()
    return user_dao


def _get_mongo():
    global mongo
    if mongo is None:
        mongo = MongoDBBase()
    return mongo


def _resolve_target_character():
    characters = _get_user_dao().find_characters({"name": target_user_alias}, limit=1)
    if not characters:
        logger.warning(f"Cannot get character by name={target_user_alias}")
        return None
    return characters[0]


def _build_synthetic_business_user(db_user_id: str, talker: dict | None):
    nickname = ""
    if isinstance(talker, dict):
        nickname = str(talker.get("nickname") or "").strip()
    if not nickname:
        nickname = f"user-{db_user_id[-6:]}"
    return {
        "id": db_user_id,
        "_id": db_user_id,
        "nickname": nickname,
        "is_coke_account": True,
    }


def _resolve_conversation_participants(conversation):
    talkers = conversation.get("talkers") or []
    if len(talkers) < 2:
        return None, None

    resolved = []
    dao = _get_user_dao()
    for talker in talkers[:2]:
        db_user_id = str(talker.get("db_user_id") or "").strip()
        if not db_user_id:
            return None, None
        participant = dao.get_user_by_id(db_user_id)
        if participant is None and not is_mongo_object_id(db_user_id):
            if is_synthetic_coke_account_id(db_user_id):
                participant = _build_synthetic_business_user(db_user_id, talker)
            else:
                return None, None
        if participant is None:
            return None, None
        resolved.append(participant)
    return resolved[0], resolved[1]


async def background_handler():
    """后台任务主处理函数。"""
    now = int(time.time())

    if now % descrease_frequency == 0:
        decrease_all()

    await check_hold_messages()


async def check_hold_messages():
    """
     检查 hold 状态消息，超时或角色空闲时恢复为 pending

     解决问题：
    -P3: hold 状态消息无恢复机制
    -E3: hold 状态超时永久挂起
    """
    try:
        now = int(time.time())
        mongo_client = _get_mongo()
        hold_messages = mongo_client.find_many("inputmessages", {"status": "hold"}, limit=100)

        if not hold_messages:
            return

        logger.info(f"[HOLD] 发现 {len(hold_messages)} 条 hold 状态消息")

        for msg in hold_messages:
            try:
                relation = mongo_client.find_one(
                    "relations",
                    {"uid": msg.get("from_user"), "cid": msg.get("to_user")},
                )

                character_status = "空闲"
                if relation:
                    character_status = relation.get("character_info", {}).get(
                        "status", "空闲"
                    )

                hold_started_at = msg.get("hold_started_at", now)
                is_timeout = (now - hold_started_at) > HOLD_TIMEOUT

                if character_status == "空闲" or is_timeout:
                    mongo_client.update_one(
                        "inputmessages",
                        {"_id": msg["_id"]},
                        {"$set": {"status": "pending", "hold_started_at": None}},
                    )
                    reason = "timeout" if is_timeout else "idle"
                    logger.info(f"[HOLD] 恢复 hold 消息: {msg['_id']}, reason={reason}")

            except Exception as exc:
                logger.error(f"[HOLD] 检查 hold 消息失败: {msg.get('_id')}, error={exc}")

    except Exception as exc:
        logger.error(f"[HOLD] check_hold_messages 异常: {exc}")


def decrease_all():
    """降低所有用户的关系数值"""
    logger.info("decrease all relationships...")
    character = _resolve_target_character()
    if not character:
        return

    character_oid = str(character["_id"])
    mongo_client = _get_mongo()
    relations = mongo_client.find_many(
        "relations",
        query={"cid": character_oid},
        limit=10000,
    )
    for relation in relations:
        try:
            relationship = relation.get("relationship", {})
            if relationship.get("closeness", 0) > 0 or relationship.get("trustness", 0) > 0:
                relationship["closeness"] = max(0, relationship.get("closeness", 0) - 1)
                relationship["trustness"] = max(0, relationship.get("trustness", 0) - 1)
                mongo_client.replace_one("relations", {"_id": relation["_id"]}, relation)
        except Exception:
            logger.exception("Failed to decrease relationship for relation=%s", relation.get("_id"))
