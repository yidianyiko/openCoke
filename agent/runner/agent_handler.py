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

V2.4 更新：
- 抽取核心处理逻辑为 handle_message() 函数
- 支持系统消息（提醒、主动消息）复用完整 Workflow 流程
- 通过 message_source 参数区分消息来源
"""

import sys
sys.path.append(".")
import os
import time
import random
import traceback
import logging
from logging import getLogger
from typing import Optional, Tuple, List, Dict, Any

# 配置日志格式，包含时间戳
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
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
from agent.agno_agent.workflows import PrepareWorkflow, PostAnalyzeWorkflow
from agent.agno_agent.workflows.chat_workflow_streaming import StreamingChatWorkflow

# 预创建 Workflow 实例
prepare_workflow = PrepareWorkflow()
streaming_chat_workflow = StreamingChatWorkflow()
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


def _send_single_message(context, multimodal_response, expect_output_timestamp, is_first=False):
    """发送单条多模态消息"""
    outputmessage = None
    msg_type = multimodal_response.get("type", "text")
    content = multimodal_response.get("content", "")
    
    if msg_type == "voice":
        voice_messages = character_voice(content, multimodal_response.get("emotion", "无"))
        for voice_url, voice_length in voice_messages:
            if not is_first:
                expect_output_timestamp += int(voice_length/1000) + random.randint(2, 5)
            outputmessage = send_message_via_context(
                context, message=content, message_type="voice",
                expect_output_timestamp=expect_output_timestamp,
                metadata={"url": voice_url, "voice_length": voice_length}
            )
    elif msg_type == "photo":
        photo_id = str(content).replace("「", "").replace("」", "").replace("照片", "", 1)
        image_url = upload_image(photo_id)
        if image_url is not None:
            context["conversation"]["conversation_info"]["photo_history"].append(photo_id)
            if len(context["conversation"]["conversation_info"]["photo_history"]) > 12:
                context["conversation"]["conversation_info"]["photo_history"] = context["conversation"]["conversation_info"]["photo_history"][-12:]
            if not is_first:
                expect_output_timestamp += random.randint(2, 8)
            outputmessage = send_message_via_context(
                context, message=content, message_type="image",
                expect_output_timestamp=expect_output_timestamp,
                metadata={"url": image_url}
            )
    else:  # text
        text_message = str(content).replace("<换行>", "\n")
        if not is_first:
            expect_output_timestamp += int(len(text_message) / typing_speed)
        outputmessage = send_message_via_context(
            context, message=text_message, message_type="text",
            expect_output_timestamp=expect_output_timestamp
        )
    return outputmessage, expect_output_timestamp


# ========== 核心消息处理函数 ==========

async def handle_message(
    user: dict,
    character: dict,
    conversation: dict,
    input_message_str: str,
    message_source: str = "user",
    metadata: Optional[Dict[str, Any]] = None,
    check_new_message: bool = True,
    worker_tag: str = "[SYS]"
) -> Tuple[List[dict], dict, bool]:
    """
    核心消息处理逻辑 - Phase 1 → 2 → 3
    
    统一处理用户消息和系统消息（提醒、主动消息），复用完整的 Workflow 流程。
    
    Args:
        user: 用户信息
        character: 角色信息
        conversation: 会话信息
        input_message_str: 输入消息字符串
        message_source: 消息来源
            - "user": 用户消息（默认）
            - "reminder": 提醒触发
            - "future": 主动消息
        metadata: 额外元数据（如 reminder_id、proactive_times 等）
        check_new_message: 是否检测新消息（系统消息通常设为 False）
        worker_tag: 日志标签
    
    Returns:
        Tuple[resp_messages, context, is_rollback]:
            - resp_messages: 发送的消息列表
            - context: 更新后的上下文
            - is_rollback: 是否因新消息而回滚
    """
    context = context_prepare(user, character, conversation)
    
    # 标记消息来源，供 Workflow 识别
    context["message_source"] = message_source
    context["system_message_metadata"] = metadata or {}
    context["conversation"]["conversation_info"]["input_messages_str"] = input_message_str
    
    resp_messages = []
    is_rollback = False
    
    try:
        # ========== Phase 1: PrepareWorkflow ==========
        logger.info(f"{worker_tag} Phase 1: PrepareWorkflow 开始 (source={message_source})")
        prepare_response = await prepare_workflow.run(
            input_message=input_message_str,
            session_state=context
        )
        context = prepare_response.get("session_state", context)
        logger.info(f"{worker_tag} Phase 1: PrepareWorkflow 完成")
        
        # 检测点 1：仅用户消息检测新消息
        if check_new_message and message_source == "user":
            if is_new_message_coming_in(str(user["_id"]), str(character["_id"]), platform):
                is_rollback = True
                logger.info(f"{worker_tag} rollback: new message before chat")
        
        if not is_rollback:
            # ========== Phase 2: ChatWorkflow (流式) ==========
            logger.info(f"{worker_tag} Phase 2: ChatWorkflow 开始")
            expect_output_timestamp = int(time.time())
            multimodal_responses_index = 0
            all_multimodal_responses = []
            
            async for event in streaming_chat_workflow.run_stream(
                input_message=input_message_str,
                session_state=context
            ):
                if event["type"] == "message":
                    multimodal_response = event["data"]
                    multimodal_responses_index += 1
                    all_multimodal_responses.append(multimodal_response)
                    
                    outputmessage, expect_output_timestamp = _send_single_message(
                        context=context,
                        multimodal_response=multimodal_response,
                        expect_output_timestamp=expect_output_timestamp,
                        is_first=(multimodal_responses_index == 1)
                    )
                    if outputmessage is not None:
                        resp_messages.append(outputmessage)
                    
                    # 检测点 2：仅用户消息检测新消息
                    if check_new_message and message_source == "user":
                        if is_new_message_coming_in(str(user["_id"]), str(character["_id"]), platform):
                            is_rollback = True
                            logger.info(f"{worker_tag} rollback: new message during streaming")
                            break
                elif event["type"] == "done":
                    logger.info(f"{worker_tag} 流式完成，共 {event['data'].get('total_messages', 0)} 条")
                elif event["type"] == "error":
                    logger.error(f"{worker_tag} 流式错误: {event['data'].get('error')}")
            
            context["MultiModalResponses"] = all_multimodal_responses
            logger.info(f"{worker_tag} Phase 2: ChatWorkflow 完成")
            
            # ========== Phase 3: PostAnalyzeWorkflow ==========
            if not is_rollback and len(resp_messages) > 0:
                logger.info(f"{worker_tag} Phase 3: PostAnalyzeWorkflow 开始")
                await post_analyze_workflow.run(session_state=context)
                logger.info(f"{worker_tag} Phase 3: PostAnalyzeWorkflow 完成")
    
    except Exception as e:
        logger.error(f"{worker_tag} handle_message failed: {e}")
        logger.error(traceback.format_exc())
        raise
    
    return resp_messages, context, is_rollback


def is_new_message_coming_in(u_id, c_id, platform):
    """检测是否有新消息到达"""
    input_messages = read_all_inputmessages(u_id, c_id, platform, "pending")
    return len(input_messages) > 0


def merge_pending_messages(current_messages: list, new_messages: list) -> list:
    """合并待处理消息"""
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
    """将已发送的消息记录到对话历史"""
    if not sent_messages:
        return conversation
    chat_history = conversation.get("conversation_info", {}).get("chat_history", [])
    for msg in sent_messages:
        if msg and msg not in chat_history:
            chat_history.append(msg)
    conversation["conversation_info"]["chat_history"] = chat_history
    logger.info(f"[消息打断] 已记录 {len(sent_messages)} 条已发送消息到对话历史")
    return conversation


def create_handler(worker_id: int = 0):
    """创建带 worker_id 的消息处理函数（用户消息入口）"""
    worker_tag = f"[W{worker_id}]"
    
    async def _handler():
        input_messages = []
        lock = None
        conversation_id = None
        user = None
        character = None
        
        try:
            if target_wechat_id is None:
                return
            
            characters = user_dao.find_characters({"platforms.wechat.id": target_wechat_id})
            if len(characters) == 0:
                return
            
            target_user_id = str(characters[0]["_id"])
            
            # 获取顶部消息
            top_messages = read_top_inputmessages(
                to_user=target_user_id, status="pending", platform=platform,
                limit=16, max_handle_age=max_handle_age
            )
            if len(top_messages) == 0:
                return
            
            # 随机打乱消息顺序，让不同 worker 从不同消息开始尝试
            random.shuffle(top_messages)
            
            # 尝试获取一个可以处理的消息（能获取到锁的）
            conversation = None
            for top_message in top_messages:
                logger.info(f"{worker_tag} try: {top_message['from_user'][-6:]} - {top_message['message'][:20]}")
                
                user = user_dao.get_user_by_id(top_message["from_user"])
                character = user_dao.get_user_by_id(top_message["to_user"])
                
                if user is None or character is None:
                    logger.warning(f"{worker_tag} 用户或角色不存在，跳过: {top_message['from_user']}")
                    top_message["status"] = "failed"
                    top_message["error"] = "user_not_found"
                    save_inputmessage(top_message)
                    continue
                
                conversation_id, _ = conversation_dao.get_or_create_private_conversation(
                    platform=platform,
                    user_id1=user["platforms"][platform]["id"],
                    nickname1=user["platforms"][platform]["nickname"],
                    user_id2=character["platforms"][platform]["id"],
                    nickname2=character["platforms"][platform]["nickname"],
                )
                conversation = conversation_dao.get_conversation_by_id(conversation_id)
                
                lock = lock_manager.acquire_lock("conversation", conversation_id, timeout=120, max_wait=1)
                if lock is not None:
                    logger.info(f"{worker_tag} 获取锁成功: {top_message['from_user'][-6:]}")
                    break
            
            if lock is None:
                return
            
            # 读取全部需要处理的消息
            input_messages = read_all_inputmessages(str(user["_id"]), str(character["_id"]), platform, "pending")
            for input_message in input_messages:
                input_message["status"] = "handling"
                save_inputmessage(input_message)
            
            conversation["conversation_info"]["input_messages"] = input_messages
            logger.info(f"{worker_tag} 处理 {len(input_messages)} 条消息")
            
            context = context_prepare(user, character, conversation)
            
            is_failed = False
            is_rollback = False
            is_hold = False
            is_hardfinish = False
            is_finish = False
            resp_messages = []
            
            # 处理拉黑逻辑
            if context["relation"]["relationship"]["dislike"] >= 100:
                send_message_via_context(context, message="[系统消息]已拉黑，如需恢复请联系作者YDYK",
                    message_type="text", expect_output_timestamp=int(time.time()))
                is_finish = True
            
            # 处理硬指令
            elif str(context["user"]["_id"]) == CONF["admin_user_id"] and str(input_messages[0]["message"]).startswith(supported_hardcode):
                handle_hardcode(context, input_messages[0]["message"])
                send_message_via_context(context, message="ok", message_type="text", expect_output_timestamp=int(time.time()))
                is_hardfinish = True
            
            # 处理繁忙期状态
            elif context["relation"]["relationship"]["status"] not in ["空闲"]:
                logger.info(f"{worker_tag} hold message as character busy...")
                is_hold = True
            
            else:
                # ========== 调用核心处理函数 ==========
                try:
                    input_message_str = context["conversation"]["conversation_info"]["input_messages_str"]
                    
                    resp_messages, context, is_rollback = await handle_message(
                        user=user,
                        character=character,
                        conversation=conversation,
                        input_message_str=input_message_str,
                        message_source="user",
                        check_new_message=True,
                        worker_tag=worker_tag
                    )
                    is_finish = True
                        
                except Exception as e:
                    logger.error(f"{worker_tag} Workflow failed: {e}")
                    logger.error(traceback.format_exc())
                    is_failed = True
            
            # ========== 后续处理逻辑 ==========
            if is_failed:
                raise Exception("Handle fail")
            
            if is_hold:
                for input_message in input_messages:
                    input_message["status"] = "hold"
                    save_inputmessage(input_message)
                lock_manager.release_lock("conversation", conversation_id, lock_id=lock)
                return
            
            if is_hardfinish:
                for input_message in input_messages:
                    input_message["status"] = "handled"
                    save_inputmessage(input_message)
                lock_manager.release_lock("conversation", conversation_id, lock_id=lock)
                return
            
            if is_rollback or is_finish or (len(resp_messages) == 0 and len(input_messages) > 0):
                conversation = context["conversation"]
                
                if is_rollback:
                    logger.info(f"{worker_tag} [消息打断] 处理消息合并")
                    new_pending_messages = read_all_inputmessages(str(user["_id"]), str(character["_id"]), platform, "pending")
                    if new_pending_messages:
                        merged_messages = merge_pending_messages(conversation["conversation_info"]["input_messages"], new_pending_messages)
                        conversation["conversation_info"]["input_messages"] = merged_messages
                        for new_msg in new_pending_messages:
                            new_msg["status"] = "handling"
                            save_inputmessage(new_msg)
                    if resp_messages:
                        conversation = record_sent_messages_to_history(conversation, resp_messages)
                
                for input_message in conversation["conversation_info"]["input_messages"]:
                    conversation["conversation_info"]["chat_history"].append(input_message)
                conversation["conversation_info"]["input_messages"] = []
                
                if not is_rollback:
                    for resp_message in resp_messages:
                        conversation["conversation_info"]["chat_history"].append(resp_message)
                
                if len(conversation["conversation_info"]["chat_history"]) > max_conversation_round:
                    conversation["conversation_info"]["chat_history"] = conversation["conversation_info"]["chat_history"][-max_conversation_round:]
                
                conversation_dao.update_conversation_info(conversation_id, conversation["conversation_info"])
                
                relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}
                mongo.replace_one("relations", query={"uid": context["relation"]["uid"], "cid": context["relation"]["cid"]}, update=relation_update)
        
        except Exception as e:
            logger.error(f"{worker_tag} {traceback.format_exc()}")
            for input_message in input_messages:
                input_message["status"] = "failed"
                save_inputmessage(input_message)
            if conversation_id and lock:
                lock_manager.release_lock("conversation", conversation_id, lock_id=lock)
            return
        
        for input_message in input_messages:
            input_message["status"] = "handled"
            save_inputmessage(input_message)
        
        if conversation_id and lock:
            lock_manager.release_lock("conversation", conversation_id, lock_id=lock)
            logger.info(f"{worker_tag} 处理完成，释放锁")
    
    return _handler


# 保持向后兼容
handler = create_handler(0)


# ========== 导出 ==========

__all__ = [
    "handle_message",
    "create_handler",
    "handler",
]
