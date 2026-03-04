# -*- coding: utf-8 -*-
"""
Timezone tool for Agno Agent.

Allows users to update their timezone via natural language.
The LLM is responsible for resolving city/region names to IANA timezone strings.
"""

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agno.tools import tool

from dao.user_dao import UserDAO

logger = logging.getLogger(__name__)

# Mapping of common IANA timezone keys to Chinese display names (UTC offset).
# Used only for the confirmation message — not for lookup logic.
_TZ_DISPLAY: dict[str, str] = {
    "Asia/Shanghai": "北京/上海时间（UTC+8）",
    "Asia/Tokyo": "东京时间（UTC+9）",
    "Asia/Seoul": "首尔时间（UTC+9）",
    "Asia/Singapore": "新加坡时间（UTC+8）",
    "Asia/Bangkok": "曼谷时间（UTC+7）",
    "Asia/Jakarta": "雅加达时间（UTC+7）",
    "Asia/Kolkata": "印度时间（UTC+5:30）",
    "Asia/Dubai": "迪拜时间（UTC+4）",
    "Europe/London": "伦敦时间（UTC+0/+1）",
    "Europe/Berlin": "柏林时间（UTC+1/+2）",
    "Europe/Moscow": "莫斯科时间（UTC+3）",
    "America/New_York": "纽约时间（UTC-5/-4）",
    "America/Chicago": "芝加哥时间（UTC-6/-5）",
    "America/Los_Angeles": "洛杉矶时间（UTC-8/-7）",
    "America/Sao_Paulo": "圣保罗时间（UTC-3/-2）",
    "Africa/Cairo": "开罗时间（UTC+2/+3）",
    "Africa/Johannesburg": "约翰内斯堡时间（UTC+2）",
    "Pacific/Auckland": "奥克兰时间（UTC+12/+13）",
    "Australia/Sydney": "悉尼时间（UTC+10/+11）",
}


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
    """
    Persist the user's timezone to the database.

    Args:
        timezone: IANA timezone string inferred by the LLM from user's message.
        session_state: Agno-injected session state containing user._id.

    Returns:
        dict with ok: bool and message: str for the agent to relay to the user.
    """
    if not session_state:
        session_state = {}

    user_id = str(session_state.get("user", {}).get("_id", ""))
    if not user_id:
        logger.warning("set_user_timezone: no user_id in session_state")
        return {"ok": False, "message": "无法获取用户信息，时区设置失败"}

    # Validate IANA timezone
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning(f"set_user_timezone: invalid timezone '{timezone}'")
        return {"ok": False, "message": f"无效的时区名称：{timezone}"}

    dao = UserDAO()
    success = dao.update_timezone(user_id, timezone)

    if not success:
        logger.error(f"set_user_timezone: DB update failed for user {user_id}")
        return {"ok": False, "message": "时区更新失败，请稍后重试"}

    display = _TZ_DISPLAY.get(timezone, timezone)
    message = f"已将您的时区更新为{display}。"

    # Write confirmation into session_state so ChatResponseAgent can use it
    if session_state is not None:
        session_state["tool_execution_context"] = {
            "user_intent": "更新时区",
            "action_executed": "set_user_timezone",
            "intent_fulfilled": True,
            "result_summary": message,
        }

    logger.info(f"set_user_timezone: user {user_id} → {timezone}")
    return {"ok": True, "message": message}
