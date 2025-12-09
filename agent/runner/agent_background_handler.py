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

from agent.runner.context import context_prepare
from agent.util.message_util import send_message_via_context
from agent.tool.voice import character_voice
from agent.tool.image import upload_image
from util.time_util import date2str, timestamp2str

# ========== Agno Workflow 导入 ==========
from agent.agno_agent.workflows import FutureMessageWorkflow

# 预创建 Workflow 实例
future_message_workflow = FutureMessageWorkflow()

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
    
    # 主动消息派发
    handle_pending_future_message()
    
    # 提醒任务派发
    handle_pending_reminders()


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


def handle_pending_future_message():
    """
    处理待发送的主动消息 (Agno 版本)
    
    使用 FutureMessageWorkflow 生成主动消息
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

        if len(conversation.get("talkers", [])) < 2:
            logger.warning(f"conversation talkers 不足2个，跳过: {conversation.get('_id')}")
            return

        users = user_dao.find_users({"platforms.wechat.id": conversation["talkers"][0]["id"]}, 1)
        if not users:
            return
        user = users[0]
        
        characters = user_dao.find_users({"platforms.wechat.id": conversation["talkers"][1]["id"]}, 1)
        if not characters:
            return
        character = characters[0]

        conversation_id = str(conversation["_id"])
        lock = lock_manager.acquire_lock("conversation", conversation_id, timeout=120, max_wait=1)
        if lock is None:
            return
        
        context = context_prepare(user, character, conversation)
        
        is_failed = False
        is_finish = False
        resp_messages = []

        # 处理拉黑逻辑
        if context["relation"]["relationship"]["dislike"] >= 100:
            is_finish = True
        else:
            # ========== 使用 Agno Workflow ==========
            try:
                logger.info("FutureMessageWorkflow 开始执行")
                workflow_response = future_message_workflow.run(session_state=context)
                context = workflow_response.get("session_state", context)
                logger.info("FutureMessageWorkflow 执行完成")
                
                content = workflow_response.get("content", {})
                multimodal_responses = content.get("MultiModalResponses", [])
                if not isinstance(multimodal_responses, list):
                    multimodal_responses = []
                
                expect_output_timestamp = int(time.time())
                
                for multimodal_response in multimodal_responses:
                    if multimodal_response.get("type") == "voice":
                        voice_messages = character_voice(
                            multimodal_response.get("content", ""),
                            multimodal_response.get("emotion", "无")
                        )
                        for voice_url, voice_length in voice_messages:
                            outputmessage = send_message_via_context(
                                context,
                                message=multimodal_response.get("content", ""),
                                message_type="voice",
                                expect_output_timestamp=expect_output_timestamp,
                                metadata={"url": voice_url, "voice_length": voice_length}
                            )
                            if outputmessage:
                                resp_messages.append(outputmessage)
                            expect_output_timestamp += int(voice_length/1000) + random.randint(2, 5)
                    
                    elif multimodal_response.get("type") == "photo":
                        photo_id = str(multimodal_response.get("content", "")).replace("「", "").replace("」", "").replace("照片", "", 1)
                        image_url = upload_image(photo_id)
                        if image_url:
                            context["conversation"]["conversation_info"]["photo_history"].append(photo_id)
                            if len(context["conversation"]["conversation_info"]["photo_history"]) > 12:
                                context["conversation"]["conversation_info"]["photo_history"] = context["conversation"]["conversation_info"]["photo_history"][-12:]
                            
                            outputmessage = send_message_via_context(
                                context,
                                message=multimodal_response.get("content", ""),
                                message_type="image",
                                expect_output_timestamp=expect_output_timestamp,
                                metadata={"url": image_url}
                            )
                            if outputmessage:
                                resp_messages.append(outputmessage)
                            expect_output_timestamp += random.randint(2, 8)
                    
                    else:
                        text_message = str(multimodal_response.get("content", "")).replace("<换行>", "\n")
                        outputmessage = send_message_via_context(
                            context,
                            message=text_message,
                            message_type="text",
                            expect_output_timestamp=expect_output_timestamp
                        )
                        if outputmessage:
                            resp_messages.append(outputmessage)
                        expect_output_timestamp += int(len(text_message) / typing_speed)
                
                is_finish = True
                
            except Exception as e:
                logger.error(f"FutureMessageWorkflow execution failed: {e}")
                logger.error(traceback.format_exc())
                is_failed = True

        if is_failed:
            raise Exception("Handle fail")
        
        if is_finish:
            conversation = context["conversation"]
            for resp_message in resp_messages:
                conversation["conversation_info"]["chat_history"].append(resp_message)
            
            if len(conversation["conversation_info"]["chat_history"]) > max_conversation_round:
                conversation["conversation_info"]["chat_history"] = conversation["conversation_info"]["chat_history"][-max_conversation_round:]
        
            conversation_dao.update_conversation_info(conversation_id, conversation["conversation_info"])

            relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}
            mongo.replace_one(
                "relations", 
                query={"uid": context["relation"]["uid"], "cid": context["relation"]["cid"]},
                update=relation_update
            )

    except Exception as e:
        logger.error(traceback.format_exc())
    finally:
        if conversation_id and lock:
            try:
                lock_manager.release_lock("conversation", conversation_id)
            except Exception as e:
                logger.error(f"释放锁失败: {e}")


def handle_pending_reminders():
    """处理待触发的提醒任务"""
    from dao.reminder_dao import ReminderDAO
    from util.time_util import calculate_next_recurrence
    
    reminder_dao = ReminderDAO()
    lock = None
    
    try:
        now = int(time.time())
        reminders = reminder_dao.find_pending_reminders(now)
        
        if len(reminders) == 0:
            return
        
        logger.info(f"发现 {len(reminders)} 个待触发的提醒")
        
        for reminder in reminders:
            try:
                conversation_id = reminder["conversation_id"]
                lock = lock_manager.acquire_lock("conversation", conversation_id, timeout=120, max_wait=1)
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
                
                # 发送提醒消息
                outputmessage = send_message_via_context(
                    context,
                    message=reminder["action_template"],
                    message_type="text",
                    expect_output_timestamp=int(time.time())
                )
                
                if not outputmessage:
                    reminder_dao.complete_reminder(reminder["reminder_id"])
                    continue
                
                logger.info(f"提醒已发送: {reminder['title']}")
                
                # 更新会话历史
                conversation["conversation_info"]["chat_history"].append(outputmessage)
                if len(conversation["conversation_info"]["chat_history"]) > max_conversation_round:
                    conversation["conversation_info"]["chat_history"] = conversation["conversation_info"]["chat_history"][-max_conversation_round:]
                
                conversation_dao.update_conversation_info(conversation_id, conversation["conversation_info"])
                
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
                if lock:
                    lock_manager.release_lock("conversation", conversation_id)
                    lock = None
    
    except Exception as e:
        logger.error(f"提醒处理异常: {traceback.format_exc()}")
    finally:
        reminder_dao.close()
