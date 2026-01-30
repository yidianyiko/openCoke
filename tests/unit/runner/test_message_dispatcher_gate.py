# -*- coding: utf-8 -*-
"""Unit tests for MessageDispatcher access gate integration"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId


class TestMessageDispatcherGate:
    """Tests for MessageDispatcher with access gate"""

    @pytest.fixture
    def mock_access_gate(self):
        return MagicMock()

    @pytest.fixture
    def msg_ctx(self):
        """Create a mock MessageContext"""
        ctx = MagicMock()
        ctx.context = {
            "user": {"_id": ObjectId()},
            "platform": "langbot_telegram",
            "relation": {
                "relationship": {"dislike": 0},
                "character_info": {"status": "空闲"},
            },
        }
        ctx.input_messages = [{"message": "hello"}]
        return ctx

    @pytest.mark.unit
    def test_dispatch_calls_access_gate(self, msg_ctx, mock_access_gate):
        """Should call access gate check in dispatch"""
        mock_access_gate.check.return_value = None

        with patch(
            "agent.runner.message_processor.AccessGate", return_value=mock_access_gate
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate

            result = dispatcher.dispatch(msg_ctx)

            mock_access_gate.check.assert_called_once()
            assert result == ("normal", None)

    @pytest.mark.unit
    def test_dispatch_returns_gate_denied(self, msg_ctx, mock_access_gate):
        """Should return gate_denied when access gate denies"""
        mock_access_gate.check.return_value = ("gate_denied", None)

        with patch(
            "agent.runner.message_processor.AccessGate", return_value=mock_access_gate
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate

            result = dispatcher.dispatch(msg_ctx)

            assert result == ("gate_denied", None)

    @pytest.mark.unit
    def test_dispatch_returns_gate_success(self, msg_ctx, mock_access_gate):
        """Should return gate_success when order verification succeeds"""
        expire_time = datetime.now() + timedelta(days=30)
        mock_access_gate.check.return_value = (
            "gate_success",
            {"expire_time": expire_time},
        )

        with patch(
            "agent.runner.message_processor.AccessGate", return_value=mock_access_gate
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate

            result = dispatcher.dispatch(msg_ctx)

            assert result[0] == "gate_success"
            assert result[1]["expire_time"] == expire_time

    @pytest.mark.unit
    def test_dispatch_blocked_takes_priority(self, msg_ctx, mock_access_gate):
        """Blacklist check should run before access gate"""
        msg_ctx.context["relation"]["relationship"]["dislike"] = 100
        mock_access_gate.check.return_value = None

        with patch(
            "agent.runner.message_processor.AccessGate", return_value=mock_access_gate
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate

            result = dispatcher.dispatch(msg_ctx)

            assert result == ("blocked", None)
            mock_access_gate.check.assert_not_called()
