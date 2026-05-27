from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from hashlib import sha256
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult

logger = logging.getLogger(__name__)

SCHEDULING_TOOL_NAMES = (
    "get_user_link",
    "reset_user_link",
    "disable_user_link",
    "create_friendship_by_user_link_code",
    "list_friends",
    "list_friend_calendar_facts",
    "list_shared_reminders",
    "remove_friendship",
    "create_shared_reminder",
    "cancel_shared_reminder",
)

_READ_ONLY_TOOL_NAMES = {
    "get_user_link",
    "list_friends",
    "list_friend_calendar_facts",
    "list_shared_reminders",
}

_VIEWER_TIMEZONE_TOOL_NAMES = {
    "create_shared_reminder",
    "list_friend_calendar_facts",
    "list_shared_reminders",
}

_DURABLE_WRITE_VISIBLE_SUMMARIES = {
    "reset_user_link": "已重置用户链接。",
    "disable_user_link": "已停用用户链接。",
    "create_friendship_by_user_link_code": "已添加好友。",
    "remove_friendship": "已移除好友关系。",
    "create_shared_reminder": "已创建共享提醒。",
    "cancel_shared_reminder": "已取消共享提醒。",
}


class SchedulingGatewayClientError(RuntimeError):
    pass


class SchedulingGatewayClient:
    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        session: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_url = (api_url or _read_gateway_api_base_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else _read_gateway_api_key()
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def call_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json(
            f"/api/internal/scheduling/tools/{tool_name}",
            payload,
        )

    def resolve_agent_focus(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/api/internal/scheduling/focus/resolve", payload)

    def bind_agent_focus_selection(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/api/internal/scheduling/focus/bind", payload)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.api_url}{path}",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        try:
            body = response.json()
        except ValueError as error:
            response.raise_for_status()
            raise SchedulingGatewayClientError(
                "invalid_scheduling_gateway_response"
            ) from error
        if not isinstance(body, dict):
            response.raise_for_status()
            raise SchedulingGatewayClientError("invalid_scheduling_gateway_response")
        if body.get("ok") is not True and getattr(response, "status_code", 200) >= 500:
            response.raise_for_status()
        return body


SchedulingContractClient = SchedulingGatewayClient


class SchedulingCapabilityPort:
    def __init__(
        self,
        *,
        tool_name: str,
        handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        client: SchedulingGatewayClient | None = None,
    ) -> None:
        if tool_name not in SCHEDULING_TOOL_NAMES:
            raise ValueError(f"unsupported scheduling tool: {tool_name}")
        self.tool_name = tool_name
        self.handler = handler
        self.client = client or SchedulingGatewayClient()

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        payload = _trusted_tool_payload(
            args or {},
            input_message=input_message,
            run_context=run_context,
            tool_name=self.tool_name,
        )
        try:
            raw = (
                self.handler(self.tool_name, payload)
                if self.handler
                else self.client.call_tool(self.tool_name, payload)
            )
        except Exception as error:
            return CapabilityResult(
                name=self.tool_name,
                ok=False,
                content={"summary": "日程操作暂时无法完成。"},
                error=str(error) or "scheduling_failed",
                metadata={
                    "durable_write": False,
                    "requires_response_synthesis": True,
                },
            )
        ok = raw.get("ok", True)
        data = raw.get("data", raw)
        if not isinstance(data, Mapping):
            data = {"value": data}
        content = dict(data)
        if ok is not True:
            logger.warning(
                "scheduling_tool_failed: tool=%s error=%s payload=%s",
                self.tool_name,
                content.get("error"),
                _safe_scheduling_payload_for_log(payload),
            )
        durable_write = self.tool_name not in _READ_ONLY_TOOL_NAMES
        if ok and self.tool_name == "list_friend_calendar_facts":
            content = _privacy_safe_friend_calendar_facts(content)
        if (
            ok
            and self.tool_name == "get_user_link"
            and not _has_explicit_visible_summary(content)
        ):
            url = content.get("url")
            if isinstance(url, str) and url.strip():
                content["visible_summary"] = f"这是你的好友邀请链接：{url.strip()}"
        if (
            ok
            and self.tool_name == "list_shared_reminders"
            and not _has_explicit_visible_summary(content)
        ):
            content["visible_summary"] = _shared_reminders_summary(content)
        if (
            ok
            and self.tool_name == "list_friends"
            and not _has_explicit_visible_summary(content)
        ):
            content["visible_summary"] = _friends_summary(
                content,
                account_id=str(payload.get("customer_id") or ""),
            )
        if ok and durable_write and not _has_explicit_visible_summary(content):
            content["visible_summary"] = _DURABLE_WRITE_VISIBLE_SUMMARIES[
                self.tool_name
            ]
        if not ok and not _has_explicit_visible_summary(content):
            failure_summary = _scheduling_failure_summary(str(raw.get("error") or ""))
            if failure_summary:
                content["visible_summary"] = failure_summary
            else:
                content["summary"] = "日程操作暂时无法完成。"
        return CapabilityResult(
            name=self.tool_name,
            ok=bool(ok),
            content=content,
            error=None if ok else str(raw.get("error") or "scheduling_failed"),
            metadata={
                "durable_write": bool(ok) and durable_write,
                "requires_response_synthesis": True,
            },
        )


def _trusted_tool_payload(
    args: dict[str, Any],
    *,
    input_message: str,
    run_context: AgentRunContext,
    tool_name: str,
) -> dict[str, Any]:
    payload = dict(args)
    _normalize_date_only_tool_fields(payload)
    _recover_shared_reminder_receiver_name(
        payload,
        input_message=input_message,
        tool_name=tool_name,
    )
    if (
        tool_name in _VIEWER_TIMEZONE_TOOL_NAMES
        and not str(payload.get("timezone") or "").strip()
    ):
        timezone = str(getattr(run_context.user, "timezone", "") or "").strip()
        if timezone:
            payload["timezone"] = timezone
    if (
        tool_name not in _READ_ONLY_TOOL_NAMES
        and not str(payload.get("idempotency_key") or "").strip()
    ):
        seed = f"{run_context.user.id}:{run_context.conversation.id}:{tool_name}:{input_message}"
        payload["idempotency_key"] = (
            f"{tool_name}:{sha256(seed.encode()).hexdigest()[:32]}"
        )
    payload.update(
        {
            "customer_id": run_context.user.id,
            "conversation_id": run_context.conversation.id,
            "platform": run_context.platform,
            "input_message": input_message,
        }
    )
    return payload


_DIRECT_INVITE_RECEIVER_PATTERN = re.compile(
    r"(?:帮我|请帮我|麻烦帮我)?(?:约|邀请)\s*([^，,。！？!?、\s]+)"
)
_NON_RECEIVER_INVITE_PREFIXES = (
    "今天",
    "明天",
    "后天",
    "今晚",
    "上午",
    "下午",
    "晚上",
    "下周",
    "本周",
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "周六",
    "周日",
    "星期",
)
_NON_RECEIVER_INVITE_MARKERS = (
    "一节",
    "一个",
    "一次",
    "会议",
    "课",
    "提醒",
    "时间",
    "篮球",
    "网球",
    "羽毛球",
    "咖啡",
    "吃饭",
    "跑步",
)


def _recover_shared_reminder_receiver_name(
    payload: dict[str, Any],
    *,
    input_message: str,
    tool_name: str,
) -> None:
    if tool_name != "create_shared_reminder":
        return
    if any(
        str(payload.get(key) or "").strip()
        for key in ("receiver_account_id", "receiver_name", "friend_account_id")
    ):
        return
    match = _DIRECT_INVITE_RECEIVER_PATTERN.search(input_message)
    if not match:
        return
    candidate = match.group(1).strip()
    if not candidate or len(candidate) > 32:
        return
    if candidate.startswith(_NON_RECEIVER_INVITE_PREFIXES):
        return
    if any(marker in candidate for marker in _NON_RECEIVER_INVITE_MARKERS):
        return
    payload["receiver_name"] = candidate


def _normalize_date_only_tool_fields(payload: dict[str, Any]) -> None:
    for key in ("from_date", "to_date"):
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if len(candidate) < 10:
            continue
        date_part = candidate[:10]
        try:
            date.fromisoformat(date_part)
        except ValueError:
            continue
        if len(candidate) == 10 or candidate[10:11] in {"T", " "}:
            payload[key] = date_part


def _safe_scheduling_payload_for_log(payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "customer_id",
        "conversation_id",
        "platform",
        "target_account_id",
        "friend_name",
        "from_date",
        "to_date",
        "timezone",
        "status",
        "request_id",
        "title",
        "fire_at",
        "duration_minutes",
    }
    safe: dict[str, Any] = {}
    for key in allowed:
        value = payload.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, str) and len(value) > 120:
            safe[key] = value[:117] + "..."
        else:
            safe[key] = value
    return safe


_FRIEND_CALENDAR_PRIVATE_KEYS = {
    "id",
    "_id",
    "reminder_id",
    "reminderid",
    "title",
    "prompt",
    "metadata",
    "agent_output_target",
    "agentoutputtarget",
    "output_target",
    "outputtarget",
    "target_account_id",
    "targetaccountid",
}


def _privacy_safe_friend_calendar_facts(content: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = _strip_friend_calendar_private_fields(content)
    privacy = dict(sanitized.get("privacy") or {})
    privacy["event_details_included"] = False
    sanitized["privacy"] = privacy
    return sanitized


def _strip_friend_calendar_private_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized = {}
        for key, item in value.items():
            normalized_key = str(key).replace("-", "_").lower()
            if normalized_key in _FRIEND_CALENDAR_PRIVATE_KEYS:
                continue
            sanitized[str(key)] = _strip_friend_calendar_private_fields(item)
        return sanitized
    if isinstance(value, list):
        return [_strip_friend_calendar_private_fields(item) for item in value]
    return value


def _has_explicit_visible_summary(content: Mapping[str, Any]) -> bool:
    for key in ("visible_summary", "summary"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _scheduling_failure_summary(error_code: str) -> str:
    if error_code == "friend_name_ambiguous":
        return "有多个同名好友，请提供完整好友名称。"
    if error_code in {"friend_name_not_found", "friend_not_found"}:
        return "没有找到这个好友，请确认好友名称。"
    return ""


def _friends_summary(content: Mapping[str, Any], *, account_id: str = "") -> str:
    raw_items = content.get("value")
    if raw_items is None:
        raw_items = content.get("friends")
    if not isinstance(raw_items, list) or not raw_items:
        return "你现在还没有好友。"
    labels = [
        label
        for label in (
            _friendship_counterpart_label(item, account_id)
            for item in raw_items[:3]
            if isinstance(item, Mapping)
        )
        if label
    ]
    if labels:
        return f"你现在有 {len(raw_items)} 个好友：" + "；".join(labels) + "。"
    return f"你现在有 {len(raw_items)} 个好友。"


def _friendship_counterpart_label(item: Mapping[str, Any], account_id: str) -> str:
    account_a_id = str(item.get("accountAId") or "").strip()
    account_b_id = str(item.get("accountBId") or "").strip()
    if account_id and account_a_id == account_id:
        return _profile_display_name(item.get("accountB"))
    if account_id and account_b_id == account_id:
        return _profile_display_name(item.get("accountA"))
    account_a_name = _profile_display_name(item.get("accountA"))
    account_b_name = _profile_display_name(item.get("accountB"))
    return account_b_name or account_a_name


def _profile_display_name(value: Any) -> str:
    if isinstance(value, Mapping):
        display_name = value.get("displayName")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
    return ""


def _shared_reminders_summary(content: Mapping[str, Any]) -> str:
    raw_items = content.get("value")
    if raw_items is None:
        raw_items = content.get("shared_reminders")
    if raw_items is None:
        raw_items = content.get("reminders")
    if not isinstance(raw_items, list) or not raw_items:
        return "目前没有符合条件的共享提醒。"

    friend_name = _shared_reminders_friend_name(content)
    labels = [
        _shared_reminder_status_label(item, friend_name)
        for item in raw_items[:3]
        if isinstance(item, Mapping)
    ]
    if not labels:
        return f"你有 {len(raw_items)} 个共享提醒。"
    return f"你有 {len(raw_items)} 个共享提醒：" + "；".join(labels) + "。"


def _shared_reminders_friend_name(content: Mapping[str, Any]) -> str:
    for key in ("friend_name", "friendName", "counterpartyName"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _shared_reminder_status_label(
    item: Mapping[str, Any],
    friend_name: str,
) -> str:
    title = str(item.get("title") or "共享提醒").strip() or "共享提醒"
    status = str(item.get("status") or "unknown").strip() or "unknown"
    time_text = _shared_reminder_time_text(item)
    friend = friend_name or _shared_reminder_counterparty_display_name(item)

    parts = []
    if friend:
        parts.append(f"{friend} 的“{title}”")
    else:
        parts.append(f"“{title}”")
    if time_text:
        parts.append(time_text)
    parts.append(f"状态 {status}")
    return "，".join(parts)


def _shared_reminder_counterparty_display_name(item: Mapping[str, Any]) -> str:
    creator = item.get("creator")
    if isinstance(creator, Mapping):
        display_name = creator.get("displayName")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
    receiver = item.get("receiver")
    if isinstance(receiver, Mapping):
        display_name = receiver.get("displayName")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
    for key in ("creatorName", "creator_name", "receiverName", "receiver_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _shared_reminder_time_text(item: Mapping[str, Any]) -> str:
    viewer_local_date = _string_value(item, "viewer_local_date", "viewerLocalDate")
    viewer_local_time = _string_value(item, "viewer_local_time", "viewerLocalTime")
    if viewer_local_date and viewer_local_time:
        return f"{viewer_local_date} {viewer_local_time[:5]}"

    raw_fire_at = item.get("fireAt")
    if raw_fire_at is None:
        raw_fire_at = item.get("fire_at")
    timezone = _string_value(item, "viewer_timezone", "viewerTimezone")
    if not timezone:
        timezone = _string_value(item, "timezone")
    if not isinstance(raw_fire_at, str) or not raw_fire_at.strip():
        return ""
    try:
        fire_at = datetime.fromisoformat(raw_fire_at.replace("Z", "+00:00"))
        if timezone:
            fire_at = fire_at.astimezone(ZoneInfo(timezone))
        return fire_at.strftime("%Y-%m-%d %H:%M")
    except (ValueError, ZoneInfoNotFoundError):
        return raw_fire_at.strip()


def _string_value(item: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _read_gateway_api_base_url() -> str:
    base = (
        os.environ.get("COKE_GATEWAY_API_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_COKE_API_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_API_URL", "").strip()
    )
    if base:
        return base

    try:
        from conf.config import CONF

        identity_api_url = str(
            CONF.get("clawscale_bridge", {}).get("identity_api_url") or ""
        ).strip()
        if identity_api_url:
            parsed = urlsplit(identity_api_url)
            return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    except Exception:
        pass
    return "http://127.0.0.1:4041"


def _read_gateway_api_key() -> str:
    api_key = os.environ.get("CLAWSCALE_IDENTITY_API_KEY", "").strip()
    if api_key:
        return api_key

    try:
        from conf.config import CONF

        return str(
            CONF.get("clawscale_bridge", {}).get("identity_api_key") or ""
        ).strip()
    except Exception:
        return ""
