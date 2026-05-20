# -*- coding: utf-8 -*-
"""
Agent runtime lock helpers.
"""

import asyncio
import os
from typing import Optional

from dao.lock import MongoDBLockManager
from util.log_util import get_logger

logger = get_logger(__name__)

LOCK_TIMEOUT = 180  # 锁超时时间（秒）- 增加到 180 秒以覆盖完整处理周期
lock_manager = MongoDBLockManager()


def _agent_runtime_lock_heartbeat_interval_seconds() -> float:
    raw_value = os.environ.get("COKE_AGENT_RUNTIME_LOCK_HEARTBEAT_SECONDS")
    default = min(60.0, max(1.0, LOCK_TIMEOUT / 3))
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning(
            "COKE_AGENT_RUNTIME_LOCK_HEARTBEAT_SECONDS=%r is invalid; using %.1fs",
            raw_value,
            default,
        )
        return default
    return value if value > 0 else default


async def _await_with_agent_runtime_lock_heartbeat(
    awaitable,
    *,
    lock_id: Optional[str],
    conversation_id: Optional[str],
    worker_tag: str,
):
    if not lock_id or not conversation_id:
        return await awaitable

    done = asyncio.Event()

    async def _heartbeat() -> None:
        interval = _agent_runtime_lock_heartbeat_interval_seconds()
        while not done.is_set():
            await asyncio.sleep(interval)
            if done.is_set():
                return
            renewed = lock_manager.renew_lock(
                "conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT
            )
            if renewed:
                logger.debug(f"{worker_tag} 锁续期成功 (single-Agent runtime heartbeat)")
            else:
                logger.warning(f"{worker_tag} single-Agent runtime heartbeat 续期失败")
                return

    heartbeat_task = asyncio.create_task(_heartbeat())
    try:
        return await awaitable
    finally:
        done.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


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


agent_runtime_lock_heartbeat_interval_seconds = (
    _agent_runtime_lock_heartbeat_interval_seconds
)
await_with_agent_runtime_lock_heartbeat = _await_with_agent_runtime_lock_heartbeat
verify_lock_ownership = _verify_lock_ownership
