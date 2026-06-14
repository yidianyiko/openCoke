from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from coke.turn.inbound.contracts import ProposedAction, ReplyNecessity, TurnPlan
from coke.turn.inbound.param_schema import (
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
- For time phrases with explicit period-of-day words (晚上/下午/上午/早上/中午,
  evening/afternoon/morning/noon), keep the period word attached to the time_phrase;
  never strip the phrase down to a bare clock.
- Keep ambiguous clock phrases or ranges with no explicit period marker (e.g.
  "8-9", "8点", "8到9点") verbatim in the time param; do NOT resolve AM/PM or
  dates in Plan — the detector picks the plausible near-future reading in Execute.
- For reminder.list schedule/list/count requests scoped to a day (e.g. 今天,
  明天, 后天, 周一, 6月15日, 2026-06-15), put the natural day/date text in
  date_phrase. Do NOT put a day/date phrase in keyword, and do NOT compute
  trigger_after/trigger_before in Plan. Use keyword only for reminder
  topic/content filters like "work" or "跑步".
- For a friend's schedule/availability/agenda question (e.g.
  "oliver今天有什么安排", "今天 Oliver 忙吗", "Oliver 什么时候有空"), use
  social_scheduling.availability_query, not social_scheduling.list_shared.
  Put the friend reference in participant and any natural day/date text in
  date_phrase. Do NOT compute local_start/local_end in Plan; Execute resolves
  date_phrase deterministically and applies the product default window when no
  day/date is given. The answer must be busy/free only, never titles.
- social_scheduling.list_shared is only for the user's own shared reminders
  with a friend (e.g. "我和oliver的共享提醒", "show shared reminders with Amy"),
  not for questions about what the friend is doing.
- For settings.set_timezone, timezone_text MUST be a valid IANA timezone identifier (e.g. "Asia/Tokyo", "America/New_York"), resolved from the user's natural place name; never a bare city name like "东京"/"Tokyo".
- A delete/remove/cancel/complete request is ALWAYS that action even when the target is vague or missing; never substitute a list or a different operation. The handler will return needs_choice/needs_input for a vague target.
- A reminder `match` keyword MUST be the reminder's topic/content (e.g. "跑步", "买牛奶"), never the generic word "提醒"/"reminder"/"提醒事项" itself. If the user names no specific topic (e.g. "删掉提醒"), OMIT `match` entirely so the turn asks which reminder.
- A social_scheduling.cancel_shared_reminder `match` MUST be the shared
  reminder's specific topic/title (e.g. "openCoke", "融资", "报告"), never a
  generic object word like "预约"/"安排"/"提醒"/"shared reminder". If the user only
  names the friend and no specific shared reminder, OMIT `match` so the handler
  can ask which one when multiple active candidates exist.
- A request to move/change/reschedule an existing shared appointment/reminder
  with another person is social_scheduling.update_shared_reminder. Preserve the
  friend reference and specific topic/title in params; never express it as
  cancel_shared_reminder or a personal reminder update.
- When the user only changes an existing shared reminder time, use social_scheduling.update_shared_reminder,
  include the new time as time_phrase, preserve the friend reference and
  topic/title, and do not ask for duration.
  Do not emit duration_minutes unless the user explicitly changes duration.
- Do not emit confidence fields, scores, thresholds, final prose, or tool calls.
- current_input_messages is the current open input window for THIS turn. Treat it
  as the authoritative current user input, ordered by seq.
- payload is the latest trigger payload and may be only the newest message.
- conversation_history is the prior turns of THIS conversation (role user = the
  person, role assistant = you). Use it to resolve the latest message in context.
- focus_subject is the typed subject of the most recent rendered product object
  when one is available. Use it only to understand what an elliptical contextual
  question/correction is about; it is not permission to create, update, cancel,
  complete, or reschedule anything by itself.
- A short contradiction/correction about the previous assistant statement (e.g.
  "不是明天吗？", "我不是约了Oliver明天开会吗？") is a contextual clarification
  unless it explicitly asks to create/update/cancel/complete/reschedule. For that
  kind of message, use empty actions with reply_needed so Express can answer from
  conversation_history/focus_subject. Do NOT emit reminder/social_scheduling
  create/update actions, and do NOT ask for fresh scheduling details just because
  the message contains a person, date, or topic.
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
    current_input_messages: Sequence[Mapping[str, Any]] = ()
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
        from coke.llm.json_completion import AgnoJSONCompletionClient

        return cls(AgnoJSONCompletionClient(model))

    @classmethod
    def from_config(cls, config: ZAILLMConfig) -> SiliconFlowPlanner:
        return cls.from_model(config.create_planner_model())

    def plan(self, request: PlanRequest) -> TurnPlan:
        payload = self.client.complete_json(
            system=TURN_PLANNER_SYSTEM_PROMPT,
            user={
                "account_id": request.account_id,
                "conversation_id": request.conversation_id,
                "payload": dict(request.payload),
                "current_input_messages": [
                    dict(m) for m in request.current_input_messages
                ],
                "conversation_history": [dict(m) for m in request.conversation_history],
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
