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
    dao.settings_collection.update_one.return_value = MagicMock(
        modified_count=1,
        matched_count=1,
        upserted_id=None,
    )
    result = dao.update_timezone("acct_123456", "America/New_York")
    assert result is True
    dao.settings_collection.update_one.assert_called_once()
    call_args = dao.settings_collection.update_one.call_args
    assert call_args[0][0] == {"account_id": "acct_123456"}
    assert call_args[0][1] == {
        "$set": {"timezone": "America/New_York"},
        "$setOnInsert": {"account_id": "acct_123456"},
    }
    assert call_args[1]["upsert"] is True


def test_update_timezone_returns_false_on_missing_account_id():
    dao = make_dao()
    result = dao.update_timezone("", "America/New_York")
    assert result is False
    dao.settings_collection.update_one.assert_not_called()


def test_update_timezone_returns_true_when_value_already_matches():
    dao = make_dao()
    dao.settings_collection.update_one.return_value = MagicMock(
        modified_count=0,
        matched_count=1,
        upserted_id=None,
    )
    result = dao.update_timezone("acct_123456", "Asia/Tokyo")
    assert result is True


def test_update_timezone_returns_true_when_settings_doc_is_upserted():
    dao = make_dao()
    dao.settings_collection.update_one.return_value = MagicMock(
        modified_count=0,
        matched_count=0,
        upserted_id="new_settings_doc",
    )

    result = dao.update_timezone("ck_123456", "America/New_York")

    assert result is True
