# -*- coding: utf-8 -*-
"""Unit tests for UserDAO access-related methods."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest


class TestUserDAOAccess:
    @pytest.fixture
    def mock_settings_collection(self):
        return MagicMock()

    @pytest.fixture
    def user_dao(self, mock_settings_collection, monkeypatch):
        from dao import user_dao as user_dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.side_effect = lambda name: {
            "users": MagicMock(),
            "user_profiles": MagicMock(),
            "coke_settings": mock_settings_collection,
            "characters": MagicMock(),
        }[name]
        mock_client.return_value.__getitem__.return_value = mock_db

        monkeypatch.setattr(user_dao_module, "MongoClient", mock_client)

        from dao.user_dao import UserDAO

        return UserDAO()

    @pytest.mark.unit
    def test_update_access_success(self, user_dao, mock_settings_collection):
        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_settings_collection.update_one.return_value = mock_result

        account_id = "acct_123456"
        order_no = "ORD123456"
        expire_time = datetime.now() + timedelta(days=30)

        result = user_dao.update_access(account_id, order_no, expire_time)

        assert result is True
        mock_settings_collection.update_one.assert_called_once()
        call_args = mock_settings_collection.update_one.call_args
        assert call_args[0][0] == {"account_id": account_id}
        update_set = call_args[0][1]["$set"]
        assert update_set["access.order_no"] == order_no
        assert update_set["access.expire_time"] == expire_time
        assert "access.granted_at" in update_set

    @pytest.mark.unit
    def test_update_access_rejects_missing_account_id(
        self, user_dao, mock_settings_collection
    ):
        result = user_dao.update_access("", "ORD123", datetime.now())

        assert result is False
        mock_settings_collection.update_one.assert_not_called()
