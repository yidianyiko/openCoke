# -*- coding: utf-8 -*-
"""
Usage Tracker - LLM Token 用量追踪

追踪每次 Agent 调用的 token 用量，用于成本监控和优化。
使用 Agno RunOutput.metrics 中的数据。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from agent.agno_agent.capabilities.usage import UsageCapabilityPort, UsageRecord
from util.log_util import get_logger

logger = get_logger(__name__)


class UsageTracker:
    """
    用量追踪器

    负责记录 Agent 调用 token 用量，并通过 UsageCapabilityPort 持久化。
    """

    def __init__(
        self,
        persist_enabled: bool = True,
        *,
        port: UsageCapabilityPort | None = None,
    ):
        self._persist_enabled = persist_enabled
        self._port = port or UsageCapabilityPort()

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
        """
        if metrics is None:
            logger.debug(f"[UsageTracker] {agent_name} metrics is None, skipping")
            return None

        input_tokens = getattr(metrics, "input_tokens", 0) or 0
        output_tokens = getattr(metrics, "output_tokens", 0) or 0
        total_tokens = getattr(metrics, "total_tokens", 0) or 0
        duration = getattr(metrics, "duration", None)

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

        try:
            self._port.record(record, persist_enabled=self._persist_enabled)
        except Exception as exc:
            logger.warning(f"[UsageTracker] Failed to persist record: {exc}")

        return record


usage_tracker = UsageTracker()
