# -*- coding: utf-8 -*-
"""Unit tests for AccessGate"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestAccessGate:
    """Tests for AccessGate class"""

    @pytest.fixture
    def mock_order_dao(self):
        return MagicMock()

    @pytest.fixture
    def mock_user_dao(self):
        return MagicMock()

    @pytest.fixture
    def access_config(self):
        return {
            "enabled": True,
            "platforms": {
                "wechat": True,
            },
            "deny_message": "[系统消息] 请发送有效订单编号开通服务",
            "expire_message": "[系统消息] 您的服务已过期",
            "success_message": "[系统消息] 验证成功，有效期至 {expire_time}",
        }

    @pytest.fixture
    def access_gate(self, mock_order_dao, mock_user_dao, access_config):
        with patch(
            "agent.runner.access_gate.CONF",
            {"access_control": access_config, "admin_user_id": "admin123"},
        ):
            from agent.runner.access_gate import AccessGate

            gate = AccessGate()
            gate.order_dao = mock_order_dao
            gate.user_dao = mock_user_dao
            return gate

    @pytest.mark.unit
    def test_check_returns_none_when_disabled(self, access_config):
        """Should return None when access control is disabled"""
        access_config["enabled"] = False
        with patch(
            "agent.runner.access_gate.CONF",
            {"access_control": access_config, "admin_user_id": ""},
        ):
            from agent.runner.access_gate import AccessGate

            gate = AccessGate()

            result = gate.check(
                platform="wechat",
                user={"_id": ObjectId()},
                message="hello",
                admin_user_id="",
            )

            assert result is None

    @pytest.mark.unit
    def test_check_returns_none_for_disabled_platform(self, mock_order_dao, mock_user_dao):
        """Should return None when platform has gate disabled"""
        config = {
            "enabled": True,
            "platforms": {"wechat": False},
            "deny_message": "denied",
            "expire_message": "expired",
            "success_message": "ok",
        }
        with patch(
            "agent.runner.access_gate.CONF",
            {"access_control": config, "admin_user_id": ""},
        ):
            from agent.runner.access_gate import AccessGate

            gate = AccessGate()
            gate.order_dao = mock_order_dao
            gate.user_dao = mock_user_dao
            result = gate.check(
                platform="wechat",
                user={"_id": ObjectId()},
                message="hello",
                admin_user_id="",
            )

        assert result is None

    @pytest.mark.unit
    def test_check_returns_none_for_admin(self, access_gate):
        """Should return None for admin user (exempt)"""
        admin_id = ObjectId()

        result = access_gate.check(
            platform="wechat",
            user={"_id": admin_id},
            message="hello",
            admin_user_id=str(admin_id),
        )

        assert result is None

    @pytest.mark.unit
    def test_check_returns_none_for_valid_access(self, access_gate):
        """Should return None when user has valid access"""
        future_time = datetime.now() + timedelta(days=30)
        user = {
            "_id": ObjectId(),
            "access": {"order_no": "ORD123", "expire_time": future_time},
        }

        result = access_gate.check(
            platform="wechat",
            user=user,
            message="hello",
            admin_user_id="",
        )

        assert result is None

    @pytest.mark.unit
    def test_check_returns_denied_for_new_user(self, access_gate, mock_order_dao):
        """Should return gate_denied for user without access"""
        mock_order_dao.find_available_order.return_value = None
        user = {"_id": ObjectId()}

        result = access_gate.check(
            platform="wechat",
            user=user,
            message="hello",
            admin_user_id="",
        )

        assert result == ("gate_denied", None)

    @pytest.mark.unit
    def test_check_returns_expired_for_expired_access(
        self, access_gate, mock_order_dao
    ):
        """Should return gate_expired when access has expired"""
        mock_order_dao.find_available_order.return_value = None
        past_time = datetime.now() - timedelta(days=1)
        user = {
            "_id": ObjectId(),
            "access": {"order_no": "ORD123", "expire_time": past_time},
        }

        result = access_gate.check(
            platform="wechat",
            user=user,
            message="hello",
            admin_user_id="",
        )

        assert result == ("gate_expired", None)

    @pytest.mark.unit
    def test_check_binds_order_on_valid_order_message(
        self, access_gate, mock_order_dao, mock_user_dao
    ):
        """Should bind order and return success when message matches valid order"""
        future_time = datetime.now() + timedelta(days=30)
        order = {
            "_id": ObjectId(),
            "order_no": "ORD123456",
            "expire_time": future_time,
            "bound_user_id": None,
        }
        mock_order_dao.find_available_order.return_value = order
        mock_order_dao.bind_to_user.return_value = True
        mock_user_dao.update_access.return_value = True

        user_id = ObjectId()
        user = {"_id": user_id}

        result = access_gate.check(
            platform="wechat",
            user=user,
            message="ORD123456",
            admin_user_id="",
        )

        assert result[0] == "gate_success"
        assert result[1]["expire_time"] == future_time
        mock_order_dao.bind_to_user.assert_called_once_with("ORD123456", user_id)
        mock_user_dao.update_access.assert_called_once()

    @pytest.mark.unit
    def test_get_message_returns_correct_messages(self, access_gate):
        """Should return correct message for each gate type"""
        deny_msg = access_gate.get_message("gate_denied")
        assert "订单编号" in deny_msg

        expire_msg = access_gate.get_message("gate_expired")
        assert "过期" in expire_msg

        future_time = datetime(2024, 12, 31, 23, 59)
        success_msg = access_gate.get_message("gate_success", future_time)
        assert "2024-12-31" in success_msg
