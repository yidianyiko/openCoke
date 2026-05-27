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
    expires_at: datetime | None = None
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
        "summary_for_llm": product_notification.get("summary_for_llm")
        or product_notification.get("summary")
        or _fallback_summary(product_notification),
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
        expires_at=expires_at,
        summary_for_llm=summary,
    )


def _allowed_actions(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
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


def _fallback_summary(product_notification: Mapping[str, Any]) -> str:
    request_type = str(product_notification.get("request_type") or "product_action")
    request_id = str(product_notification.get("request_id") or "")
    return f"{request_type} {request_id}".strip()
