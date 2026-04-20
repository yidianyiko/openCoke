# -*- coding: utf-8 -*-
"""
Message Processor-消息处理器模块

从 agent_handler.py 重构抽取，职责单一化.

职责划分：
- MessageAcquirer: 消息获取与锁管理
- MessageDispatcher: 消息分发与预处理
- MessageFinalizer: 后处理与状态更新

Requirements: 重构 create_handler，降低复杂度
"""

import random
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from agent.runner.identity import get_agent_entity_id, resolve_agent_user_context
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
from util.log_util import get_logger
from util.message_log_util import (
    format_std_messages_for_log,
    should_log_message_content,
)
from util.profile_util import resolve_profile_label

logger = get_logger(__name__)

# ========== 配置常量 ==========
MAX_HANDLE_AGE = 3600 * 12  # 只处理12小时以内的消息
MAX_RETRIES = 3  # 最大重试次数
MAX_ROLLBACK = 4  # 最大 rollback 次数
LOCK_TIMEOUT = 180  # 锁超时时间（秒）
# 多平台支持：平台从消息中动态获取（wechat, 等）


class ProcessResult(Enum):
    """处理结果枚举"""

    FINISH = "finish"  # 正常完成
    ROLLBACK = "rollback"  # 需要回滚
    HOLD = "hold"  # 暂时挂起
    HARDFINISH = "hardfinish"  # 硬指令完成
    BLOCKED = "blocked"  # 内容审核失败
    FAILED = "failed"  # 处理失败


@dataclass
class MessageContext:
    """消息处理上下文"""

    user: Optional[Dict] = None
    character: Optional[Dict] = None
    conversation: Optional[Dict] = None
    conversation_id: Optional[str] = None
    lock_id: Optional[str] = None
    input_messages: List[Dict] = field(default_factory=list)
    context: Optional[Dict] = None  # context_prepare 生成的完整上下文

    @property
    def has_lock(self) -> bool:
        return self.lock_id is not None


@dataclass
class ProcessOutput:
    """处理输出"""

    result: ProcessResult
    resp_messages: List[Dict] = field(default_factory=list)
    context: Optional[Dict] = None
    error: Optional[str] = None


class MessageAcquirer:
    """
    消息获取器

    职责：
    1. 获取待处理消息
    2. 验证用户/角色
    3. 获取分布式锁
    """

    def __init__(self, worker_tag: str):
        self.worker_tag = worker_tag
        self.user_dao = UserDAO()
        self.conversation_dao = ConversationDAO()
        self.lock_manager = MongoDBLockManager()

        # 获取目标角色配置
        self.target_user_alias = CONF.get("default_character_alias", "coke")

    def acquire(self) -> Optional[MessageContext]:
        """
        获取一个可处理的消息上下文

        Returns:
            MessageContext 或 None（无可处理消息）
        """
        # 获取目标角色 - 优先按名称查找，支持多平台
        characters = self.user_dao.find_characters({"name": self.target_user_alias})

        if len(characters) == 0:
            logger.debug(f"{self.worker_tag} 未找到目标角色: {self.target_user_alias}")
            return None

        target_user_id = get_agent_entity_id(characters[0])

        # 获取待处理消息
        top_messages = read_top_inputmessages(
            to_user=target_user_id,
            status="pending",
            platform=None,  # None 表示处理所有平台
            limit=16,
            max_handle_age=MAX_HANDLE_AGE,
        )
        if len(top_messages) == 0:
            return None

        # 只在有消息时才输出日志
        # logger.info(
        #     f"{self.worker_tag} 找到 {len(top_messages)} 条待处理消息 (角色: {self.target_user_alias})"
        # )

        # 获取已锁定的会话列表
        locked_conversation_ids = get_locked_conversation_ids()

        # 随机打乱，让不同 worker 从不同消息开始
        random.shuffle(top_messages)

        # 尝试获取一个可处理的消息
        for top_message in top_messages:
            msg_ctx = self._try_acquire_message(top_message, locked_conversation_ids)
            if msg_ctx is not None:
                return msg_ctx

        return None

    def _try_acquire_message(
        self, top_message: Dict, locked_conversation_ids: set
    ) -> Optional[MessageContext]:
        """尝试获取单条消息的处理权"""

        # 检查重试次数
        retry_count = top_message.get("retry_count", 0)
        if retry_count >= MAX_RETRIES:
            logger.warning(
                f"{self.worker_tag} 消息达到最大重试次数({MAX_RETRIES})，标记为 failed: {top_message['_id']}"
            )
            update_message_status_safe(top_message["_id"], "failed", "pending")
            return None

        # 获取用户和角色
        user = resolve_agent_user_context(
            top_message["from_user"], top_message, self.user_dao
        )
        if user is None:
            logger.warning(
                f"{self.worker_tag} 用户ID无效，跳过: {top_message['from_user']}"
            )
            top_message["status"] = "failed"
            top_message["error"] = "invalid_user_id"
            save_inputmessage(top_message)
            return None

        character = self.user_dao.get_user_by_id(top_message["to_user"])
        user_id = get_agent_entity_id(user)
        character_id = get_agent_entity_id(character)

        if character is None or not user_id or not character_id:
            logger.warning(
                f"{self.worker_tag} 用户或角色不存在，跳过: {top_message['from_user']}"
            )
            top_message["status"] = "failed"
            top_message["error"] = "user_not_found"
            save_inputmessage(top_message)
            return None

        # Get platform from the message (support multi-platform)
        platform = top_message.get("platform")
        if not platform:
            logger.error(
                f"{self.worker_tag} 消息缺少 platform 字段: {top_message.get('_id')}"
            )
            top_message["status"] = "failed"
            top_message["error"] = "missing_platform_in_message"
            save_inputmessage(top_message)
            return None

        # 验证 platform 字段
        platform_profiles = self._resolve_platform_profiles(
            user, character, top_message, platform
        )
        if not platform_profiles:
            return None
        user_platform_profile, character_platform_profile = platform_profiles

        # 获取/创建会话（群聊或私聊）
        chatroom_name = top_message.get("chatroom_name")
        if chatroom_name:
            # 群聊消息：使用群聊会话
            conversation_id, _ = self.conversation_dao.get_or_create_group_conversation(
                platform=platform,
                chatroom_name=chatroom_name,
                initial_talkers=[
                    {
                        "id": user_platform_profile["id"],
                        "nickname": user_platform_profile["nickname"],
                        "db_user_id": user_id,
                    },
                    {
                        "id": character_platform_profile["id"],
                        "nickname": character_platform_profile["nickname"],
                        "db_user_id": character_id,
                    },
                ],
            )
        else:
            existing_private_conversation_id = (
                self._find_compatible_clawscale_request_response_private_conversation(
                    platform=platform,
                    user_platform_profile=user_platform_profile,
                    character_platform_profile=character_platform_profile,
                    top_message=top_message,
                )
            )
            if existing_private_conversation_id:
                conversation_id = existing_private_conversation_id
            else:
                # 私聊消息：使用私聊会话
                conversation_id, _ = (
                    self.conversation_dao.get_or_create_private_conversation(
                        platform=platform,
                        user_id1=user_platform_profile["id"],
                        nickname1=user_platform_profile["nickname"],
                        user_id2=character_platform_profile["id"],
                        nickname2=character_platform_profile["nickname"],
                        db_user_id1=user_id,
                        db_user_id2=character_id,
                    )
                )

        # 跳过已锁定的会话
        if conversation_id in locked_conversation_ids:
            return None

        # 尝试获取锁
        lock_id = self.lock_manager.acquire_lock(
            "conversation", conversation_id, timeout=LOCK_TIMEOUT, max_wait=0.1
        )
        if lock_id is None:
            logger.debug(f"{self.worker_tag} 锁获取失败: {conversation_id}")
            return None

        logger.info(
            f"{self.worker_tag} 获取锁成功: {top_message['from_user'][-6:]}, lock_id={lock_id}"
        )

        # 获取会话详情
        conversation = self.conversation_dao.get_conversation_by_id(conversation_id)
        conversation = self._ensure_business_conversation_key(
            conversation_id=conversation_id,
            conversation=conversation,
            top_message=top_message,
        )

        # 读取该会话所有待处理消息
        input_messages = read_all_inputmessages(
            user_id, character_id, platform, "pending"
        )

        if should_log_message_content():
            logger.info(
                f"{self.worker_tag} 待处理消息: conversation_id={conversation_id}, "
                f"platform={platform}, count={len(input_messages)}; "
                f"{format_std_messages_for_log(input_messages)}"
            )

        return MessageContext(
            user=user,
            character=character,
            conversation=conversation,
            conversation_id=conversation_id,
            lock_id=lock_id,
            input_messages=input_messages,
        )

    def _ensure_business_conversation_key(
        self, *, conversation_id: str, conversation: Dict | None, top_message: Dict
    ) -> Dict:
        if not isinstance(conversation, dict):
            return conversation

        metadata = top_message.get("metadata") or {}
        business_protocol = metadata.get("business_protocol")
        if not isinstance(business_protocol, dict):
            business_protocol = {}

        if (
            top_message.get("platform") != "business"
            or metadata.get("source") != "clawscale"
            or business_protocol.get("delivery_mode") != "request_response"
        ):
            return conversation

        existing_key = conversation.get("business_conversation_key")
        if isinstance(existing_key, str) and existing_key.strip():
            conversation.setdefault("conversation_info", {})
            conversation["conversation_info"].setdefault(
                "business_conversation_key", existing_key
            )
            return conversation

        minted_key = f"bc_{conversation_id}"
        self.conversation_dao.update_conversation(
            conversation_id,
            {
                "business_conversation_key": minted_key,
                "conversation_info.business_conversation_key": minted_key,
            },
        )
        conversation["business_conversation_key"] = minted_key
        conversation.setdefault("conversation_info", {})
        conversation["conversation_info"]["business_conversation_key"] = minted_key
        return conversation

    def _resolve_platform_profiles(
        self, user: Dict, character: Dict, top_message: Dict, platform: str
    ) -> Optional[Tuple[Dict, Dict]]:
        """解析用于会话建模的参与者资料，不依赖持久化平台档案。"""
        user_platform_profile = self._build_clawscale_virtual_user_platform(
            user, top_message, platform
        ) or {
            "id": f"{platform}-user:{get_agent_entity_id(user)}",
            "nickname": resolve_profile_label(user, f"user-{get_agent_entity_id(user)[-6:]}"),
        }

        character_platform_profile = self._build_clawscale_virtual_character_platform(
            character, top_message, platform
        ) or {
            "id": f"{platform}-character:{get_agent_entity_id(character)}",
            "nickname": resolve_profile_label(
                character, self.target_user_alias or "character"
            ),
        }

        return user_platform_profile, character_platform_profile

    def _find_compatible_clawscale_request_response_private_conversation(
        self,
        *,
        platform: str,
        user_platform_profile: Dict,
        character_platform_profile: Dict,
        top_message: Dict,
    ) -> Optional[str]:
        metadata = top_message.get("metadata") or {}
        business_protocol = metadata.get("business_protocol")
        if not isinstance(business_protocol, dict):
            business_protocol = {}
        delivery_mode = business_protocol.get("delivery_mode") or metadata.get(
            "delivery_mode"
        )
        if (
            metadata.get("source") != "clawscale"
            or delivery_mode != "request_response"
        ):
            return None

        get_private_conversation = getattr(
            self.conversation_dao, "get_private_conversation", None
        )
        if not callable(get_private_conversation):
            return None

        candidate_user_ids = []
        business_conversation_key = business_protocol.get("business_conversation_key")
        gateway_conversation_id = business_protocol.get("gateway_conversation_id")

        if business_conversation_key:
            candidate_user_ids.append(f"clawscale:{business_conversation_key}")
        if gateway_conversation_id:
            gateway_user_id = f"clawscale:{gateway_conversation_id}"
            if gateway_user_id not in candidate_user_ids:
                candidate_user_ids.append(gateway_user_id)

        for candidate_user_id in candidate_user_ids:
            conversation = get_private_conversation(
                platform,
                candidate_user_id,
                character_platform_profile["id"],
            )
            if conversation:
                return str(conversation["_id"])

        return None

    def _build_clawscale_virtual_user_platform(
        self, user: Dict, top_message: Dict, platform: str
    ) -> Optional[Dict]:
        metadata = top_message.get("metadata") or {}
        business_protocol = metadata.get("business_protocol")
        if not isinstance(business_protocol, dict):
            business_protocol = {}
        delivery_mode = business_protocol.get("delivery_mode") or metadata.get(
            "delivery_mode"
        )
        if (
            metadata.get("source") != "clawscale"
            or delivery_mode != "request_response"
        ):
            return None

        # Prefer the durable business key once it exists, but preserve the
        # gateway conversation id as establishment-time fallback metadata.
        stable_id = (
            business_protocol.get("business_conversation_key")
            or business_protocol.get("gateway_conversation_id")
            or business_protocol.get("causal_inbound_event_id")
        )
        if not stable_id:
            clawscale_meta = metadata.get("clawscale")
            if isinstance(clawscale_meta, dict):
                stable_id = clawscale_meta.get("conversation_id") or clawscale_meta.get(
                    "external_id"
                )
        if not stable_id:
            stable_id = get_agent_entity_id(user)
        if not stable_id:
            return None

        user_id = get_agent_entity_id(user)
        nickname = resolve_profile_label(user, f"user-{user_id[-6:]}")

        logger.info(
            f"{self.worker_tag} 使用 Clawscale 虚拟业务会话身份: user_id={user_id}, conversation_key={stable_id}"
        )
        return {
            "id": f"clawscale:{stable_id}",
            "nickname": nickname,
        }

    def _build_clawscale_virtual_character_platform(
        self, character: Dict, top_message: Dict, platform: str
    ) -> Optional[Dict]:
        metadata = top_message.get("metadata") or {}
        business_protocol = metadata.get("business_protocol")
        if not isinstance(business_protocol, dict):
            business_protocol = {}
        delivery_mode = business_protocol.get("delivery_mode") or metadata.get(
            "delivery_mode"
        )
        if (
            metadata.get("source") != "clawscale"
            or delivery_mode != "request_response"
        ):
            return None

        character_id = get_agent_entity_id(character)
        if not character_id:
            return None

        nickname = resolve_profile_label(
            character, self.target_user_alias or "character"
        )

        logger.info(
            f"{self.worker_tag} 使用 Clawscale 虚拟角色身份: character_id={character_id}"
        )
        return {
            "id": f"clawscale-character:{character_id}",
            "nickname": nickname,
        }

    def release_lock(self, msg_ctx: MessageContext, reason: str = ""):
        """释放锁"""
        if msg_ctx.has_lock:
            released, release_reason = self.lock_manager.release_lock_safe(
                "conversation", msg_ctx.conversation_id, msg_ctx.lock_id
            )
            if not released:
                logger.warning(
                    f"{self.worker_tag} 锁释放异常({reason}): {release_reason}"
                )
            else:
                logger.info(f"{self.worker_tag} 处理完成，释放锁")

    def renew_lock(self, msg_ctx: MessageContext):
        """续期锁"""
        if msg_ctx.has_lock:
            self.lock_manager.renew_lock(
                "conversation",
                msg_ctx.conversation_id,
                msg_ctx.lock_id,
                timeout=LOCK_TIMEOUT,
            )


class MessageDispatcher:
    """
    消息分发器

    职责：
    1. 构建处理上下文
    2. 判断消息类型并分发
    3. 处理特殊情况（拉黑、硬指令、繁忙）
    """

    # 硬指令前缀
    SUPPORTED_HARDCODE = ("/", "\\", "、")

    def __init__(self, worker_tag: str):
        self.worker_tag = worker_tag
        self.admin_user_id = CONF.get("admin_user_id", "")

    def dispatch(self, msg_ctx: MessageContext) -> Tuple[str, Optional[Dict]]:
        """
        分发消息到对应处理器

        Returns:
            (dispatch_type, extra_data)
           -("blocked", None): 用户被拉黑
           -("hardcode", {"command": ...}): 硬指令
           -("hold", None): 角色繁忙
           -("normal", None): 正常消息
        """
        context = msg_ctx.context
        input_messages = msg_ctx.input_messages

        # 检查拉黑
        if context["relation"]["relationship"]["dislike"] >= 100:
            return ("blocked", None)

        # 检查硬指令
        if str(context["user"].get("id") or context["user"].get("_id")) == self.admin_user_id and str(
            input_messages[0]["message"]
        ).startswith(self.SUPPORTED_HARDCODE):
            return ("hardcode", {"command": input_messages[0]["message"]})

        # 检查繁忙状态
        if context["relation"]["character_info"].get("status", "空闲") not in ["空闲"]:
            logger.info(f"{self.worker_tag} hold message as character busy...")
            return ("hold", None)

        return ("normal", None)


class MessageFinalizer:
    """
    消息后处理器

    职责：
    1. 更新消息状态
    2. 保存对话历史
    3. 处理 rollback 逻辑
    """

    def __init__(self, worker_tag: str, max_conversation_round: int = 15):
        self.worker_tag = worker_tag
        self.max_conversation_round = max_conversation_round
        self.conversation_dao = ConversationDAO()
        self.mongo = MongoDBBase()

    def finalize_hold(self, msg_ctx: MessageContext):
        """处理 hold 状态"""
        for input_message in msg_ctx.input_messages:
            set_hold_status(input_message["_id"])

    def finalize_hardfinish(self, msg_ctx: MessageContext):
        """处理硬指令完成"""
        for input_message in msg_ctx.input_messages:
            success = update_message_status_safe(
                input_message["_id"], "handled", "pending"
            )
            if not success:
                logger.warning(
                    f"{self.worker_tag} 乐观锁更新失败(hardfinish): {input_message['_id']}"
                )

    def finalize_blocked(self, msg_ctx: MessageContext):
        """处理内容审核失败"""
        logger.warning(
            f"{self.worker_tag} 内容安全审核失败，标记 {len(msg_ctx.input_messages)} 条消息为 handled"
        )
        for input_message in msg_ctx.input_messages:
            update_message_status_safe(input_message["_id"], "handled", "pending")

    def finalize_rollback(
        self, msg_ctx: MessageContext, resp_messages: List[Dict]
    ) -> bool:
        """
        处理 rollback

        Returns:
            bool: True 表示应该继续 rollback，False 表示强制完成
        """
        max_rollback_count = max(
            msg.get("rollback_count", 0) for msg in msg_ctx.input_messages
        )

        if max_rollback_count >= MAX_ROLLBACK:
            logger.warning(
                f"{self.worker_tag} 达到最大 rollback 次数({MAX_ROLLBACK})，强制完成处理"
            )
            return False  # 强制完成，不再 rollback

        logger.info(
            f"{self.worker_tag} [消息打断] rollback_count={max_rollback_count + 1}/{MAX_ROLLBACK}"
        )

        # 增加 rollback 计数
        for input_message in msg_ctx.input_messages:
            increment_rollback_count(input_message["_id"])

        # 记录已发送的消息到历史
        if resp_messages:
            self._record_partial_messages(msg_ctx, resp_messages)

        return True  # 继续 rollback

    def _record_partial_messages(
        self, msg_ctx: MessageContext, resp_messages: List[Dict]
    ):
        """记录部分已发送的消息"""
        conversation = msg_ctx.context["conversation"]
        chat_history = conversation["conversation_info"]["chat_history"]

        for msg in resp_messages:
            if msg and msg not in chat_history:
                chat_history.append(msg)

        logger.info(
            f"{self.worker_tag} [消息打断] 已记录 {len(resp_messages)} 条已发送消息到对话历史"
        )

        # 记录本轮已发送内容，用于下一轮去重
        sent_contents = [
            msg.get("message", "") for msg in resp_messages if msg.get("message")
        ]
        existing = conversation["conversation_info"].get("turn_sent_contents", [])
        conversation["conversation_info"]["turn_sent_contents"] = (
            existing + sent_contents
        )

        logger.info(f"{self.worker_tag} [去重] 记录已发送内容: {len(sent_contents)} 条")

        self.conversation_dao.update_conversation_info(
            msg_ctx.conversation_id, conversation["conversation_info"]
        )

    def finalize_success(
        self,
        msg_ctx: MessageContext,
        resp_messages: List[Dict],
        store_messages_callback=None,
    ):
        """处理成功完成"""
        context = msg_ctx.context
        conversation = context["conversation"]

        # 将输入消息加入历史
        for input_message in conversation["conversation_info"]["input_messages"]:
            conversation["conversation_info"]["chat_history"].append(input_message)
        conversation["conversation_info"]["input_messages"] = []

        # 将响应消息加入历史
        for resp_message in resp_messages:
            conversation["conversation_info"]["chat_history"].append(resp_message)

        # 限制历史长度
        if (
            len(conversation["conversation_info"]["chat_history"])
            > self.max_conversation_round
        ):
            conversation["conversation_info"]["chat_history"] = conversation[
                "conversation_info"
            ]["chat_history"][-self.max_conversation_round :]

        # 清空去重列表
        if conversation["conversation_info"].get("turn_sent_contents"):
            logger.info(f"{self.worker_tag} [去重] Turn 完成，清空 turn_sent_contents")
            conversation["conversation_info"]["turn_sent_contents"] = []

        # 保存会话信息
        self.conversation_dao.update_conversation_info(
            msg_ctx.conversation_id, conversation["conversation_info"]
        )

        # 后台存储消息用于语义检索
        if store_messages_callback:
            store_messages_callback(context, resp_messages)

        # 更新关系
        relation_update = {k: v for k, v in context["relation"].items() if k != "_id"}
        self.mongo.replace_one(
            "relations",
            query={
                "uid": context["relation"]["uid"],
                "cid": context["relation"]["cid"],
            },
            update=relation_update,
        )

        # 更新消息状态
        for input_message in msg_ctx.input_messages:
            success = update_message_status_safe(
                input_message["_id"], "handled", "pending"
            )
            if not success:
                logger.warning(
                    f"{self.worker_tag} 乐观锁更新失败: {input_message['_id']}"
                )

    def finalize_error(self, msg_ctx: MessageContext, error: Exception):
        """处理错误"""
        logger.error(f"{self.worker_tag} {traceback.format_exc()}")

        for input_message in msg_ctx.input_messages:
            retry_count = input_message.get("retry_count", 0) + 1
            if retry_count < MAX_RETRIES:
                increment_retry_count(input_message["_id"], str(error)[:500])
                logger.info(
                    f"{self.worker_tag} 消息重试计数: {input_message['_id']}, "
                    f"retry_count={retry_count}/{MAX_RETRIES}"
                )
            else:
                update_message_status_safe(input_message["_id"], "failed", "pending")
                logger.warning(
                    f"{self.worker_tag} 消息达到最大重试次数，标记为 failed: {input_message['_id']}"
                )


def consume_stream_batch(
    redis_client,
    mongo: MongoDBBase,
    group: str = "coke-workers",
    stream: str = "coke:input",
    consumer: str = "worker-1",
    count: int = 10,
    block_ms: int = 1000,
):
    entries = redis_client.xreadgroup(
        group, consumer, {stream: ">"}, count=count, block=block_ms
    )
    for _stream, messages in entries:
        for entry_id, data in messages:
            message_id = None
            if isinstance(data, dict):
                message_id = data.get(b"message_id", data.get("message_id"))
            if isinstance(message_id, bytes):
                message_id = message_id.decode()
            if message_id:
                mongo.find_one("inputmessages", {"_id": message_id})
            redis_client.xack(stream, group, entry_id)


def get_queue_mode() -> str:
    return CONF.get("queue_mode", "poll")
