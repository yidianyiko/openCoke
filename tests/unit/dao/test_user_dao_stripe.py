# -*- coding: utf-8 -*-
"""Unit tests for UserDAO Stripe access methods."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestUserDAOStripe:
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
    def test_update_access_stripe(self, user_dao):
        user_dao.settings_collection.update_one.return_value = MagicMock(modified_count=1)
        account_id = "acct_123456"
        expire = datetime.now() + timedelta(days=30)

        result = user_dao.update_access_stripe(
            user_id=account_id,
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_456",
            expire_time=expire,
        )

        assert result is True
        call_args = user_dao.settings_collection.update_one.call_args
        assert call_args[0][0] == {"account_id": account_id}
        update_set = call_args[0][1]["$set"]
        assert update_set["access.stripe_customer_id"] == "cus_123"
        assert update_set["access.stripe_subscription_id"] == "sub_456"
        assert update_set["access.expire_time"] == expire

    @pytest.mark.unit
    def test_update_access_stripe_returns_false_for_missing_account_id(self, user_dao):
        result = user_dao.update_access_stripe(
            user_id="",
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            expire_time=datetime.now(),
        )
        assert result is False
        user_dao.settings_collection.update_one.assert_not_called()

    @pytest.mark.unit
    def test_update_access_stripe_returns_false_when_not_found(self, user_dao):
        account_id = "acct_123456"
        user_dao.settings_collection.update_one.return_value = MagicMock(modified_count=0)
        result = user_dao.update_access_stripe(
            user_id=account_id,
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            expire_time=datetime.now(),
        )
        assert result is False

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
