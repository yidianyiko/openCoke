# -*- coding: utf-8 -*-
"""
Timezone tool adapters for Agno Agent.

The business behavior lives behind TimezoneCapabilityPort; these functions only
translate Agno tool arguments into the capability contract.
"""

from __future__ import annotations

from typing import Any

from agno.tools import tool

from agent.agno_agent.capabilities.timezone import (
    PENDING_PROPOSAL_EXPIRED_MESSAGE,
    TimezoneCapabilityPort,
    is_timezone_proposal_expired,
    normalize_timezone_confirmation_decision,
)


def _run_timezone_capability(
    *,
    action: str,
    session_state: dict | None,
    timezone: str = "",
    decision: str = "",
) -> dict[str, Any]:
    result = TimezoneCapabilityPort().run(
        "",
        None,
        {
            "action": action,
            "timezone": timezone,
            "decision": decision,
            "session_state": session_state or {},
        },
    )
    return dict(result.content)


def clear_pending_timezone_proposal(
    session_state: dict = None,
    *,
    current_state: dict | None = None,
    dao: Any | None = None,
) -> dict:
    del current_state, dao
    return _run_timezone_capability(
        action="clear_pending",
        session_state=session_state,
    )


@tool(
    stop_after_tool_call=True,
    description="""更新用户的时区设置。当用户提到自己所在城市/国家/地区，或要求切换时区时调用。

参数:
- timezone: IANA 时区名称，例如 "America/New_York"、"Asia/Tokyo"、"Europe/London"
  根据用户提到的城市/地区推断，不要询问用户，直接给出 IANA 名称。
""",
)
def set_user_timezone(
    timezone: str,
    session_state: dict = None,
) -> dict:
    return _run_timezone_capability(
        action="direct_set",
        timezone=timezone,
        session_state=session_state,
    )


@tool(
    stop_after_tool_call=True,
    description="""记录待确认的时区变更提议。

参数:
- timezone: 推断出的 IANA 时区名称。
""",
)
def store_timezone_proposal(
    timezone: str,
    session_state: dict = None,
) -> dict:
    return _run_timezone_capability(
        action="proposal",
        timezone=timezone,
        session_state=session_state,
    )


@tool(
    stop_after_tool_call=True,
    description="""消费同一会话里的时区确认回复。

参数:
- decision: yes 或 no。
""",
)
def consume_timezone_confirmation(
    decision: str,
    session_state: dict = None,
) -> dict:
    return _run_timezone_capability(
        action="confirm",
        decision=decision,
        session_state=session_state,
    )
