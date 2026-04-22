# tests/unit/test_user_dao_timezone.py
import pytest
from unittest.mock import MagicMock, patch
from dao.user_dao import UserDAO


def make_dao():
    with patch("dao.user_dao.MongoClient"):
        dao = UserDAO.__new__(UserDAO)
        dao.settings_collection = MagicMock()
        return dao


def test_update_timezone_returns_true_on_success():
    dao = make_dao()
    dao.settings_collection.update_one.return_value = MagicMock(modified_count=1)
    result = dao.update_timezone("acct_123456", "America/New_York")
    assert result is True
    dao.settings_collection.update_one.assert_called_once()
    call_args = dao.settings_collection.update_one.call_args
    assert call_args[0][0] == {"account_id": "acct_123456"}
    assert call_args[0][1] == {"$set": {"timezone": "America/New_York"}}


def test_update_timezone_returns_false_on_missing_account_id():
    dao = make_dao()
    result = dao.update_timezone("", "America/New_York")
    assert result is False
    dao.settings_collection.update_one.assert_not_called()


def test_update_timezone_returns_false_when_not_modified():
    dao = make_dao()
    dao.settings_collection.update_one.return_value = MagicMock(modified_count=0)
    result = dao.update_timezone("acct_123456", "Asia/Tokyo")
    assert result is False


def test_update_timezone_state_upserts_settings_document():
    dao = make_dao()
    dao.settings_collection.update_one.return_value = MagicMock(
        modified_count=0,
        upserted_id="new-settings",
    )

    state = {
        "timezone": "America/New_York",
        "timezone_source": "messaging_identity_region",
        "timezone_status": "system_inferred",
    }

    result = dao.update_timezone_state("acct_123456", state)

    assert result is True
    dao.settings_collection.update_one.assert_called_once_with(
        {"account_id": "acct_123456"},
        {
            "$set": {
                "timezone": "America/New_York",
                "timezone_source": "messaging_identity_region",
                "timezone_status": "system_inferred",
                "pending_timezone_change": None,
                "pending_task_draft": None,
            },
            "$setOnInsert": {"account_id": "acct_123456"},
        },
        upsert=True,
    )


def test_get_timezone_state_returns_only_timezone_fields():
    dao = make_dao()
    dao.settings_collection.find_one.return_value = {
        "account_id": "acct_123456",
        "timezone": "Asia/Tokyo",
        "timezone_source": "user_explicit",
        "timezone_status": "user_confirmed",
        "pending_timezone_change": None,
        "access": {"order_no": "keep-out"},
    }

    result = dao.get_timezone_state("acct_123456")

    assert result == {
        "timezone": "Asia/Tokyo",
        "timezone_source": "user_explicit",
        "timezone_status": "user_confirmed",
        "pending_timezone_change": None,
        "pending_task_draft": None,
    }


def test_update_timezone_state_rejects_missing_required_fields():
    dao = make_dao()

    result = dao.update_timezone_state(
        "acct_123456",
        {
            "timezone": "Asia/Tokyo",
            "timezone_source": "user_explicit",
        },
    )

    assert result is False
    dao.settings_collection.update_one.assert_not_called()
