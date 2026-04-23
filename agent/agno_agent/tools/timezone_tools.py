# -*- coding: utf-8 -*-
"""
Timezone tool for Agno Agent.

Allows users to update their timezone via natural language.
The LLM is responsible for resolving city/region names to IANA timezone strings.
"""

import logging
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agno.tools import tool

from agent.timezone_service import TimezoneService
from dao.user_dao import UserDAO
from util.time_util import get_default_timezone

logger = logging.getLogger(__name__)

TIMEZONE_PROPOSAL_TTL_SECONDS = 15 * 60

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

_YES_REPLIES = {
    "yes",
    "y",
    "ok",
    "okay",
    "sure",
    "confirm",
    "是",
    "好",
    "好的",
    "对",
    "嗯",
    "行",
}
_NO_REPLIES = {
    "no",
    "n",
    "nope",
    "cancel",
    "不用",
    "不",
    "不是",
    "否",
    "先别",
}

PENDING_PROPOSAL_EXPIRED_MESSAGE = "当前时区确认已过期，请根据最新位置重新发起。"


def _canonicalize_timezone(timezone: str) -> str:
    try:
        return ZoneInfo(timezone).key
    except (ZoneInfoNotFoundError, KeyError) as exc:
        raise ValueError(f"invalid timezone: {timezone}") from exc


def _get_user_id(session_state: dict | None) -> str:
    return str((session_state or {}).get("user", {}).get("id", "")).strip()


def _get_conversation_id(session_state: dict | None) -> str:
    conversation = (session_state or {}).get("conversation", {})
    return str(
        conversation.get("_id")
        or (session_state or {}).get("conversation_id", "")
    ).strip()


def _get_fallback_timezone(session_state: dict | None) -> str:
    user = (session_state or {}).get("user", {})
    candidate = (
        user.get("effective_timezone")
        or user.get("timezone")
        or get_default_timezone().key
    )
    return _canonicalize_timezone(str(candidate))


def _get_current_timezone_state(
    dao: UserDAO,
    session_state: dict | None,
    user_id: str,
) -> dict:
    state = dao.get_timezone_state(user_id)
    if state and state.get("timezone"):
        return state

    service = TimezoneService()
    return service.build_initial_state(
        existing_state=None,
        candidates=[],
        fallback_timezone=_get_fallback_timezone(session_state),
    )


def _update_session_user_state(session_state: dict | None, state: dict) -> None:
    if session_state is None:
        return
    session_state.setdefault("user", {}).update(state)


def _append_tool_result(session_state: dict | None, *, tool_name: str, ok: bool, message: str) -> None:
    if session_state is None:
        return
    from agent.agno_agent.tools.tool_result import append_tool_result

    append_tool_result(
        session_state,
        tool_name=tool_name,
        ok=ok,
        result_summary=message,
    )


def _realign_visible_reminders_for_timezone_change(user_id: str, timezone: str) -> None:
    if not user_id or not timezone:
        return

    try:
        from agent.agno_agent.tools.deferred_action.service import (
            DeferredActionService,
        )

        DeferredActionService().realign_visible_reminders_for_timezone_change(
            user_id, timezone
        )
    except Exception:
        logger.exception(
            "realign_visible_reminders_for_timezone_change failed for user %s",
            user_id,
        )


def _normalize_confirmation_decision(decision: str) -> str:
    normalized = str(decision or "").strip().lower()
    if normalized in _YES_REPLIES:
        return "yes"
    if normalized in _NO_REPLIES:
        return "no"
    return ""


def normalize_timezone_confirmation_decision(decision: str) -> str:
    return _normalize_confirmation_decision(decision)


def _format_timezone_transition_message(old_timezone: str, new_timezone: str) -> str:
    return (
        f"检测到您可能换了时区。要把时区从 {old_timezone} "
        f"切换到 {new_timezone} 吗？回复“是”确认，回复“否”保持不变。"
    )


def is_timezone_proposal_expired(
    pending_change: dict | None,
    *,
    now_ts: int | None = None,
) -> bool:
    if not pending_change:
        return False

    expires_at = pending_change.get("expires_at")
    if expires_at in (None, ""):
        return False

    try:
        expires_at_value = int(expires_at)
    except (TypeError, ValueError):
        return True

    current_ts = int(time.time()) if now_ts is None else int(now_ts)
    return expires_at_value <= current_ts


def clear_pending_timezone_proposal(
    session_state: dict = None,
    *,
    current_state: dict | None = None,
    dao: UserDAO | None = None,
) -> dict:
    if not session_state:
        session_state = {}

    user_id = _get_user_id(session_state)
    if not user_id:
        return {"ok": False, "message": "无法清理待确认的时区变更"}

    dao = dao or UserDAO()
    state = current_state or dao.get_timezone_state(user_id)
    if not state:
        state = _get_current_timezone_state(dao, session_state, user_id)

    if not state.get("pending_timezone_change") and not state.get("pending_task_draft"):
        _update_session_user_state(session_state, state)
        return {"ok": True, "message": "", "state": state, "cleared": False}

    next_state = dict(state)
    next_state["pending_timezone_change"] = None
    next_state["pending_task_draft"] = None
    if not dao.update_timezone_state(user_id, next_state):
        logger.error(
            "clear_pending_timezone_proposal: DB update failed for user %s", user_id
        )
        return {"ok": False, "message": "待确认的时区变更清理失败"}

    _update_session_user_state(session_state, next_state)
    return {"ok": True, "message": "", "state": next_state, "cleared": True}


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

    user_id = str(session_state.get("user", {}).get("id", ""))
    if not user_id:
        logger.warning("set_user_timezone: no user_id in session_state")
        return {"ok": False, "message": "无法获取用户信息，时区设置失败"}

    try:
        canonical_timezone = _canonicalize_timezone(timezone)
    except ValueError:
        logger.warning(f"set_user_timezone: invalid timezone '{timezone}'")
        return {"ok": False, "message": f"无效的时区名称：{timezone}"}

    dao = UserDAO()
    service = TimezoneService()
    current_state = dao.get_timezone_state(user_id)
    next_state = service.apply_user_explicit_change(current_state, canonical_timezone)
    success = dao.update_timezone_state(user_id, next_state)

    if not success:
        logger.error(f"set_user_timezone: DB update failed for user {user_id}")
        return {"ok": False, "message": "时区更新失败，请稍后重试"}

    display = _TZ_DISPLAY.get(canonical_timezone, canonical_timezone)
    message = f"已将您的时区更新为{display}。"
    _update_session_user_state(session_state, next_state)
    _append_tool_result(session_state, tool_name="时区更新", ok=True, message=message)
    _realign_visible_reminders_for_timezone_change(user_id, canonical_timezone)

    logger.info(f"set_user_timezone: user {user_id} → {canonical_timezone}")
    return {"ok": True, "message": message, "state": next_state}


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
    if not session_state:
        session_state = {}

    user_id = _get_user_id(session_state)
    conversation_id = _get_conversation_id(session_state)
    if not user_id or not conversation_id:
        logger.warning("store_timezone_proposal: missing user_id or conversation_id")
        return {"ok": False, "message": "无法记录待确认的时区变更"}

    try:
        canonical_timezone = _canonicalize_timezone(timezone)
    except ValueError:
        logger.warning(f"store_timezone_proposal: invalid timezone '{timezone}'")
        return {"ok": False, "message": f"无效的时区名称：{timezone}"}

    dao = UserDAO()
    current_state = _get_current_timezone_state(dao, session_state, user_id)
    if current_state.get("timezone_status") == "user_confirmed":
        _update_session_user_state(session_state, current_state)
        return {"ok": True, "message": "", "state": current_state, "ignored": True}

    next_state = dict(current_state)
    next_state["pending_timezone_change"] = {
        "timezone": canonical_timezone,
        "origin_conversation_id": conversation_id,
        "expires_at": int(time.time()) + TIMEZONE_PROPOSAL_TTL_SECONDS,
    }

    if not dao.update_timezone_state(user_id, next_state):
        logger.error(f"store_timezone_proposal: DB update failed for user {user_id}")
        return {"ok": False, "message": "暂时无法记录待确认的时区变更"}

    old_timezone = str(current_state.get("timezone") or _get_fallback_timezone(session_state))
    message = _format_timezone_transition_message(old_timezone, canonical_timezone)
    _update_session_user_state(session_state, next_state)
    _append_tool_result(session_state, tool_name="时区确认", ok=True, message=message)
    logger.info(
        "store_timezone_proposal: user %s pending proposal %s for conversation %s",
        user_id,
        canonical_timezone,
        conversation_id,
    )
    return {"ok": True, "message": message, "state": next_state}


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
    if not session_state:
        session_state = {}

    normalized_decision = normalize_timezone_confirmation_decision(decision)
    if not normalized_decision:
        return {"ok": False, "message": "无法识别时区确认回复"}

    user_id = _get_user_id(session_state)
    conversation_id = _get_conversation_id(session_state)
    if not user_id or not conversation_id:
        logger.warning(
            "consume_timezone_confirmation: missing user_id or conversation_id"
        )
        return {"ok": False, "message": "当前没有可确认的时区变更"}

    dao = UserDAO()
    current_state = dao.get_timezone_state(user_id) or {}
    pending_change = current_state.get("pending_timezone_change") or {}
    if pending_change.get("origin_conversation_id") != conversation_id:
        return {"ok": False, "message": "当前没有可确认的时区变更"}
    if is_timezone_proposal_expired(pending_change):
        clear_pending_timezone_proposal(
            session_state=session_state,
            current_state=current_state,
            dao=dao,
        )
        return {"ok": False, "message": PENDING_PROPOSAL_EXPIRED_MESSAGE}

    if normalized_decision == "yes":
        timezone = pending_change.get("timezone", "")
        if not timezone:
            return {"ok": False, "message": "当前没有可确认的时区变更"}
        service = TimezoneService()
        next_state = service.apply_user_explicit_change(current_state, timezone)
        next_state["timezone_source"] = "user_confirmation"
        display = _TZ_DISPLAY.get(timezone, timezone)
        message = f"已将您的时区更新为{display}。"
    else:
        next_state = dict(current_state)
        next_state["pending_timezone_change"] = None
        next_state["pending_task_draft"] = None
        message = "好的，保持当前时区不变。"

    if not dao.update_timezone_state(user_id, next_state):
        logger.error(
            "consume_timezone_confirmation: DB update failed for user %s", user_id
        )
        return {"ok": False, "message": "时区确认处理失败，请稍后重试"}

    _update_session_user_state(session_state, next_state)
    _append_tool_result(session_state, tool_name="时区确认", ok=True, message=message)
    _realign_visible_reminders_for_timezone_change(user_id, str(next_state.get("timezone", "")))
    logger.info(
        "consume_timezone_confirmation: user %s decision=%s conversation=%s",
        user_id,
        normalized_decision,
        conversation_id,
    )
    return {
        "ok": True,
        "message": message,
        "state": next_state,
        "decision": normalized_decision,
    }
