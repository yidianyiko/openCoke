# tests/unit/test_user_dao_timezone.py
import pytest
from unittest.mock import MagicMock, patch
from dao.user_dao import UserDAO


def make_dao():
    with patch("dao.user_dao.MongoClient"):
        dao = UserDAO.__new__(UserDAO)
        dao.collection = MagicMock()
        return dao


def test_update_timezone_returns_true_on_success():
    dao = make_dao()
    dao.collection.update_one.return_value = MagicMock(modified_count=1)
    result = dao.update_timezone("507f1f77bcf86cd799439011", "America/New_York")
    assert result is True
    dao.collection.update_one.assert_called_once()
    call_args = dao.collection.update_one.call_args
    assert call_args[0][1] == {"$set": {"timezone": "America/New_York"}}


def test_update_timezone_returns_false_on_invalid_id():
    dao = make_dao()
    result = dao.update_timezone("bad_id", "America/New_York")
    assert result is False
    dao.collection.update_one.assert_not_called()


def test_update_timezone_returns_false_when_not_modified():
    dao = make_dao()
    dao.collection.update_one.return_value = MagicMock(modified_count=0)
    result = dao.update_timezone("507f1f77bcf86cd799439011", "Asia/Tokyo")
    assert result is False
