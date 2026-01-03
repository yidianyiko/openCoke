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
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from util.log_util import get_logger

logger = get_logger(__name__)

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


# ========== 配置常量 ==========
MAX_HANDLE_AGE = 3600 * 12  # 只处理12小时以内的消息
MAX_RETRIES = 3  # 最大重试次数
MAX_ROLLBACK = 4  # 最大 rollback 次数
LOCK_TIMEOUT = 180  # 锁超时时间（秒）
PLATFORM = "wechat"


class ProcessResult(Enum):
    """处理结果枚举"""
    FINISH = "finish"           # 正常完成
    ROLLBACK = "rollback"       # 需要回滚
    HOLD = "hold"               # 暂时挂起
    HARDFINISH = "hardfinish"   # 硬指令完成
    BLOCKED = "blocked"         # 内容审核失败
    FAILED = "failed"           # 处理失败


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
        _characters_conf = (
            CONF.get("characters") or (CONF.get("aliyun") or {}).get("characters") or {}
        )
        self.target_wechat_id = _characters_conf.get(self.target_user_alias)
    
    def acquire(self) -> Optional[MessageContext]:
        """
        获取一个可处理的消息上下文
        
        Returns:
            MessageContext 或 None（无可处理消息）
        """
        if self.target_wechat_id is None:
            return None
        
        # 获取目标角色
        characters = self.user_dao.find_characters(
            {"platforms.wechat.id": self.target_wechat_id}
        )
        if len(characters) == 0:
            return None
        
        target_user_id = str(characters[0]["_id"])
        
        # 获取待处理消息
        top_messages = read_top_inputmessages(
            to_user=target_user_id,
            status="pending",
            platform=PLATFORM,
            limit=16,
            max_handle_age=MAX_HANDLE_AGE,
        )
        if len(top_messages) == 0:
            return None
        
        # 获取已锁定的会话列表
        locked_conversation_ids = get_locked_conversation_ids()
        
        # 随机打乱，让不同 worker 从不同消息开始
        random.shuffle(top_messages)
        
        # 尝试获取一个可处理的消息
        for top_message in top_messages:
            msg_ctx = self._try_acquire_message(
                top_message, locked_conversation_ids
            )
            if msg_ctx is not None:
                return msg_ctx
        
        return None
    
    def _try_acquire_message(
        self, 
        top_message: Dict, 
        locked_conversation_ids: set
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
        user = self.user_dao.get_user_by_id(top_message["from_user"])
        character = self.user_dao.get_user_by_id(top_message["to_user"])
        
        if user is None or character is None:
            logger.warning(
                f"{self.worker_tag} 用户或角色不存在，跳过: {top_message['from_user']}"
            )
            top_message["status"] = "failed"
            top_message["error"] = "user_not_found"
            save_inputmessage(top_message)
            return None
        
        # 验证 platform 字段
        if not self._validate_platform(user, character, top_message):
            return None
        
        # 获取/创建会话
        conversation_id, _ = self.conversation_dao.get_or_create_private_conversation(
            platform=PLATFORM,
            user_id1=user["platforms"][PLATFORM]["id"],
            nickname1=user["platforms"][PLATFORM]["nickname"],
            user_id2=character["platforms"][PLATFORM]["id"],
            nickname2=character["platforms"][PLATFORM]["nickname"],
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
        
        # 读取该会话所有待处理消息
        input_messages = read_all_inputmessages(
            str(user["_id"]), str(character["_id"]), PLATFORM, "pending"
        )
        
        return MessageContext(
            user=user,
            character=character,
            conversation=conversation,
            conversation_id=conversation_id,
            lock_id=lock_id,
            input_messages=input_messages,
        )
    
    def _validate_platform(
        self, user: Dict, character: Dict, top_message: Dict
    ) -> bool:
        """验证 platform 字段"""
        if PLATFORM not in user.get("platforms", {}):
            logger.error(
                f"{self.worker_tag} 用户缺少 platforms.{PLATFORM} 字段: {user.get('_id')}"
            )
            top_message["status"] = "failed"
            top_message["error"] = "missing_platform"
            save_inputmessage(top_message)
            return False
        
        if PLATFORM not in character.get("platforms", {}):
            logger.error(
                f"{self.worker_tag} 角色缺少 platforms.{PLATFORM} 字段: {character.get('_id')}"
            )
            top_message["status"] = "failed"
            top_message["error"] = "missing_platform"
            save_inputmessage(top_message)
            return False
        
        return True
    
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
                "conversation", msg_ctx.conversation_id, 
                msg_ctx.lock_id, timeout=LOCK_TIMEOUT
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
    
    def dispatch(
        self, 
        msg_ctx: MessageContext
    ) -> Tuple[str, Optional[Dict]]:
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
        if (str(context["user"]["_id"]) == self.admin_user_id and 
            str(input_messages[0]["message"]).startswith(self.SUPPORTED_HARDCODE)):
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
        self, 
        msg_ctx: MessageContext, 
        resp_messages: List[Dict]
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
        self, 
        msg_ctx: MessageContext, 
        resp_messages: List[Dict]
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
        conversation["conversation_info"]["turn_sent_contents"] = existing + sent_contents
        
        logger.info(
            f"{self.worker_tag} [去重] 记录已发送内容: {len(sent_contents)} 条"
        )
        
        self.conversation_dao.update_conversation_info(
            msg_ctx.conversation_id, conversation["conversation_info"]
        )
    
    def finalize_success(
        self, 
        msg_ctx: MessageContext, 
        resp_messages: List[Dict],
        store_messages_callback=None
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
        if len(conversation["conversation_info"]["chat_history"]) > self.max_conversation_round:
            conversation["conversation_info"]["chat_history"] = (
                conversation["conversation_info"]["chat_history"][-self.max_conversation_round:]
            )
        
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
        relation_update = {
            k: v for k, v in context["relation"].items() if k != "_id"
        }
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
    
    def finalize_error(
        self, 
        msg_ctx: MessageContext, 
        error: Exception
    ):
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
