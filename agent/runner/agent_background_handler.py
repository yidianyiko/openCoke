# -*- coding: utf-8 -*-
"""
Agent Background Handler-Agno Version

后台任务处理模块，包括：
- 主动消息触发和生成
- 提醒任务派发
- 关系衰减
- 忙闲状态管理
"""

import sys

sys.path.append(".")
import random
import time
import traceback

from util.log_util import get_logger

logger = get_logger(__name__)
# ========== 核心处理函数导入 ==========
from agent.runner.agent_handler import handle_message
from conf.config import CONF
from dao.conversation_dao import ConversationDAO
from dao.lock import MongoDBLockManager
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.time_util import date2str

# ========== 配置 ==========
target_user_alias = CONF.get("default_character_alias", "coke")
_characters_conf = (
    CONF.get("characters") or (CONF.get("aliyun") or {}).get("characters") or {}
)
target_user_id = _characters_conf.get(target_user_alias, "default_id")  # WeChat ID

platform = CONF.get("default_platform", "wechat")
typing_speed = 2.2
max_conversation_round = 50
descrease_frequency = 30240  # 多少秒降低一次关系数值
proactive_frequency = 5338  # 多少秒触发一次主动消息
proactive_chance = 0.03  # 多少概率触发

# ========== DAO 实例 ==========
conversation_dao = ConversationDAO()
user_dao = UserDAO()
lock_manager = MongoDBLockManager()
mongo = MongoDBBase()


# ========== 配置常量 ==========
HOLD_TIMEOUT = 3600  # hold 超时时间（1小时）

# ========== 锁获取失败冷却机制 ==========
# 记录 {conversation_id: last_failed_time} 用于避免频繁重试
_lock_cooldown_cache: dict[str, float] = {}
LOCK_COOLDOWN_SECONDS = 5  # 锁获取失败后的冷却时间（秒），缩短以提高提醒及时性


def _cleanup_cooldown_cache():
    """清理过期的冷却缓存条目"""
    now = time.time()
    expired_keys = [
        key
        for key, last_failed in _lock_cooldown_cache.items()
        if now - last_failed > LOCK_COOLDOWN_SECONDS * 2
    ]
    for key in expired_keys:
        _lock_cooldown_cache.pop(key, None)
    if expired_keys:
        logger.debug(f"清理了 {len(expired_keys)} 个过期的冷却缓存条目")


async def background_handler():
    """后台任务主处理函数"""
    is_decrease = False
    is_proactive = False

    now = int(time.time())

    # 关系衰减检查
    if now % descrease_frequency == 0:
        is_decrease = True

    # 主动消息检查
    if now % proactive_frequency == 0:
        is_proactive = True

    # ========== 定期清理冷却缓存（每分钟清理一次） ==========
    if now % 60 == 0:
        _cleanup_cooldown_cache()

    # 关系衰减
    if is_decrease:
        decrease_all()

    # 主动消息触发
    if is_proactive:
        handle_proactive_message()

    # ========== 新增：检查 hold 状态消息 ==========
    await check_hold_messages()

    # 主动消息派发 (异步，使用统一入口)
    await handle_pending_future_message()

    # 提醒任务派发 (异步，使用统一入口)
    await handle_pending_reminders()


async def check_hold_messages():
    """
     检查 hold 状态消息，超时或角色空闲时恢复为 pending

     解决问题：
    -P3: hold 状态消息无恢复机制
    -E3: hold 状态超时永久挂起
    """
    try:
        now = int(time.time())
        hold_messages = mongo.find_many("inputmessages", {"status": "hold"}, limit=100)

        if not hold_messages:
            return

        logger.info(f"[HOLD] 发现 {len(hold_messages)} 条 hold 状态消息")

        for msg in hold_messages:
            try:
                # 获取用户-角色关系
                relation = mongo.find_one(
                    "relations",
                    {"uid": msg.get("from_user"), "cid": msg.get("to_user")},
                )

                # 获取角色状态
                character_status = "空闲"
                if relation:
                    character_status = relation.get("character_info", {}).get(
                        "status", "空闲"
                    )

                # 检查 hold 超时
                hold_started_at = msg.get("hold_started_at", now)
                is_timeout = (now - hold_started_at) > HOLD_TIMEOUT

                # 角色空闲或超时时恢复为 pending
                if character_status == "空闲" or is_timeout:
                    mongo.update_one(
                        "inputmessages",
                        {"_id": msg["_id"]},
                        {"$set": {"status": "pending", "hold_started_at": None}},
                    )
                    reason = "timeout" if is_timeout else "idle"
                    logger.info(f"[HOLD] 恢复 hold 消息: {msg['_id']}, reason={reason}")

            except Exception as e:
                logger.error(f"[HOLD] 检查 hold 消息失败: {msg.get('_id')}, error={e}")

    except Exception as e:
        logger.error(f"[HOLD] check_hold_messages 异常: {e}")


def decrease_all():
    """降低所有用户的关系数值"""
    logger.info("decrease all relationships...")
    # relations.cid 存储的是 MongoDB ObjectId 字符串，不是 WeChat ID
    # 使用名称查找角色，支持多平台（不再依赖 wechat 平台配置）
    characters = user_dao.find_characters({"name": target_user_alias})
    if not characters:
        # 向后兼容：如果按名称找不到，尝试按 wechat ID 查找
        characters = user_dao.find_characters({"platforms.wechat.id": target_user_id})
    if not characters:
        logger.warning(
            f"Cannot get character by name={target_user_alias} or wechat_id={target_user_id}, skip decrease_all"
        )
        return
    character = characters[0]
    character_oid = str(character["_id"])
    relations = mongo.find_many("relations", query={"cid": character_oid}, limit=10000)
    for relation in relations:
        try:
            if (
                relation["relationship"]["closeness"] > 0
                or relation["relationship"]["trustness"] > 0
            ):
                relation["relationship"]["closeness"] = max(
                    0, relation["relationship"]["closeness"] - 1
                )
                relation["relationship"]["trustness"] = max(
                    0, relation["relationship"]["trustness"] - 1
                )
                mongo.replace_one("relations", {"_id": relation["_id"]}, relation)
        except Exception:
            logger.error(traceback.format_exc())


def handle_proactive_message():
    """处理主动消息触发"""
    try:
        logger.info("start character proactive agent...")
        now = int(time.time())
        date_str = date2str(now)
        # 使用名称查找角色，支持多平台
        characters = user_dao.find_characters({"name": target_user_alias})
        if not characters:
            # 向后兼容：如果按名称找不到，尝试按 wechat ID 查找
            characters = user_dao.find_characters(
                {"platforms.wechat.id": target_user_id}
            )
        if not characters:
            logger.warning(
                f"Cannot get character by name={target_user_alias} or wechat_id={target_user_id}, skip handle_proactive_message"
            )
            return
        character = characters[0]
        character_oid = str(character["_id"])

        current_script = mongo.find_one(
            "dailyscripts",
            {
                "date": date_str,
                "cid": target_user_id,
                "start_timestamp": {"$lt": now},
                "end_timestamp": {"$gt": now},
            },
        )

        if current_script is not None:
            if character.get("user_info", {}).get("status", {}).get(
                "status", "空闲"
            ) in ["空闲"]:
                logger.info("fetch all relations...")
                # relations 集合中的 cid 存储的是 MongoDB ObjectId 字符串
                relations = mongo.find_many("relations", {"cid": character_oid})

                for relation in relations:
                    if relation["relationship"]["dislike"] >= 100:
                        continue
                    if relation.get("character_info", {}).get("status", "空闲") not in [
                        "空闲"
                    ]:
                        continue

                    user = user_dao.get_user_by_id(relation["uid"])
                    character = user_dao.get_user_by_id(relation["cid"])

                    # 动态获取用户的平台（支持 wechat, langbot_LarkAdapter 等）
                    user_platform = None
                    for plat in user.get("platforms", {}).keys():
                        if plat in character.get("platforms", {}):
                            user_platform = plat
                            break

                    if not user_platform:
                        logger.debug(
                            f"用户和角色没有共同平台，跳过: user={user.get('name')}"
                        )
                        continue

                    conversation = conversation_dao.get_private_conversation(
                        user_platform,
                        user["platforms"][user_platform]["id"],
                        character["platforms"][user_platform]["id"],
                    )

                    if conversation is None:
                        continue
                    if (
                        conversation.get("conversation_info", {}).get("action")
                        is not None
                    ):
                        continue

                    # 单次预期概率
                    chance = (
                        (
                            relation["relationship"]["closeness"]
                            + relation["relationship"]["trustness"]
                        )
                        / 200
                        + 0.5
                    ) * proactive_chance
                    if chance < random.random():
                        continue

                    # 多次惩罚
                    future_proactive_times = (
                        conversation.get("conversation_info", {})
                        .get("future", {})
                        .get("proactive_times", 0)
                    )
                    if future_proactive_times > 0:
                        if random.random() > (0.3**future_proactive_times):
                            continue

                    # 开始主动消息
                    random_topics = ["聊一聊之前谈论过的话题"]
                    random_topic = random.sample(random_topics, 1)[0]
                    logger.info("发起主动话题..." + random_topic)

                    conversation["conversation_info"]["future"]["timestamp"] = int(
                        time.time()
                    )
                    conversation["conversation_info"]["future"]["action"] = random_topic
                    mongo.replace_one(
                        "conversations", {"_id": conversation["_id"]}, conversation
                    )

    except Exception:
        logger.error(traceback.format_exc())


async def handle_pending_future_message():
    """
    处理待发送的主动消息 (V2.4-使用统一入口)

    使用 handle_message 复用完整的 Phase 1 → 2 → 3 流程
    """
    lock = None
    conversation_id = None
    conversation = None  # 用于异常时清理
    original_future_timestamp = None  # 用于异常时清理 processing 状态

    try:
        now = int(time.time())
        # 查询未过期且时间已到的主动消息
        # status != "expired" 表示未达到主动消息次数上限
        # proactive_times < 2 限制主动消息发送次数（最多发送2次）
        conversations = conversation_dao.find_conversations(
            query={
                "conversation_info.future.action": {"$ne": None, "$exists": True},
                "conversation_info.future.timestamp": {"$lt": now, "$gt": now - 1800},
                "conversation_info.future.status": {"$nin": ["expired", "processing"]},
                "$or": [
                    {"conversation_info.future.proactive_times": {"$exists": False}},
                    {"conversation_info.future.proactive_times": {"$lt": 2}},
                ],
            }
        )

        if len(conversations) == 0:
            return

        conversation = conversations[0]
        conversation_id = str(conversation["_id"])

        # ========== 冷却机制：在日志之前检查，避免频繁输出 ==========
        now_time = time.time()
        last_failed = _lock_cooldown_cache.get(conversation_id, 0)
        if now_time - last_failed < LOCK_COOLDOWN_SECONDS:
            # 仍在冷却期内，静默跳过
            return

        logger.info(
            "try sending proactive message:"
            + str(conversation["conversation_info"]["future"])
        )

        def clear_invalid_future():
            """清除无效的 future 记录"""
            conversation["conversation_info"]["future"] = {}
            mongo.replace_one(
                "conversations", {"_id": conversation["_id"]}, conversation
            )
            logger.info(f"已清除无效的 future 记录: {conversation.get('_id')}")

        if len(conversation.get("talkers", [])) < 2:
            logger.warning(
                f"conversation talkers 不足2个，清除: {conversation.get('_id')}"
            )
            clear_invalid_future()
            return

        # 使用平台字段动态构建查询（支持 wechat, langbot_LarkAdapter 等）
        platform = conversation.get("platform", "wechat")
        users = user_dao.find_users(
            {f"platforms.{platform}.id": conversation["talkers"][0]["id"]}, 1
        )
        if not users:
            logger.warning(
                f"找不到用户: {conversation['talkers'][0]['id']} (platform={platform})，清除 future"
            )
            clear_invalid_future()
            return
        user = users[0]

        characters = user_dao.find_users(
            {f"platforms.{platform}.id": conversation["talkers"][1]["id"]}, 1
        )
        if not characters:
            logger.warning(
                f"找不到角色: {conversation['talkers'][1]['id']}，清除 future"
            )
            clear_invalid_future()
            return
        character = characters[0]

        logger.info(f"准备获取锁: conversation_id={conversation_id}")

        # 使用异步锁获取
        lock = await lock_manager.acquire_lock_async(
            "conversation", conversation_id, timeout=120, max_wait=1
        )
        if lock is None:
            # 记录失败时间，进入冷却期
            _lock_cooldown_cache[conversation_id] = now_time
            # 只在首次失败时记录详细日志
            existing_lock = lock_manager.get_lock_info("conversation", conversation_id)
            if existing_lock:
                logger.info(
                    f"获取锁失败，进入 {LOCK_COOLDOWN_SECONDS}s 冷却期: conversation_id={conversation_id}, "
                    f"lock_holder={existing_lock.get('owner_id', 'N/A')[:8]}, "
                    f"expires_at={existing_lock.get('expires_at')}"
                )
            else:
                logger.info(
                    f"获取锁失败，进入 {LOCK_COOLDOWN_SECONDS}s 冷却期: conversation_id={conversation_id}"
                )
            return

        # 成功获取锁，清除冷却记录
        _lock_cooldown_cache.pop(conversation_id, None)

        # ========== 立即标记 future 状态为 processing，防止并发重复处理 ==========
        original_future_timestamp = conversation["conversation_info"]["future"].get(
            "timestamp"
        )
        modified_count = mongo.update_one(
            "conversations",
            {
                "_id": conversation["_id"],
                "conversation_info.future.timestamp": original_future_timestamp,
                "conversation_info.future.status": {"$nin": ["expired", "processing"]},
            },
            {"$set": {"conversation_info.future.status": "processing"}},
        )
        if modified_count == 0:
            logger.info(
                f"[FUTURE] future 消息已被其他进程处理，跳过: conversation_id={conversation_id}"
            )
            return

        # 处理拉黑逻辑
        from agent.runner.context import (
            context_prepare,
            detect_repeated_proactive_output,
        )

        context = context_prepare(user, character, conversation)

        if context["relation"]["relationship"]["dislike"] >= 100:
            logger.info("用户已被拉黑，跳过主动消息")
        else:
            # ========== 使用统一入口 handle_message ==========
            try:
                future_action = conversation["conversation_info"]["future"].get(
                    "action", ""
                )
                future_proactive_times = conversation["conversation_info"][
                    "future"
                ].get("proactive_times", 0)

                # ========== V2.10 新增：提取角色最近发送的消息，防止主动消息重复 ==========
                chat_history = conversation.get("conversation_info", {}).get(
                    "chat_history", []
                )
                character_user_id = str(character["_id"])
                proactive_forbidden_messages = detect_repeated_proactive_output(
                    chat_history, character_user_id, limit=3
                )
                context["proactive_forbidden_messages"] = proactive_forbidden_messages
                if proactive_forbidden_messages:
                    logger.info("[FUTURE] 检测到角色最近消息，已添加防重复提示")

                # 构造系统消息
                input_message_str = (
                    f"[系统主动话题(这是我们要主动发给用户的话)] {future_action}"
                )

                logger.info(
                    f"[FUTURE] 开始处理主动消息: {future_action} (proactive_times={future_proactive_times})"
                )
                resp_messages, context, _, is_content_blocked = await handle_message(
                    context=context,  # 传递已构建好的 context，避免重复调用 context_prepare
                    input_message_str=input_message_str,
                    message_source="future",
                    metadata={
                        "action": future_action,
                        "proactive_times": future_proactive_times,
                    },
                    check_new_message=False,  # 系统消息不检测新消息
                    worker_tag="[FUTURE]",
                    lock_id=lock,  # 传递 lock_id 用于续期
                    conversation_id=conversation_id,
                )

                # 内容安全审核失败，跳过后续处理
                if is_content_blocked:
                    logger.warning("[FUTURE] 内容安全审核失败，跳过主动消息处理")
                else:
                    logger.info(
                        f"[FUTURE] 主动消息处理完成，发送 {len(resp_messages)} 条消息"
                    )

                    # 更新会话历史
                    conversation = context["conversation"]
                    for resp_message in resp_messages:
                        conversation["conversation_info"]["chat_history"].append(
                            resp_message
                        )

                    if (
                        len(conversation["conversation_info"]["chat_history"])
                        > max_conversation_round
                    ):
                        conversation["conversation_info"]["chat_history"] = (
                            conversation["conversation_info"]["chat_history"][
                                -max_conversation_round:
                            ]
                        )

                    # 只更新 chat_history 和 photo_history，不更新 future
                    # future 由后台 PostAnalyzeWorkflow 负责更新，避免竞态条件
                    mongo.update_one(
                        "conversations",
                        {"_id": conversation["_id"]},
                        {
                            "$set": {
                                "conversation_info.chat_history": conversation[
                                    "conversation_info"
                                ].get("chat_history", []),
                                "conversation_info.photo_history": conversation[
                                    "conversation_info"
                                ].get("photo_history", []),
                            }
                        },
                    )

                    # 更新关系
                    relation_update = {
                        k: v for k, v in context["relation"].items() if k != "_id"
                    }
                    mongo.replace_one(
                        "relations",
                        query={
                            "uid": context["relation"]["uid"],
                            "cid": context["relation"]["cid"],
                        },
                        update=relation_update,
                    )

            except Exception as e:
                logger.error(f"[FUTURE] handle_message failed: {e}")
                logger.error(traceback.format_exc())

        # 清除 future 记录 - 使用原子更新避免竞态条件
        # 注意：不能用 replace_one，因为 PostAnalyzeWorkflow 在后台可能已更新了 future
        # 使用 original_future_timestamp 而不是从 conversation 中重新获取，避免被中间更新影响
        if original_future_timestamp:
            # 只有当 timestamp 仍是原来的值时才清除（避免覆盖 PostAnalyze 设置的新 future）
            mongo.update_one(
                "conversations",
                {
                    "_id": conversation["_id"],
                    "conversation_info.future.timestamp": original_future_timestamp,
                },
                {"$set": {"conversation_info.future": {}}},
            )
        else:
            # 如果原来没有 timestamp，直接清除
            mongo.update_one(
                "conversations",
                {"_id": conversation["_id"]},
                {"$set": {"conversation_info.future": {}}},
            )

    except Exception:
        logger.error(traceback.format_exc())
        # ========== 异常情况下清除 processing 状态，避免残留 ==========
        if conversation and original_future_timestamp:
            mongo.update_one(
                "conversations",
                {
                    "_id": conversation["_id"],
                    "conversation_info.future.timestamp": original_future_timestamp,
                    "conversation_info.future.status": "processing",
                },
                {"$set": {"conversation_info.future": {}}},
            )
            logger.info(
                f"[FUTURE] 异常后清除 processing 状态: conversation_id={conversation_id}"
            )
    finally:
        if conversation_id and lock:
            try:
                # 使用安全锁释放
                released, reason = lock_manager.release_lock_safe(
                    "conversation", conversation_id, lock
                )
                if not released:
                    logger.warning(f"[FUTURE] 锁释放异常: {reason}")
            except Exception as release_err:
                logger.error(f"释放锁失败: {release_err}")


# 提醒分组时间容差（秒）- 滑动窗口分组（从最早提醒开始的3分钟内）
_REMINDER_GROUP_TOLERANCE = 180


def _group_reminders_by_time(
    reminders: list, tolerance: int = _REMINDER_GROUP_TOLERANCE
) -> dict:
    """
    按会话和触发时间分组提醒，将相近时间的提醒合并处理。

    避免在创建时合并不同类型（重复/非重复）的提醒，
    改为在触发时分组，处理完成后各自独立更新生命周期。

    分组方式：使用滑动窗口，从最早提醒的触发时间开始，
    将 tolerance 范围内的所有提醒归入同一组。

    例如 tolerance=300 时：
    - 提醒A: 8:03:00 → 窗口 8:03:00 - 8:07:59

    Args:
        reminders: 待触发的提醒列表
        tolerance: 滑动窗口大小（秒），默认300秒（5分钟）

    Returns:
        dict: {(conversation_id, anchor_time): [reminder1, reminder2, ...]}
    """
    # 先按会话分组
    by_conversation: dict[str, list] = {}
    for reminder in reminders:
        conv_id = reminder.get("conversation_id")
        if conv_id not in by_conversation:
            by_conversation[conv_id] = []
        by_conversation[conv_id].append(reminder)

    groups = {}
    for conv_id, conv_reminders in by_conversation.items():
        # 按触发时间排序
        conv_reminders.sort(key=lambda r: r.get("next_trigger_time", 0))

        # 使用滑动窗口分组
        remaining = conv_reminders[:]
        while remaining:
            # 以最早的提醒为锚点
            anchor = remaining[0]
            anchor_time = anchor.get("next_trigger_time", 0)
            window_end = anchor_time + tolerance

            # 找出在窗口内的所有提醒
            group = []
            next_remaining = []
            for r in remaining:
                t = r.get("next_trigger_time", 0)
                if t < window_end:
                    group.append(r)
                else:
                    next_remaining.append(r)

            # 使用锚点时间作为分组key
            key = (conv_id, anchor_time)
            groups[key] = group
            remaining = next_remaining

    return groups


async def handle_pending_reminders():
    """
    处理待触发的提醒任务 (V3.0-支持前瞻分组触发)

    使用 handle_message 复用完整的 Phase 1 → 2 → 3 流程。
    同一时间桶（5分钟）内触发的提醒会被分组合并为单条消息，
    但每个提醒的生命周期（重复/非重复）独立管理。

    前瞻查询机制：
    - 查询范围扩大到 now + 5分钟，预取未来即将触发的提醒
    - 只有当分组内最早的提醒已到期时，才处理整个分组
    - 避免无故提前触发，同时实现相近时间提醒的合并
    """
    from dao.reminder_dao import ReminderDAO

    reminder_dao = ReminderDAO()
    _lock = None  # 保留变量以备将来使用

    try:
        now = int(time.time())
        # 前瞻查询：查询 now + 5分钟内的所有提醒
        reminders = reminder_dao.find_pending_reminders(
            now, lookahead=_REMINDER_GROUP_TOLERANCE
        )

        if len(reminders) == 0:
            return

        # 检查是否所有提醒都在冷却期内，避免重复日志
        all_in_cooldown = True
        for reminder in reminders:
            conversation_id = reminder.get("conversation_id")
            if conversation_id:
                last_failed = _lock_cooldown_cache.get(conversation_id, 0)
                if time.time() - last_failed >= LOCK_COOLDOWN_SECONDS:
                    all_in_cooldown = False
                    break

        if not all_in_cooldown:
            logger.info(f"发现 {len(reminders)} 个待触发的提醒（含前瞻）")

        # 按会话和时间分组提醒
        grouped = _group_reminders_by_time(reminders)

        for (conv_id, _time_bucket), reminder_group in grouped.items():
            # 检查分组内最早的提醒是否已到期
            earliest_time = min(r.get("next_trigger_time", 0) for r in reminder_group)
            if earliest_time > now:
                # 最早的提醒还没到期，跳过整组，等下次轮询
                continue

            if len(reminder_group) == 1:
                # 单个提醒，使用原有逻辑
                await _process_single_reminder(reminder_group[0], now, reminder_dao)
            else:
                # 多个提醒，合并处理
                await _process_reminder_group(reminder_group, now, reminder_dao)

    except Exception:
        logger.error(f"提醒处理异常: {traceback.format_exc()}")
    finally:
        reminder_dao.close()


async def _process_single_reminder(reminder: dict, now: int, reminder_dao) -> None:
    """处理单个提醒项

    Args:
        reminder: 提醒文档
        now: 当前时间戳
        reminder_dao: 提醒DAO实例
    """
    conversation_id = None
    lock = None

    try:
        conversation_id = reminder["conversation_id"]

        # 检查时间段限制
        if not await _check_time_period_and_reschedule(reminder, now, reminder_dao):
            return  # 不在时间段内，已重新安排

        # 检查锁和冷却机制
        lock = await _acquire_reminder_lock(conversation_id)
        if lock is None:
            return  # 获取锁失败

        # 获取会话和用户信息
        conversation, user, character = await _get_reminder_context(
            conversation_id, reminder
        )
        if not all([conversation, user, character]):
            # 上下文获取失败，标记提醒为完成状态避免无限重试
            logger.info(
                f"[REMINDER] Context fetch failed for reminder {reminder.get('reminder_id')}, "
                "marking as completed to prevent infinite retries"
            )
            reminder_dao.complete_reminder(reminder["reminder_id"])
            return

        # 检查用户关系状态
        if _should_cancel_reminder_for_user(user, character, conversation):
            reminder_dao.cancel_reminder(reminder["reminder_id"])
            return

        # 处理提醒消息
        await _handle_reminder_message(
            reminder, user, character, conversation, lock, conversation_id
        )

    except Exception:
        logger.error(f"处理提醒失败: {traceback.format_exc()}")
    finally:
        if lock and conversation_id:
            # 使用安全锁释放
            released, reason = lock_manager.release_lock_safe(
                "conversation", conversation_id, lock
            )
            if not released:
                logger.warning(f"[REMINDER] 锁释放异常: {reason}")


async def _process_reminder_group(reminder_group: list, now: int, reminder_dao) -> None:
    """处理同一时间触发的多个提醒（合并为单条消息）

    Args:
        reminder_group: 同一时间触发的提醒列表
        now: 当前时间戳
        reminder_dao: 提醒DAO实例
    """
    conversation_id = None
    lock = None

    # 筛选出可以触发的提醒（检查时间段限制）
    valid_reminders = []
    for reminder in reminder_group:
        if await _check_time_period_and_reschedule(reminder, now, reminder_dao):
            valid_reminders.append(reminder)

    if not valid_reminders:
        return  # 所有提醒都不在时间段内

    try:
        # 使用第一个提醒的会话ID（同一组的会话ID相同）
        conversation_id = valid_reminders[0]["conversation_id"]

        # 检查锁和冷却机制
        lock = await _acquire_reminder_lock(conversation_id)
        if lock is None:
            return  # 获取锁失败

        # 获取会话和用户信息（使用第一个提醒）
        conversation, user, character = await _get_reminder_context(
            conversation_id, valid_reminders[0]
        )
        if not all([conversation, user, character]):
            # 上下文获取失败，标记所有提醒为完成状态避免无限重试
            logger.info(
                f"[REMINDER] Context fetch failed for reminder group, "
                "marking all as completed to prevent infinite retries"
            )
            for reminder in valid_reminders:
                reminder_dao.complete_reminder(reminder["reminder_id"])
            return

        # 检查用户关系状态
        if _should_cancel_reminder_for_user(user, character, conversation):
            for reminder in valid_reminders:
                reminder_dao.cancel_reminder(reminder["reminder_id"])
            return

        # 处理合并的提醒消息
        await _handle_reminder_group_message(
            valid_reminders, user, character, conversation, lock, conversation_id
        )

    except Exception:
        logger.error(f"处理提醒组失败: {traceback.format_exc()}")
    finally:
        if lock and conversation_id:
            released, reason = lock_manager.release_lock_safe(
                "conversation", conversation_id, lock
            )
            if not released:
                logger.warning(f"[REMINDER] 锁释放异常: {reason}")


async def _check_time_period_and_reschedule(
    reminder: dict, now: int, reminder_dao
) -> bool:
    """检查时间段限制并重新安排提醒

    Args:
        reminder: 提醒文档
        now: 当前时间戳
        reminder_dao: 提醒DAO实例

    Returns:
        bool: True表示可以继续处理，False表示已重新安排
    """
    from util.time_util import calculate_next_period_trigger, is_within_time_period

    time_period = reminder.get("time_period", {})
    if time_period.get("enabled"):
        # 检查当前时间是否在时间段内
        if not is_within_time_period(
            now,
            time_period["start_time"],
            time_period["end_time"],
            time_period.get("active_days"),
            time_period.get("timezone", "Asia/Shanghai"),
        ):
            # 不在时间段内，重新计算下次触发时间
            logger.info(
                f"[REMINDER] 提醒 {reminder['reminder_id']} 不在时间段内，重新计算下次触发时间"
            )
            recurrence = reminder.get("recurrence", {})
            if recurrence.get("enabled") and recurrence.get("type") == "interval":
                next_time = calculate_next_period_trigger(
                    now,
                    recurrence.get("interval", 30),
                    time_period["start_time"],
                    time_period["end_time"],
                    time_period.get("active_days"),
                    time_period.get("timezone", "Asia/Shanghai"),
                )
                if next_time:
                    reminder_dao.reschedule_reminder(reminder["reminder_id"], next_time)
                    logger.info(f"[REMINDER] 已重新安排到下一个时间段: {next_time}")
                else:
                    logger.warning("[REMINDER] 无法计算下次触发时间，标记为完成")
                    reminder_dao.complete_reminder(reminder["reminder_id"])
            return False
    return True


async def _acquire_reminder_lock(conversation_id: str):
    """获取提醒处理锁

    Args:
        conversation_id: 会话ID

    Returns:
        lock object or None if failed
    """
    # 冷却机制：避免频繁重试同一个锁
    now_time = time.time()
    last_failed = _lock_cooldown_cache.get(conversation_id, 0)
    if now_time - last_failed < LOCK_COOLDOWN_SECONDS:
        # 仍在冷却期内，静默跳过
        return None

    # 使用异步锁获取
    lock = await lock_manager.acquire_lock_async(
        "conversation", conversation_id, timeout=120, max_wait=1
    )
    if lock is None:
        # 记录失败时间，进入冷却期
        _lock_cooldown_cache[conversation_id] = now_time
        logger.info(
            f"[REMINDER] 获取锁失败，进入 {LOCK_COOLDOWN_SECONDS}s 冷却期: conversation_id={conversation_id}"
        )
        return None

    # 成功获取锁，清除冷却记录
    _lock_cooldown_cache.pop(conversation_id, None)
    return lock


async def _get_reminder_context(conversation_id: str, reminder: dict):
    """获取提醒处理所需的上下文信息

    Args:
        conversation_id: 会话ID
        reminder: 提醒文档

    Returns:
        tuple: (conversation, user, character) or (None, None, None) if failed
    """
    conversation = conversation_dao.get_conversation_by_id(conversation_id)
    if not conversation:
        logger.warning(
            f"[REMINDER] Conversation not found: {conversation_id}, "
            f"reminder_id={reminder.get('reminder_id')}, will mark as completed"
        )
        return None, None, None

    user = user_dao.get_user_by_id(reminder["user_id"])
    character = user_dao.get_user_by_id(reminder["character_id"])
    if not user or not character:
        logger.warning(
            f"[REMINDER] User or character not found, "
            f"reminder_id={reminder.get('reminder_id')}, will mark as completed"
        )
        return None, None, None

    return conversation, user, character


def _should_cancel_reminder_for_user(user, character, conversation):
    """检查是否应该取消提醒（如用户被拉黑）

    Args:
        user: 用户信息
        character: 角色信息
        conversation: 会话信息

    Returns:
        bool: True表示应该取消
    """
    from agent.runner.context import context_prepare

    context = context_prepare(user, character, conversation)
    return context["relation"]["relationship"]["dislike"] >= 100


async def _handle_reminder_message(
    reminder: dict, user, character, conversation, lock, conversation_id
):
    """处理提醒消息的发送和后续逻辑

    Args:
        reminder: 提醒文档
        user: 用户信息
        character: 角色信息
        conversation: 会话信息
        lock: 锁对象
        conversation_id: 会话ID
    """
    from agent.runner.agent_handler import handle_message
    from agent.runner.context import context_prepare

    try:
        # 构造系统消息
        reminder_title = reminder.get("title", "提醒")
        reminder_content = reminder.get("action_template", reminder_title)
        input_message_str = f"[系统提醒触发] {reminder_content}"

        # 构建 context
        context = context_prepare(user, character, conversation)

        logger.info(f"[REMINDER] 开始处理提醒: {reminder_title}")
        resp_messages, context, _, is_content_blocked = await handle_message(
            context=context,  # 传递已构建好的 context，避免重复调用 context_prepare
            input_message_str=input_message_str,
            message_source="reminder",
            metadata={
                "reminder_id": reminder["reminder_id"],
                "title": reminder_title,
                "action_template": reminder_content,
            },
            check_new_message=False,  # 系统消息不检测新消息
            worker_tag="[REMINDER]",
            lock_id=lock,  # 传递 lock_id 用于续期
            conversation_id=conversation_id,
        )

        # 内容安全审核失败，跳过后续处理
        if is_content_blocked:
            logger.warning("[REMINDER] 内容安全审核失败，跳过提醒处理")
            return

        logger.info(f"[REMINDER] 提醒处理完成，发送 {len(resp_messages)} 条消息")

        # 【关键修复】立即标记提醒状态，防止重复触发
        # 无论后续会话/关系更新是否成功，提醒状态都应该被更新
        _handle_reminder_completion(reminder, conversation_id)

        # 如果没有响应消息，跳过会话历史更新
        if not resp_messages:
            return

        # 更新会话历史（失败不影响提醒状态）
        try:
            conversation = context["conversation"]
            for resp_message in resp_messages:
                conversation["conversation_info"]["chat_history"].append(resp_message)

            if (
                len(conversation["conversation_info"]["chat_history"])
                > max_conversation_round
            ):
                conversation["conversation_info"]["chat_history"] = conversation[
                    "conversation_info"
                ]["chat_history"][-max_conversation_round:]

            conversation_dao.update_conversation_info(
                conversation_id, conversation["conversation_info"]
            )

            # 更新关系
            relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}
            mongo.replace_one(
                "relations",
                query={
                    "uid": context["relation"]["uid"],
                    "cid": context["relation"]["cid"],
                },
                update=relation_update,
            )
        except Exception as update_err:
            # 会话/关系更新失败不影响提醒状态（已在前面更新）
            logger.warning(
                f"[REMINDER] 会话/关系更新失败（提醒状态已更新）: {update_err}"
            )

    except Exception as e:
        logger.error(f"[REMINDER] handle_message failed: {e}")
        logger.error(traceback.format_exc())
        logger.warning(
            f"[REMINDER] 提醒处理失败，保留 active 状态等待重试: {reminder['reminder_id']}"
        )



async def _handle_reminder_group_message(
    reminders: list, user, character, conversation, lock, conversation_id
):
    """处理合并的提醒消息（多个提醒合并为单条消息发送）

    Args:
        reminders: 提醒列表（已按触发时间排序）
        user: 用户信息
        character: 角色信息
        conversation: 会话信息
        lock: 锁对象
        conversation_id: 会话ID
    """
    from agent.runner.agent_handler import handle_message
    from agent.runner.context import context_prepare

    try:
        now = int(time.time())
        
        # 按触发时间排序确保顺序正确
        sorted_reminders = sorted(reminders, key=lambda r: r.get("next_trigger_time", 0))
        
        # 构建带时间信息的合并内容
        combined_titles = []
        combined_items = []
        for i, reminder in enumerate(sorted_reminders, 1):
            title = reminder.get("title", "提醒")
            content = reminder.get("action_template", title)
            trigger_time = reminder.get("next_trigger_time", now)
            
            combined_titles.append(title)
            
            # 计算相对时间描述
            diff_seconds = trigger_time - now
            if diff_seconds <= 0:
                time_desc = "现在"
            elif diff_seconds < 60:
                time_desc = f"{diff_seconds}秒后"
            else:
                minutes = diff_seconds // 60
                time_desc = f"{minutes}分钟后"
            
            combined_items.append(f"{i}. {content}（{time_desc}）")

        combined_title = "；".join(combined_titles)
        # 新格式：带序号和时间的列表
        combined_content = "\n".join(combined_items)
        input_message_str = f"[系统提醒触发-多条合并] 按顺序提醒用户：\n{combined_content}"

        # 构建 context
        context = context_prepare(user, character, conversation)

        logger.info(
            f"[REMINDER] 开始处理合并提醒 ({len(reminders)} 个): {combined_title}"
        )
        resp_messages, context, _, is_content_blocked = await handle_message(
            context=context,
            input_message_str=input_message_str,
            message_source="reminder",
            metadata={
                "reminder_ids": [r["reminder_id"] for r in reminders],
                "titles": combined_titles,
                "combined_title": combined_title,
                "is_grouped": True,
            },
            check_new_message=False,
            worker_tag="[REMINDER]",
            lock_id=lock,
            conversation_id=conversation_id,
        )

        # 内容安全审核失败，跳过后续处理
        if is_content_blocked:
            logger.warning("[REMINDER] 内容安全审核失败，跳过提醒处理")
            return

        logger.info(f"[REMINDER] 合并提醒处理完成，发送 {len(resp_messages)} 条消息")

        # 【关键修复】立即标记所有提醒状态，防止重复触发
        # 无论后续会话/关系更新是否成功，提醒状态都应该被更新
        for reminder in sorted_reminders:
            _handle_reminder_completion(reminder, conversation_id)

        # 如果没有响应消息，跳过会话历史更新
        if not resp_messages:
            return

        # 更新会话历史（失败不影响提醒状态）
        try:
            conversation = context["conversation"]
            for resp_message in resp_messages:
                conversation["conversation_info"]["chat_history"].append(resp_message)

            if (
                len(conversation["conversation_info"]["chat_history"])
                > max_conversation_round
            ):
                conversation["conversation_info"]["chat_history"] = conversation[
                    "conversation_info"
                ]["chat_history"][-max_conversation_round:]

            conversation_dao.update_conversation_info(
                conversation_id, conversation["conversation_info"]
            )

            # 更新关系
            relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}
            mongo.replace_one(
                "relations",
                query={
                    "uid": context["relation"]["uid"],
                    "cid": context["relation"]["cid"],
                },
                update=relation_update,
            )
        except Exception as update_err:
            # 会话/关系更新失败不影响提醒状态（已在前面更新）
            logger.warning(
                f"[REMINDER] 会话/关系更新失败（提醒状态已更新）: {update_err}"
            )

    except Exception as e:
        logger.error(f"[REMINDER] handle_message failed for group: {e}")
        logger.error(traceback.format_exc())
        logger.warning(
            f"[REMINDER] 合并提醒处理失败，保留 active 状态等待重试: "
            f"{[r['reminder_id'] for r in reminders]}"
        )



def _handle_reminder_completion(reminder: dict, conversation_id: str):
    """处理提醒完成后的状态更新和周期计算

    Args:
        reminder: 提醒文档
        conversation_id: 会话ID
    """
    from dao.reminder_dao import ReminderDAO
    from util.time_util import calculate_next_period_trigger, calculate_next_recurrence

    reminder_id = reminder["reminder_id"]
    reminder_dao = ReminderDAO()
    try:
        # 先标记为已触发（增加触发计数，状态改为 triggered 防止重复触发）
        if not reminder_dao.mark_as_triggered(reminder_id):
            logger.warning(
                f"[REMINDER] mark_as_triggered 失败，提醒可能已被处理: {reminder_id}"
            )
            return  # 避免重复处理

        logger.info(f"[REMINDER] 已标记提醒为 triggered: {reminder_id}")

        # 处理周期提醒
        recurrence = reminder.get("recurrence", {})
        if recurrence.get("enabled"):
            now = int(time.time())
            time_period = reminder.get("time_period", {})

            # 时间段提醒使用特殊的计算逻辑
            if time_period.get("enabled") and recurrence.get("type") == "interval":
                next_time = calculate_next_period_trigger(
                    now,
                    recurrence.get("interval", 30),
                    time_period["start_time"],
                    time_period["end_time"],
                    time_period.get("active_days"),
                    time_period.get("timezone", "Asia/Shanghai"),
                )
            else:
                # 普通周期提醒
                next_time = calculate_next_recurrence(
                    reminder["next_trigger_time"],
                    recurrence.get("type", "daily"),
                    recurrence.get("interval", 1),
                )

            if next_time:
                end_time = recurrence.get("end_time")
                max_count = recurrence.get("max_count")
                triggered_count = reminder.get("triggered_count", 0) + 1

                should_continue = True
                if end_time and next_time > end_time:
                    should_continue = False
                if max_count and triggered_count >= max_count:
                    should_continue = False

                if should_continue:
                    # 周期提醒：重新调度到下次触发时间，状态改回 active
                    if reminder_dao.reschedule_reminder(reminder_id, next_time):
                        logger.info(
                            f"[REMINDER] 周期提醒已重新调度: {reminder_id}, next_time={next_time}"
                        )
                    else:
                        logger.warning(f"[REMINDER] reschedule_reminder 失败: {reminder_id}")
                else:
                    # 周期结束：标记为完成
                    reminder_dao.complete_reminder(reminder_id)
                    logger.info(f"[REMINDER] 周期提醒已结束: {reminder_id}")
            else:
                reminder_dao.complete_reminder(reminder_id)
        else:
            # 非周期提醒：触发后直接标记为完成
            if reminder_dao.complete_reminder(reminder_id):
                logger.info(f"[REMINDER] 一次性提醒已完成: {reminder_id}")
            else:
                logger.warning(f"[REMINDER] complete_reminder 失败: {reminder_id}")
    finally:
        reminder_dao.close()
