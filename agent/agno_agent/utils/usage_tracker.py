# -*- coding: utf-8 -*-
"""
Usage Tracker - LLM Token 用量追踪

追踪每次 Agent 调用的 token 用量，用于成本监控和优化。
使用 Agno RunOutput.metrics 中的数据。
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from util.log_util import get_logger

logger = get_logger(__name__)


@dataclass
class UsageRecord:
    """单次调用的用量记录"""

    timestamp: datetime
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration: Optional[float] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    workflow_name: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典，用于 MongoDB 存储"""
        return asdict(self)


class UsageTracker:
    """
    用量追踪器

    负责记录和持久化 Agent 调用的 token 用量。
    """

    def __init__(self, persist_enabled: bool = True):
        """
        初始化用量追踪器

        Args:
            persist_enabled: 是否启用持久化到 MongoDB
        """
        self._persist_enabled = persist_enabled
        self._dao = None

    def _get_dao(self):
        """懒加载 DAO，避免循环导入"""
        if self._dao is None:
            from dao.usage_dao import UsageDAO

            self._dao = UsageDAO()
        return self._dao

    def record_from_metrics(
        self,
        agent_name: str,
        metrics,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
    ) -> Optional[UsageRecord]:
        """
        从 Agno Metrics 对象记录用量

        Args:
            agent_name: Agent 名称
            metrics: Agno RunOutput.metrics 对象
            user_id: 用户 ID
            session_id: 会话 ID
            workflow_name: Workflow 名称

        Returns:
            创建的 UsageRecord，如果 metrics 无效则返回 None
        """
        if metrics is None:
            logger.debug(f"[UsageTracker] {agent_name} metrics is None, skipping")
            return None

        # 从 Agno Metrics 提取数据
        input_tokens = getattr(metrics, "input_tokens", 0) or 0
        output_tokens = getattr(metrics, "output_tokens", 0) or 0
        total_tokens = getattr(metrics, "total_tokens", 0) or 0
        duration = getattr(metrics, "duration", None)

        # 如果没有 token 数据，跳过记录
        if total_tokens == 0:
            logger.debug(f"[UsageTracker] {agent_name} total_tokens=0, skipping record")
            return None

        record = UsageRecord(
            timestamp=datetime.now(),
            agent_name=agent_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            duration=duration,
            user_id=user_id,
            session_id=session_id,
            workflow_name=workflow_name,
        )

        logger.info(
            f"[UsageTracker] {agent_name}: in={input_tokens}, out={output_tokens}, "
            f"total={total_tokens}, duration={duration:.2f}s"
            if duration
            else f"[UsageTracker] {agent_name}: in={input_tokens}, out={output_tokens}, "
            f"total={total_tokens}"
        )

        # 持久化
        if self._persist_enabled:
            try:
                self._get_dao().insert_usage_record(record.to_dict())
            except Exception as e:
                logger.warning(f"[UsageTracker] Failed to persist record: {e}")

        return record


# 全局实例
usage_tracker = UsageTracker()
