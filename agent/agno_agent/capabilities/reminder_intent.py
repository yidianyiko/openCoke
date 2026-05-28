from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent.agno_agent.adapters.reminder_command_executor import (
    ReminderCommandExecutor,
)
from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.domain_results import (
    DomainError,
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
)
from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
from agent.agno_agent.tools.reminder_protocol import visible_reminder_tool

logger = logging.getLogger(__name__)
_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS = 30.0


def _float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning(
            "%s=%r is not a valid float; using %.1f", name, raw_value, default
        )
        return default
    return value if value > 0 else default


def _agent_runtime_reminder_detect_timeout_seconds() -> float:
    return _float_env(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS",
        _DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS,
    )


def _create_reminder_detector() -> Any:
    from agno.agent import Agent

    from agent.agno_agent.model_factory import create_llm_model
    from agent.prompt.agent_instructions_prompt import (
        DESCRIPTION_REMINDER_DETECT,
        INSTRUCTIONS_REMINDER_DETECT,
    )

    return Agent(
        model=create_llm_model(role="reminder_detect", max_tokens=8000),
        description=DESCRIPTION_REMINDER_DETECT,
        instructions=INSTRUCTIONS_REMINDER_DETECT,
        output_schema=ReminderDetectDecision,
        structured_outputs=True,
        markdown=False,
    )


def _decision_from_response(response: Any) -> Any:
    if isinstance(response, ReminderDetectDecision):
        return response
    content = getattr(response, "content", response)
    if isinstance(content, ReminderDetectDecision):
        return content
    if isinstance(content, Mapping):
        try:
            return ReminderDetectDecision.model_validate(content)
        except Exception:
            logger.warning("ReminderDetectAgent returned invalid structured mapping")
            return "ReminderDetectInvalidStructuredOutput"
    if isinstance(content, str) and content.strip():
        try:
            return ReminderDetectDecision.model_validate_json(content)
        except Exception:
            return content
    return content


def _decision_value(decision: Any, field: str) -> Any:
    if isinstance(decision, Mapping):
        return decision.get(field)
    get_value = getattr(decision, "get", None)
    if callable(get_value):
        return get_value(field)
    return getattr(decision, field, None)


class ReminderIntentPort:
    def __init__(
        self,
        *,
        detector_agent: Any | None = None,
        command_executor: Any | None = None,
    ) -> None:
        self.detector_agent = detector_agent
        self.command_executor = command_executor or ReminderCommandExecutor(
            visible_reminder_tool.entrypoint
        )

    async def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> DomainExecutionResult:
        detector_run_context = run_context
        session_state = {
            "user": {
                "id": run_context.user.id,
                "timezone": run_context.user.timezone,
            },
            "character": {"id": run_context.character.id},
            "conversation": {"id": run_context.conversation.id},
            "platform": run_context.platform,
        }
        try:
            detector_agent = self.detector_agent or _create_reminder_detector()
            response = await asyncio.wait_for(
                detector_agent.arun(
                    input=build_reminder_intent_input(
                        input_message,
                        detector_run_context,
                    ),
                    session_state=session_state,
                    session_id=run_context.conversation.id,
                ),
                timeout=_agent_runtime_reminder_detect_timeout_seconds(),
            )
            decision = _decision_from_response(response)
        except asyncio.TimeoutError:
            logger.error(
                "ReminderDetectAgent timed out in single-Agent runtime: timeout=%.1fs",
                _agent_runtime_reminder_detect_timeout_seconds(),
            )
            return _timeout_clarification_result()
        if _decision_value(decision, "intent_type") in {"discussion", "none"}:
            return _no_action_discussion_result()
        if _is_unrecognized_decision(decision):
            return _invalid_decision_clarification_result()
        if _is_clarification_decision(decision):
            reason = str(
                _decision_value(decision, "clarification_reason") or ""
            ).strip()
            builder = _CLARIFICATION_TEMPLATES.get(reason)
            if builder is None:
                return _invalid_decision_clarification_result()
            return builder()
        if not _should_execute_decision(decision):
            return _invalid_decision_clarification_result()
        return self.command_executor.execute(decision, run_context)


def _should_execute_decision(decision: Any) -> bool:
    intent_type = _decision_value(decision, "intent_type")
    action = _decision_value(decision, "action")
    return intent_type == "crud" or (intent_type == "query" and action == "list")


def _is_unrecognized_decision(decision: Any) -> bool:
    if decision is None:
        return False
    if isinstance(decision, (str, bytes)):
        return bool(str(decision).strip())
    intent_type = _decision_value(decision, "intent_type")
    action = _decision_value(decision, "action")
    if intent_type in {"crud", "clarify", "query", "discussion", "none"}:
        return False
    if action in {
        "",
        None,
        "create",
        "update",
        "delete",
        "cancel",
        "complete",
        "batch",
        "list",
    }:
        return False
    return True


_BARE_CLOCK_PATTERN = re.compile(
    r"(\d{1,2}\s*[:：∶.]\s*\d{1,2}|\d{1,2}\s*(?:点|时)|"
    r"[零一二两三四五六七八九十百半]+\s*(?:点|时))"
)
_EXPLICIT_DATE_PATTERN = re.compile(
    r"(今天|今日|今晚|今早|明天|明早|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{1,4}\s*年|\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|\d{1,2}[/-]\d{1,2})",
    re.IGNORECASE,
)
_INPUT_MESSAGE_PREFIX_PATTERN = re.compile(r"^(?:（[^）]*）\s*)+")
_REMINDER_VERB_PATTERN = re.compile(
    r"提醒我|叫我|喊我|通知我|监督我|问我|检查我|"
    r"remind me|call me|notify me|nudge me",
    re.IGNORECASE,
)
_RELATIVE_DELAY_PATTERN = re.compile(
    r"(?:过\s*(?P<prefix_amount>\d+|[零〇一二两三四五六七八九十]{1,4})\s*"
    r"(?P<prefix_unit>minutes?|mins?|分钟|分|小时|个小时|天|日))"
    r"|(?:(?P<suffix_amount>\d+|[零〇一二两三四五六七八九十]{1,4})\s*"
    r"(?P<suffix_unit>minutes?|mins?|分钟|分|小时|个小时|天|日)\s*"
    r"(?:后|之后|以后|later))"
    r"|(?:(?P<timer_amount>\d+|[零〇一二两三四五六七八九十]{1,4})\s*"
    r"(?P<timer_unit>minutes?|mins?|分钟|分|小时|个小时|天|日)\s*"
    r"(?:计时|倒计时))",
    re.IGNORECASE,
)
_SINGLE_BARE_CLOCK_EXTRACTION_PATTERN = re.compile(
    r"(?P<hour>\d{1,2})\s*[:：.]\s*(?P<minute>\d{1,2})"
    r"|(?P<hour_only>\d{1,2})\s*(?:点|时)(?P<half>半)?"
    r"(?:\s*差\s*(?P<hour_only_minus_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分?"
    r"|\s*(?:过)?\s*(?P<hour_only_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分?)?"
    r"|(?P<chinese_hour>[零〇一二两三四五六七八九十]{1,3})\s*(?:点|时)(?P<chinese_half>半)?"
    r"(?:\s*差\s*(?P<chinese_minus_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分?"
    r"|\s*(?:过)?\s*(?P<chinese_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分?)?"
)
_PM_DAY_PERIOD_PATTERN = re.compile(r"(下午|晚上|今晚|傍晚|每晚)")
_AM_DAY_PERIOD_PATTERN = re.compile(r"(早上|早晨|上午|凌晨|清晨|今早|明早)")
_VAGUE_DATE_EVIDENCE_PATTERN = re.compile(
    r"(?:今天|今日|明天|明早|后天|大后天|"
    r"(?:下下|下|本|这)?(?:周|星期|礼拜)[一二三四五六日天1-7]|"
    r"\d{1,4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|"
    r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|"
    r"\d{1,2}[/-]\d{1,2})"
)
_EXPLICIT_PAST_DATE_WORD_PATTERN = re.compile(r"(?:昨天|昨日|前天|大前天)")
_CLOCK_WITH_SECONDS_PATTERN = re.compile(
    r"(?P<hour>\d{1,2})\s*[:：.]\s*(?P<minute>\d{1,2})\s*[:：.]\s*(?P<second>\d{1,2})"
    r"|(?P<hour_only>\d{1,2})\s*(?:点|时)\s*"
    r"(?P<hour_only_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分\s*"
    r"(?P<hour_only_second>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*秒"
    r"|(?P<chinese_hour>[零〇一二两三四五六七八九十]{1,3})\s*(?:点|时)\s*"
    r"(?P<chinese_minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*分\s*"
    r"(?P<chinese_second>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*秒"
)


def _explicit_past_time_evidence(
    current_user_text: str,
    run_context: AgentRunContext,
) -> bool:
    if _EXPLICIT_PAST_DATE_WORD_PATTERN.search(current_user_text):
        return _has_exact_clock_evidence(current_user_text)
    clock = _extract_single_clock_evidence(current_user_text)
    if clock is None:
        return False
    hour, minute, second = clock
    current_local = _current_local_datetime(run_context)
    if re.search(r"(?:今天|今日|今早|今晚)", current_user_text):
        candidate = current_local.replace(
            hour=hour,
            minute=minute,
            second=second,
            microsecond=0,
        )
        runtime_local = _runtime_local_datetime(run_context)
        runtime_candidate = runtime_local.replace(
            hour=hour,
            minute=minute,
            second=second,
            microsecond=0,
        )
        return candidate <= current_local or runtime_candidate <= runtime_local
    explicit_date = _explicit_local_date_from_text(current_user_text, current_local)
    if explicit_date is None:
        return False
    candidate = datetime.combine(
        explicit_date,
        current_local.timetz().replace(
            hour=hour,
            minute=minute,
            second=second,
            microsecond=0,
        ),
    )
    return candidate <= current_local


def _has_exact_clock_evidence(current_user_text: str) -> bool:
    return bool(
        _CLOCK_WITH_SECONDS_PATTERN.search(current_user_text)
        or _SINGLE_BARE_CLOCK_EXTRACTION_PATTERN.search(current_user_text)
    )


def _extract_single_clock_evidence(
    current_user_text: str,
) -> tuple[int, int, int] | None:
    seconds_match = _single_seconds_clock_match(current_user_text)
    if seconds_match is not None:
        return seconds_match
    matches = list(_SINGLE_BARE_CLOCK_EXTRACTION_PATTERN.finditer(current_user_text))
    if len(matches) != 1:
        return None
    parsed = _parse_bare_clock_match(current_user_text, matches[0])
    if parsed is None:
        return None
    hour, minute = parsed
    return hour, minute, 0


def _single_seconds_clock_match(current_user_text: str) -> tuple[int, int, int] | None:
    matches = list(_CLOCK_WITH_SECONDS_PATTERN.finditer(current_user_text))
    if len(matches) != 1:
        return None
    match = matches[0]
    if match.group("hour") is not None:
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        second = int(match.group("second"))
    elif match.group("hour_only") is not None:
        hour = int(match.group("hour_only"))
        minute = _parse_clock_minute(match.group("hour_only_minute") or "")
        second = _parse_clock_minute(match.group("hour_only_second") or "")
    else:
        hour = _parse_chinese_hour(match.group("chinese_hour") or "")
        minute = _parse_chinese_minute(match.group("chinese_minute") or "")
        second = _parse_chinese_minute(match.group("chinese_second") or "")
    if hour is None or minute is None or second is None:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    prefix = current_user_text[max(0, match.start() - 6) : match.start()]
    if 1 <= hour < 12 and _PM_DAY_PERIOD_PATTERN.search(prefix):
        hour += 12
    return hour, minute, second


def _current_local_datetime(run_context: AgentRunContext) -> datetime:
    try:
        timezone = ZoneInfo(run_context.user.timezone or "UTC")
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    current_time = run_context.current_time
    return (
        current_time.replace(tzinfo=timezone)
        if current_time.tzinfo is None
        else current_time.astimezone(timezone)
    )


def _runtime_local_datetime(run_context: AgentRunContext) -> datetime:
    current_time = run_context.current_time
    return (
        current_time.astimezone() if current_time.tzinfo is not None else current_time
    )


def _explicit_local_date_from_text(
    current_user_text: str,
    current_local: datetime,
) -> date | None:
    match = re.search(
        r"(?:(?P<year>\d{4})\s*年\s*)?(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*[日号]?",
        current_user_text,
    )
    if match is None:
        match = re.search(
            r"(?P<month>\d{1,2})[/-](?P<day>\d{1,2})",
            current_user_text,
        )
    if match is None:
        return None
    explicit_year = match.groupdict().get("year")
    if explicit_year:
        year = int(explicit_year)
    elif re.search(r"明年|next\s+year", current_user_text, re.IGNORECASE):
        year = current_local.year + 1
    else:
        year = current_local.year
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _latest_user_turn_text(input_message: str) -> str:
    parts = re.split(r"（[^）]*发来了文本消息）", input_message)
    if len(parts) > 1:
        return parts[-1].strip()
    return _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()


def _parse_bare_clock_match(
    current_user_text: str,
    match: re.Match[str],
) -> tuple[int, int] | None:
    prefix = current_user_text[max(0, match.start() - 6) : match.start()]
    period_applied = False
    if match.group("hour") is not None:
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
    elif match.group("hour_only") is not None:
        hour = int(match.group("hour_only"))
        minus_text = match.group("hour_only_minus_minute")
        minute_text = match.group("hour_only_minute")
        if minus_text:
            parsed_minus = _parse_clock_minute(minus_text)
            if parsed_minus is None or not (1 <= parsed_minus <= 59):
                return None
            if 1 <= hour < 12 and _PM_DAY_PERIOD_PATTERN.search(prefix):
                hour += 12
                period_applied = True
            hour, minute = _subtract_clock_minutes(hour, parsed_minus)
        else:
            minute = (
                _parse_clock_minute(minute_text)
                if minute_text
                else (30 if match.group("half") else 0)
            )
    else:
        hour = _parse_chinese_hour(match.group("chinese_hour") or "")
        minus_text = match.group("chinese_minus_minute")
        minute_text = match.group("chinese_minute")
        if hour is None:
            return None
        if minus_text:
            parsed_minus = _parse_clock_minute(minus_text)
            if parsed_minus is None or not (1 <= parsed_minus <= 59):
                return None
            if 1 <= hour < 12 and _PM_DAY_PERIOD_PATTERN.search(prefix):
                hour += 12
                period_applied = True
            hour, minute = _subtract_clock_minutes(hour, parsed_minus)
        else:
            minute = (
                _parse_chinese_minute(minute_text)
                if minute_text
                else (30 if match.group("chinese_half") else 0)
            )
    if hour is None or minute is None or not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    if not period_applied and 1 <= hour < 12 and _PM_DAY_PERIOD_PATTERN.search(prefix):
        hour += 12
    return hour, minute


_CHINESE_DIGIT_VALUES = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _parse_chinese_hour(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text in _CHINESE_DIGIT_VALUES:
        return _CHINESE_DIGIT_VALUES[text]
    if text == "十":
        return 10
    if text.startswith("十"):
        suffix = text[1:]
        if suffix in _CHINESE_DIGIT_VALUES:
            return 10 + _CHINESE_DIGIT_VALUES[suffix]
        return None
    if text.endswith("十"):
        prefix = text[:-1]
        if prefix in _CHINESE_DIGIT_VALUES:
            return _CHINESE_DIGIT_VALUES[prefix] * 10
        return None
    if "十" in text:
        prefix, suffix = text.split("十", 1)
        if prefix in _CHINESE_DIGIT_VALUES and suffix in _CHINESE_DIGIT_VALUES:
            return _CHINESE_DIGIT_VALUES[prefix] * 10 + _CHINESE_DIGIT_VALUES[suffix]
    return None


def _parse_chinese_minute(value: str) -> int | None:
    text = str(value or "").strip()
    if len(text) == 2 and text[0] in {"零", "〇"} and text[1] in _CHINESE_DIGIT_VALUES:
        return _CHINESE_DIGIT_VALUES[text[1]]
    return _parse_chinese_hour(text)


def _parse_clock_minute(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return _parse_chinese_minute(text)


def _subtract_clock_minutes(hour: int, minutes_before: int) -> tuple[int, int]:
    total_minutes = (hour % 24) * 60 - minutes_before
    total_minutes %= 24 * 60
    return total_minutes // 60, total_minutes % 60


def _single_relative_delay(current_user_text: str) -> timedelta | None:
    matches = list(_RELATIVE_DELAY_PATTERN.finditer(current_user_text))
    if len(matches) != 1:
        return None
    match = matches[0]
    amount_text = (
        match.group("prefix_amount")
        or match.group("suffix_amount")
        or match.group("timer_amount")
        or ""
    )
    amount = (
        int(amount_text) if amount_text.isdigit() else _parse_chinese_hour(amount_text)
    )
    if amount is None or amount <= 0:
        return None
    unit = (
        match.group("prefix_unit")
        or match.group("suffix_unit")
        or match.group("timer_unit")
        or ""
    )
    if unit.lower() in {"分钟", "分", "min", "mins", "minute", "minutes"}:
        return timedelta(minutes=amount)
    if unit in {"小时", "个小时"}:
        return timedelta(hours=amount)
    if unit in {"天", "日"}:
        return timedelta(days=amount)
    return None


def _decision_has_recurring_create(decision: Any) -> bool:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "create":
        return bool(str(_decision_value(decision, "rrule") or "").strip())
    if action != "batch":
        return False
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        if (
            str(_operation_value(operation, "action") or "").strip() == "create"
            and str(_operation_value(operation, "rrule") or "").strip()
        ):
            return True
    return False


def _operation_value(operation: Any, field: str) -> Any:
    if isinstance(operation, Mapping):
        return operation.get(field)
    return getattr(operation, field, None)


def _is_clarification_decision(decision: Any) -> bool:
    return _decision_value(decision, "intent_type") == "clarify"


def _high_frequency_input_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="这个高频提醒要从什么时候开始，持续到什么时候结束？请告诉我开始时间和截止时间。",
        missing_fields=("trigger_at", "end_time"),
        safety_boundary="high_frequency_requires_end",
    )


def _timeout_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="提醒设置还没完成。请确认具体提醒时间和提醒内容。",
        missing_fields=("title", "trigger_at"),
        safety_boundary=None,
        error=DomainError(
            code="ReminderDetectTimeout",
            message="Reminder detect agent timed out",
            retryable=True,
            detail={},
        ),
    )


def _no_action_discussion_result() -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="no_action",
        operations=(),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="direct_answer",
            required_facts=(),
            allow_rephrase=True,
        ),
    )


def _deadline_without_trigger_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="这是截止时间。你想在这个时间之前的什么时候提醒你？",
        missing_fields=("trigger_at",),
        safety_boundary="deadline_without_trigger",
    )


def _date_only_missing_time_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="你想在那天几点提醒你？",
        missing_fields=("trigger_at",),
        safety_boundary="date_only_missing_time",
    )


def _ambiguous_time_range_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="这个时间范围不够精确，你想在具体几点提醒你？",
        missing_fields=("trigger_at",),
        safety_boundary="ambiguous_time_range",
    )


def _completion_condition_missing_time_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="我不能自动知道你什么时候完成。请告诉我具体什么时候提醒你。",
        missing_fields=("trigger_at",),
        safety_boundary="completion_condition_missing_time",
    )


def _advance_offset_missing_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="你想提前多久提醒你？",
        missing_fields=("advance_offset",),
        safety_boundary="advance_offset_missing",
    )


def _missing_reminder_content_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="你想让我提醒你做什么？",
        missing_fields=("title",),
        safety_boundary="missing_reminder_content",
    )


def _invalid_decision_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="提醒设置还没完成。请确认具体提醒时间和提醒内容。",
        missing_fields=("title", "trigger_at"),
        safety_boundary=None,
        error=DomainError(
            code="ReminderDetectInvalidDecision",
            message="Reminder detect agent returned an invalid decision",
            retryable=True,
            detail={},
        ),
    )


def _invalid_past_schedule_result() -> DomainExecutionResult:
    message = "这个提醒时间已经过去了，请告诉我一个未来的时间。"
    error = DomainError(
        code="InvalidSchedule",
        message=message,
        retryable=False,
        detail={"reason": "past_one_shot"},
    )
    return DomainExecutionResult(
        domain="reminder",
        outcome="failed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=False,
                effect="none",
                entity_type="reminder",
                entity_id=None,
                facts={"visible_summary": message},
                error=error,
            ),
        ),
        missing_fields=(),
        safety_boundary="explicit_past",
        reply_contract=ReplyContract(
            intent="report_failure",
            required_facts=(),
            allow_rephrase=True,
        ),
        error=error,
    )


def _needs_clarification_result(
    *,
    summary: str,
    missing_fields: Sequence[str],
    safety_boundary: str | None,
    error: DomainError | None = None,
) -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="needs_clarification",
        operations=(),
        missing_fields=missing_fields,
        safety_boundary=safety_boundary,
        reply_contract=ReplyContract(
            intent="ask_clarification",
            required_facts=(),
            allow_rephrase=True,
        ),
        error=error,
    )


def _ambiguous_request_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="请补充提醒信息。",
        missing_fields=("target_reminder",),
        safety_boundary="ambiguous_request",
    )


_CLARIFICATION_TEMPLATES = {
    "date_only_missing_time": _date_only_missing_time_clarification_result,
    "ambiguous_time_range": _ambiguous_time_range_clarification_result,
    "completion_condition_missing_time": _completion_condition_missing_time_clarification_result,
    "status_only_content": _missing_reminder_content_clarification_result,
    "deadline_without_trigger": _deadline_without_trigger_clarification_result,
    "advance_offset_missing": _advance_offset_missing_clarification_result,
    "high_frequency_requires_end": _high_frequency_input_clarification_result,
    "missing_reminder_content": _missing_reminder_content_clarification_result,
    "ambiguous_request": _ambiguous_request_clarification_result,
}
