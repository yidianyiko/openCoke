# -*- coding: utf-8 -*-
"""
Agent Message Handler - Agno Version

消息处理主模块，使用 Agno Workflow 实现。

执行流程：
- Phase 1: PrepareWorkflow (QueryRewrite + ReminderDetect + ContextRetrieve)
- 检测点 1: 检测新消息
- Phase 2: ChatWorkflow (ChatResponseAgent)
- 检测点 2: 每条消息发送后检测新消息
- Phase 3: PostAnalyzeWorkflow (PostAnalyzeAgent) - 可被跳过
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

from entity.message import read_top_inputmessages, read_all_inputmessages, save_inputmessage
from dao.conversation_dao import ConversationDAO
from dao.user_dao import UserDAO
from dao.lock import MongoDBLockManager
from dao.mongo import MongoDBBase
from conf.config import CONF

from agent.runner.agent_hardcode_handler import handle_hardcode, supported_hardcode
from agent.runner.context import context_prepare
from agent.util.message_util import send_message_via_context

from agent.tool.voice import character_voice
from agent.tool.image import upload_image

# ========== Agno Workflow 导入 ==========
from agent.agno_agent.workflows import PrepareWorkflow, ChatWorkflow, PostAnalyzeWorkflow

# 预创建 Workflow 实例
prepare_workflow = PrepareWorkflow()
chat_workflow = ChatWorkflow()
post_analyze_workflow = PostAnalyzeWorkflow()

# ========== 配置 ==========
max_handle_age = 3600 * 12  # 只处理12小时以内的消息

target_user_alias = CONF.get("default_character_alias", "coke")
_characters_conf = CONF.get("characters") or (CONF.get("aliyun") or {}).get("characters") or {}
target_wechat_id = _characters_conf.get(target_user_alias)

platform = "wechat"
typing_speed = 2.2
max_conversation_round = 50

# ========== DAO 实例 ==========
conversation_dao = ConversationDAO()
user_dao = UserDAO()
lock_manager = MongoDBLockManager()
mongo = MongoDBBase()


def is_new_message_coming_in(u_id, c_id, platform):
    """检测是否有新消息到达"""
    input_messages = read_all_inputmessages(u_id, c_id, platform, "pending")
    return len(input_messages) > 0


def merge_pending_messages(current_messages: list, new_messages: list) -> list:
    """
    合并待处理消息
    
    当 rollback 发生时，将当前正在处理的消息和新到达的消息合并为一个上下文
    """
    seen_ids = set()
    merged = []
    
    for msg in current_messages + new_messages:
        msg_id = str(msg.get("_id", ""))
        if msg_id and msg_id not in seen_ids:
            seen_ids.add(msg_id)
            merged.append(msg)
        elif not msg_id:
            merged.append(msg)
    
    merged.sort(key=lambda x: x.get("timestamp", 0))
    return merged


def record_sent_messages_to_history(conversation: dict, sent_messages: list) -> dict:
    """
    将已发送的消息记录到对话历史
    
    当 rollback 发生时，已发送的消息不会被撤回，需要记录到历史中
    """
    if not sent_messages:
        return conversation
    
    chat_history = conversation.get("conversation_info", {}).get("chat_history", [])
    
    for msg in sent_messages:
        if msg and msg not in chat_history:
            chat_history.append(msg)
    
    conversation["conversation_info"]["chat_history"] = chat_history
    logger.info(f"[消息打断] 已记录 {len(sent_messages)} 条已发送消息到对话历史")
    
    return conversation


async def main_handler():
    """
    消息处理主函数 (Agno 版本)
    
    使用 Agno Workflow 处理消息：
    - Phase 1: PrepareWorkflow
    - Phase 2: ChatWorkflow  
    - Phase 3: PostAnalyzeWorkflow
    """
    input_messages = []
    lock = None
    conversation_id = None
    
    try:
        if target_wechat_id is None:
            return
        
        characters = user_dao.find_characters({
            "platforms.wechat.id": target_wechat_id
        })
        if len(characters) == 0:
            return
        
        target_user_id = str(characters[0]["_id"])
        
        # 获取顶部消息
        top_messages = read_top_inputmessages(
            to_user=target_user_id, 
            status="pending", 
            platform=platform, 
            limit=16, 
            max_handle_age=max_handle_age
        )
        if len(top_messages) == 0:
            return
        
        for top_message in top_messages:
            logger.info("try handle message:")
            logger.info(top_message)

            # 获取 user 和 character
            user = user_dao.get_user_by_id(top_message["from_user"])
            character = user_dao.get_user_by_id(top_message["to_user"])

            # 获取 conversation 并上锁
            conversation_id, _ = conversation_dao.get_or_create_private_conversation(
                platform=platform,
                user_id1=user["platforms"][platform]["id"],
                nickname1=user["platforms"][platform]["nickname"],
                user_id2=character["platforms"][platform]["id"],
                nickname2=character["platforms"][platform]["nickname"],
            )
            conversation = conversation_dao.get_conversation_by_id(conversation_id)
            
            # 对 conversation 上锁
            lock = lock_manager.acquire_lock("conversation", conversation_id, timeout=120, max_wait=1)
            if lock is None:
                continue

        # 读取全部需要处理的消息
        input_messages = read_all_inputmessages(str(user["_id"]), str(character["_id"]), platform, "pending")
        for input_message in input_messages:
            input_message["status"] = "handling"
            save_inputmessage(input_message)
        
        conversation["conversation_info"]["input_messages"] = input_messages
        logger.info(input_messages)
        
        # 构建 context (session_state)
        context = context_prepare(user, character, conversation)

        # 状态标志
        is_failed = False
        is_rollback = False
        is_hold = False
        is_hardfinish = False
        is_finish = False
        resp_messages = []

        # 处理拉黑逻辑
        if context["relation"]["relationship"]["dislike"] >= 100:
            send_message_via_context(
                context,
                message="[系统消息]已拉黑，如需恢复请联系作者YDYK",
                message_type="text",
                expect_output_timestamp=int(time.time())
            )
            is_finish = True

        # 处理硬指令
        elif str(context["user"]["_id"]) == CONF["admin_user_id"] and str(input_messages[0]["message"]).startswith(supported_hardcode):
            handle_hardcode(context, input_messages[0]["message"])
            send_message_via_context(
                context,
                message="ok",
                message_type="text",
                expect_output_timestamp=int(time.time())
            )
            is_hardfinish = True

        # 处理繁忙期状态
        elif context["relation"]["relationship"]["status"] not in ["空闲"]:
            logger.info("hold message as character busy...")
            is_hold = True

        else:
            # ========== Agno Workflow 执行流程 ==========
            try:
                input_message_str = context["conversation"]["conversation_info"]["input_messages_str"]
                
                # ========== Phase 1: 准备阶段 ==========
                logger.info("Phase 1: PrepareWorkflow 开始执行")
                prepare_response = prepare_workflow.run(
                    input_message=input_message_str,
                    session_state=context,
                )
                context = prepare_response.get("session_state", context)
                logger.info("Phase 1: PrepareWorkflow 执行完成")
                
                # ===== 检测点 1：在生成回复前检测新消息 =====
                if is_new_message_coming_in(str(user["_id"]), str(character["_id"]), platform):
                    is_rollback = True
                    logger.info("roll back as new incoming message before chat response")
                
                if not is_rollback:
                    # ========== Phase 2: 生成回复 ==========
                    logger.info("Phase 2: ChatWorkflow 开始执行")
                    chat_response = chat_workflow.run(
                        input_message=input_message_str,
                        session_state=context,
                    )
                    context = chat_response.get("session_state", context)
                    logger.info("Phase 2: ChatWorkflow 执行完成")
                    
                    # 处理回复内容
                    resp = chat_response.get("content", {})
                    multimodal_responses = resp.get("MultiModalResponses", [])
                    if not isinstance(multimodal_responses, list):
                        multimodal_responses = []
                    
                    # 保存到 context 供 PostAnalyze 使用
                    context["MultiModalResponses"] = multimodal_responses
                    
                    # 发送消息
                    expect_output_timestamp = int(time.time())
                    multimodal_responses_index = 0
                    
                    for multimodal_response in multimodal_responses:
                        multimodal_responses_index += 1
                        
                        # 处理声音
                        if multimodal_response.get("type") == "voice":
                            voice_messages = character_voice(
                                multimodal_response.get("content", ""),
                                multimodal_response.get("emotion", "无")
                            )
                            for voice_url, voice_length in voice_messages:
                                if multimodal_responses_index > 1:
                                    expect_output_timestamp += int(voice_length/1000) + random.randint(2, 5)
                                outputmessage = send_message_via_context(
                                    context,
                                    message=multimodal_response.get("content", ""),
                                    message_type="voice",
                                    expect_output_timestamp=expect_output_timestamp,
                                    metadata={
                                        "url": voice_url,
                                        "voice_length": voice_length
                                    }
                                )
                                if outputmessage is not None:
                                    resp_messages.append(outputmessage)
                        
                        # 处理照片
                        elif multimodal_response.get("type") == "photo":
                            photo_id = str(multimodal_response.get("content", "")).replace("「", "").replace("」", "").replace("照片", "", 1)
                            image_url = upload_image(photo_id)
                            if image_url is not None:
                                context["conversation"]["conversation_info"]["photo_history"].append(photo_id)
                                if len(context["conversation"]["conversation_info"]["photo_history"]) > 12:
                                    context["conversation"]["conversation_info"]["photo_history"] = context["conversation"]["conversation_info"]["photo_history"][-12:]
                                
                                if multimodal_responses_index > 1:
                                    expect_output_timestamp += random.randint(2, 8)
                                outputmessage = send_message_via_context(
                                    context,
                                    message=multimodal_response.get("content", ""),
                                    message_type="image",
                                    expect_output_timestamp=expect_output_timestamp,
                                    metadata={"url": image_url}
                                )
                                if outputmessage is not None:
                                    resp_messages.append(outputmessage)
                        
                        # 处理文本
                        else:
                            text_message = str(multimodal_response.get("content", "")).replace("<换行>", "\n")
                            if multimodal_responses_index > 1:
                                expect_output_timestamp += int(len(text_message) / typing_speed)
                            outputmessage = send_message_via_context(
                                context,
                                message=text_message,
                                message_type="text",
                                expect_output_timestamp=expect_output_timestamp
                            )
                            if outputmessage is not None:
                                resp_messages.append(outputmessage)
                        
                        # ===== 检测点 2：每条消息发送后检测新消息 =====
                        if is_new_message_coming_in(str(user["_id"]), str(character["_id"]), platform):
                            is_rollback = True
                            logger.info("roll back as new incoming message during sending")
                            break
                    
                    # ========== Phase 3: 后处理（如果没有被打断）==========
                    if not is_rollback and len(resp_messages) > 0:
                        logger.info("Phase 3: PostAnalyzeWorkflow 开始执行")
                        post_analyze_workflow.run(session_state=context)
                        logger.info("Phase 3: PostAnalyzeWorkflow 执行完成")
                    
                    is_finish = True
                    
            except Exception as e:
                logger.error(f"Workflow execution failed: {e}")
                logger.error(traceback.format_exc())
                is_failed = True

        # ========== 后续处理逻辑 ==========
        if is_failed:
            raise Exception("Handle fail")
        
        if is_hold:
            for input_message in input_messages:
                input_message["status"] = "hold"
                save_inputmessage(input_message)
            lock_manager.release_lock("conversation", conversation_id)
            return

        if is_hardfinish:
            for input_message in input_messages:
                input_message["status"] = "handled"
                save_inputmessage(input_message)
            lock_manager.release_lock("conversation", conversation_id)
            return
        
        if is_rollback or is_finish or (len(resp_messages) == 0 and len(input_messages) > 0):
            conversation = context["conversation"]
            
            # 消息打断机制处理
            if is_rollback:
                logger.info("[消息打断] 检测到 rollback，开始处理消息合并")
                new_pending_messages = read_all_inputmessages(
                    str(user["_id"]), str(character["_id"]), platform, "pending"
                )
                if new_pending_messages:
                    merged_messages = merge_pending_messages(
                        conversation["conversation_info"]["input_messages"],
                        new_pending_messages
                    )
                    conversation["conversation_info"]["input_messages"] = merged_messages
                    for new_msg in new_pending_messages:
                        new_msg["status"] = "handling"
                        save_inputmessage(new_msg)
                
                if resp_messages:
                    conversation = record_sent_messages_to_history(conversation, resp_messages)
            
            # 将 input_messages 放入 history
            for input_message in conversation["conversation_info"]["input_messages"]:
                conversation["conversation_info"]["chat_history"].append(input_message)
            conversation["conversation_info"]["input_messages"] = []

            # 将回复消息放入 history（非 rollback 情况）
            if not is_rollback:
                for resp_message in resp_messages:
                    conversation["conversation_info"]["chat_history"].append(resp_message)
            
            # 截断历史
            if len(conversation["conversation_info"]["chat_history"]) > max_conversation_round:
                conversation["conversation_info"]["chat_history"] = conversation["conversation_info"]["chat_history"][-max_conversation_round:]
        
            # 更新 conversation
            conversation_dao.update_conversation_info(
                conversation_id,
                conversation["conversation_info"]
            )

            # 更新 relation
            mongo.replace_one(
                "relations", 
                query={
                    "uid": context["relation"]["uid"],
                    "cid": context["relation"]["cid"],
                },
                update=context["relation"]
            )

    except Exception as e:
        logger.error(traceback.format_exc())
        for input_message in input_messages:
            input_message["status"] = "failed"
            save_inputmessage(input_message)
        if conversation_id:
            lock_manager.release_lock("conversation", conversation_id)
        return 

    for input_message in input_messages:
        input_message["status"] = "handled"
        save_inputmessage(input_message)
    
    if conversation_id:
        lock_manager.release_lock("conversation", conversation_id)


# 保持向后兼容的别名
handler = main_handler
