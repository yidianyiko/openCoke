# -*- coding: utf-8 -*-
"""Unit tests for UserDAO Stripe access methods"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestUserDAOStripe:
    """Tests for Stripe-related UserDAO methods"""

    @pytest.fixture
    def user_dao(self):
        with patch("dao.user_dao.CONF", {
            "mongodb": {"mongodb_ip": "127.0.0.1", "mongodb_port": "27017", "mongodb_name": "test"}
        }), patch("dao.user_dao.MongoClient") as mock_client:
            from dao.user_dao import UserDAO

            dao = UserDAO()
            dao.collection = MagicMock()
            return dao

    @pytest.mark.unit
    def test_update_access_stripe(self, user_dao):
        """Should update user access with Stripe fields"""
        user_dao.collection.update_one.return_value = MagicMock(modified_count=1)
        user_id = str(ObjectId())
        expire = datetime.now() + timedelta(days=30)

        result = user_dao.update_access_stripe(
            user_id=user_id,
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_456",
            expire_time=expire,
        )

        assert result is True
        call_args = user_dao.collection.update_one.call_args
        update_set = call_args[0][1]["$set"]
        assert update_set["access.stripe_customer_id"] == "cus_123"
        assert update_set["access.stripe_subscription_id"] == "sub_456"
        assert update_set["access.expire_time"] == expire

    @pytest.mark.unit
    def test_revoke_access(self, user_dao):
        """Should set expire_time to now to revoke access"""
        user_dao.collection.update_one.return_value = MagicMock(modified_count=1)
        user_id = str(ObjectId())

        result = user_dao.revoke_access(user_id)

        assert result is True
        call_args = user_dao.collection.update_one.call_args
        update_set = call_args[0][1]["$set"]
        assert "access.expire_time" in update_set
