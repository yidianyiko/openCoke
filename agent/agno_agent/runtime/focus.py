from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

FocusAmbiguity = Literal["none", "multi_pending", "none_actionable"]


class PendingAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    kind: str
    allowed_actions: tuple[str, ...]
    status: str
    focus_token: str | None = None
    expires_at: datetime | None = None
    delivered_at: datetime | None = None
    summary_for_llm: str


class FocusChannel(BaseModel):
    model_config = ConfigDict(frozen=True)

    current: PendingAction | None
    ambiguity: FocusAmbiguity
    candidates: tuple[PendingAction, ...] = ()


def build_focus_channel(
    trusted_actions: Sequence[Mapping[str, Any]],
    *,
    current_time: datetime,
) -> FocusChannel:
    actions = tuple(
        action
        for action in (
            _pending_action_from_mapping(item, current_time=current_time)
            for item in trusted_actions
        )
        if action is not None
    )
    if not actions:
        return FocusChannel(current=None, ambiguity="none_actionable")
    if len(actions) > 1:
        return FocusChannel(current=None, ambiguity="multi_pending", candidates=actions)
    action = actions[0]
    return FocusChannel(current=action, ambiguity="none", candidates=(action,))


def focus_from_product_notification(
    product_notification: Mapping[str, Any] | None,
    *,
    current_time: datetime,
) -> FocusChannel:
    if not isinstance(product_notification, Mapping):
        return FocusChannel(current=None, ambiguity="none_actionable")
    candidates = product_notification.get("candidates")
    if isinstance(candidates, Sequence) and not isinstance(
        candidates, (str, bytes, bytearray)
    ):
        return build_focus_channel(
            [
                _action_input_from_product_notification(candidate)
                for candidate in candidates
                if isinstance(candidate, Mapping)
            ],
            current_time=current_time,
        )
    return build_focus_channel(
        [_action_input_from_product_notification(product_notification)],
        current_time=current_time,
    )


def focus_from_agent_focus_binding(
    binding: Mapping[str, Any] | None,
    *,
    current_time: datetime,
) -> FocusChannel:
    if not isinstance(binding, Mapping):
        return FocusChannel(current=None, ambiguity="none_actionable")
    candidates = binding.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(
        candidates, (str, bytes, bytearray)
    ):
        return FocusChannel(current=None, ambiguity="none_actionable")
    focus_token = str(binding.get("focus_token") or "").strip()
    expires_at = binding.get("expires_at")
    actions = [
        _action_input_from_agent_focus_candidate(
            candidate,
            focus_token=focus_token,
            expires_at=expires_at,
        )
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    return build_focus_channel(actions, current_time=current_time)


def focus_from_session_state(
    focus_state: Mapping[str, Any] | None,
    *,
    current_time: datetime,
) -> FocusChannel:
    if not isinstance(focus_state, Mapping):
        return FocusChannel(current=None, ambiguity="none_actionable")
    candidates = focus_state.get("candidates")
    if isinstance(candidates, Sequence) and not isinstance(
        candidates, (str, bytes, bytearray)
    ):
        actions = [item for item in candidates if isinstance(item, Mapping)]
    else:
        current = focus_state.get("current")
        actions = [current] if isinstance(current, Mapping) else []
    return build_focus_channel(actions, current_time=current_time)


def focus_to_session_state(focus: FocusChannel) -> dict[str, Any]:
    return focus.model_dump(mode="json")


def _action_input_from_product_notification(
    product_notification: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "action_id": product_notification.get("action_id")
        or product_notification.get("request_id"),
        "kind": product_notification.get("kind")
        or product_notification.get("request_type"),
        "allowed_actions": product_notification.get("allowed_actions")
        or ("accept", "reject"),
        "status": product_notification.get("status") or "pending",
        "expires_at": product_notification.get("expires_at"),
        "delivered_at": product_notification.get("delivered_at"),
        "summary_for_llm": product_notification.get("summary_for_llm")
        or product_notification.get("summary")
        or _fallback_summary(product_notification),
    }


def _action_input_from_agent_focus_candidate(
    candidate: Mapping[str, Any],
    *,
    focus_token: str,
    expires_at: Any,
) -> dict[str, Any]:
    summary = candidate.get("summary")
    return {
        "action_id": candidate.get("handle"),
        "kind": candidate.get("kind"),
        "allowed_actions": candidate.get("allowed_actions") or ("accept", "reject"),
        "status": candidate.get("status") or "pending",
        "focus_token": focus_token,
        "expires_at": expires_at,
        "delivered_at": candidate.get("offered_at") or candidate.get("delivered_at"),
        "summary_for_llm": candidate.get("summary_for_llm")
        or _agent_focus_summary(summary)
        or _fallback_summary(candidate),
    }


def _pending_action_from_mapping(
    value: Mapping[str, Any],
    *,
    current_time: datetime,
) -> PendingAction | None:
    status = str(value.get("status") or "").strip()
    if status != "pending":
        return None
    expires_at = _parse_datetime(value.get("expires_at"))
    if expires_at is not None and expires_at <= current_time:
        return None
    delivered_at = _parse_datetime(value.get("delivered_at"))
    action_id = str(value.get("action_id") or value.get("request_id") or "").strip()
    kind = str(value.get("kind") or value.get("request_type") or "").strip()
    summary = str(value.get("summary_for_llm") or value.get("summary") or "").strip()
    if not action_id or not kind or not summary:
        return None
    return PendingAction(
        action_id=action_id,
        kind=kind,
        allowed_actions=_allowed_actions(value.get("allowed_actions")),
        status=status,
        focus_token=_optional_string(value.get("focus_token")),
        expires_at=expires_at,
        delivered_at=delivered_at,
        summary_for_llm=summary,
    )


def _allowed_actions(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        actions = tuple(str(item).strip() for item in value if str(item).strip())
        if actions:
            return actions
    return ("accept", "reject")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def _agent_focus_summary(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    title = str(value.get("title") or "").strip()
    requester_name = str(value.get("requester_name") or "").strip()
    fire_at = str(value.get("fire_at") or "").strip()
    message = str(value.get("message") or "").strip()
    if title and requester_name and fire_at:
        return f"{requester_name}邀请你参加“{title}”，时间{fire_at}。"
    if title and requester_name:
        return f"{requester_name}邀请你参加“{title}”。"
    if title:
        return f"共享提醒“{title}”。"
    if requester_name and message:
        return f"{requester_name}发来的好友请求：{message}"
    if requester_name:
        return f"{requester_name}发来的好友请求。"
    request_id = str(value.get("request_id") or "").strip()
    if request_id:
        return f"待处理请求 {request_id}"
    return ""


def _fallback_summary(product_notification: Mapping[str, Any]) -> str:
    request_type = str(product_notification.get("request_type") or "product_action")
    request_id = str(product_notification.get("request_id") or "")
    return f"{request_type} {request_id}".strip()
