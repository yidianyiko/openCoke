# -*- coding: utf-8 -*-
"""Unit tests for DeferredActionDAO."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from bson import ObjectId


class TestDeferredActionDAO:
    @pytest.mark.unit
    def test_constructor_uses_timezone_aware_mongo_client(self, monkeypatch):
        from dao import deferred_action_dao as dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.return_value = MagicMock()
        mock_client.return_value.__getitem__.return_value = mock_db
        monkeypatch.setattr(dao_module, "MongoClient", mock_client)

        from dao.deferred_action_dao import DeferredActionDAO

        DeferredActionDAO()

        assert mock_client.call_args.kwargs["tz_aware"] is True

    @pytest.fixture
    def mock_collection(self):
        return MagicMock()

    @pytest.fixture
    def deferred_action_dao(self, mock_collection, monkeypatch):
        from dao import deferred_action_dao as dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.return_value = mock_collection
        mock_client.return_value.__getitem__.return_value = mock_db

        monkeypatch.setattr(dao_module, "MongoClient", mock_client)

        from dao.deferred_action_dao import DeferredActionDAO

        dao_instance = DeferredActionDAO()
        dao_instance.collection = mock_collection
        return dao_instance

    @pytest.mark.unit
    def test_collection_name_constant(self, deferred_action_dao):
        assert deferred_action_dao.COLLECTION == "deferred_actions"

    @pytest.mark.unit
    def test_create_indexes_creates_required_indexes(
        self, deferred_action_dao, mock_collection
    ):
        deferred_action_dao.create_indexes()

        calls = [(call.args, call.kwargs) for call in mock_collection.create_index.call_args_list]

        assert (([("lifecycle_state", 1), ("next_run_at", 1)],), {}) in calls
        assert (([("conversation_id", 1), ("kind", 1), ("lifecycle_state", 1)],), {}) in calls
        assert (([("user_id", 1), ("visibility", 1), ("lifecycle_state", 1), ("next_run_at", 1)],), {}) in calls
        assert (
            (
                [
                    ("user_id", 1),
                    ("payload.metadata.import_provider", 1),
                    ("payload.metadata.source_event_id", 1),
                    ("payload.metadata.source_original_start_time", 1),
                ],
            ),
            {},
        ) in calls
        assert (
            ([("conversation_id", 1), ("kind", 1), ("lifecycle_state", 1)],),
            {
                "unique": True,
                "partialFilterExpression": {
                    "kind": "proactive_followup",
                    "lifecycle_state": "active",
                },
            },
        ) in calls

    @pytest.mark.unit
    def test_create_action_returns_inserted_id(self, deferred_action_dao, mock_collection):
        inserted_id = ObjectId()
        mock_collection.insert_one.return_value = MagicMock(inserted_id=inserted_id)
        doc = {
            "conversation_id": "conv_1",
            "user_id": "user_1",
            "character_id": "char_1",
            "kind": "user_reminder",
            "source": "user_explicit",
            "visibility": "visible",
            "lifecycle_state": "active",
            "revision": 1,
            "title": "drink water",
            "payload": {"prompt": "drink water", "metadata": {}},
            "timezone": "Asia/Tokyo",
            "dtstart": datetime.now(timezone.utc),
            "rrule": None,
            "next_run_at": datetime.now(timezone.utc),
            "last_run_at": None,
            "run_count": 0,
            "max_runs": None,
            "expires_at": None,
            "retry_policy": {
                "max_attempts_per_occurrence": 3,
                "base_backoff_seconds": 60,
                "max_backoff_seconds": 900,
            },
            "lease": {"token": None, "leased_at": None, "lease_expires_at": None},
            "last_error": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = deferred_action_dao.create_action(doc)

        assert result == str(inserted_id)
        mock_collection.insert_one.assert_called_once_with(doc)

    @pytest.mark.unit
    def test_get_action_by_id_returns_document(self, deferred_action_dao, mock_collection):
        action_id = ObjectId()
        expected = {"_id": action_id, "title": "stand up"}
        mock_collection.find_one.return_value = expected

        result = deferred_action_dao.get_action(str(action_id))

        assert result == expected
        mock_collection.find_one.assert_called_once_with({"_id": action_id})

    @pytest.mark.unit
    def test_update_action_sets_fields_and_revision(self, deferred_action_dao, mock_collection):
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        action_id = ObjectId()
        now = datetime.now(timezone.utc)

        result = deferred_action_dao.update_action(
            str(action_id),
            {"title": "updated"},
            expected_revision=3,
            now=now,
        )

        assert result is True
        mock_collection.update_one.assert_called_once_with(
            {"_id": action_id, "revision": 3},
            {"$set": {"title": "updated", "updated_at": now}, "$inc": {"revision": 1}},
        )

    @pytest.mark.unit
    def test_claim_action_lease_uses_revision_and_next_run_fence(
        self, deferred_action_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        action_id = ObjectId()
        scheduled_for = datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc)
        lease_until = datetime(2026, 4, 21, 9, 5, tzinfo=timezone.utc)
        leased_at = datetime(2026, 4, 21, 9, 0, 1, tzinfo=timezone.utc)

        result = deferred_action_dao.claim_action_lease(
            str(action_id),
            revision=7,
            scheduled_for=scheduled_for,
            token="lease-1",
            leased_at=leased_at,
            lease_until=lease_until,
        )

        assert result is True
        mock_collection.update_one.assert_called_once_with(
            {
                "_id": action_id,
                "lifecycle_state": "active",
                "revision": 7,
                "next_run_at": scheduled_for,
                "lease.token": None,
            },
            {
                "$set": {
                    "lease.token": "lease-1",
                    "lease.leased_at": leased_at,
                    "lease.lease_expires_at": lease_until,
                }
            },
        )

    @pytest.mark.unit
    def test_release_action_lease_clears_matching_token(
        self, deferred_action_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        action_id = ObjectId()

        result = deferred_action_dao.release_action_lease(str(action_id), token="lease-1")

        assert result is True
        mock_collection.update_one.assert_called_once_with(
            {"_id": action_id, "lease.token": "lease-1"},
            {
                "$set": {
                    "lease.token": None,
                    "lease.leased_at": None,
                    "lease.lease_expires_at": None,
                }
            },
        )

    @pytest.mark.unit
    def test_list_active_actions_sorts_by_next_run_at(self, deferred_action_dao, mock_collection):
        expected = [{"_id": ObjectId()}]
        cursor = MagicMock()
        cursor.sort.return_value = expected
        mock_collection.find.return_value = cursor

        result = deferred_action_dao.list_active_actions()

        assert result == expected
        mock_collection.find.assert_called_once_with({"lifecycle_state": "active"})
        cursor.sort.assert_called_once_with("next_run_at", 1)

    @pytest.mark.unit
    def test_find_imported_reminder_duplicate_uses_import_metadata(
        self, deferred_action_dao, mock_collection
    ):
        expected = {"_id": ObjectId(), "title": "Imported reminder"}
        mock_collection.find_one.return_value = expected

        result = deferred_action_dao.find_imported_reminder_duplicate(
            user_id="ck_1",
            import_provider="google_calendar",
            source_event_id="evt_123",
            source_original_start_time="2026-04-22T09:00:00Z",
        )

        assert result == expected
        mock_collection.find_one.assert_called_once_with(
            {
                "user_id": "ck_1",
                "payload.metadata.import_provider": "google_calendar",
                "payload.metadata.source_event_id": "evt_123",
                "payload.metadata.source_original_start_time": "2026-04-22T09:00:00Z",
            }
        )

    @pytest.mark.unit
    def test_reconcile_expired_leases_clears_expired_active_leases(
        self, deferred_action_dao, mock_collection
    ):
        now = datetime.now(timezone.utc)
        mock_collection.update_many.return_value = MagicMock(modified_count=2)

        result = deferred_action_dao.reconcile_expired_leases(now=now)

        assert result == 2
        mock_collection.update_many.assert_called_once_with(
            {
                "lifecycle_state": "active",
                "lease.token": {"$ne": None},
                "lease.lease_expires_at": {"$lt": now},
            },
            {
                "$set": {
                    "lease.token": None,
                    "lease.leased_at": None,
                    "lease.lease_expires_at": None,
                    "updated_at": now,
                }
            },
        )
