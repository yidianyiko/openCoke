# -*- coding: utf-8 -*-
"""Unit tests for UserDAO Creem access methods"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestUserDAOCreem:
    """Tests for Creem-related UserDAO methods"""

    @pytest.fixture
    def user_dao(self):
        with patch(
            "dao.user_dao.CONF",
            {
                "mongodb": {
                    "mongodb_ip": "127.0.0.1",
                    "mongodb_port": "27017",
                    "mongodb_name": "test",
                }
            },
        ), patch("dao.user_dao.MongoClient"):
            from dao.user_dao import UserDAO

            dao = UserDAO()
            dao.collection = MagicMock()
            return dao

    @pytest.mark.unit
    def test_update_access_creem(self, user_dao):
        """Should update user access with Creem fields"""
        user_dao.collection.update_one.return_value = MagicMock(modified_count=1)
        user_id = str(ObjectId())
        expire = datetime.now() + timedelta(days=30)

        result = user_dao.update_access_creem(
            user_id=user_id,
            creem_customer_id="cust_123",
            creem_subscription_id="sub_456",
            expire_time=expire,
        )

        assert result is True
        call_args = user_dao.collection.update_one.call_args
        update_set = call_args[0][1]["$set"]
        assert update_set["access.creem_customer_id"] == "cust_123"
        assert update_set["access.creem_subscription_id"] == "sub_456"
        assert update_set["access.expire_time"] == expire

    @pytest.mark.unit
    def test_update_access_creem_invalid_user_id(self, user_dao):
        """Should return False for invalid user_id"""
        result = user_dao.update_access_creem(
            user_id="not_an_objectid",
            creem_customer_id="cust_123",
            creem_subscription_id="sub_456",
            expire_time=datetime.now(),
        )
        assert result is False

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
