from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.turn.inbound.contracts import ProposedAction, ReplyNecessity, TurnPlan
from coke.turn.inbound.param_schema import (
    PARAM_KEY_SCHEMA,
    allowed_actions_from_schema,
    param_key_schema_payload,
)

if TYPE_CHECKING:
    from coke.llm.config import ZAILLMConfig

ALLOWED_ACTIONS: Mapping[str, frozenset[str]] = allowed_actions_from_schema()
PRECISE_TIME_PARAM_KEYS = frozenset({"trigger_time", "local_trigger_at"})
LOGGER = logging.getLogger(__name__)
REPLY_NECESSITIES: set[ReplyNecessity] = {
    "intentional_no_reply",
    "reply_needed",
}

TURN_PLANNER_SYSTEM_PROMPT = """
Plan this Coke turn. Do not use keyword or regex routing.
Return a single turn_plan JSON object and nothing else.
The top-level keys must be exactly actions and reply_necessity.
Do not add extra top-level keys.
Do not array-wrap the turn_plan object. Do not include prose or markdown fences.
Each action.params object must use exactly the keys from param_key_schema for its
domain.operation: all required keys that apply plus only applicable optional keys,
and never extra keys.

Ownership:
- Plan proposes a flat ordered list of requested actions.
- Each action is {domain, operation, params}.
- Params must be keyword/natural references, never IDs, never precise extracted times.
- For each domain.operation, use exactly these param keys from param_key_schema;
  do not invent key names.
- Reminder and social detectors own precise time extraction later in Execute.
- For natural-language reminder.create, raw_text should preserve the exact current user text
  whenever content/time_phrase would omit words that affect extraction, such as
  an explicit duration; omit trigger_time and duration_minutes from natural-language
  create actions. Execute/detector will extract exact times and durations.
- reminder.batch_create items follow the same rule: for natural-language items,
  put natural text in content/time_phrase/text/raw_text; omit trigger_time and duration_minutes from natural-language batch items. Execute/detector will extract exact times and durations.
- When current_input_messages or one user message contains multiple personal
  reminder create requests, emit one reminder.batch_create action with one item per reminder.
  Do not combine multiple reminders into one reminder.create or one detector input.
- For time phrases with explicit period-of-day words (晚上/下午/上午/早上/中午,
  evening/afternoon/morning/noon), keep the period word attached to the time_phrase;
  never strip the phrase down to a bare clock.
- Keep ambiguous clock phrases or ranges with no explicit period marker (e.g.
  "8-9", "8点", "8到9点") verbatim in the time param; do NOT resolve AM/PM or
  dates in Plan — the detector picks the plausible near-future reading in Execute.
- For reminder.list schedule/list/count requests and date-scoped
  reminder.delete/reminder.complete requests (e.g. 今天, 明天, 后天, 周一,
  6月15日, 2026-06-15), put the natural day/date text in date_phrase. Do NOT
  put a day/date phrase in keyword, and do NOT compute
  trigger_after/trigger_before in Plan. Use keyword only for reminder
  topic/content filters like "work" or "跑步".
- For "cancel/delete/complete all reminders on <day>" requests, use
  reminder.delete/reminder.complete with date_phrase and omit match. Execute
  applies the date window to all user-mutable reminders in that day.
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
  re-bind a bare attribute change right after you created or confirmed something
  to another person/friend merely because they appeared earlier or more often in
  conversation_history. It continues the same request you just acted on: same
  domain, operation, target object, and same person/friend. Only switch the person/target
  when the user explicitly names a new one. Never
  downgrade a shared/social-scheduling request to a personal reminder, and never
  treat such a follow-up as converse.
- Empty actions mean converse/greeting/no product action.
""".strip()

DEEPSEEK_TURN_PLANNER_SYSTEM_PROMPT = (TURN_PLANNER_SYSTEM_PROMPT + """

DeepSeek-specific planner contract:
- Reply necessity:
  If actions is non-empty, reply_necessity MUST be reply_needed.
  Use intentional_no_reply only when actions is empty and the latest user input
  is a pure acknowledgement or ending such as "嗯", "ok", "知道了".
- Chinese shared reminder rule:
  "提醒我/帮我记得/让我..." is a personal reminder.
  "提醒/让/叫/通知 + <other person/friend> + <task>" is a shared reminder.
  Example: "明天提醒小王交报告" -> social_scheduling.create_shared_reminder
  with participant "小王", content "交报告", time_phrase "明天".
  Example: "提醒我明天九点跑步" -> reminder.create with content "跑步",
  time_phrase "明天九点".
- Chinese shared reminder cancel rule:
  "取消/删除 + 给/和 + <person> + 的 + <topic>提醒/预约/安排" is
  social_scheduling.cancel_shared_reminder.
  Example: "取消给小王的报告提醒" -> participant "小王", match "报告".
- Availability date granularity:
  For social_scheduling.availability_query, date_phrase is date granularity
  only: 今天, 明天, 后天, 周一, 6月15日, 2026-06-15.
  Do not include period-of-day words such as 上午/下午/晚上 in date_phrase.
  Do not emit local_start or local_end in Planner output.
  Example: "小王明天下午有空吗" -> participant "小王", date_phrase "明天".
- Settings timezone:
  Convert natural city/place names to IANA timezone IDs.
  Example: "把我的时区改成东京" -> timezone_text "Asia/Tokyo".
- Settings preferences:
  Direct preference requests are settings.update_settings.
  Example: "use concise replies" -> preference "concise replies".
  The preference value is the desired style/content, not the command verb.
  Example: "以后简短点" -> preference "简短点".
- Reminder match cleanup:
  For update/delete/complete, match is the topic only. Do not include generic
  object words like "reminder" or "提醒".
  Example: "move the gym reminder to tomorrow night" -> match "gym",
  time_phrase "tomorrow night".
- Calendar import:
  When the user says "导入这个日历" or "import this calendar", use
  calendar_import.import with source "current_attachment"; do not copy the
  natural phrase into source.
- Simple reminder.create output should omit raw_text/text when content and
  time_phrase fully capture the request. Use raw_text/text only when the user
  includes explicit duration, recurrence, or other words needed by Execute.
- For reminder.batch_create items with no explicit time phrase, include only
  content; omit time_phrase, raw_text, and text.
- Memory/proactive toggles:
  Requests to stop remembering preferences are settings.toggle_memory with
  enabled=false; requests to stop proactive reminders are
  settings.toggle_proactive with enabled=false.
- Count/list wording:
  "我现在有几个提醒" means reminder.list with empty params; do not add
  date_phrase "现在".
""").strip()


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
    system_prompt: str = TURN_PLANNER_SYSTEM_PROMPT

    @classmethod
    def from_model(
        cls,
        model: Any,
        *,
        system_prompt: str = TURN_PLANNER_SYSTEM_PROMPT,
    ) -> SiliconFlowPlanner:
        from coke.llm.json_completion import AgnoJSONCompletionClient

        return cls(AgnoJSONCompletionClient(model), system_prompt=system_prompt)

    @classmethod
    def from_config(cls, config: ZAILLMConfig) -> SiliconFlowPlanner:
        return cls.from_model(
            config.create_planner_model(),
            system_prompt=_planner_system_prompt_for_provider(
                getattr(config, "planner_provider", "zai")
            ),
        )

    def plan(self, request: PlanRequest) -> TurnPlan:
        payload = self.client.complete_json(
            system=self.system_prompt,
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
        actions = _required_actions(payload, self.allowed_actions)
        reply_necessity = _reply_necessity_for_actions(
            _required_reply_necessity(payload),
            actions,
        )
        return TurnPlan(actions=actions, reply_necessity=reply_necessity)


def _required_reply_necessity(payload: Mapping[str, Any]) -> ReplyNecessity:
    value = payload.get("reply_necessity")
    if value not in REPLY_NECESSITIES:
        raise PlannerOutputError("invalid reply_necessity")
    return value


def _reply_necessity_for_actions(
    reply_necessity: ReplyNecessity,
    actions: Sequence[ProposedAction],
) -> ReplyNecessity:
    if actions:
        return "reply_needed"
    return reply_necessity


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
    params = _validated_params(domain, operation, params)
    return ProposedAction(
        domain=domain,
        operation=operation,
        params=params,
    )


def _planner_system_prompt_for_provider(provider: str) -> str:
    if provider == "deepseek":
        return DEEPSEEK_TURN_PLANNER_SYSTEM_PROMPT
    return TURN_PLANNER_SYSTEM_PROMPT


def _validated_params(
    domain: str,
    operation: str,
    params: Mapping[str, Any],
) -> Mapping[str, Any]:
    normalized = dict(_drop_empty_optional_values(params))
    spec = PARAM_KEY_SCHEMA[domain][operation]
    allowed_keys = frozenset((*spec.required, *spec.optional))
    unknown_keys = tuple(sorted(key for key in normalized if key not in allowed_keys))
    if unknown_keys:
        LOGGER.warning(
            "planner_unknown_param_keys_dropped",
            extra={
                "domain": domain,
                "operation": operation,
                "dropped_param_keys": unknown_keys,
            },
        )
        normalized = {
            key: value for key, value in normalized.items() if key in allowed_keys
        }
    _reject_precise_time_keys(domain, operation, normalized)
    _validate_timezone_text(domain, operation, normalized)
    _canonicalize_availability_date_phrase(domain, operation, normalized)
    _normalize_calendar_import_source(domain, operation, normalized)
    return normalized


def _drop_empty_optional_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _drop_empty_optional_values(item)
            for key, item in value.items()
            if item is not None and item != ""
        }
    if isinstance(value, list):
        return [_drop_empty_optional_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_drop_empty_optional_values(item) for item in value)
    return value


def _reject_precise_time_keys(
    domain: str,
    operation: str,
    params: Mapping[str, Any],
) -> None:
    if domain != "social_scheduling" or operation not in {
        "create_shared_reminder",
        "update_shared_reminder",
    }:
        return
    precise_keys = sorted(PRECISE_TIME_PARAM_KEYS.intersection(params))
    if precise_keys:
        raise PlannerOutputError(
            "precise time params are not valid Planner output: "
            + ", ".join(precise_keys)
        )


def _validate_timezone_text(
    domain: str,
    operation: str,
    params: Mapping[str, Any],
) -> None:
    if domain != "settings" or operation != "set_timezone":
        return
    timezone_text = params.get("timezone_text")
    if not isinstance(timezone_text, str) or not timezone_text.strip():
        raise PlannerOutputError("invalid timezone_text")
    try:
        ZoneInfo(timezone_text)
    except ZoneInfoNotFoundError as exc:
        raise PlannerOutputError("invalid timezone_text") from exc


def _canonicalize_availability_date_phrase(
    domain: str,
    operation: str,
    params: dict[str, Any],
) -> None:
    if domain != "social_scheduling" or operation != "availability_query":
        return
    date_phrase = params.get("date_phrase")
    if not isinstance(date_phrase, str):
        return
    for period_word in ("上午", "下午", "晚上", "早上", "中午"):
        if date_phrase.endswith(period_word):
            stripped = date_phrase[: -len(period_word)].strip()
            if stripped:
                params["date_phrase"] = stripped
            return


def _normalize_calendar_import_source(
    domain: str,
    operation: str,
    params: dict[str, Any],
) -> None:
    if domain != "calendar_import" or operation != "import":
        return
    source = params.get("source")
    if not isinstance(source, str):
        return
    if source.strip().lower() in {
        "这个日历",
        "這個日曆",
        "this calendar",
        "attached calendar",
    }:
        params["source"] = "current_attachment"


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
