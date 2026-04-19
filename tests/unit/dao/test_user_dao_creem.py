# -*- coding: utf-8 -*-
"""Unit tests for UserDAO Creem access methods."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestUserDAOCreem:
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
        ), patch("dao.user_dao.MongoClient") as mock_client:
            from dao.user_dao import UserDAO

            mock_db = MagicMock()
            settings_collection = MagicMock()
            mock_db.get_collection.side_effect = lambda name: {
                "users": MagicMock(),
                "user_profiles": MagicMock(),
                "coke_settings": settings_collection,
                "characters": MagicMock(),
            }[name]
            mock_client.return_value.__getitem__.return_value = mock_db

            dao = UserDAO()
            dao.settings_collection = settings_collection
            return dao

    @pytest.mark.unit
    def test_update_access_creem(self, user_dao):
        user_dao.settings_collection.update_one.return_value = MagicMock(modified_count=1)
        account_id = "acct_123456"
        expire = datetime.now() + timedelta(days=30)

        result = user_dao.update_access_creem(
            user_id=account_id,
            creem_customer_id="cust_123",
            creem_subscription_id="sub_456",
            expire_time=expire,
        )

        assert result is True
        call_args = user_dao.settings_collection.update_one.call_args
        assert call_args[0][0] == {"account_id": account_id}
        update_set = call_args[0][1]["$set"]
        assert update_set["access.creem_customer_id"] == "cust_123"
        assert update_set["access.creem_subscription_id"] == "sub_456"
        assert update_set["access.expire_time"] == expire

    @pytest.mark.unit
    def test_update_access_creem_invalid_user_id(self, user_dao):
        result = user_dao.update_access_creem(
            user_id="",
            creem_customer_id="cust_123",
            creem_subscription_id="sub_456",
            expire_time=datetime.now(),
        )
        assert result is False
        user_dao.settings_collection.update_one.assert_not_called()

    @pytest.mark.unit
    def test_revoke_access(self, user_dao):
        user_dao.settings_collection.update_one.return_value = MagicMock(modified_count=1)
        account_id = "acct_123456"

        result = user_dao.revoke_access(account_id)

        assert result is True
        call_args = user_dao.settings_collection.update_one.call_args
        assert call_args[0][0] == {"account_id": account_id}
        update_set = call_args[0][1]["$set"]
        assert "access.expire_time" in update_set
