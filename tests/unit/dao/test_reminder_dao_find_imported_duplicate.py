from unittest.mock import MagicMock


def test_find_imported_duplicate_queries_import_metadata_without_lifecycle_filter():
    from dao.reminder_dao import ReminderDAO

    dao = ReminderDAO.__new__(ReminderDAO)
    dao.collection = MagicMock()
    expected = {
        "_id": "rem-1",
        "lifecycle_state": "completed",
        "metadata": {"source_event_id": "evt-1"},
    }
    dao.collection.find_one.return_value = expected

    result = dao.find_imported_duplicate(
        owner_user_id="user-1",
        import_provider="google_calendar",
        source_event_id="evt-1",
        source_original_start_time="2026-04-29T10:00:00",
    )

    assert result == expected
    dao.collection.find_one.assert_called_once_with(
        {
            "owner_user_id": "user-1",
            "metadata.import_provider": "google_calendar",
            "metadata.source_event_id": "evt-1",
            "metadata.source_original_start_time": "2026-04-29T10:00:00",
        }
    )


def test_find_imported_duplicate_returns_none_when_no_match():
    from dao.reminder_dao import ReminderDAO

    dao = ReminderDAO.__new__(ReminderDAO)
    dao.collection = MagicMock()
    dao.collection.find_one.return_value = None

    result = dao.find_imported_duplicate(
        owner_user_id="user-1",
        import_provider="google_calendar",
        source_event_id="missing",
        source_original_start_time="2026-04-29T10:00:00",
    )

    assert result is None


def test_find_visible_by_metadata_key_only_reuses_active_reminders():
    from dao.reminder_dao import ReminderDAO

    dao = ReminderDAO.__new__(ReminderDAO)
    dao.collection = MagicMock()
    expected = {
        "_id": "rem-1",
        "lifecycle_state": "active",
        "metadata": {"runtime_idempotency_key": "shared-reminder:sr_1:creator"},
    }
    dao.collection.find_one.return_value = expected

    result = dao.find_visible_by_metadata_key(
        owner_user_id="user-1",
        key="runtime_idempotency_key",
        value="shared-reminder:sr_1:creator",
    )

    assert result == expected
    dao.collection.find_one.assert_called_once_with(
        {
            "owner_user_id": "user-1",
            "visibility": "visible",
            "lifecycle_state": "active",
            "metadata.runtime_idempotency_key": "shared-reminder:sr_1:creator",
        }
    )
