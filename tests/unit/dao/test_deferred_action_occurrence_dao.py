# -*- coding: utf-8 -*-
"""Unit tests for DeferredActionOccurrenceDAO."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from bson import ObjectId


class TestDeferredActionOccurrenceDAO:
    @pytest.fixture
    def mock_collection(self):
        return MagicMock()

    @pytest.fixture
    def occurrence_dao(self, mock_collection, monkeypatch):
        from dao import deferred_action_occurrence_dao as dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.return_value = mock_collection
        mock_client.return_value.__getitem__.return_value = mock_db

        monkeypatch.setattr(dao_module, "MongoClient", mock_client)

        from dao.deferred_action_occurrence_dao import DeferredActionOccurrenceDAO

        dao_instance = DeferredActionOccurrenceDAO()
        dao_instance.collection = mock_collection
        return dao_instance

    @pytest.mark.unit
    def test_collection_name_constant(self, occurrence_dao):
        assert occurrence_dao.COLLECTION == "deferred_action_occurrences"

    @pytest.mark.unit
    def test_create_indexes_creates_unique_trigger_key(self, occurrence_dao, mock_collection):
        occurrence_dao.create_indexes()

        calls = [(call.args, call.kwargs) for call in mock_collection.create_index.call_args_list]
        assert (("trigger_key",), {"unique": True}) in calls
        assert (([("action_id", 1), ("scheduled_for", 1)],), {}) in calls

    @pytest.mark.unit
    def test_claim_or_get_occurrence_inserts_new_occurrence(self, occurrence_dao, mock_collection):
        inserted_id = ObjectId()
        mock_collection.find_one_and_update.return_value = {
            "_id": inserted_id,
            "trigger_key": "action:1:time",
            "status": "claimed",
            "attempt_count": 1,
        }
        scheduled_for = datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc)
        started_at = datetime(2026, 4, 21, 9, 0, 1, tzinfo=timezone.utc)

        result = occurrence_dao.claim_or_get_occurrence(
            action_id="action_1",
            trigger_key="action:1:time",
            scheduled_for=scheduled_for,
            started_at=started_at,
        )

        assert result["status"] == "claimed"
        mock_collection.find_one_and_update.assert_called_once()

    @pytest.mark.unit
    def test_increment_attempt_count_updates_existing_occurrence(
        self, occurrence_dao, mock_collection
    ):
        started_at = datetime(2026, 4, 21, 9, 0, 2, tzinfo=timezone.utc)

        occurrence_dao.increment_attempt_count("action:1:time", started_at=started_at)

        mock_collection.update_one.assert_called_once_with(
            {"trigger_key": "action:1:time"},
            {
                "$inc": {"attempt_count": 1},
                "$set": {"status": "claimed", "last_started_at": started_at},
            },
        )

    @pytest.mark.unit
    def test_mark_occurrence_succeeded_sets_terminal_fields(
        self, occurrence_dao, mock_collection
    ):
        finished_at = datetime(2026, 4, 21, 9, 0, 5, tzinfo=timezone.utc)

        occurrence_dao.mark_occurrence_succeeded("action:1:time", finished_at=finished_at)

        mock_collection.update_one.assert_called_once_with(
            {"trigger_key": "action:1:time"},
            {
                "$set": {
                    "status": "succeeded",
                    "last_finished_at": finished_at,
                    "last_error": None,
                }
            },
        )

    @pytest.mark.unit
    def test_mark_occurrence_failed_sets_error_fields(self, occurrence_dao, mock_collection):
        finished_at = datetime(2026, 4, 21, 9, 0, 5, tzinfo=timezone.utc)

        occurrence_dao.mark_occurrence_failed(
            "action:1:time",
            error="network failed",
            finished_at=finished_at,
        )

        mock_collection.update_one.assert_called_once_with(
            {"trigger_key": "action:1:time"},
            {
                "$set": {
                    "status": "failed",
                    "last_finished_at": finished_at,
                    "last_error": "network failed",
                }
            },
        )
