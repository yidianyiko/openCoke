# -*- coding: utf-8 -*-
"""Unit tests for ReminderDAO."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from bson import ObjectId


class TestReminderDAO:
    @pytest.mark.unit
    def test_constructor_uses_timezone_aware_mongo_client(self, monkeypatch):
        from dao import reminder_dao as dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.return_value = MagicMock()
        mock_client.return_value.__getitem__.return_value = mock_db
        monkeypatch.setattr(dao_module, "MongoClient", mock_client)

        from dao.reminder_dao import ReminderDAO

        ReminderDAO()

        assert mock_client.call_args.kwargs["tz_aware"] is True

    @pytest.fixture
    def mock_collection(self):
        return MagicMock()

    @pytest.fixture
    def reminder_dao(self, mock_collection, monkeypatch):
        from dao import reminder_dao as dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.return_value = mock_collection
        mock_client.return_value.__getitem__.return_value = mock_db
        monkeypatch.setattr(dao_module, "MongoClient", mock_client)

        from dao.reminder_dao import ReminderDAO

        dao_instance = ReminderDAO()
        dao_instance.collection = mock_collection
        return dao_instance

    @pytest.mark.unit
    def test_collection_name_constant(self, reminder_dao):
        assert reminder_dao.COLLECTION == "reminders"

    @pytest.mark.unit
    def test_create_indexes_creates_required_indexes(
        self, reminder_dao, mock_collection
    ):
        reminder_dao.create_indexes()

        calls = [
            (call.args, call.kwargs)
            for call in mock_collection.create_index.call_args_list
        ]

        assert (
            ([("owner_user_id", 1), ("lifecycle_state", 1), ("created_at", 1)],),
            {},
        ) in calls
        assert (([("lifecycle_state", 1), ("next_fire_at", 1)],), {}) in calls

    @pytest.mark.unit
    def test_insert_reminder_returns_inserted_id(self, reminder_dao, mock_collection):
        inserted_id = ObjectId()
        mock_collection.insert_one.return_value = MagicMock(inserted_id=inserted_id)
        document = {
            "owner_user_id": "user_1",
            "lifecycle_state": "active",
            "title": "drink water",
            "next_fire_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = reminder_dao.insert_reminder(document)

        assert result == str(inserted_id)
        mock_collection.insert_one.assert_called_once_with(document)

    @pytest.mark.unit
    def test_get_reminder_loads_by_id(self, reminder_dao, mock_collection):
        reminder_id = ObjectId()
        expected = {"_id": reminder_id, "title": "stand up"}
        mock_collection.find_one.return_value = expected

        result = reminder_dao.get_reminder(str(reminder_id))

        assert result == expected
        mock_collection.find_one.assert_called_once_with({"_id": reminder_id})

    @pytest.mark.unit
    def test_get_reminder_for_owner_includes_owner_user_id(
        self, reminder_dao, mock_collection
    ):
        reminder_id = ObjectId()
        expected = {"_id": reminder_id, "owner_user_id": "user_1"}
        mock_collection.find_one.return_value = expected

        result = reminder_dao.get_reminder_for_owner(str(reminder_id), "user_1")

        assert result == expected
        mock_collection.find_one.assert_called_once_with(
            {"_id": reminder_id, "owner_user_id": "user_1"}
        )

    @pytest.mark.unit
    def test_list_for_owner_filters_by_owner_and_lifecycle_states(
        self, reminder_dao, mock_collection
    ):
        expected = [{"_id": ObjectId(), "owner_user_id": "user_1"}]
        mock_collection.find.return_value = expected

        result = reminder_dao.list_for_owner(
            "user_1", lifecycle_states=["active", "paused"]
        )

        assert result == expected
        mock_collection.find.assert_called_once_with(
            {
                "owner_user_id": "user_1",
                "lifecycle_state": {"$in": ["active", "paused"]},
            }
        )

    @pytest.mark.unit
    def test_list_for_owner_all_states_when_lifecycle_states_omitted(
        self, reminder_dao, mock_collection
    ):
        expected = [{"_id": ObjectId(), "owner_user_id": "user_1"}]
        mock_collection.find.return_value = expected

        result = reminder_dao.list_for_owner("user_1")

        assert result == expected
        mock_collection.find.assert_called_once_with({"owner_user_id": "user_1"})

    @pytest.mark.unit
    def test_list_due_active_filters_active_reminders_with_next_fire_at(
        self, reminder_dao, mock_collection
    ):
        expected = [{"_id": ObjectId(), "lifecycle_state": "active"}]
        cursor = MagicMock()
        cursor.sort.return_value = expected
        mock_collection.find.return_value = cursor

        result = reminder_dao.list_due_active()

        assert result == expected
        mock_collection.find.assert_called_once_with(
            {
                "lifecycle_state": "active",
                "next_fire_at": {"$ne": None, "$exists": True},
            }
        )
        cursor.sort.assert_called_once_with("next_fire_at", 1)

    @pytest.mark.unit
    def test_replace_reminder_filters_by_id_and_owner(
        self, reminder_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(matched_count=1)
        reminder_id = ObjectId()
        updates = {"title": "updated"}

        result = reminder_dao.replace_reminder(str(reminder_id), "user_1", updates)

        assert result is True
        mock_collection.update_one.assert_called_once_with(
            {"_id": reminder_id, "owner_user_id": "user_1"},
            {"$set": updates},
        )

    @pytest.mark.unit
    def test_replace_reminder_can_filter_by_lifecycle_state(
        self, reminder_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(matched_count=1)
        reminder_id = ObjectId()
        updates = {"title": "updated"}

        result = reminder_dao.replace_reminder(
            str(reminder_id),
            "user_1",
            updates,
            lifecycle_state="active",
        )

        assert result is True
        mock_collection.update_one.assert_called_once_with(
            {
                "_id": reminder_id,
                "owner_user_id": "user_1",
                "lifecycle_state": "active",
            },
            {"$set": updates},
        )

    @pytest.mark.unit
    def test_replace_reminder_treats_idempotent_matched_update_as_success(
        self, reminder_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(
            matched_count=1, modified_count=0
        )
        reminder_id = ObjectId()

        result = reminder_dao.replace_reminder(
            str(reminder_id), "user_1", {"title": "unchanged"}
        )

        assert result is True

    @pytest.mark.unit
    def test_atomic_apply_fire_success_uses_active_next_fire_selector(
        self, reminder_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(matched_count=1)
        reminder_id = ObjectId()
        expected_next_fire_at = datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc)
        updates = {
            "last_fired_at": expected_next_fire_at,
            "next_fire_at": datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
        }

        result = reminder_dao.atomic_apply_fire_success(
            str(reminder_id), expected_next_fire_at, updates
        )

        assert result is True
        mock_collection.update_one.assert_called_once_with(
            {
                "_id": reminder_id,
                "next_fire_at": expected_next_fire_at,
                "lifecycle_state": "active",
            },
            {"$set": updates},
        )

    @pytest.mark.unit
    def test_atomic_apply_fire_success_treats_idempotent_matched_update_as_success(
        self, reminder_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(
            matched_count=1, modified_count=0
        )
        reminder_id = ObjectId()
        expected_next_fire_at = datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc)

        result = reminder_dao.atomic_apply_fire_success(
            str(reminder_id),
            expected_next_fire_at,
            {"last_fired_at": expected_next_fire_at},
        )

        assert result is True

    @pytest.mark.unit
    def test_atomic_apply_fire_failure_clears_next_fire_at_and_sets_failed_fields(
        self, reminder_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(matched_count=1)
        reminder_id = ObjectId()
        expected_next_fire_at = datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc)
        finished_at = datetime(2026, 4, 28, 9, 1, tzinfo=timezone.utc)
        updates = {
            "lifecycle_state": "failed",
            "last_error": "delivery failed",
            "updated_at": finished_at,
        }

        result = reminder_dao.atomic_apply_fire_failure(
            str(reminder_id), expected_next_fire_at, updates
        )

        assert result is True
        mock_collection.update_one.assert_called_once_with(
            {
                "_id": reminder_id,
                "next_fire_at": expected_next_fire_at,
                "lifecycle_state": "active",
            },
            {
                "$set": {
                    "lifecycle_state": "failed",
                    "last_error": "delivery failed",
                    "updated_at": finished_at,
                    "next_fire_at": None,
                }
            },
        )

    @pytest.mark.unit
    def test_atomic_apply_fire_failure_forces_failed_state_and_next_fire_clear(
        self, reminder_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(matched_count=1)
        reminder_id = ObjectId()
        expected_next_fire_at = datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc)
        failed_at = datetime(2026, 4, 28, 9, 1, tzinfo=timezone.utc)
        last_fired_at = datetime(2026, 4, 28, 9, 0, 30, tzinfo=timezone.utc)

        result = reminder_dao.atomic_apply_fire_failure(
            str(reminder_id),
            expected_next_fire_at,
            {
                "lifecycle_state": "active",
                "next_fire_at": expected_next_fire_at,
                "failed_at": failed_at,
                "last_fired_at": last_fired_at,
                "last_error": "delivery failed",
            },
        )

        assert result is True
        mock_collection.update_one.assert_called_once_with(
            {
                "_id": reminder_id,
                "next_fire_at": expected_next_fire_at,
                "lifecycle_state": "active",
            },
            {
                "$set": {
                    "lifecycle_state": "failed",
                    "next_fire_at": None,
                    "failed_at": failed_at,
                    "last_fired_at": last_fired_at,
                    "last_error": "delivery failed",
                }
            },
        )

    @pytest.mark.unit
    def test_atomic_apply_fire_failure_treats_idempotent_matched_update_as_success(
        self, reminder_dao, mock_collection
    ):
        mock_collection.update_one.return_value = MagicMock(
            matched_count=1, modified_count=0
        )
        reminder_id = ObjectId()
        expected_next_fire_at = datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc)

        result = reminder_dao.atomic_apply_fire_failure(
            str(reminder_id),
            expected_next_fire_at,
            {"last_error": "already failed"},
        )

        assert result is True
