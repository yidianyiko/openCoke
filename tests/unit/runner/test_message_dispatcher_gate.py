# -*- coding: utf-8 -*-
"""Unit tests for MessageDispatcher access gate integration"""

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
        ctx = MagicMock()
        ctx.context = {
            "user": {"_id": ObjectId()},
            "platform": "wechat",
            "relation": {
                "relationship": {"dislike": 0},
                "character_info": {"status": "空闲"},
            },
        }
        ctx.input_messages = [{"message": "hello"}]
        return ctx

    @pytest.mark.unit
    def test_dispatch_calls_access_gate(self, msg_ctx, mock_access_gate):
        mock_access_gate.check.return_value = None
        with patch(
            "agent.runner.message_processor.AccessGate",
            return_value=mock_access_gate,
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate
            result = dispatcher.dispatch(msg_ctx)
            mock_access_gate.check.assert_called_once()
            assert result == ("normal", None)

    @pytest.mark.unit
    def test_dispatch_returns_gate_denied_with_checkout_url(
        self, msg_ctx, mock_access_gate
    ):
        mock_access_gate.check.return_value = (
            "gate_denied",
            {"checkout_url": "https://checkout.creem.io/test"},
        )
        with patch(
            "agent.runner.message_processor.AccessGate",
            return_value=mock_access_gate,
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate
            result = dispatcher.dispatch(msg_ctx)
            assert result[0] == "gate_denied"
            assert "checkout_url" in result[1]

    @pytest.mark.unit
    def test_dispatch_blocked_takes_priority(self, msg_ctx, mock_access_gate):
        msg_ctx.context["relation"]["relationship"]["dislike"] = 100
        mock_access_gate.check.return_value = None
        with patch(
            "agent.runner.message_processor.AccessGate",
            return_value=mock_access_gate,
        ):
            from agent.runner.message_processor import MessageDispatcher

            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate
            result = dispatcher.dispatch(msg_ctx)
            assert result == ("blocked", None)
            mock_access_gate.check.assert_not_called()
