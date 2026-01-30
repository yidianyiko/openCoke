# -*- coding: utf-8 -*-
"""Unit tests for OrderDAO"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestOrderDAO:
    """Tests for OrderDAO class"""

    @pytest.fixture
    def mock_collection(self):
        """Create a mock MongoDB collection"""
        return MagicMock()

    @pytest.fixture
    def order_dao(self, mock_collection, monkeypatch):
        """Create OrderDAO with mocked collection"""
        from dao import order_dao as order_dao_module

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.get_collection.return_value = mock_collection
        mock_client.return_value.__getitem__.return_value = mock_db

        monkeypatch.setattr(order_dao_module, "MongoClient", mock_client)

        from dao.order_dao import OrderDAO

        dao_instance = OrderDAO()
        dao_instance.collection = mock_collection
        return dao_instance

    @pytest.mark.unit
    def test_find_available_order_returns_valid_order(self, order_dao, mock_collection):
        """Should return order when it exists, is unbound, and not expired"""
        future_time = datetime.now() + timedelta(days=30)
        expected_order = {
            "_id": ObjectId(),
            "order_no": "ORD123456",
            "expire_time": future_time,
            "bound_user_id": None,
        }
        mock_collection.find_one.return_value = expected_order

        result = order_dao.find_available_order("ORD123456")

        assert result == expected_order
        mock_collection.find_one.assert_called_once()
        call_args = mock_collection.find_one.call_args[0][0]
        assert call_args["order_no"] == "ORD123456"
        assert call_args["bound_user_id"] is None

    @pytest.mark.unit
    def test_find_available_order_returns_none_when_not_found(
        self, order_dao, mock_collection
    ):
        """Should return None when order doesn't exist"""
        mock_collection.find_one.return_value = None

        result = order_dao.find_available_order("NONEXISTENT")

        assert result is None

    @pytest.mark.unit
    def test_bind_to_user_success(self, order_dao, mock_collection):
        """Should return True when binding succeeds"""
        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_collection.update_one.return_value = mock_result
        user_id = ObjectId()

        result = order_dao.bind_to_user("ORD123456", user_id)

        assert result is True
        mock_collection.update_one.assert_called_once()

    @pytest.mark.unit
    def test_bind_to_user_fails_when_already_bound(self, order_dao, mock_collection):
        """Should return False when order is already bound"""
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_collection.update_one.return_value = mock_result
        user_id = ObjectId()

        result = order_dao.bind_to_user("ORD123456", user_id)

        assert result is False

    @pytest.mark.unit
    def test_get_by_order_no(self, order_dao, mock_collection):
        """Should return order by order_no"""
        expected_order = {"_id": ObjectId(), "order_no": "ORD123456"}
        mock_collection.find_one.return_value = expected_order

        result = order_dao.get_by_order_no("ORD123456")

        assert result == expected_order
        mock_collection.find_one.assert_called_once_with({"order_no": "ORD123456"})
