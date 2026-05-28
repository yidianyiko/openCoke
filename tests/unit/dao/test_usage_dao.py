# -*- coding: utf-8 -*-
"""Unit tests for non-persistent usage tracking."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest


class TestUsageTracker:
    """Tests for UsageTracker class"""

    @pytest.fixture
    def mock_metrics(self):
        """Create a mock Agno metrics object"""
        metrics = MagicMock()
        metrics.input_tokens = 100
        metrics.output_tokens = 50
        metrics.total_tokens = 150
        metrics.duration = 1.5
        return metrics

    @pytest.mark.unit
    def test_record_from_metrics_creates_record(self, mock_metrics):
        """Should create UsageRecord from Agno metrics"""
        from agent.agno_agent.utils.usage_tracker import UsageTracker

        tracker = UsageTracker(persist_enabled=False)

        record = tracker.record_from_metrics(
            agent_name="TestAgent",
            metrics=mock_metrics,
            user_id="user_123",
            session_id="session_456",
        )

        assert record is not None
        assert record.agent_name == "TestAgent"
        assert record.input_tokens == 100
        assert record.output_tokens == 50
        assert record.total_tokens == 150
        assert record.duration == 1.5
        assert record.user_id == "user_123"
        assert record.session_id == "session_456"

    @pytest.mark.unit
    def test_record_from_metrics_returns_none_for_none_metrics(self):
        """Should return None when metrics is None"""
        from agent.agno_agent.utils.usage_tracker import UsageTracker

        tracker = UsageTracker(persist_enabled=False)

        record = tracker.record_from_metrics(
            agent_name="TestAgent",
            metrics=None,
        )

        assert record is None

    @pytest.mark.unit
    def test_record_from_metrics_skips_zero_tokens(self, mock_metrics):
        """Should return None when total_tokens is 0"""
        from agent.agno_agent.utils.usage_tracker import UsageTracker

        mock_metrics.total_tokens = 0
        tracker = UsageTracker(persist_enabled=False)

        record = tracker.record_from_metrics(
            agent_name="TestAgent",
            metrics=mock_metrics,
        )

        assert record is None

    @pytest.mark.unit
    def test_usage_record_to_dict(self):
        """Should convert UsageRecord to dict"""
        from agent.agno_agent.utils.usage_tracker import UsageRecord

        now = datetime.now()
        record = UsageRecord(
            timestamp=now,
            agent_name="TestAgent",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            duration=1.5,
            user_id="user_123",
            session_id="session_456",
            workflow_name="TestWorkflow",
        )

        result = record.to_dict()

        assert result["timestamp"] == now
        assert result["agent_name"] == "TestAgent"
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["total_tokens"] == 150
        assert result["duration"] == 1.5
        assert result["user_id"] == "user_123"
        assert result["session_id"] == "session_456"
        assert result["workflow_name"] == "TestWorkflow"

    @pytest.mark.unit
    def test_persist_enabled_records_without_mongo_dependency(self, mock_metrics):
        """Should keep recording metrics without importing the removed Mongo DAO."""
        from agent.agno_agent.utils.usage_tracker import UsageTracker

        tracker = UsageTracker(persist_enabled=True)

        record = tracker.record_from_metrics(
            agent_name="PostAnalyzeAgent",
            metrics=mock_metrics,
            user_id="user_123",
            session_id="session_456",
            workflow_name="post_analyze",
        )

        assert record is not None
        assert record.agent_name == "PostAnalyzeAgent"
        assert record.total_tokens == 150

    @pytest.mark.unit
    def test_usage_capability_marks_persist_as_non_durable(self):
        """Should acknowledge persist requests without a durable write side effect."""
        from agent.agno_agent.capabilities.usage import (
            UsageCapabilityPort,
            UsageRecord,
        )

        record = UsageRecord(
            timestamp=datetime.now(),
            agent_name="TestAgent",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )

        result = UsageCapabilityPort().run(
            input_message="",
            run_context=None,
            args={"record": record, "persist_enabled": True},
        )

        assert result.ok is True
        assert result.content["record"]["total_tokens"] == 15
        assert result.content["persist_enabled"] is True
        assert result.metadata["durable_write"] is False
