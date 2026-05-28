# -*- coding: utf-8 -*-
"""
Agent Message Handler-Agno Version

消息处理主模块，使用 single-Agent runtime.

执行流程：
- single-Agent runtime handles semantic planning and capability dispatch
- post-analyze runs in the background when the runtime result requests it

V2.4 更新：
- 抽取核心处理逻辑为 handle_message() 函数
- 支持系统消息（提醒、主动消息）复用完整 Workflow 流程
- 通过 message_source 参数区分消息来源
"""

import asyncio
import os
import re
import sys

sys.path.append(".")
import copy
import time
import traceback
from datetime import UTC, datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from util.log_util import get_logger

logger = get_logger(__name__)

from agent.runner import message_history, output_delivery, runtime_lock
from agent.agno_agent.runtime.post_analyze import run_post_analyze
from agent.agno_agent.runtime.session import initialize_agent_session_db
from agent.runner.context import context_prepare
from conf.config import CONF
from dao.conversation_dao import ConversationDAO
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.message_log_util import (
    preview_text,
    should_log_full_message_content,
    should_log_message_content,
)

# ========== 配置 ==========
max_handle_age = 3600 * 12  # 只处理12小时以内的消息
HOLD_TIMEOUT = 3600  # hold 超时时间（1小时）
target_user_alias = CONF.get("default_character_alias", "coke")
# V2.7 优化：减少历史对话保留轮数，从 20 降低到 15，减少 token 消耗
max_conversation_round = 15


def _agent_runtime_should_skip_post_analyze() -> bool:
    raw_value = (
        os.environ.get("COKE_AGENT_RUNTIME_SKIP_POST_ANALYZE")
        or os.environ.get("SKIP_POST_ANALYZE")
        or ""
    )
    return raw_value.lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _run_agent_runtime_event(
    *,
    agent_input,
    context: dict,
    message_source: str,
    metadata: Optional[Dict[str, Any]],
):
    from agent.agno_agent.runtime.event_adapter import run_agent_runtime_event

    return await run_agent_runtime_event(
        agent_input=agent_input,
        context=context,
        message_source=message_source,
        metadata=metadata,
    )


# ========== DAO 实例 ==========
conversation_dao = ConversationDAO()
user_dao = UserDAO()
mongo = MongoDBBase()
initialize_agent_session_db()


async def _run_post_analyze_background(
    context: dict,
    conversation_id: str,
    worker_tag: str,
) -> None:
    """
    后台执行 post-analyze（Fire-and-Forget 模式）

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
        logger.info(f"{worker_tag} [BG] PostAnalyze 开始")
        await run_post_analyze(session_state=context)

        # 更新 relation 到数据库
        relation = context.get("relation", {})
        if relation.get("uid") and relation.get("cid"):
            relation_update = {k: v for k, v in relation.items() if k != "_id"}
            mongo.replace_one(
                "relations",
                query={"uid": relation["uid"], "cid": relation["cid"]},
                update=relation_update,
            )

        logger.info(f"{worker_tag} [BG] PostAnalyze 完成")

    except Exception as e:
        logger.warning(f"{worker_tag} [BG] PostAnalyze 失败: {e}")


def _latest_input_message_timestamp(context: dict) -> int | None:
    input_messages = (
        context.get("conversation", {})
        .get("conversation_info", {})
        .get("input_messages", [])
    )
    timestamps = []
    for message in input_messages if isinstance(input_messages, list) else []:
        try:
            timestamp = int(message.get("input_timestamp", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if timestamp > 0:
            timestamps.append(timestamp)
    return max(timestamps) if timestamps else None


def _derive_agent_runtime_user_turn_occurred_at(context: dict) -> datetime:
    wall_now = datetime.now(UTC)
    timestamp = _latest_input_message_timestamp(context)
    if timestamp is None:
        return wall_now
    try:
        message_time = datetime.fromtimestamp(timestamp, UTC)
    except (OverflowError, OSError, ValueError):
        return wall_now
    return max(wall_now, message_time)


def _extract_user_turn_runtime_metadata(input_messages: List[Dict]) -> Dict[str, Any]:
    for message in reversed(input_messages or []):
        metadata = message.get("metadata") if isinstance(message, Mapping) else None
        if not isinstance(metadata, Mapping):
            continue
        runtime_metadata: Dict[str, Any] = {}
        source_eval = metadata.get("source_eval")
        trace_config = metadata.get("agent_turn_trace")
        if isinstance(source_eval, str) and source_eval.strip():
            runtime_metadata["source_eval"] = source_eval.strip()
        if isinstance(trace_config, Mapping):
            suite = trace_config.get("suite")
            run_id = trace_config.get("run_id")
            if (
                isinstance(suite, str)
                and suite.strip()
                and isinstance(run_id, str)
                and run_id.strip()
            ):
                runtime_metadata["agent_turn_trace"] = {
                    "suite": suite.strip(),
                    "run_id": run_id.strip(),
                }
        product_notification = metadata.get("product_notification")
        if isinstance(product_notification, Mapping):
            runtime_metadata["product_notification"] = dict(product_notification)
            message_type = metadata.get("message_type")
            business_protocol = metadata.get("business_protocol")
            if not isinstance(message_type, str) and isinstance(
                business_protocol, Mapping
            ):
                message_type = business_protocol.get("message_type")
            if isinstance(message_type, str) and message_type.strip():
                runtime_metadata["message_type"] = message_type.strip()
            message_text = message.get("message")
            if isinstance(message_text, str) and message_text.strip():
                runtime_metadata["product_notification_input_text"] = (
                    message_text.strip()
                )
        if runtime_metadata:
            return runtime_metadata
    return {}


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
) -> Tuple[list[dict], dict, bool]:
    """
    核心消息处理逻辑-Phase 1 → 2 → 3

    统一处理用户消息和系统消息（提醒、主动消息），复用完整的 Workflow 流程.

    Args:
        context: 已构建好的上下文（由 context_prepare 生成）
        input_message_str: 输入消息字符串
        message_source: 消息来源
           -"user": 用户消息（默认）
           -"reminder": 统一提醒触发
        metadata: 额外元数据（如 reminder_id、proactive_times 等）
        check_new_message: 是否检测新消息（系统消息通常设为 False）
        worker_tag: 日志标签
        lock_id: 锁ID（用于续期）
        conversation_id: 会话ID（用于续期）
        current_message_ids: 当前正在处理的消息ID列表（用于排除新消息检测）

    Returns:
        Tuple[resp_messages, context, is_content_blocked]:
           -resp_messages: 发送的消息列表
           -context: 更新后的上下文
           -is_content_blocked: 是否因内容安全审核失败
    """
    # 标记消息来源，供 Workflow 识别
    context["message_source"] = message_source
    context["system_message_metadata"] = metadata or {}
    context["conversation"]["conversation_info"][
        "input_messages_str"
    ] = input_message_str

    if should_log_message_content():
        max_chars = 0 if should_log_full_message_content() else None
        logger.info(
            f"{worker_tag} 输入消息聚合 (source={message_source}): "
            f"{preview_text(input_message_str, max_chars=max_chars)}"
        )

    # 将 proactive_times 放到顶层，供模板使用
    context["proactive_times"] = (metadata or {}).get("proactive_times", 0)

    # 将锁信息放入 context，供 runtime 能力执行时续期使用。
    if lock_id:
        context["lock_id"] = lock_id
    if conversation_id:
        context["conversation_id"] = conversation_id

    # 提取最近的对话历史（精简版），用于主动消息/提醒消息场景
    conversation = context.get("conversation", {})
    recent_chat_history = message_history.extract_recent_chat_history(
        conversation.get("conversation_info", {}).get("chat_history", []),
        limit=6,  # 最近6条消息，约3轮对话
    )
    context["recent_chat_history"] = recent_chat_history

    resp_messages = []
    is_content_blocked = False  # 内容安全审核失败标志

    try:
        if lock_id and conversation_id:
            runtime_lock.lock_manager.renew_lock(
                "conversation",
                conversation_id,
                lock_id,
                timeout=runtime_lock.LOCK_TIMEOUT,
            )
            logger.debug(f"{worker_tag} 锁续期成功 (single-Agent runtime 前)")

        logger.info(f"{worker_tag} AgentRuntime 开始")
        from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload

        selected_conversation_id = str(
            context.get("conversation", {}).get("_id")
            or context.get("conversation", {}).get("id")
            or conversation_id
            or ""
        )
        agent_input = AgentInput(
            input_type="user.turn",
            conversation_id=selected_conversation_id,
            text=input_message_str,
            payload=UserTurnPayload(
                current_message_ids=tuple(current_message_ids or ()),
                check_new_message=check_new_message,
                metadata=metadata or {},
            ),
            occurred_at=_derive_agent_runtime_user_turn_occurred_at(context),
            metadata={"message_source": message_source, "worker_tag": worker_tag},
        )
        result = await runtime_lock.await_with_agent_runtime_lock_heartbeat(
            _run_agent_runtime_event(
                agent_input=agent_input,
                context=context,
                message_source=message_source,
                metadata=metadata,
            ),
            lock_id=lock_id,
            conversation_id=conversation_id,
            worker_tag=worker_tag,
        )

        expect_output_timestamp = int(time.time())
        all_multimodal_responses = []

        if (
            lock_id
            and conversation_id
            and not runtime_lock.verify_lock_ownership(conversation_id, lock_id)
        ):
            logger.warning(f"{worker_tag} 锁已丢失，停止接受 single-Agent runtime 结果")
            context["MultiModalResponses"] = all_multimodal_responses
            return resp_messages, context, False

        for visible_message in result.visible_messages:
            multimodal_response = {
                "type": visible_message.message_type,
                "content": visible_message.content,
                "metadata": dict(visible_message.metadata),
            }

            if lock_id and conversation_id:
                if not runtime_lock.verify_lock_ownership(conversation_id, lock_id):
                    logger.warning(f"{worker_tag} 锁已丢失，停止发送 runtime 消息")
                    context["MultiModalResponses"] = all_multimodal_responses
                    return resp_messages, context, False

            outputmessage, expect_output_timestamp = (
                output_delivery.send_single_message(
                    context=context,
                    multimodal_response=multimodal_response,
                    expect_output_timestamp=expect_output_timestamp,
                    is_first=(len(all_multimodal_responses) == 0),
                )
            )
            if outputmessage is not None:
                all_multimodal_responses.append(multimodal_response)
                resp_messages.append(outputmessage)

        context["MultiModalResponses"] = all_multimodal_responses
        if (
            result.post_analyze_input is not None
            and not _agent_runtime_should_skip_post_analyze()
        ):
            post_context = copy.deepcopy(context)
            post_conversation_id = str(
                post_context.get("conversation", {}).get("_id") or conversation_id or ""
            )
            asyncio.create_task(
                _run_post_analyze_background(
                    post_context,
                    post_conversation_id,
                    worker_tag,
                )
            )
            logger.info(f"{worker_tag} AgentRuntime PostAnalyze 已提交后台执行")
        elif result.post_analyze_input is not None:
            logger.info(f"{worker_tag} AgentRuntime PostAnalyze 已跳过")
        is_content_blocked = False
        logger.info(
            f"{worker_tag} AgentRuntime 完成 "
            f"(visible_messages={len(result.visible_messages)}, "
            f"status={result.output_disposition.status})"
        )
        return resp_messages, context, is_content_blocked

    except Exception as e:
        logger.error(f"{worker_tag} handle_message failed: {e}")
        logger.error(traceback.format_exc())
        raise


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
            msg_ctx.conversation["conversation_info"][
                "input_messages"
            ] = msg_ctx.input_messages
            logger.info(f"{worker_tag} 处理 {len(msg_ctx.input_messages)} 条消息")

            msg_ctx.context = context_prepare(
                msg_ctx.user, msg_ctx.character, msg_ctx.conversation
            )

            # Step 2: 分发消息
            dispatch_type, _ = dispatcher.dispatch(msg_ctx)

            resp_messages = []
            is_content_blocked = False

            if dispatch_type == "hold":
                # 角色繁忙
                finalizer.finalize_hold(msg_ctx)

            else:
                # 正常消息处理
                try:
                    input_message_str = msg_ctx.context["conversation"][
                        "conversation_info"
                    ]["input_messages_str"]

                    # 锁续期
                    acquirer.renew_lock(msg_ctx)

                    # 提取当前消息ID用于排除新消息检测
                    current_message_ids = [
                        str(m["_id"]) for m in msg_ctx.input_messages
                    ]

                    resp_messages, msg_ctx.context, is_content_blocked = (
                        await handle_message(
                            context=msg_ctx.context,
                            input_message_str=input_message_str,
                            message_source="user",
                            metadata=_extract_user_turn_runtime_metadata(
                                msg_ctx.input_messages
                            ),
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
                    else:
                        finalizer.finalize_success(
                            msg_ctx,
                            resp_messages,
                            message_history.store_messages_background,
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
