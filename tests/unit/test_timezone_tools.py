# tests/unit/test_timezone_tools.py
import pytest
from unittest.mock import MagicMock, patch


def make_session_state(user_id="507f1f77bcf86cd799439011"):
    return {
        "user": {"_id": user_id},
    }


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_success(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    dao_instance = MagicMock()
    dao_instance.update_timezone.return_value = True
    mock_dao_class.return_value = dao_instance

    session_state = make_session_state()
    result = set_user_timezone(
        timezone="America/New_York",
        session_state=session_state,
    )

    assert result["ok"] is True
    assert "纽约" in result["message"] or "America/New_York" in result["message"]
    dao_instance.update_timezone.assert_called_once_with(
        "507f1f77bcf86cd799439011", "America/New_York"
    )


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_invalid_iana(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    session_state = make_session_state()
    result = set_user_timezone(
        timezone="Not/AValid",
        session_state=session_state,
    )

    assert result["ok"] is False
    mock_dao_class.return_value.update_timezone.assert_not_called()


@patch("agent.agno_agent.tools.timezone_tools.UserDAO")
def test_set_user_timezone_tool_missing_user(mock_dao_class):
    from agent.agno_agent.tools.timezone_tools import set_user_timezone

    result = set_user_timezone(
        timezone="Asia/Tokyo",
        session_state={},
    )

    assert result["ok"] is False
    mock_dao_class.return_value.update_timezone.assert_not_called()
