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
from concurrent.futures import ThreadPoolExecutor

# 配置日志格式，包含时间戳
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = getLogger(__name__)

from entity.message import (
    read_top_inputmessages, read_all_inputmessages, save_inputmessage,
    update_message_status_safe, increment_retry_count, increment_rollback_count, set_hold_status,
    get_locked_conversation_ids
)
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
MAX_RETRIES = 3             # 最大重试次数
MAX_ROLLBACK = 3            # 最大 rollback 次数
LOCK_TIMEOUT = 180          # 锁超时时间（秒）- 增加到 180 秒以覆盖完整处理周期
HOLD_TIMEOUT = 3600         # hold 超时时间（1小时）

target_user_alias = CONF.get("default_character_alias", "coke")
_characters_conf = CONF.get("characters") or (CONF.get("aliyun") or {}).get("characters") or {}
target_wechat_id = _characters_conf.get(target_user_alias)

platform = "wechat"
typing_speed = 2.2
# V2.6 优化：减少历史对话保留轮数，从 50 降低到 20，减少 token 消耗
max_conversation_round = 20

# ========== DAO 实例 ==========
conversation_dao = ConversationDAO()
user_dao = UserDAO()
lock_manager = MongoDBLockManager()
mongo = MongoDBBase()

# Thread pool for background embedding storage
_embedding_executor = ThreadPoolExecutor(max_workers=2)


def _store_messages_for_retrieval_sync(context: dict, resp_messages: list):
    """
    Store messages as embeddings for future retrieval (sync, runs in background thread).
    """
    from util.embedding_util import store_chat_message
    
    character_id = str(context.get("character", {}).get("_id", ""))
    user_id = str(context.get("user", {}).get("_id", ""))
    
    try:
        # Store user's input messages
        input_messages = context.get("conversation", {}).get("conversation_info", {}).get("input_messages", [])
        for msg in input_messages:
            message_content = msg.get("message", "")
            if message_content:
                store_chat_message(
                    message=message_content,
                    from_user=msg.get("from_user", ""),
                    to_user=msg.get("to_user", ""),
                    character_id=character_id,
                    user_id=user_id,
                    timestamp=msg.get("input_timestamp", 0),
                    message_type=msg.get("message_type", "text")
                )
        
        # Store character's responses
        for msg in resp_messages:
            message_content = msg.get("message", "")
            if message_content:
                store_chat_message(
                    message=message_content,
                    from_user=character_id,
                    to_user=user_id,
                    character_id=character_id,
                    user_id=user_id,
                    timestamp=msg.get("expect_output_timestamp", 0),
                    message_type=msg.get("message_type", "text")
                )
        
        logger.debug(f"Stored {len(input_messages) + len(resp_messages)} messages for semantic retrieval")
    except Exception as e:
        logger.warning(f"Failed to store messages for retrieval: {e}")


def store_messages_background(context: dict, resp_messages: list):
    """Submit message storage to background thread pool."""
    _embedding_executor.submit(_store_messages_for_retrieval_sync, context, resp_messages)


def _extract_recent_chat_history(chat_history: list, limit: int = 6) -> str:
    """
    从聊天历史中提取最近的对话（包括用户和角色的消息）
    用于主动消息/提醒消息场景，避免传入过长的历史对话
    
    Args:
        chat_history: 聊天历史列表
        limit: 提取的消息数量（默认6条，约3轮对话）
    
    Returns:
        格式化的最近对话字符串
    """
    if not chat_history:
        return "（无历史消息）"
    
    # 取最近的 limit 条消息
    recent_messages = chat_history[-limit:] if len(chat_history) > limit else chat_history
    
    if not recent_messages:
        return "（无历史消息）"
    
    # 格式化输出，保持与原始 chat_history_str 类似的格式
    result_lines = []
    for msg in recent_messages:
        msg_from = msg.get("from_nickname", "") or msg.get("from", "")
        msg_content = msg.get("message", "") or msg.get("content", "")
        msg_time = msg.get("time_str", "")
        msg_type = msg.get("message_type", "text")
        
        if msg_content:
            # 截断过长的消息
            if len(msg_content) > 150:
                msg_content = msg_content[:150] + "..."
            
            if msg_time:
                result_lines.append(f"（{msg_time} {msg_from}发来了{msg_type}消息）{msg_content}")
            else:
                result_lines.append(f"（{msg_from}发来了{msg_type}消息）{msg_content}")
    
    return "\n".join(result_lines)


def _verify_lock_ownership(conversation_id: str, lock_id: str) -> bool:
    """
    验证当前是否仍然持有锁
    
    解决问题：锁超时后继续执行导致重复发送消息
    
    Args:
        conversation_id: 会话ID
        lock_id: 锁ID
        
    Returns:
        bool: 是否仍然持有锁
    """
    if not conversation_id or not lock_id:
        return True  # 没有锁信息时默认允许（向后兼容）
    
    lock_info = lock_manager.get_lock_info("conversation", conversation_id)
    if lock_info is None:
        logger.warning(f"锁已不存在: conversation_id={conversation_id}")
        return False
    if lock_info.get("lock_id") != lock_id:
        logger.warning(f"锁已被其他 Worker 获取: conversation_id={conversation_id}, "
                      f"expected={lock_id[:8]}, actual={lock_info.get('lock_id', 'N/A')[:8]}")
        return False
    return True


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
    worker_tag: str = "[SYS]",
    lock_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    current_message_ids: Optional[List[str]] = None
) -> Tuple[List[dict], dict, bool, bool]:
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
        lock_id: 锁ID（用于续期）
        conversation_id: 会话ID（用于续期）
        current_message_ids: 当前正在处理的消息ID列表（用于排除新消息检测）
    
    Returns:
        Tuple[resp_messages, context, is_rollback, is_content_blocked]:
            - resp_messages: 发送的消息列表
            - context: 更新后的上下文
            - is_rollback: 是否因新消息而回滚
            - is_content_blocked: 是否因内容安全审核失败
    """
    context = context_prepare(user, character, conversation)
    
    # 标记消息来源，供 Workflow 识别
    context["message_source"] = message_source
    context["system_message_metadata"] = metadata or {}
    context["conversation"]["conversation_info"]["input_messages_str"] = input_message_str
    
    # 将 proactive_times 放到顶层，供模板使用
    context["proactive_times"] = (metadata or {}).get("proactive_times", 0)
    
    # 提取最近的对话历史（精简版），用于主动消息/提醒消息场景
    recent_chat_history = _extract_recent_chat_history(
        conversation.get("conversation_info", {}).get("chat_history", []),
        limit=6  # 最近6条消息，约3轮对话
    )
    context["recent_chat_history"] = recent_chat_history
    
    resp_messages = []
    is_rollback = False
    is_content_blocked = False  # 内容安全审核失败标志
    
    try:
        # ========== Phase 1: PrepareWorkflow ==========
        logger.info(f"{worker_tag} Phase 1: PrepareWorkflow 开始 (source={message_source})")
        prepare_response = await prepare_workflow.run(
            input_message=input_message_str,
            session_state=context
        )
        context = prepare_response.get("session_state", context)
        logger.info(f"{worker_tag} Phase 1: PrepareWorkflow 完成")
        
        # 检测点 1：仅用户消息检测新消息（排除当前正在处理的消息）
        if check_new_message and message_source == "user":
            if is_new_message_coming_in(str(user["_id"]), str(character["_id"]), platform, current_message_ids):
                is_rollback = True
                logger.info(f"{worker_tag} rollback: new message before chat")
        
        if not is_rollback:
            # ========== Phase 2: ChatWorkflow (流式) ==========
            logger.info(f"{worker_tag} Phase 2: ChatWorkflow 开始")
            
            # ========== 新增：Phase 2 前续期锁 ==========
            if lock_id and conversation_id:
                lock_manager.renew_lock("conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT)
                logger.debug(f"{worker_tag} 锁续期成功 (Phase 2 前)")
            
            expect_output_timestamp = int(time.time())
            multimodal_responses_index = 0
            all_multimodal_responses = []
            is_lock_lost = False  # 新增：锁丢失标志
            
            async for event in streaming_chat_workflow.run_stream(
                input_message=input_message_str,
                session_state=context
            ):
                if event["type"] == "message":
                    multimodal_response = event["data"]
                    multimodal_responses_index += 1
                    all_multimodal_responses.append(multimodal_response)
                    
                    # ========== 新增：发送消息前验证锁所有权 ==========
                    if lock_id and conversation_id:
                        if not _verify_lock_ownership(conversation_id, lock_id):
                            logger.warning(f"{worker_tag} 锁已丢失，停止发送消息")
                            is_lock_lost = True
                            break
                    
                    outputmessage, expect_output_timestamp = _send_single_message(
                        context=context,
                        multimodal_response=multimodal_response,
                        expect_output_timestamp=expect_output_timestamp,
                        is_first=(multimodal_responses_index == 1)
                    )
                    if outputmessage is not None:
                        resp_messages.append(outputmessage)
                        
                        # ========== 新增：每发送一条消息后续期锁 ==========
                        if lock_id and conversation_id:
                            lock_manager.renew_lock("conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT)
                    
                    # 检测点 2：仅用户消息检测新消息（排除当前正在处理的消息）
                    if check_new_message and message_source == "user":
                        if is_new_message_coming_in(str(user["_id"]), str(character["_id"]), platform, current_message_ids):
                            is_rollback = True
                            logger.info(f"{worker_tag} rollback: new message during streaming")
                            break
                elif event["type"] == "done":
                    logger.info(f"{worker_tag} 流式完成，共 {event['data'].get('total_messages', 0)} 条")
                elif event["type"] == "content_blocked":
                    # ========== 内容安全审核失败，设置标志并停止处理 ==========
                    logger.warning(f"{worker_tag} 内容安全审核失败 (Content Exists Risk)，跳过后续处理")
                    is_content_blocked = True
                    break
                elif event["type"] == "error":
                    logger.error(f"{worker_tag} 流式错误: {event['data'].get('error')}")
            
            # ========== 新增：锁丢失时标记为 rollback ==========
            if is_lock_lost:
                is_rollback = True
            
            context["MultiModalResponses"] = all_multimodal_responses
            logger.info(f"{worker_tag} Phase 2: ChatWorkflow 完成")
            
            # ========== Phase 3: PostAnalyzeWorkflow ==========
            # 跳过条件：rollback、无响应消息、或内容安全审核失败
            if not is_rollback and not is_content_blocked and len(resp_messages) > 0:
                # ========== 新增：Phase 3 前续期锁 ==========
                if lock_id and conversation_id:
                    lock_manager.renew_lock("conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT)
                    logger.debug(f"{worker_tag} 锁续期成功 (Phase 3 前)")
                
                logger.info(f"{worker_tag} Phase 3: PostAnalyzeWorkflow 开始")
                await post_analyze_workflow.run(session_state=context)
                logger.info(f"{worker_tag} Phase 3: PostAnalyzeWorkflow 完成")
            elif is_content_blocked:
                logger.warning(f"{worker_tag} 跳过 Phase 3: 内容安全审核失败")
    
    except Exception as e:
        logger.error(f"{worker_tag} handle_message failed: {e}")
        logger.error(traceback.format_exc())
        raise
    
    return resp_messages, context, is_rollback, is_content_blocked


def is_new_message_coming_in(u_id, c_id, platform, current_message_ids: list = None):
    """
    检测是否有新消息到达（排除当前正在处理的消息）
    
    Args:
        u_id: 用户ID
        c_id: 角色ID
        platform: 平台
        current_message_ids: 当前正在处理的消息ID列表（字符串格式）
        
    Returns:
        bool: 是否有新消息
    """
    input_messages = read_all_inputmessages(u_id, c_id, platform, "pending")
    
    # 排除当前正在处理的消息
    if current_message_ids:
        current_ids_set = set(current_message_ids)
        input_messages = [m for m in input_messages if str(m.get("_id", "")) not in current_ids_set]
    
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
        lock_id = None
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
            
            # ========== 优化：获取已锁定的会话列表，避免不必要的锁获取尝试 ==========
            locked_conversation_ids = get_locked_conversation_ids()
            
            # 随机打乱消息顺序，让不同 worker 从不同消息开始尝试
            random.shuffle(top_messages)
            
            # 尝试获取一个可以处理的消息（能获取到锁的）
            conversation = None
            for top_message in top_messages:
                # ========== 新增：检查重试次数 ==========
                retry_count = top_message.get("retry_count", 0)
                if retry_count >= MAX_RETRIES:
                    logger.warning(f"{worker_tag} 消息达到最大重试次数({MAX_RETRIES})，标记为 failed: {top_message['_id']}")
                    update_message_status_safe(top_message["_id"], "failed", "pending")
                    continue
                
                user = user_dao.get_user_by_id(top_message["from_user"])
                character = user_dao.get_user_by_id(top_message["to_user"])
                
                if user is None or character is None:
                    logger.warning(f"{worker_tag} 用户或角色不存在，跳过: {top_message['from_user']}")
                    top_message["status"] = "failed"
                    top_message["error"] = "user_not_found"
                    save_inputmessage(top_message)
                    continue
                
                # 检查 platform 字段是否存在
                if platform not in user.get("platforms", {}):
                    logger.error(f"{worker_tag} 用户缺少 platforms.{platform} 字段: {user.get('_id')}")
                    top_message["status"] = "failed"
                    top_message["error"] = "missing_platform"
                    save_inputmessage(top_message)
                    continue
                if platform not in character.get("platforms", {}):
                    logger.error(f"{worker_tag} 角色缺少 platforms.{platform} 字段: {character.get('_id')}")
                    top_message["status"] = "failed"
                    top_message["error"] = "missing_platform"
                    save_inputmessage(top_message)
                    continue
                
                conversation_id, _ = conversation_dao.get_or_create_private_conversation(
                    platform=platform,
                    user_id1=user["platforms"][platform]["id"],
                    nickname1=user["platforms"][platform]["nickname"],
                    user_id2=character["platforms"][platform]["id"],
                    nickname2=character["platforms"][platform]["nickname"],
                )
                
                # ========== 优化：跳过已锁定的会话，避免不必要的锁获取尝试 ==========
                if conversation_id in locked_conversation_ids:
                    logger.debug(f"{worker_tag} 会话已被锁定，跳过: {conversation_id}")
                    continue
                
                conversation = conversation_dao.get_conversation_by_id(conversation_id)
                
                logger.debug(f"{worker_tag} 尝试获取锁: conversation_id={conversation_id}")
                lock_id = lock_manager.acquire_lock("conversation", conversation_id, timeout=LOCK_TIMEOUT, max_wait=0.1)
                if lock_id is not None:
                    logger.info(f"{worker_tag} 获取锁成功: {top_message['from_user'][-6:]}, lock_id={lock_id}")
                    break
                else:
                    # 锁获取失败（可能是竞争导致），记录 DEBUG 日志
                    logger.debug(f"{worker_tag} 锁获取失败: {conversation_id}")
            
            if lock_id is None:
                logger.debug(f"{worker_tag} 所有消息都无法获取锁，跳过本轮")
                return
            
            # 读取全部需要处理的消息（保持 pending 状态，不再标记为 handling）
            input_messages = read_all_inputmessages(str(user["_id"]), str(character["_id"]), platform, "pending")
            
            # ========== 删除：不再标记为 handling ==========
            # 消息保持 pending 状态，由锁保护
            
            conversation["conversation_info"]["input_messages"] = input_messages
            logger.info(f"{worker_tag} 处理 {len(input_messages)} 条消息")
            
            context = context_prepare(user, character, conversation)
            
            is_failed = False
            is_rollback = False
            is_hold = False
            is_hardfinish = False
            is_finish = False
            is_content_blocked = False  # 新增：内容安全审核失败标志
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
            elif context["relation"]["character_info"].get("status", "空闲") not in ["空闲"]:
                logger.info(f"{worker_tag} hold message as character busy...")
                is_hold = True
            
            else:
                # ========== 调用核心处理函数 ==========
                try:
                    input_message_str = context["conversation"]["conversation_info"]["input_messages_str"]
                    
                    # ========== 新增：锁续期（Phase 2 前） ==========
                    lock_manager.renew_lock("conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT)
                    
                    # 提取当前正在处理的消息ID列表，用于排除新消息检测
                    current_message_ids = [str(msg["_id"]) for msg in input_messages]
                    
                    resp_messages, context, is_rollback, is_content_blocked = await handle_message(
                        user=user,
                        character=character,
                        conversation=conversation,
                        input_message_str=input_message_str,
                        message_source="user",
                        check_new_message=True,
                        worker_tag=worker_tag,
                        lock_id=lock_id,  # 传递 lock_id 用于续期
                        conversation_id=conversation_id,
                        current_message_ids=current_message_ids  # 传递当前消息ID用于排除
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
                    set_hold_status(input_message["_id"])
                # 使用安全锁释放
                released, reason = lock_manager.release_lock_safe("conversation", conversation_id, lock_id)
                if not released:
                    logger.warning(f"{worker_tag} 锁释放异常(hold): {reason}")
                return
            
            if is_hardfinish:
                for input_message in input_messages:
                    # 使用乐观锁更新
                    success = update_message_status_safe(input_message["_id"], "handled", "pending")
                    if not success:
                        logger.warning(f"{worker_tag} 乐观锁更新失败(hardfinish): {input_message['_id']}")
                # 使用安全锁释放
                released, reason = lock_manager.release_lock_safe("conversation", conversation_id, lock_id)
                if not released:
                    logger.warning(f"{worker_tag} 锁释放异常(hardfinish): {reason}")
                return
            
            # ========== 新增：内容安全审核失败，不写入历史记录 ==========
            if is_content_blocked:
                logger.warning(f"{worker_tag} 内容安全审核失败，标记 {len(input_messages)} 条消息为 handled，不写入历史记录")
                for input_message in input_messages:
                    update_message_status_safe(input_message["_id"], "handled", "pending")
                # 使用安全锁释放
                released, reason = lock_manager.release_lock_safe("conversation", conversation_id, lock_id)
                if not released:
                    logger.warning(f"{worker_tag} 锁释放异常(content_blocked): {reason}")
                return
            
            # rollback 时：检查 rollback 次数限制
            if is_rollback:
                max_rollback_count = max(msg.get("rollback_count", 0) for msg in input_messages)
                
                if max_rollback_count >= MAX_ROLLBACK:
                    # ========== 新增：达到最大 rollback 次数，强制处理 ==========
                    logger.warning(f"{worker_tag} 达到最大 rollback 次数({MAX_ROLLBACK})，强制完成处理")
                    is_rollback = False
                    is_finish = True
                else:
                    logger.info(f"{worker_tag} [消息打断] rollback_count={max_rollback_count+1}/{MAX_ROLLBACK}")
                    for input_message in input_messages:
                        increment_rollback_count(input_message["_id"])
                    # 如果已经发送了部分消息，记录到历史
                    if resp_messages:
                        conversation = context["conversation"]
                        conversation = record_sent_messages_to_history(conversation, resp_messages)
                        conversation_dao.update_conversation_info(conversation_id, conversation["conversation_info"])
                    # 使用安全锁释放
                    released, reason = lock_manager.release_lock_safe("conversation", conversation_id, lock_id)
                    if not released:
                        logger.warning(f"{worker_tag} 锁释放异常(rollback): {reason}")
                    logger.info(f"{worker_tag} 释放锁，等待下一轮处理合并后的消息")
                    return
            
            if is_finish or (len(resp_messages) == 0 and len(input_messages) > 0):
                conversation = context["conversation"]
                
                for input_message in conversation["conversation_info"]["input_messages"]:
                    conversation["conversation_info"]["chat_history"].append(input_message)
                conversation["conversation_info"]["input_messages"] = []
                
                if not is_rollback:
                    for resp_message in resp_messages:
                        conversation["conversation_info"]["chat_history"].append(resp_message)
                
                if len(conversation["conversation_info"]["chat_history"]) > max_conversation_round:
                    conversation["conversation_info"]["chat_history"] = conversation["conversation_info"]["chat_history"][-max_conversation_round:]
                
                conversation_dao.update_conversation_info(conversation_id, conversation["conversation_info"])
                
                # Store messages for semantic retrieval (background, non-blocking)
                store_messages_background(context, resp_messages)
                
                relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}
                mongo.replace_one("relations", query={"uid": context["relation"]["uid"], "cid": context["relation"]["cid"]}, update=relation_update)
        
        except Exception as e:
            logger.error(f"{worker_tag} {traceback.format_exc()}")
            # ========== 修改：错误处理增加重试计数 ==========
            for input_message in input_messages:
                retry_count = input_message.get("retry_count", 0) + 1
                if retry_count < MAX_RETRIES:
                    # 未达上限：保持 pending，增加 retry_count
                    increment_retry_count(input_message["_id"], str(e)[:500])
                    logger.info(f"{worker_tag} 消息重试计数: {input_message['_id']}, retry_count={retry_count}/{MAX_RETRIES}")
                else:
                    # 达到上限：标记 failed
                    update_message_status_safe(input_message["_id"], "failed", "pending")
                    logger.warning(f"{worker_tag} 消息达到最大重试次数，标记为 failed: {input_message['_id']}")
            
            if conversation_id and lock_id:
                # 使用安全锁释放
                released, reason = lock_manager.release_lock_safe("conversation", conversation_id, lock_id)
                if not released:
                    logger.warning(f"{worker_tag} 锁释放异常(exception): {reason}")
            return
        
        # ========== 修改：使用乐观锁更新状态 ==========
        for input_message in input_messages:
            success = update_message_status_safe(input_message["_id"], "handled", "pending")
            if not success:
                logger.warning(f"{worker_tag} 乐观锁更新失败，消息可能已被其他 Worker 处理: {input_message['_id']}")
        
        if conversation_id and lock_id:
            # 使用安全锁释放
            released, reason = lock_manager.release_lock_safe("conversation", conversation_id, lock_id)
            if not released:
                logger.warning(f"{worker_tag} 锁释放异常(finish): {reason}")
            else:
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
