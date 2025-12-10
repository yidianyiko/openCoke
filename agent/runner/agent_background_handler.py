# -*- coding: utf-8 -*-
"""
Agent Background Handler - Agno Version

后台任务处理模块，包括：
- 主动消息触发和生成
- 提醒任务派发
- 关系衰减
- 忙闲状态管理
"""

import sys
sys.path.append(".")
import os
import time
import random
import traceback
import logging
from logging import getLogger

logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

from bson import ObjectId
from entity.message import read_all_inputmessages
from dao.conversation_dao import ConversationDAO
from dao.user_dao import UserDAO
from dao.lock import MongoDBLockManager
from dao.mongo import MongoDBBase
from conf.config import CONF

from util.time_util import date2str, timestamp2str

# ========== 核心处理函数导入 ==========
from agent.runner.agent_handler import handle_message

# ========== 配置 ==========
target_user_alias = CONF.get("default_character_alias", "coke")
_characters_conf = CONF.get("characters") or (CONF.get("aliyun") or {}).get("characters") or {}
target_user_id = _characters_conf.get(target_user_alias, "default_id")

platform = "wechat"
typing_speed = 2.2
max_conversation_round = 50
descrease_frequency = 30240  # 多少秒降低一次关系数值
proactive_frequency = 5338   # 多少秒触发一次主动消息
proactive_chance = 0.03      # 多少概率触发

# ========== DAO 实例 ==========
conversation_dao = ConversationDAO()
user_dao = UserDAO()
lock_manager = MongoDBLockManager()
mongo = MongoDBBase()


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

    # 关系衰减
    if is_decrease:
        decrease_all()
    
    # 主动消息触发
    if is_proactive:
        handle_proactive_message()
    
    # 主动消息派发 (异步，使用统一入口)
    await handle_pending_future_message()
    
    # 提醒任务派发 (异步，使用统一入口)
    await handle_pending_reminders()


def decrease_all():
    """降低所有用户的关系数值"""
    logger.info("decrease all relationships...")
    relations = mongo.find_many("relations", query={"cid": target_user_id}, limit=10000)
    for relation in relations:
        try:
            if relation["relationship"]["closeness"] > 0 or relation["relationship"]["trustness"] > 0:
                relation["relationship"]["closeness"] = max(0, relation["relationship"]["closeness"] - 1)
                relation["relationship"]["trustness"] = max(0, relation["relationship"]["trustness"] - 1)
                mongo.replace_one("relations", {"_id": relation["_id"]}, relation)
        except Exception as e:
            logger.error(traceback.format_exc())


def handle_proactive_message():
    """处理主动消息触发"""
    try:
        logger.info("start character proactive agent...")
        now = int(time.time())
        date_str = date2str(now)
        character = user_dao.get_user_by_id(target_user_id)
        
        current_script = mongo.find_one("dailyscripts", {
            "date": date_str, 
            "cid": target_user_id, 
            "start_timestamp": {"$lt": now}, 
            "end_timestamp": {"$gt": now}
        })
        
        if current_script is not None:
            if character.get("user_info", {}).get("status", {}).get("status", "空闲") in ["空闲"]:
                logger.info("fetch all relations...")
                relations = mongo.find_many("relations", {"cid": target_user_id})
                
                for relation in relations:
                    if relation["relationship"]["dislike"] >= 100:
                        continue
                    if relation.get("character_info", {}).get("status", "空闲") not in ["空闲"]:
                        continue
                    
                    user = user_dao.get_user_by_id(relation["uid"])
                    character = user_dao.get_user_by_id(relation["cid"])
                    conversation = conversation_dao.get_private_conversation(
                        "wechat",
                        user["platforms"]["wechat"]["id"],
                        character["platforms"]["wechat"]["id"],
                    )
                    
                    if conversation is None:
                        continue
                    if conversation.get("conversation_info", {}).get("action") is not None:
                        continue

                    # 单次预期概率
                    chance = ((relation["relationship"]["closeness"] + relation["relationship"]["trustness"]) / 200 + 0.5) * proactive_chance
                    if chance < random.random():
                        continue

                    # 多次惩罚
                    future_proactive_times = conversation.get("conversation_info", {}).get("future", {}).get("proactive_times", 0)
                    if future_proactive_times > 0:
                        if random.random() > (0.3 ** future_proactive_times):
                            continue
                    
                    # 开始主动消息
                    random_topics = ["聊一聊之前谈论过的话题"]
                    random_topic = random.sample(random_topics, 1)[0]
                    logger.info("发起主动话题..." + random_topic)
                    
                    conversation["conversation_info"]["future"]["timestamp"] = int(time.time())
                    conversation["conversation_info"]["future"]["action"] = random_topic
                    mongo.replace_one("conversations", {"_id": conversation["_id"]}, conversation)
                    
    except Exception as e:
        logger.error(traceback.format_exc())


async def handle_pending_future_message():
    """
    处理待发送的主动消息 (V2.4 - 使用统一入口)
    
    使用 handle_message 复用完整的 Phase 1 → 2 → 3 流程
    """
    lock = None
    conversation_id = None
    
    try:
        now = int(time.time())
        conversations = conversation_dao.find_conversations(query={
            "conversation_info.future.action": {"$ne": None, "$exists": True},
            "conversation_info.future.timestamp": {"$lt": now, "$gt": now - 1800}
        })
        
        if len(conversations) == 0:
            return
        
        conversation = conversations[0]
        logger.info("try sending proactive message:" + str(conversation["conversation_info"]["future"]))

        def clear_invalid_future():
            """清除无效的 future 记录"""
            conversation["conversation_info"]["future"] = {}
            mongo.replace_one("conversations", {"_id": conversation["_id"]}, conversation)
            logger.info(f"已清除无效的 future 记录: {conversation.get('_id')}")

        if len(conversation.get("talkers", [])) < 2:
            logger.warning(f"conversation talkers 不足2个，清除: {conversation.get('_id')}")
            clear_invalid_future()
            return

        users = user_dao.find_users({"platforms.wechat.id": conversation["talkers"][0]["id"]}, 1)
        if not users:
            logger.warning(f"找不到用户: {conversation['talkers'][0]['id']}，清除 future")
            clear_invalid_future()
            return
        user = users[0]
        
        characters = user_dao.find_users({"platforms.wechat.id": conversation["talkers"][1]["id"]}, 1)
        if not characters:
            logger.warning(f"找不到角色: {conversation['talkers'][1]['id']}，清除 future")
            clear_invalid_future()
            return
        character = characters[0]
        
        logger.info(f"准备获取锁: conversation_id={conversation['_id']}")

        conversation_id = str(conversation["_id"])
        
        # 调试：检查当前锁状态
        existing_lock = lock_manager.get_lock_info("conversation", conversation_id)
        if existing_lock:
            logger.warning(f"锁已存在: resource_id={existing_lock.get('resource_id')}, "
                          f"created_at={existing_lock.get('created_at')}, "
                          f"expires_at={existing_lock.get('expires_at')}, "
                          f"owner_id={existing_lock.get('owner_id')[:8] if existing_lock.get('owner_id') else 'N/A'}")
        
        # 使用异步锁获取
        lock = await lock_manager.acquire_lock_async("conversation", conversation_id, timeout=120, max_wait=1)
        if lock is None:
            logger.warning(f"获取锁失败，conversation_id={conversation_id}")
            return
        
        # 处理拉黑逻辑
        from agent.runner.context import context_prepare
        context = context_prepare(user, character, conversation)
        
        if context["relation"]["relationship"]["dislike"] >= 100:
            logger.info("用户已被拉黑，跳过主动消息")
        else:
            # ========== 使用统一入口 handle_message ==========
            try:
                future_action = conversation["conversation_info"]["future"].get("action", "")
                future_proactive_times = conversation["conversation_info"]["future"].get("proactive_times", 0)
                
                # 构造系统消息
                input_message_str = f"[系统主动话题(这是我们要主动发给用户的话)] {future_action}"
                
                logger.info(f"[FUTURE] 开始处理主动消息: {future_action} (proactive_times={future_proactive_times})")
                resp_messages, context, _ = await handle_message(
                    user=user,
                    character=character,
                    conversation=conversation,
                    input_message_str=input_message_str,
                    message_source="future",
                    metadata={
                        "action": future_action,
                        "proactive_times": future_proactive_times
                    },
                    check_new_message=False,  # 系统消息不检测新消息
                    worker_tag="[FUTURE]"
                )
                logger.info(f"[FUTURE] 主动消息处理完成，发送 {len(resp_messages)} 条消息")
                
                # 更新会话历史
                conversation = context["conversation"]
                for resp_message in resp_messages:
                    conversation["conversation_info"]["chat_history"].append(resp_message)
                
                if len(conversation["conversation_info"]["chat_history"]) > max_conversation_round:
                    conversation["conversation_info"]["chat_history"] = conversation["conversation_info"]["chat_history"][-max_conversation_round:]
                
                conversation_dao.update_conversation_info(conversation_id, conversation["conversation_info"])
                
                # 更新关系
                relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}
                mongo.replace_one(
                    "relations", 
                    query={"uid": context["relation"]["uid"], "cid": context["relation"]["cid"]},
                    update=relation_update
                )
                
            except Exception as e:
                logger.error(f"[FUTURE] handle_message failed: {e}")
                logger.error(traceback.format_exc())
        
        # 清除 future 记录
        conversation["conversation_info"]["future"] = {}
        mongo.replace_one("conversations", {"_id": conversation["_id"]}, conversation)

    except Exception as e:
        logger.error(traceback.format_exc())
    finally:
        if conversation_id and lock:
            try:
                lock_manager.release_lock("conversation", conversation_id, lock_id=lock)
            except Exception as e:
                logger.error(f"释放锁失败: {e}")


async def handle_pending_reminders():
    """
    处理待触发的提醒任务 (V2.4 - 使用统一入口)
    
    使用 handle_message 复用完整的 Phase 1 → 2 → 3 流程
    """
    from dao.reminder_dao import ReminderDAO
    from util.time_util import calculate_next_recurrence
    from agent.runner.context import context_prepare
    
    reminder_dao = ReminderDAO()
    lock = None
    
    try:
        now = int(time.time())
        reminders = reminder_dao.find_pending_reminders(now)
        
        if len(reminders) == 0:
            return
        
        logger.info(f"发现 {len(reminders)} 个待触发的提醒")
        
        for reminder in reminders:
            conversation_id = None
            try:
                conversation_id = reminder["conversation_id"]
                
                # 使用异步锁获取
                lock = await lock_manager.acquire_lock_async("conversation", conversation_id, timeout=120, max_wait=1)
                if lock is None:
                    continue
                
                conversation = conversation_dao.get_conversation_by_id(conversation_id)
                if not conversation:
                    continue
                
                user = user_dao.get_user_by_id(reminder["user_id"])
                character = user_dao.get_user_by_id(reminder["character_id"])
                if not user or not character:
                    continue
                
                context = context_prepare(user, character, conversation)
                
                if context["relation"]["relationship"]["dislike"] >= 100:
                    reminder_dao.cancel_reminder(reminder["reminder_id"])
                    continue
                
                # ========== 使用统一入口 handle_message ==========
                try:
                    # 构造系统消息
                    reminder_title = reminder.get("title", "提醒")
                    reminder_content = reminder.get("action_template", reminder_title)
                    input_message_str = f"[系统提醒触发] {reminder_content}"
                    
                    logger.info(f"[REMINDER] 开始处理提醒: {reminder_title}")
                    resp_messages, context, _ = await handle_message(
                        user=user,
                        character=character,
                        conversation=conversation,
                        input_message_str=input_message_str,
                        message_source="reminder",
                        metadata={
                            "reminder_id": reminder["reminder_id"],
                            "title": reminder_title,
                            "action_template": reminder_content
                        },
                        check_new_message=False,  # 系统消息不检测新消息
                        worker_tag="[REMINDER]"
                    )
                    logger.info(f"[REMINDER] 提醒处理完成，发送 {len(resp_messages)} 条消息")
                    
                    if not resp_messages:
                        reminder_dao.complete_reminder(reminder["reminder_id"])
                        continue
                    
                    # 更新会话历史
                    conversation = context["conversation"]
                    for resp_message in resp_messages:
                        conversation["conversation_info"]["chat_history"].append(resp_message)
                    
                    if len(conversation["conversation_info"]["chat_history"]) > max_conversation_round:
                        conversation["conversation_info"]["chat_history"] = conversation["conversation_info"]["chat_history"][-max_conversation_round:]
                    
                    conversation_dao.update_conversation_info(conversation_id, conversation["conversation_info"])
                    
                    # 更新关系
                    relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}
                    mongo.replace_one(
                        "relations", 
                        query={"uid": context["relation"]["uid"], "cid": context["relation"]["cid"]},
                        update=relation_update
                    )
                    
                except Exception as e:
                    logger.error(f"[REMINDER] handle_message failed: {e}")
                    logger.error(traceback.format_exc())
                    reminder_dao.complete_reminder(reminder["reminder_id"])
                    continue
                
                # 先标记为已触发（增加触发计数）
                reminder_dao.mark_as_triggered(reminder["reminder_id"])
                
                # 处理周期提醒
                recurrence = reminder.get("recurrence", {})
                if recurrence.get("enabled"):
                    next_time = calculate_next_recurrence(
                        reminder["next_trigger_time"],
                        recurrence.get("type", "daily"),
                        recurrence.get("interval", 1)
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
                            # 周期提醒：重新调度到下次触发时间，状态改回 confirmed
                            reminder_dao.reschedule_reminder(reminder["reminder_id"], next_time)
                        else:
                            # 周期结束：标记为完成
                            reminder_dao.complete_reminder(reminder["reminder_id"])
                    else:
                        reminder_dao.complete_reminder(reminder["reminder_id"])
                else:
                    # 非周期提醒：触发后直接标记为完成
                    reminder_dao.complete_reminder(reminder["reminder_id"])
                
            except Exception as e:
                logger.error(f"处理提醒失败: {traceback.format_exc()}")
            finally:
                if lock and conversation_id:
                    lock_manager.release_lock("conversation", conversation_id, lock_id=lock)
                    lock = None
    
    except Exception as e:
        logger.error(f"提醒处理异常: {traceback.format_exc()}")
    finally:
        reminder_dao.close()
