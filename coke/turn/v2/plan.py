from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from coke.turn.v2.contracts import ProposedAction, ReplyNecessity, TurnPlan
from coke.turn.v2.param_schema import (
    allowed_actions_from_schema,
    param_key_schema_payload,
)

if TYPE_CHECKING:
    from coke.llm.config import ZAILLMConfig

ALLOWED_ACTIONS: Mapping[str, frozenset[str]] = allowed_actions_from_schema()
REPLY_NECESSITIES: set[ReplyNecessity] = {
    "intentional_no_reply",
    "reply_needed",
}

TURN_PLANNER_SYSTEM_PROMPT = """
Plan this Coke turn. Do not use keyword or regex routing.
Return only JSON with actions and reply_necessity.

Ownership:
- Plan proposes a flat ordered list of requested actions.
- Each action is {domain, operation, params}.
- Params must be keyword/natural references, never IDs, never precise extracted times.
- For each domain.operation, use exactly these param keys from param_key_schema;
  do not invent key names.
- Reminder and social detectors own precise time extraction later in Execute.
- For settings.set_timezone, timezone_text MUST be a valid IANA timezone identifier (e.g. "Asia/Tokyo", "America/New_York"), resolved from the user's natural place name; never a bare city name like "东京"/"Tokyo".
- A delete/remove/cancel/complete request is ALWAYS that action even when the target is vague or missing; never substitute a list or a different operation. The handler will return needs_choice/needs_input for a vague target.
- A reminder `match` keyword MUST be the reminder's topic/content (e.g. "跑步", "买牛奶"), never the generic word "提醒"/"reminder"/"提醒事项" itself. If the user names no specific topic (e.g. "删掉提醒"), OMIT `match` entirely so the turn asks which reminder.
- Do not emit confidence fields, scores, thresholds, final prose, or tool calls.
- conversation_history is the prior turns of THIS conversation (role user = the
  person, role assistant = you). Use it to resolve the latest message in context.
- The latest message may be a FOLLOW-UP that continues, answers, or corrects the
  most recent still-open request (e.g. a bare time like "晚上七点半", a friend name
  answering "who?", "改成X"/"换成Y", or a new time after you asked to reschedule).
  When it is a follow-up, RECONSTRUCT the prior request's full action from
  conversation_history: same domain and operation, carry forward ALL of its params
  (participant/friend, content/title, etc.), then merge in the new detail. Never
  downgrade a shared/social-scheduling request to a personal reminder, and never
  treat such a follow-up as converse.
- Empty actions mean converse/greeting/no product action.
""".strip()


@dataclass(frozen=True, slots=True)
class PlanRequest:
    account_id: str
    conversation_id: str
    payload: Mapping[str, Any]
    trusted_facts: Mapping[str, Any]
    conversation_history: Sequence[Mapping[str, Any]] = ()
    focus_subject: Any | None = None


class PlannerOutputError(RuntimeError):
    """Raised when planner JSON is not trusted structured output."""


class JSONCompletionClient(Protocol):
    def complete_json(
        self,
        *,
        system: str,
        user: dict,
        schema_name: str,
    ) -> Mapping[str, Any]: ...


class Planner(Protocol):
    def plan(self, request: PlanRequest) -> TurnPlan: ...


@dataclass(frozen=True, slots=True)
class SiliconFlowPlanner:
    client: JSONCompletionClient
    allowed_actions: Mapping[str, frozenset[str]] = field(
        default_factory=lambda: ALLOWED_ACTIONS
    )

    @classmethod
    def from_model(cls, model: Any) -> SiliconFlowPlanner:
        from coke.llm.semantic_interpreter import AgnoJSONCompletionClient

        return cls(AgnoJSONCompletionClient(model))

    @classmethod
    def from_config(cls, config: ZAILLMConfig) -> SiliconFlowPlanner:
        return cls.from_model(config.create_interpreter_model())

    def plan(self, request: PlanRequest) -> TurnPlan:
        payload = self.client.complete_json(
            system=TURN_PLANNER_SYSTEM_PROMPT,
            user={
                "account_id": request.account_id,
                "conversation_id": request.conversation_id,
                "payload": dict(request.payload),
                "conversation_history": [
                    dict(m) for m in request.conversation_history
                ],
                "trusted_facts": dict(request.trusted_facts),
                "focus_subject": _focus_subject_payload(request.focus_subject),
                "allowed_actions": _allowed_actions_payload(self.allowed_actions),
                "allowed_domains": sorted(self.allowed_actions),
                "allowed_reply_necessity": sorted(REPLY_NECESSITIES),
                "param_key_schema": param_key_schema_payload(),
            },
            schema_name="turn_plan",
        )
        if "confidence" in payload:
            raise PlannerOutputError("confidence is not part of TurnPlan")
        reply_necessity = _required_reply_necessity(payload)
        actions = _required_actions(payload, self.allowed_actions)
        return TurnPlan(actions=actions, reply_necessity=reply_necessity)


def _required_reply_necessity(payload: Mapping[str, Any]) -> ReplyNecessity:
    value = payload.get("reply_necessity")
    if value not in REPLY_NECESSITIES:
        raise PlannerOutputError("invalid reply_necessity")
    return value


def _required_actions(
    payload: Mapping[str, Any],
    allowed_actions: Mapping[str, frozenset[str]],
) -> tuple[ProposedAction, ...]:
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise PlannerOutputError("invalid actions")
    return tuple(_proposed_action(action, allowed_actions) for action in actions)


def _proposed_action(
    action: Any,
    allowed_actions: Mapping[str, frozenset[str]],
) -> ProposedAction:
    if not isinstance(action, Mapping):
        raise PlannerOutputError("invalid action")
    if "confidence" in action:
        raise PlannerOutputError("confidence is not part of ProposedAction")
    domain = action.get("domain")
    if domain not in allowed_actions:
        raise PlannerOutputError("invalid action.domain")
    operation = action.get("operation")
    if operation not in allowed_actions[domain]:
        raise PlannerOutputError("invalid action.operation")
    params = action.get("params", {})
    if not isinstance(params, Mapping):
        raise PlannerOutputError("invalid action.params")
    return ProposedAction(
        domain=domain,
        operation=operation,
        params=params,
    )


def _allowed_actions_payload(
    allowed_actions: Mapping[str, frozenset[str]],
) -> dict[str, list[str]]:
    return {
        domain: sorted(operations)
        for domain, operations in sorted(allowed_actions.items())
    }


def _focus_subject_payload(focus_subject: Any | None) -> dict[str, Any] | None:
    if focus_subject is None:
        return None
    if isinstance(focus_subject, Mapping):
        subject_type = focus_subject.get("subject_type")
        object_ids = focus_subject.get("object_ids")
        ordered = focus_subject.get("ordered", False)
    else:
        subject_type = getattr(focus_subject, "subject_type", None)
        object_ids = getattr(focus_subject, "object_ids", None)
        ordered = getattr(focus_subject, "ordered", False)
    if not isinstance(subject_type, str) or isinstance(object_ids, str):
        return None
    try:
        normalized_object_ids = tuple(str(object_id) for object_id in object_ids or ())
    except TypeError:
        return None
    return {
        "subject_type": subject_type,
        "object_ids": list(normalized_object_ids),
        "ordered": bool(ordered),
    }
