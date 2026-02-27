# -*- coding: utf-8 -*-
"""Unit tests for UsageDAO and UsageTracker"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestUsageDAO:
    """Tests for UsageDAO class"""

    @pytest.fixture
    def mock_collection(self):
        """Create a mock MongoDB collection"""
        return MagicMock()

    @pytest.fixture
    def usage_dao(self, mock_collection, monkeypatch):
        """Create UsageDAO with mocked collection"""
        from dao import usage_dao as usage_dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.return_value = mock_collection
        mock_client.return_value.__getitem__.return_value = mock_db

        monkeypatch.setattr(usage_dao_module, "MongoClient", mock_client)

        from dao.usage_dao import UsageDAO

        dao_instance = UsageDAO()
        dao_instance.collection = mock_collection
        return dao_instance

    @pytest.mark.unit
    def test_insert_usage_record_returns_inserted_id(self, usage_dao, mock_collection):
        """Should insert record and return inserted ID"""
        from bson import ObjectId

        inserted_id = ObjectId()
        mock_result = MagicMock()
        mock_result.inserted_id = inserted_id
        mock_collection.insert_one.return_value = mock_result

        record = {
            "timestamp": datetime.now(),
            "agent_name": "TestAgent",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

        result = usage_dao.insert_usage_record(record)

        assert result == str(inserted_id)
        mock_collection.insert_one.assert_called_once_with(record)

    @pytest.mark.unit
    def test_get_daily_summary_returns_aggregated_data(
        self, usage_dao, mock_collection
    ):
        """Should return daily summary with aggregated token counts"""
        mock_collection.aggregate.return_value = [
            {
                "_id": "OrchestratorAgent",
                "total_input": 1000,
                "total_output": 500,
                "total_tokens": 1500,
                "count": 10,
                "avg_duration": 1.5,
            },
            {
                "_id": "PostAnalyzeAgent",
                "total_input": 800,
                "total_output": 400,
                "total_tokens": 1200,
                "count": 10,
                "avg_duration": 2.0,
            },
        ]

        result = usage_dao.get_daily_summary()

        assert result["total_tokens"] == 2700
        assert result["total_input_tokens"] == 1800
        assert result["total_output_tokens"] == 900
        assert result["total_calls"] == 20
        assert "OrchestratorAgent" in result["by_agent"]
        assert "PostAnalyzeAgent" in result["by_agent"]

    @pytest.mark.unit
    def test_get_daily_summary_returns_zeros_when_no_data(
        self, usage_dao, mock_collection
    ):
        """Should return zeros when no records exist for the day"""
        mock_collection.aggregate.return_value = []

        result = usage_dao.get_daily_summary()

        assert result["total_tokens"] == 0
        assert result["total_input_tokens"] == 0
        assert result["total_output_tokens"] == 0
        assert result["total_calls"] == 0
        assert result["by_agent"] == {}

    @pytest.mark.unit
    def test_get_user_daily_summary(self, usage_dao, mock_collection):
        """Should return user-specific daily summary"""
        mock_collection.aggregate.return_value = [
            {
                "_id": None,
                "total_input": 500,
                "total_output": 250,
                "total_tokens": 750,
                "count": 5,
            }
        ]

        result = usage_dao.get_user_daily_summary("user_123")

        assert result["user_id"] == "user_123"
        assert result["total_tokens"] == 750
        assert result["total_calls"] == 5

    @pytest.mark.unit
    def test_get_user_daily_summary_returns_zeros_when_no_data(
        self, usage_dao, mock_collection
    ):
        """Should return zeros when user has no records"""
        mock_collection.aggregate.return_value = []

        result = usage_dao.get_user_daily_summary("user_123")

        assert result["user_id"] == "user_123"
        assert result["total_tokens"] == 0
        assert result["total_calls"] == 0

    @pytest.mark.unit
    def test_create_indexes(self, usage_dao, mock_collection):
        """Should create all required indexes"""
        usage_dao.create_indexes()

        assert mock_collection.create_index.call_count == 4


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
