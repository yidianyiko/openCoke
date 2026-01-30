# -*- coding: utf-8 -*-
"""Unit tests for UserDAO access-related methods"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from bson import ObjectId


class TestUserDAOAccess:
    """Tests for UserDAO access methods"""

    @pytest.fixture
    def mock_collection(self):
        """Create a mock MongoDB collection"""
        return MagicMock()

    @pytest.fixture
    def user_dao(self, mock_collection, monkeypatch):
        """Create UserDAO with mocked collection"""
        from dao import user_dao as user_dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.return_value = mock_collection
        mock_client.return_value.__getitem__.return_value = mock_db

        monkeypatch.setattr(user_dao_module, "MongoClient", mock_client)

        from dao.user_dao import UserDAO

        dao_instance = UserDAO()
        dao_instance.collection = mock_collection
        return dao_instance

    @pytest.mark.unit
    def test_update_access_success(self, user_dao, mock_collection):
        """Should update user access fields"""
        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_collection.update_one.return_value = mock_result

        user_id = ObjectId()
        order_no = "ORD123456"
        expire_time = datetime.now() + timedelta(days=30)

        result = user_dao.update_access(user_id, order_no, expire_time)

        assert result is True
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"_id": user_id}
        update_set = call_args[0][1]["$set"]
        assert update_set["access.order_no"] == order_no
        assert update_set["access.expire_time"] == expire_time
        assert "access.granted_at" in update_set

    @pytest.mark.unit
    def test_update_access_user_not_found(self, user_dao, mock_collection):
        """Should return False when user not found"""
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_collection.update_one.return_value = mock_result

        user_id = ObjectId()
        result = user_dao.update_access(user_id, "ORD123", datetime.now())

        assert result is False
