from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult
from agent.reminder.models import ReminderPatch, ReminderQuery, ReminderSchedule
from agent.timezone_service import TimezoneService
from dao.user_dao import UserDAO
from util.time_util import get_default_timezone

logger = logging.getLogger(__name__)

TIMEZONE_PROPOSAL_TTL_SECONDS = 15 * 60
PENDING_PROPOSAL_EXPIRED_MESSAGE = "当前时区确认已过期，请根据最新位置重新发起。"

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


class TimezoneCapabilityPort:
    def __init__(
        self,
        *,
        contract_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self.contract_factory = contract_factory or _default_contract_factory

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext | Any,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        del input_message
        request_args = _normalize_timezone_args(args or {})
        contract = self.contract_factory(run_context)
        content = dict(contract.handle_timezone_request(run_context, request_args))
        ok = bool(content.get("ok", True))
        message = content.get("message")
        if (
            ok
            and isinstance(message, str)
            and message.strip()
            and not content.get("summary")
        ):
            content["summary"] = message.strip()
        if (
            ok
            and isinstance(message, str)
            and message.strip()
            and not content.get("visible_summary")
        ):
            content["visible_summary"] = message.strip()
        return CapabilityResult(
            name="timezone",
            ok=ok,
            content=content,
            metadata={"durable_write": bool(content.get("state"))},
        )


class TimezoneDomainContract:
    def __init__(
        self,
        *,
        user_dao: UserDAO | None = None,
        timezone_service: TimezoneService | None = None,
    ) -> None:
        self.user_dao = user_dao or UserDAO()
        self.timezone_service = timezone_service or TimezoneService()

    def handle_timezone_request(
        self,
        run_context: Any,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        session_state = _session_state(run_context, args)
        action = str(args.get("action") or "").strip()
        if action == "direct_set":
            return self.set_user_timezone(
                timezone=str(args.get("timezone") or ""),
                session_state=session_state,
            )
        if action == "proposal":
            return self.store_timezone_proposal(
                timezone=str(args.get("timezone") or ""),
                session_state=session_state,
            )
        if action == "confirm":
            return self.consume_timezone_confirmation(
                decision=str(args.get("decision") or ""),
                session_state=session_state,
            )
        if action == "clear_pending":
            return self.clear_pending_timezone_proposal(session_state=session_state)
        return {"ok": False, "message": f"unsupported timezone action: {action}"}

    def set_user_timezone(
        self,
        *,
        timezone: str,
        session_state: dict | None = None,
    ) -> dict[str, Any]:
        session_state = session_state or {}
        user_id = _get_user_id(session_state)
        if not user_id:
            logger.warning("set_user_timezone: no user_id in session_state")
            return {"ok": False, "message": "无法获取用户信息，时区设置失败"}

        try:
            canonical_timezone = canonicalize_timezone(timezone)
        except ValueError:
            logger.warning("set_user_timezone: invalid timezone %r", timezone)
            return {"ok": False, "message": f"无效的时区名称：{timezone}"}

        current_state = self.user_dao.get_timezone_state(user_id)
        next_state = self.timezone_service.apply_user_explicit_change(
            current_state,
            canonical_timezone,
        )
        if not self.user_dao.update_timezone_state(user_id, next_state):
            logger.error("set_user_timezone: DB update failed for user %s", user_id)
            return {"ok": False, "message": "时区更新失败，请稍后重试"}

        display = _TZ_DISPLAY.get(canonical_timezone, canonical_timezone)
        message = f"已将您的时区更新为{display}。"
        _update_session_user_state(session_state, next_state)
        _append_tool_result(session_state, tool_name="时区更新", ok=True, message=message)
        _realign_visible_reminders_for_timezone_change(user_id, canonical_timezone)

        logger.info("set_user_timezone: user %s -> %s", user_id, canonical_timezone)
        return {"ok": True, "message": message, "state": next_state}

    def store_timezone_proposal(
        self,
        *,
        timezone: str,
        session_state: dict | None = None,
    ) -> dict[str, Any]:
        session_state = session_state or {}
        user_id = _get_user_id(session_state)
        conversation_id = _get_conversation_id(session_state)
        if not user_id or not conversation_id:
            logger.warning("store_timezone_proposal: missing user_id or conversation_id")
            return {"ok": False, "message": "无法记录待确认的时区变更"}

        try:
            canonical_timezone = canonicalize_timezone(timezone)
        except ValueError:
            logger.warning("store_timezone_proposal: invalid timezone %r", timezone)
            return {"ok": False, "message": f"无效的时区名称：{timezone}"}

        current_state = self._get_current_timezone_state(session_state, user_id)
        if current_state.get("timezone_status") == "user_confirmed":
            _update_session_user_state(session_state, current_state)
            return {"ok": True, "message": "", "state": current_state, "ignored": True}

        next_state = dict(current_state)
        next_state["pending_timezone_change"] = {
            "timezone": canonical_timezone,
            "origin_conversation_id": conversation_id,
            "expires_at": int(time.time()) + TIMEZONE_PROPOSAL_TTL_SECONDS,
        }

        if not self.user_dao.update_timezone_state(user_id, next_state):
            logger.error("store_timezone_proposal: DB update failed for user %s", user_id)
            return {"ok": False, "message": "暂时无法记录待确认的时区变更"}

        old_timezone = str(
            current_state.get("timezone") or _get_fallback_timezone(session_state)
        )
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

    def consume_timezone_confirmation(
        self,
        *,
        decision: str,
        session_state: dict | None = None,
    ) -> dict[str, Any]:
        session_state = session_state or {}
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

        current_state = self.user_dao.get_timezone_state(user_id) or {}
        pending_change = current_state.get("pending_timezone_change") or {}
        if pending_change.get("origin_conversation_id") != conversation_id:
            return {"ok": False, "message": "当前没有可确认的时区变更"}
        if is_timezone_proposal_expired(pending_change):
            self.clear_pending_timezone_proposal(
                session_state=session_state,
                current_state=current_state,
            )
            return {"ok": False, "message": PENDING_PROPOSAL_EXPIRED_MESSAGE}

        if normalized_decision == "yes":
            timezone = pending_change.get("timezone", "")
            if not timezone:
                return {"ok": False, "message": "当前没有可确认的时区变更"}
            next_state = self.timezone_service.apply_user_explicit_change(
                current_state,
                timezone,
            )
            next_state["timezone_source"] = "user_confirmation"
            display = _TZ_DISPLAY.get(timezone, timezone)
            message = f"已将您的时区更新为{display}。"
        else:
            next_state = dict(current_state)
            next_state["pending_timezone_change"] = None
            message = "好的，保持当前时区不变。"

        if not self.user_dao.update_timezone_state(user_id, next_state):
            logger.error(
                "consume_timezone_confirmation: DB update failed for user %s", user_id
            )
            return {"ok": False, "message": "时区确认处理失败，请稍后重试"}

        _update_session_user_state(session_state, next_state)
        _append_tool_result(session_state, tool_name="时区确认", ok=True, message=message)
        if normalized_decision == "yes":
            _realign_visible_reminders_for_timezone_change(
                user_id,
                str(next_state.get("timezone") or ""),
            )
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

    def clear_pending_timezone_proposal(
        self,
        *,
        session_state: dict | None = None,
        current_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_state = session_state or {}
        user_id = _get_user_id(session_state)
        if not user_id:
            return {"ok": False, "message": "无法清理待确认的时区变更"}

        state = current_state or self.user_dao.get_timezone_state(user_id)
        if not state:
            state = self._get_current_timezone_state(session_state, user_id)

        if not state.get("pending_timezone_change"):
            _update_session_user_state(session_state, state)
            return {"ok": True, "message": "", "state": state, "cleared": False}

        next_state = dict(state)
        next_state["pending_timezone_change"] = None
        if not self.user_dao.update_timezone_state(user_id, next_state):
            logger.error(
                "clear_pending_timezone_proposal: DB update failed for user %s",
                user_id,
            )
            return {"ok": False, "message": "待确认的时区变更清理失败"}

        _update_session_user_state(session_state, next_state)
        return {"ok": True, "message": "", "state": next_state, "cleared": True}

    def _get_current_timezone_state(
        self,
        session_state: dict | None,
        user_id: str,
    ) -> dict[str, Any]:
        state = self.user_dao.get_timezone_state(user_id)
        if state and state.get("timezone"):
            return state

        return self.timezone_service.build_initial_state(
            existing_state=None,
            candidates=[],
            fallback_timezone=_get_fallback_timezone(session_state),
        )


def _default_contract_factory(_run_context: Any) -> TimezoneDomainContract:
    return TimezoneDomainContract()


def _session_state(run_context: Any, args: dict[str, Any]) -> dict[str, Any]:
    existing_state = args.get("session_state")
    if isinstance(existing_state, dict):
        return existing_state
    if run_context is None:
        return {}
    user = getattr(run_context, "user", None)
    conversation = getattr(run_context, "conversation", None)
    return {
        "user": {
            "id": getattr(user, "id", ""),
            "timezone": getattr(user, "timezone", ""),
        },
        "conversation": {
            "id": getattr(conversation, "id", ""),
            "_id": getattr(conversation, "id", ""),
        },
    }


def canonicalize_timezone(timezone: str) -> str:
    try:
        return ZoneInfo(timezone).key
    except (ZoneInfoNotFoundError, KeyError) as exc:
        raise ValueError(f"invalid timezone: {timezone}") from exc


def _get_user_id(session_state: dict | None) -> str:
    return str((session_state or {}).get("user", {}).get("id", "")).strip()


def _get_conversation_id(session_state: dict | None) -> str:
    conversation = (session_state or {}).get("conversation", {})
    return str(
        conversation.get("_id") or conversation.get("id") or (session_state or {}).get(
            "conversation_id",
            "",
        )
    ).strip()


def _get_fallback_timezone(session_state: dict | None) -> str:
    user = (session_state or {}).get("user", {})
    candidate = (
        user.get("effective_timezone")
        or user.get("timezone")
        or get_default_timezone().key
    )
    return canonicalize_timezone(str(candidate))


def _update_session_user_state(session_state: dict | None, state: dict[str, Any]) -> None:
    if session_state is None:
        return
    session_state.setdefault("user", {}).update(state)


def _append_tool_result(
    session_state: dict | None,
    *,
    tool_name: str,
    ok: bool,
    message: str,
) -> None:
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
        from agent.reminder.runtime import get_reminder_runtime_instance

        runtime = get_reminder_runtime_instance()
        if runtime is not None:
            service = runtime.contract.reminder_service
            reminders = service.list_for_user(
                owner_user_id=user_id,
                query=ReminderQuery(lifecycle_states=["active"]),
            )
            for reminder in reminders:
                new_anchor = datetime.combine(
                    reminder.schedule.local_date,
                    reminder.schedule.local_time,
                    tzinfo=ZoneInfo(timezone),
                ).astimezone(UTC)
                new_schedule = ReminderSchedule(
                    anchor_at=new_anchor,
                    local_date=reminder.schedule.local_date,
                    local_time=reminder.schedule.local_time,
                    timezone=timezone,
                    rrule=reminder.schedule.rrule,
                )
                service.update(
                    reminder_id=reminder.id,
                    owner_user_id=user_id,
                    patch=ReminderPatch(schedule=new_schedule),
                )
    except Exception:
        logger.exception(
            "realign_visible_reminders_for_timezone_change failed for user %s",
            user_id,
        )


def normalize_timezone_confirmation_decision(decision: str) -> str:
    normalized = str(decision or "").strip().lower()
    if normalized in _YES_REPLIES:
        return "yes"
    if normalized in _NO_REPLIES:
        return "no"
    return ""


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


def _normalize_timezone_args(args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    action = str(normalized.get("action") or "").strip().lower()
    action_aliases = {
        "set": "direct_set",
        "update": "direct_set",
        "change": "direct_set",
        "direct": "direct_set",
        "direct-set": "direct_set",
        "direct set": "direct_set",
        "propose": "proposal",
        "ask": "proposal",
        "confirm_yes": "confirm",
        "confirm_no": "confirm",
    }
    normalized["action"] = action_aliases.get(action, action)
    return normalized
