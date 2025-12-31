# -*- coding: utf-8 -*-
"""
Agent Message Handler-Agno Version

消息处理主模块，使用 Agno Workflow 实现.

执行流程：
- Phase 1: PrepareWorkflow (QueryRewrite + ReminderDetect + ContextRetrieve)
- 检测点 1: 检测新消息
- Phase 2: ChatWorkflow (ChatResponseAgent)
- 检测点 2: 每条消息发送后检测新消息
- Phase 3: PostAnalyzeWorkflow (PostAnalyzeAgent)-可被跳过

V2.4 更新：
- 抽取核心处理逻辑为 handle_message() 函数
- 支持系统消息（提醒、主动消息）复用完整 Workflow 流程
- 通过 message_source 参数区分消息来源
"""

import asyncio
import os
import sys

sys.path.append(".")
import copy
import random
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from util.log_util import get_logger

logger = get_logger(__name__)

# ========== Agno Workflow 导入 ==========
from agent.agno_agent.workflows import PostAnalyzeWorkflow, PrepareWorkflow
from agent.agno_agent.workflows.chat_workflow_streaming import StreamingChatWorkflow
from agent.runner.agent_hardcode_handler import handle_hardcode, supported_hardcode
from agent.runner.context import context_prepare
from agent.tool.image import upload_image
from agent.tool.voice import character_voice
from agent.util.message_util import send_message_via_context
from conf.config import CONF
from dao.conversation_dao import ConversationDAO
from dao.lock import MongoDBLockManager
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from entity.message import (
    get_locked_conversation_ids,
    increment_retry_count,
    increment_rollback_count,
    read_all_inputmessages,
    read_top_inputmessages,
    save_inputmessage,
    set_hold_status,
    update_message_status_safe,
)

# 预创建 Workflow 实例
prepare_workflow = PrepareWorkflow()
streaming_chat_workflow = StreamingChatWorkflow()
post_analyze_workflow = PostAnalyzeWorkflow()

# ========== 配置 ==========
max_handle_age = 3600 * 12  # 只处理12小时以内的消息
MAX_RETRIES = 3  # 最大重试次数
MAX_ROLLBACK = 3  # 最大 rollback 次数
LOCK_TIMEOUT = 180  # 锁超时时间（秒）- 增加到 180 秒以覆盖完整处理周期
HOLD_TIMEOUT = 3600  # hold 超时时间（1小时）

target_user_alias = CONF.get("default_character_alias", "coke")
_characters_conf = (
    CONF.get("characters") or (CONF.get("aliyun") or {}).get("characters") or {}
)
target_wechat_id = _characters_conf.get(target_user_alias)

platform = "wechat"
typing_speed = 2.2
# V2.7 优化：减少历史对话保留轮数，从 20 降低到 15，减少 token 消耗
max_conversation_round = 15

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
        input_messages = (
            context.get("conversation", {})
            .get("conversation_info", {})
            .get("input_messages", [])
        )
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
                    message_type=msg.get("message_type", "text"),
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
                    message_type=msg.get("message_type", "text"),
                )

        logger.debug(
            f"Stored {len(input_messages) + len(resp_messages)} messages for semantic retrieval"
        )
    except Exception as e:
        logger.warning(f"Failed to store messages for retrieval: {e}")


def store_messages_background(context: dict, resp_messages: list):
    """Submit message storage to background thread pool.
    
    BUG-008 fix: Use deep copy to prevent concurrent modification of context
    while the background thread is accessing it.
    """
    # Deep copy to avoid race condition with concurrent context modifications
    context_copy = copy.deepcopy(context)
    resp_messages_copy = copy.deepcopy(resp_messages)
    _embedding_executor.submit(
        _store_messages_for_retrieval_sync, context_copy, resp_messages_copy
    )


async def _run_post_analyze_background(
    context: dict,
    conversation_id: str,
    worker_tag: str,
) -> None:
    """
    后台执行 PostAnalyzeWorkflow（Fire-and-Forget 模式）

    优化目的：
    - 不阻塞主流程，Phase 2 完成后立即返回
    - 失败时仅记录日志，不影响用户体验
    - 成功后更新 relation 和 conversation 到数据库

    Args:
        context: 深拷贝的上下文（避免并发修改）
        conversation_id: 会话ID
        worker_tag: 日志标签
    """
    try:
        logger.info(f"{worker_tag} [BG] PostAnalyzeWorkflow 开始")
        await post_analyze_workflow.run(session_state=context)

        # 更新 relation 到数据库
        relation = context.get("relation", {})
        if relation.get("uid") and relation.get("cid"):
            relation_update = {k: v for k, v in relation.items() if k != "_id"}
            mongo.replace_one(
                "relations",
                query={"uid": relation["uid"], "cid": relation["cid"]},
                update=relation_update,
            )

        # 只更新 conversation.future 字段到数据库
        # 注意：不能更新整个 conversation_info，会覆盖主流程的 chat_history 更新
        if conversation_id:
            future_info = context.get("conversation", {}).get(
                "conversation_info", {}
            ).get("future", {})
            mongo.update_one(
                "conversations",
                {"_id": ObjectId(conversation_id)},
                {"$set": {"conversation_info.future": future_info}}
            )

        logger.info(f"{worker_tag} [BG] PostAnalyzeWorkflow 完成")

    except Exception as e:
        logger.warning(f"{worker_tag} [BG] PostAnalyzeWorkflow 失败: {e}")


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
    recent_messages = (
        chat_history[-limit:] if len(chat_history) > limit else chat_history
    )

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
                result_lines.append(
                    f"（{msg_time} {msg_from}发来了{msg_type}消息）{msg_content}"
                )
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
        logger.warning(
            f"锁已被其他 Worker 获取: conversation_id={conversation_id}, "
            f"expected={lock_id[:8]}, actual={lock_info.get('lock_id', 'N/A')[:8]}"
        )
        return False
    return True


def _send_single_message(
    context, multimodal_response, expect_output_timestamp, is_first=False
):
    """发送单条多模态消息"""
    outputmessage = None
    msg_type = multimodal_response.get("type", "text")
    content = multimodal_response.get("content", "")

    # ========== 去重检查：跳过 rollback 恢复场景中已发送的内容 ==========
    turn_sent = (
        context.get("conversation", {})
        .get("conversation_info", {})
        .get("turn_sent_contents", [])
    )
    if turn_sent and content in turn_sent:
        logger.info(f"[去重] 跳过已发送内容: {content[:30]}...")
        return None, expect_output_timestamp

    if msg_type == "voice":
        voice_messages = character_voice(
            content, multimodal_response.get("emotion", "无")
        )
        for voice_url, voice_length in voice_messages:
            if not is_first:
                expect_output_timestamp += int(voice_length/1000) + random.randint(
                    2, 5
                )
            outputmessage = send_message_via_context(
                context,
                message=content,
                message_type="voice",
                expect_output_timestamp=expect_output_timestamp,
                metadata={"url": voice_url, "voice_length": voice_length},
            )
    elif msg_type == "photo":
        photo_id = (
            str(content).replace("「", "").replace("」", "").replace("照片", "", 1)
        )
        image_url = upload_image(photo_id)
        if image_url is not None:
            context["conversation"]["conversation_info"]["photo_history"].append(
                photo_id
            )
            if len(context["conversation"]["conversation_info"]["photo_history"]) > 12:
                context["conversation"]["conversation_info"]["photo_history"] = context[
                    "conversation"
                ]["conversation_info"]["photo_history"][-12:]
            if not is_first:
                expect_output_timestamp += random.randint(2, 8)
            outputmessage = send_message_via_context(
                context,
                message=content,
                message_type="image",
                expect_output_timestamp=expect_output_timestamp,
                metadata={"url": image_url},
            )
    else:  # text
        text_message = str(content).replace("<换行>", "\n")
        if not is_first:
            expect_output_timestamp += int(len(text_message)/typing_speed)
        outputmessage = send_message_via_context(
            context,
            message=text_message,
            message_type="text",
            expect_output_timestamp=expect_output_timestamp,
        )
    return outputmessage, expect_output_timestamp


# ========== 核心消息处理函数 ==========


async def handle_message(
    context: dict,
    input_message_str: str,
    message_source: str = "user",
    metadata: Optional[Dict[str, Any]] = None,
    check_new_message: bool = True,
    worker_tag: str = "[SYS]",
    lock_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    current_message_ids: Optional[List[str]] = None,
) -> Tuple[List[dict], dict, bool, bool]:
    """
    核心消息处理逻辑-Phase 1 → 2 → 3

    统一处理用户消息和系统消息（提醒、主动消息），复用完整的 Workflow 流程.

    Args:
        context: 已构建好的上下文（由 context_prepare 生成）
        input_message_str: 输入消息字符串
        message_source: 消息来源
           -"user": 用户消息（默认）
           -"reminder": 提醒触发
           -"future": 主动消息
        metadata: 额外元数据（如 reminder_id、proactive_times 等）
        check_new_message: 是否检测新消息（系统消息通常设为 False）
        worker_tag: 日志标签
        lock_id: 锁ID（用于续期）
        conversation_id: 会话ID（用于续期）
        current_message_ids: 当前正在处理的消息ID列表（用于排除新消息检测）

    Returns:
        Tuple[resp_messages, context, is_rollback, is_content_blocked]:
           -resp_messages: 发送的消息列表
           -context: 更新后的上下文
           -is_rollback: 是否因新消息而回滚
           -is_content_blocked: 是否因内容安全审核失败
    """
    # 标记消息来源，供 Workflow 识别
    context["message_source"] = message_source
    context["system_message_metadata"] = metadata or {}
    context["conversation"]["conversation_info"][
        "input_messages_str"
    ] = input_message_str

    # 将 proactive_times 放到顶层，供模板使用
    context["proactive_times"] = (metadata or {}).get("proactive_times", 0)

    # ========== 将锁信息放入 context，供 PrepareWorkflow 续期使用 ==========
    # 解决问题：ReminderDetectAgent 执行时间过长导致锁过期
    if lock_id:
        context["lock_id"] = lock_id
    if conversation_id:
        context["conversation_id"] = conversation_id

    # 提取最近的对话历史（精简版），用于主动消息/提醒消息场景
    conversation = context.get("conversation", {})
    recent_chat_history = _extract_recent_chat_history(
        conversation.get("conversation_info", {}).get("chat_history", []),
        limit=6,  # 最近6条消息，约3轮对话
    )
    context["recent_chat_history"] = recent_chat_history

    resp_messages = []
    is_rollback = False
    is_content_blocked = False  # 内容安全审核失败标志

    try:
        # ========== Phase 1: PrepareWorkflow ==========
        logger.info(
            f"{worker_tag} Phase 1: PrepareWorkflow 开始 (source={message_source})"
        )
        prepare_response = await prepare_workflow.run(
            input_message=input_message_str, session_state=context
        )
        context = prepare_response.get("session_state", context)
        logger.info(f"{worker_tag} Phase 1: PrepareWorkflow 完成")

        # 检测点 1：仅用户消息检测新消息（排除当前正在处理的消息）
        if check_new_message and message_source == "user":
            user = context.get("user", {})
            character = context.get("character", {})
            if is_new_message_coming_in(
                str(user["_id"]), str(character["_id"]), platform, current_message_ids
            ):
                is_rollback = True
                logger.info(f"{worker_tag} rollback: new message before chat")

        if not is_rollback:
            # ========== Phase 2: ChatWorkflow (流式) ==========
            logger.info(f"{worker_tag} Phase 2: ChatWorkflow 开始")

            # ========== 新增：Phase 2 前续期锁 ==========
            if lock_id and conversation_id:
                lock_manager.renew_lock(
                    "conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT
                )
                logger.debug(f"{worker_tag} 锁续期成功 (Phase 2 前)")

            expect_output_timestamp = int(time.time())
            multimodal_responses_index = 0
            all_multimodal_responses = []
            is_lock_lost = False  # 新增：锁丢失标志

            async for event in streaming_chat_workflow.run_stream(
                input_message=input_message_str, session_state=context
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
                        is_first=(multimodal_responses_index == 1),
                    )
                    if outputmessage is not None:
                        resp_messages.append(outputmessage)

                        # ========== 新增：每发送一条消息后续期锁 ==========
                        if lock_id and conversation_id:
                            lock_manager.renew_lock(
                                "conversation",
                                conversation_id,
                                lock_id,
                                timeout=LOCK_TIMEOUT,
                            )

                    # 检测点 2：仅用户消息检测新消息（排除当前正在处理的消息）
                    if check_new_message and message_source == "user":
                        user = context.get("user", {})
                        character = context.get("character", {})
                        if is_new_message_coming_in(
                            str(user["_id"]),
                            str(character["_id"]),
                            platform,
                            current_message_ids,
                        ):
                            is_rollback = True
                            logger.info(
                                f"{worker_tag} rollback: new message during streaming"
                            )
                            break
                elif event["type"] == "done":
                    logger.info(
                        f"{worker_tag} 流式完成，共 {event['data'].get('total_messages', 0)} 条"
                    )
                elif event["type"] == "content_blocked":
                    # ========== 内容安全审核失败，设置标志并停止处理 ==========
                    logger.warning(
                        f"{worker_tag} 内容安全审核失败 (Content Exists Risk)，跳过后续处理"
                    )
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
                    lock_manager.renew_lock(
                        "conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT
                    )
                    logger.debug(f"{worker_tag} 锁续期成功 (Phase 3 前)")

                # ========== V2.8 优化：提醒消息跳过 LLM 调用 ==========
                if message_source == "reminder":
                    # 提醒消息：跳过 LLM 分析，只更新 proactive_times
                    conversation_info = context.get("conversation", {}).get(
                        "conversation_info", {}
                    )
                    future_info = conversation_info.get("future", {})
                    if "future" not in conversation_info:
                        conversation_info["future"] = {}
                        future_info = conversation_info["future"]
                    future_info["proactive_times"] = (
                        future_info.get("proactive_times", 0) + 1
                    )
                    logger.info(
                        f"{worker_tag} Phase 3: 提醒消息，跳过 PostAnalyze LLM，proactive_times={future_info['proactive_times']}"
                    )
                else:
                    # 用户消息/主动消息：后台执行 PostAnalyze（Fire-and-Forget）
                    # E2E 测试时可通过环境变量 SKIP_POST_ANALYZE=1 跳过
                    if os.environ.get("SKIP_POST_ANALYZE") == "1":
                        logger.info(
                            f"{worker_tag} Phase 3: SKIP_POST_ANALYZE=1，跳过 PostAnalyze"
                        )
                    else:
                        context_copy = copy.deepcopy(context)
                        asyncio.create_task(
                            _run_post_analyze_background(
                                context_copy, conversation_id, worker_tag
                            )
                        )
                        logger.info(
                            f"{worker_tag} Phase 3: PostAnalyzeWorkflow 已提交后台执行"
                        )
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
        input_messages = [
            m for m in input_messages if str(m.get("_id", "")) not in current_ids_set
        ]

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
    """
    创建带 worker_id 的消息处理函数（用户消息入口）
    
    重构说明：
   -使用 MessageAcquirer 处理消息获取和锁管理
   -使用 MessageDispatcher 处理消息分发
   -使用 MessageFinalizer 处理后续状态更新
   -复杂度从 50 降低到约 15
    """
    from agent.runner.message_processor import (
        MessageAcquirer,
        MessageDispatcher,
        MessageFinalizer,
    )
    
    worker_tag = f"[W{worker_id}]"
    
    # 初始化处理器组件
    acquirer = MessageAcquirer(worker_tag)
    dispatcher = MessageDispatcher(worker_tag)
    finalizer = MessageFinalizer(worker_tag, max_conversation_round)

    async def _handler():
        # Step 1: 获取消息和锁
        msg_ctx = acquirer.acquire()
        if msg_ctx is None:
            return
        
        try:
            # 准备上下文
            msg_ctx.conversation["conversation_info"]["input_messages"] = msg_ctx.input_messages
            logger.info(f"{worker_tag} 处理 {len(msg_ctx.input_messages)} 条消息")
            
            msg_ctx.context = context_prepare(
                msg_ctx.user, msg_ctx.character, msg_ctx.conversation
            )
            
            # Step 2: 分发消息
            dispatch_type, dispatch_data = dispatcher.dispatch(msg_ctx)
            
            resp_messages = []
            is_rollback = False
            is_content_blocked = False
            
            if dispatch_type == "blocked":
                # 用户被拉黑
                send_message_via_context(
                    msg_ctx.context,
                    message="[系统消息]已拉黑，如需恢复请联系作者YDYK",
                    message_type="text",
                    expect_output_timestamp=int(time.time()),
                )
                finalizer.finalize_success(msg_ctx, [], store_messages_background)
                
            elif dispatch_type == "hardcode":
                # 硬指令
                handle_hardcode(msg_ctx.context, dispatch_data["command"])
                send_message_via_context(
                    msg_ctx.context,
                    message="ok",
                    message_type="text",
                    expect_output_timestamp=int(time.time()),
                )
                finalizer.finalize_hardfinish(msg_ctx)
                
            elif dispatch_type == "hold":
                # 角色繁忙
                finalizer.finalize_hold(msg_ctx)
                
            else:
                # 正常消息处理
                try:
                    input_message_str = msg_ctx.context["conversation"]["conversation_info"]["input_messages_str"]
                    
                    # 锁续期
                    acquirer.renew_lock(msg_ctx)
                    
                    # 提取当前消息ID用于排除新消息检测
                    current_message_ids = [str(m["_id"]) for m in msg_ctx.input_messages]
                    
                    resp_messages, msg_ctx.context, is_rollback, is_content_blocked = (
                        await handle_message(
                            context=msg_ctx.context,
                            input_message_str=input_message_str,
                            message_source="user",
                            check_new_message=True,
                            worker_tag=worker_tag,
                            lock_id=msg_ctx.lock_id,
                            conversation_id=msg_ctx.conversation_id,
                            current_message_ids=current_message_ids,
                        )
                    )
                    
                    # Step 3: 后处理
                    if is_content_blocked:
                        finalizer.finalize_blocked(msg_ctx)
                    elif is_rollback:
                        should_rollback = finalizer.finalize_rollback(msg_ctx, resp_messages)
                        if not should_rollback:
                            # 达到最大 rollback 次数，强制完成
                            finalizer.finalize_success(
                                msg_ctx, resp_messages, store_messages_background
                            )
                    else:
                        finalizer.finalize_success(
                            msg_ctx, resp_messages, store_messages_background
                        )
                        
                except Exception as e:
                    logger.error(f"{worker_tag} Workflow failed: {e}")
                    logger.error(traceback.format_exc())
                    raise
                    
        except Exception as e:
            finalizer.finalize_error(msg_ctx, e)
        finally:
            acquirer.release_lock(msg_ctx, "finish")

    return _handler


# 保持向后兼容
handler = create_handler(0)


# ========== 导出 ==========

__all__ = [
    "handle_message",
    "create_handler",
    "handler",
]
