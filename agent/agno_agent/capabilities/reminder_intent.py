from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from types import SimpleNamespace
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
        if _should_reject_quoted_title_loss(input_message, decision):
            return _invalid_decision_clarification_result()
        if _is_clarification_decision(decision):
            reason = str(
                _decision_value(decision, "clarification_reason") or ""
            ).strip()
            builder = _CLARIFICATION_TEMPLATES.get(reason)
            if builder is None:
                return _invalid_decision_clarification_result()
            return builder()
        if _should_execute_decision(decision) and _is_bounded_cadence_deadline_loss(
            input_message, decision
        ):
            return _bounded_cadence_deadline_loss_clarification_result(decision)
        if _should_execute_decision(decision) and _is_unbounded_high_frequency_cadence(
            decision, input_message=input_message
        ):
            return _unbounded_high_frequency_cadence_clarification_result(decision)
        if not _should_execute_decision(decision):
            return _invalid_decision_clarification_result()
        decision = _normalize_create_title_from_user_text(input_message, decision)
        decision = _drop_ungoverned_batch_plan_operations(input_message, decision)
        decision = _drop_batch_operations_without_local_schedule_evidence(
            input_message, decision
        )
        if _should_reject_title_schedule_evidence_leak(decision):
            return _invalid_decision_clarification_result()
        if _should_reject_weekday_mismatch(input_message, decision, run_context):
            return _invalid_decision_clarification_result()
        if _should_reject_ungoverned_single_create_title(input_message, decision):
            return _invalid_decision_clarification_result()
        if _should_reject_day_of_month_mismatch(input_message, decision, run_context):
            return _invalid_decision_clarification_result()
        if _should_reject_missing_scheduled_clauses(input_message, decision):
            return _invalid_decision_clarification_result()
        decision = _normalize_create_duration_from_title(decision)
        return self.command_executor.execute(decision, run_context)


def _should_execute_decision(decision: Any) -> bool:
    intent_type = _decision_value(decision, "intent_type")
    action = _decision_value(decision, "action")
    return intent_type == "crud" or (intent_type == "query" and action == "list")


def _normalize_explicit_list_title_query(value: str) -> str | None:
    query = re.sub(
        r"^(?:我|我的|现在|当前|所有|全部|今天|今日|今晚|今早|明天|明日|设过|有|哪些)+",
        "",
        str(value or "").strip(),
    )
    query = re.sub(r"(?:的|相关的)$", "", query.strip())
    query = " ".join(query.split())
    if query in {"", "我", "我的", "什么", "有什么", "有哪些", "哪些"}:
        return None
    if any(marker in query for marker in ("什么", "哪些")):
        return None
    return query or None


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


def _should_reject_quoted_title_loss(input_message: str, decision: Any) -> bool:
    if not _should_execute_decision(decision):
        return False
    quoted_segments = _quoted_segments(input_message)
    if not quoted_segments:
        return False
    titles = _decision_titles(decision)
    if not titles:
        return False
    return any(
        segment and not any(segment in title for title in titles)
        for segment in quoted_segments
    )


_BARE_CLOCK_PATTERN = re.compile(
    r"(\d{1,2}\s*[:：∶.]\s*\d{1,2}|\d{1,2}\s*(?:点|时)|"
    r"[零一二两三四五六七八九十百半]+\s*(?:点|时))"
)
_EXPLICIT_DATE_PATTERN = re.compile(
    r"(今天|今日|今晚|今早|明天|明早|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{1,4}\s*年|\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|\d{1,2}[/-]\d{1,2})",
    re.IGNORECASE,
)
_STANDALONE_DAY_OF_MONTH_PATTERN = re.compile(r"(?<!\d)\d{1,2}\s*[日号](?!\d)")
_WEEKDAY_RANGE_PATTERN = re.compile(
    r"(?:周|星期|礼拜)([一二三四五六日天1-7])\s*(?:到|至|-|—|~)\s*"
    r"(?:周|星期|礼拜)([一二三四五六日天1-7])"
)
_INPUT_MESSAGE_PREFIX_PATTERN = re.compile(r"^(?:（[^）]*）\s*)+")
_REMINDER_VERB_PATTERN = re.compile(
    r"提醒我|叫我|喊我|通知我|监督我|问我|检查我|"
    r"remind me|call me|notify me|nudge me",
    re.IGNORECASE,
)
_SCHEDULE_BACK_REFERENCE_PATTERN = re.compile(
    r"上述这些时间|上面这些时间|这些时间|这几个时间|以上时间|上述时间"
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
_DURATION_SUFFIX_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?i)\s*(?:for\s+)?(?:半小时|半个小时|半钟头|half(?:\s+an?)?\s+hour(?:s)?)\s*$"
        ),
        "half_hour",
    ),
    (
        re.compile(r"(?i)\s*(?:for\s+)?(?:一刻钟|quarter(?:\s+of)?\s+an?\s+hour)\s*$"),
        "quarter_hour",
    ),
    (
        re.compile(
            r"(?i)\s*(?:for\s+)?(?:三刻钟|three\s+quarters?\s+of\s+an?\s+hour)\s*$"
        ),
        "three_quarter_hour",
    ),
    (
        re.compile(
            r"(?i)\s*(?:for\s+)?(?P<amount>\d+|[零〇一二两三四五六七八九十百]{1,4})\s*"
            r"(?P<unit>个小时|小时|hours?|hrs?|h|分钟|分|minutes?|mins?|min|m)\s*$"
        ),
        "numeric_duration",
    ),
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


def _extract_single_clock_evidence(current_user_text: str) -> tuple[int, int, int] | None:
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
    return current_time.astimezone() if current_time.tzinfo is not None else current_time


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


# kept for Phase 3 cleanup: _normalize_create_title_from_user_text still references this helper.
def _extract_create_title_after_reminder_verb_verbatim(text: str) -> str:
    match = _REMINDER_VERB_PATTERN.search(text)
    if match is None:
        return ""
    title = text[match.end() :]
    title = re.split(r"[。.!！？?；;]", title, maxsplit=1)[0]
    return title.strip()


def _normalize_create_title_from_user_text(input_message: str, decision: Any) -> Any:
    if str(_decision_value(decision, "action") or "").strip() != "create":
        return decision
    current_title = str(_decision_value(decision, "title") or "").strip()
    if not current_title:
        return decision
    current_user_text = _latest_user_turn_text(input_message)
    user_title = _extract_create_title_after_reminder_verb_verbatim(current_user_text)
    if not user_title or user_title == current_title:
        return decision
    if (
        user_title.casefold().startswith("to ")
        or _BARE_CLOCK_PATTERN.search(user_title)
        or _VAGUE_DATE_EVIDENCE_PATTERN.search(user_title)
    ):
        return decision
    compact_current = re.sub(r"\s+", "", current_title)
    compact_user = re.sub(r"\s+", "", user_title)
    if current_title in user_title or (
        compact_current and compact_current in compact_user
    ):
        return _copy_decision_with_value(decision, "title", user_title)
    return decision


# kept for Phase 3 cleanup: _normalize_* helpers and runtime safety path still reference this helper.
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


def _input_has_relative_delay_and_preceding_task_content(input_message: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    delay_match = _RELATIVE_DELAY_PATTERN.search(current_user_text)
    reminder_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    if delay_match is None or reminder_match is None:
        return False
    prefix = current_user_text[: min(delay_match.start(), reminder_match.start())]
    prefix = re.sub(
        r"(?:\bok+\b|好的|好|行|嗯|请|麻烦|帮我|记得|please|[,，。；;、\s])+",
        "",
        prefix,
        flags=re.IGNORECASE,
    )
    return bool(prefix)


_NEXT_WHOLE_HOUR_PATTERN = re.compile(
    r"(?:下个|下一个|下次|next)\s*(?:整点|whole hour)",
    re.IGNORECASE,
)


def _input_has_next_whole_hour_reference(input_message: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    return bool(_NEXT_WHOLE_HOUR_PATTERN.search(current_user_text))


def _input_has_clocked_task_before_trailing_reminder_verb(input_message: str) -> bool:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    reminder_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    if reminder_match is None:
        return False
    suffix = current_user_text[reminder_match.end() :]
    suffix = re.sub(
        r"(?:一下|我|吧|哦|噢|啊|呀|啦|哈|呢|么|吗|[。.!！?？~～,，；;\s])+",
        "",
        suffix,
    )
    if suffix:
        return False
    prefix = current_user_text[: reminder_match.start()]
    if not _BARE_CLOCK_PATTERN.search(prefix):
        return False
    task_text = _BARE_CLOCK_PATTERN.sub("", prefix, count=1)
    task_text = re.sub(
        r"(?:我要|我会|我想|准备|打算|开始|请|麻烦|帮我|[,，。；;、\s])+",
        "",
        task_text,
    )
    task_text = re.sub(
        r"(?:今天|今日|今晚|明天|明早|后天|上午|早上|下午|晚上|中午|凌晨|"
        r"点|时|分|半|左右|的时候)+",
        "",
        task_text,
    )
    return bool(task_text.strip())


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


def _parse_duration_minutes_from_title(title: str) -> tuple[str, int | None]:
    normalized = re.sub(r"[。.!！？?；;、,，]+$", "", str(title or "").strip()).strip()
    if not normalized:
        return "", None

    for pattern, kind in _DURATION_SUFFIX_PATTERNS:
        match = pattern.search(normalized)
        if match is None or match.end() != len(normalized):
            continue

        if kind == "half_hour":
            duration_minutes = 30
        elif kind == "quarter_hour":
            duration_minutes = 15
        elif kind == "three_quarter_hour":
            duration_minutes = 45
        else:
            amount_text = str(match.group("amount") or "").strip()
            if amount_text.isdigit():
                amount = int(amount_text)
            else:
                amount = _parse_chinese_hour(amount_text)
            if amount is None or amount <= 0:
                continue
            unit = str(match.group("unit") or "").strip().lower()
            if unit in {"小时", "个小时", "hour", "hours", "hr", "hrs", "h"}:
                duration_minutes = amount * 60
            elif unit in {"分钟", "分", "minute", "minutes", "min", "mins", "m"}:
                duration_minutes = amount
            else:
                continue

        stripped = normalized[: match.start()].rstrip()
        stripped = re.sub(r"[。.!！？?；;、,，]+$", "", stripped).strip()
        if not stripped:
            continue
        return stripped, duration_minutes

    return normalized, None


_DEFAULT_TASK_DURATION_MINUTES = 60


def _duration_minutes_or_default(value: Any) -> int:
    if isinstance(value, bool):
        return _DEFAULT_TASK_DURATION_MINUTES
    if isinstance(value, int) and value > 0:
        return value
    return _DEFAULT_TASK_DURATION_MINUTES


def _normalize_create_duration_from_title(decision: Any) -> Any:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "batch":
        operations = list(_decision_value(decision, "operations") or [])
        if not operations:
            return decision
        normalized_operations = []
        changed = False
        for operation in operations:
            if str(_operation_value(operation, "action") or "").strip() != "create":
                normalized_operations.append(operation)
                continue
            title = str(_operation_value(operation, "title") or "").strip()
            stripped_title, title_duration_minutes = _parse_duration_minutes_from_title(
                title
            )
            duration_minutes = _duration_minutes_or_default(
                _operation_value(operation, "duration_minutes")
                if title_duration_minutes is None
                else title_duration_minutes
            )
            updated_operation = operation
            if stripped_title and stripped_title != title:
                updated_operation = _copy_operation_with_value(
                    updated_operation, "title", stripped_title
                )
                changed = True
            if (
                _operation_value(updated_operation, "duration_minutes")
                != duration_minutes
            ):
                updated_operation = _copy_operation_with_value(
                    updated_operation, "duration_minutes", duration_minutes
                )
                changed = True
            normalized_operations.append(updated_operation)
        if changed:
            return _copy_decision_with_operations(decision, normalized_operations)
        return decision

    if action != "create":
        return decision

    title = str(_decision_value(decision, "title") or "").strip()
    stripped_title, title_duration_minutes = _parse_duration_minutes_from_title(title)
    duration_minutes = _duration_minutes_or_default(
        _decision_value(decision, "duration_minutes")
        if title_duration_minutes is None
        else title_duration_minutes
    )

    updated_decision = decision
    if stripped_title and stripped_title != title:
        updated_decision = _copy_decision_with_value(
            updated_decision, "title", stripped_title
        )
    if _decision_value(updated_decision, "duration_minutes") != duration_minutes:
        updated_decision = _copy_decision_with_value(
            updated_decision, "duration_minutes", duration_minutes
        )
    return updated_decision


def _subtract_clock_minutes(hour: int, minutes_before: int) -> tuple[int, int]:
    total_minutes = (hour % 24) * 60 - minutes_before
    total_minutes %= 24 * 60
    return total_minutes // 60, total_minutes % 60


def _copy_decision_with_value(decision: Any, field: str, value: Any) -> Any:
    if isinstance(decision, Mapping):
        return {**dict(decision), field: value}
    model_dump = getattr(decision, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        data[field] = value
        return SimpleNamespace(**data)
    try:
        data = vars(decision).copy()
    except TypeError:
        return decision
    data[field] = value
    return SimpleNamespace(**data)


def _copy_operation_with_value(operation: Any, field: str, value: Any) -> Any:
    if isinstance(operation, Mapping):
        return {**dict(operation), field: value}
    model_dump = getattr(operation, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        data[field] = value
        return SimpleNamespace(**data)
    try:
        data = vars(operation).copy()
    except TypeError:
        return operation
    data[field] = value
    return SimpleNamespace(**data)


def _drop_ungoverned_batch_plan_operations(input_message: str, decision: Any) -> Any:
    if str(_decision_value(decision, "action") or "").strip() != "batch":
        return decision
    operations = list(_decision_value(decision, "operations") or [])
    if len(operations) <= 1:
        return decision
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if _SCHEDULE_BACK_REFERENCE_PATTERN.search(current_user_text):
        return decision
    reminder_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    if reminder_match is not None:
        reminder_start = reminder_match.start()
        kept_operations = []
        changed = False
        for operation in operations:
            if str(_operation_value(operation, "action") or "").strip() != "create":
                kept_operations.append(operation)
                continue
            title = str(_operation_value(operation, "title") or "").strip()
            if not title:
                kept_operations.append(operation)
                continue
            first_title_at = current_user_text.find(title)
            if first_title_at < 0:
                kept_operations.append(operation)
                continue
            later_title_at = current_user_text.find(title, reminder_start)
            if first_title_at < reminder_start and later_title_at < 0:
                changed = True
                continue
            kept_operations.append(operation)
        if changed and kept_operations:
            decision = _copy_decision_with_operations(decision, kept_operations)
    return _drop_ungoverned_cadence_task_operations(current_user_text, decision)


def _drop_batch_operations_without_local_schedule_evidence(
    input_message: str, decision: Any
) -> Any:
    if str(_decision_value(decision, "action") or "").strip() != "batch":
        return decision
    operations = list(_decision_value(decision, "operations") or [])
    if len(operations) <= 1:
        return decision
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    kept_operations = []
    changed = False
    for operation in operations:
        if str(_operation_value(operation, "action") or "").strip() != "create":
            kept_operations.append(operation)
            continue
        title = str(_operation_value(operation, "title") or "").strip()
        if not title or current_user_text.find(title) < 0:
            kept_operations.append(operation)
            continue
        if _title_has_local_schedule_context(current_user_text, title):
            kept_operations.append(operation)
            continue
        changed = True
    if not changed or not kept_operations:
        return decision
    return _copy_decision_with_operations(decision, kept_operations)


def _drop_ungoverned_cadence_task_operations(text: str, decision: Any) -> Any:
    if str(_decision_value(decision, "action") or "").strip() != "batch":
        return decision
    operations = list(_decision_value(decision, "operations") or [])
    if len(operations) <= 1:
        return decision
    has_high_frequency_recurring_create = any(
        str(_operation_value(operation, "action") or "").strip() == "create"
        and _is_high_frequency_rrule(str(_operation_value(operation, "rrule") or ""))
        for operation in operations
    )
    if not has_high_frequency_recurring_create:
        return decision

    kept_operations = []
    changed = False
    for operation in operations:
        if str(_operation_value(operation, "action") or "").strip() != "create":
            kept_operations.append(operation)
            continue
        title = str(_operation_value(operation, "title") or "").strip()
        rrule = str(_operation_value(operation, "rrule") or "").strip()
        if rrule and not _is_high_frequency_rrule(rrule):
            kept_operations.append(operation)
            continue
        if title and (
            _title_has_local_reminder_verb_context(text, title)
            or (rrule and _title_has_local_cadence_context(text, title))
        ):
            kept_operations.append(operation)
            continue
        changed = True
    if not changed or not kept_operations:
        return decision
    return _copy_decision_with_operations(decision, kept_operations)


def _title_has_local_reminder_verb_context(text: str, title: str) -> bool:
    start = 0
    while True:
        position = text.find(title, start)
        if position < 0:
            return False
        clause_start = _previous_clause_boundary(text, position)
        clause = text[clause_start : position + len(title)]
        if _REMINDER_VERB_PATTERN.search(clause):
            return True
        start = position + len(title)


def _title_has_local_cadence_context(text: str, title: str) -> bool:
    start = 0
    while True:
        position = text.find(title, start)
        if position < 0:
            return False
        clause_start = _previous_clause_boundary(text, position)
        clause_end = _next_clause_boundary(text, position + len(title))
        clause = text[clause_start:clause_end]
        if _is_high_frequency_evidence(clause):
            return True
        start = position + len(title)


def _title_has_local_schedule_context(text: str, title: str) -> bool:
    start = 0
    while True:
        position = text.find(title, start)
        if position < 0:
            return False
        clause_start = _previous_clause_boundary(text, position)
        clause_end = _next_clause_boundary(text, position + len(title))
        clause = text[clause_start:clause_end]
        if _BARE_CLOCK_PATTERN.search(clause) or _RELATIVE_DELAY_PATTERN.search(clause):
            return True
        start = position + len(title)


def _previous_clause_boundary(text: str, position: int) -> int:
    boundary = 0
    for separator in "，,。；;！？!?\n":
        index = text.rfind(separator, 0, position)
        if index >= boundary:
            boundary = index + 1
    return boundary


def _next_clause_boundary(text: str, position: int) -> int:
    boundary = len(text)
    for separator in "，,。；;！？!?\n":
        index = text.find(separator, position)
        if index != -1 and index < boundary:
            boundary = index
    return boundary


def _copy_decision_with_operations(decision: Any, operations: list[Any]) -> Any:
    if isinstance(decision, Mapping):
        return {**dict(decision), "operations": operations}
    model_dump = getattr(decision, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        data["operations"] = operations
        return SimpleNamespace(**data)
    try:
        data = vars(decision).copy()
    except TypeError:
        return decision
    data["operations"] = operations
    return SimpleNamespace(**data)


def _should_reject_ungoverned_single_create_title(
    input_message: str, decision: Any
) -> bool:
    if str(_decision_value(decision, "action") or "").strip() != "create":
        return False
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    reminder_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    if reminder_match is None:
        return False
    title = str(_decision_value(decision, "title") or "").strip()
    if not title:
        return False
    first_title_at = current_user_text.find(title)
    if first_title_at < 0 or first_title_at >= reminder_match.start():
        return False
    if _input_has_relative_delay_and_preceding_task_content(input_message):
        return False
    if _input_has_clocked_task_before_trailing_reminder_verb(input_message):
        return False
    if _input_has_next_whole_hour_reference(input_message):
        return False
    if current_user_text.find(title, reminder_match.start()) >= 0:
        return False
    return not _title_has_local_reminder_verb_context(current_user_text, title)


def _should_reject_title_schedule_evidence_leak(decision: Any) -> bool:
    if str(_decision_value(decision, "action") or "").strip() != "create":
        return False
    title = str(_decision_value(decision, "title") or "").strip()
    return bool(title and re.search(r"提前", title))


_CHINESE_WEEKDAY_INDEX = {
    "一": 0,
    "1": 0,
    "二": 1,
    "2": 1,
    "三": 2,
    "3": 2,
    "四": 3,
    "4": 3,
    "五": 4,
    "5": 4,
    "六": 5,
    "6": 5,
    "日": 6,
    "天": 6,
    "7": 6,
}
_EXPLICIT_WEEKDAY_PATTERN = re.compile(
    r"(?:下周|本周|这周|这星期|下星期|星期|周)([一二三四五六日天1-7])"
)


def _should_reject_weekday_mismatch(
    input_message: str,
    decision: Any,
    run_context: AgentRunContext,
) -> bool:
    if str(_decision_value(decision, "action") or "").strip() != "create":
        return False
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if _WEEKDAY_RANGE_PATTERN.search(current_user_text):
        return False
    weekday = _explicit_weekday_index(current_user_text)
    if weekday is None:
        return False
    trigger_at = str(_decision_value(decision, "trigger_at") or "").strip()
    if not trigger_at:
        return False
    try:
        parsed = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(run_context.user.timezone or "UTC"))
        except ZoneInfoNotFoundError:
            return False
    else:
        try:
            parsed = parsed.astimezone(ZoneInfo(run_context.user.timezone or "UTC"))
        except ZoneInfoNotFoundError:
            return False
    return parsed.weekday() != weekday


def _explicit_weekday_index(text: str) -> int | None:
    match = _EXPLICIT_WEEKDAY_PATTERN.search(text)
    if match is None:
        return None
    return _CHINESE_WEEKDAY_INDEX.get(match.group(1))


def _decision_has_create_operation(decision: Any) -> bool:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "create":
        return True
    if action != "batch":
        return False
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        if str(_operation_value(operation, "action") or "").strip() == "create":
            return True
    return False


def _should_reject_day_of_month_mismatch(
    input_message: str,
    decision: Any,
    run_context: AgentRunContext,
) -> bool:
    expected_day = _explicit_schedule_day_of_month_before_reminder_verb(input_message)
    if expected_day is None:
        return False
    try:
        timezone = ZoneInfo(run_context.user.timezone or "UTC")
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    for trigger_at in _create_trigger_values(decision):
        try:
            parsed = datetime.fromisoformat(str(trigger_at).replace("Z", "+00:00"))
        except Exception:
            continue
        if parsed.tzinfo is None:
            local = parsed.replace(tzinfo=timezone)
        else:
            local = parsed.astimezone(timezone)
        if local.day != expected_day:
            return True
    return False


def _should_reject_missing_scheduled_clauses(input_message: str, decision: Any) -> bool:
    expected_count = _explicit_scheduled_clause_count(input_message)
    if expected_count < 2:
        return False
    return _decision_create_operation_count(decision) < expected_count


def _explicit_scheduled_clause_count(input_message: str) -> int:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not current_user_text:
        return 0
    if not (
        _REMINDER_VERB_PATTERN.search(current_user_text)
        or re.search(r"询问我|告诉我|问问我|check in|report", current_user_text, re.I)
    ):
        return 0
    normalized = re.sub(
        r"(\d{1,2}[:：]\d{2})\s*[-–—]\s*\d{1,2}[:：]\d{2}",
        r"\1",
        current_user_text,
    )
    matches = list(_SINGLE_BARE_CLOCK_EXTRACTION_PATTERN.finditer(normalized))
    if _SCHEDULE_BACK_REFERENCE_PATTERN.search(current_user_text):
        return len({re.sub(r"\s+", "", match.group(0)) for match in matches})
    governed_matches: set[str] = set()
    for index, match in enumerate(matches):
        next_start = (
            matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        )
        clause = normalized[match.end() : next_start]
        if _REMINDER_VERB_PATTERN.search(clause) or re.search(
            r"询问我|告诉我|问问我|check in|report",
            clause,
            re.I,
        ):
            governed_matches.add(re.sub(r"\s+", "", match.group(0)))
    return len(governed_matches)


def _decision_create_operation_count(decision: Any) -> int:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "create":
        return 1
    if action != "batch":
        return 0
    return sum(
        1
        for operation in (_decision_value(decision, "operations") or [])
        if str(_operation_value(operation, "action") or "").strip() == "create"
    )


def _explicit_schedule_day_of_month_before_reminder_verb(
    input_message: str,
) -> int | None:
    current_user_text = _INPUT_MESSAGE_PREFIX_PATTERN.sub("", input_message).strip()
    if not current_user_text:
        return None
    verb_match = _REMINDER_VERB_PATTERN.search(current_user_text)
    search_end = verb_match.start() if verb_match else len(current_user_text)
    prefix = current_user_text[:search_end]
    for match in _STANDALONE_DAY_OF_MONTH_PATTERN.finditer(prefix):
        after_day = prefix[match.end() :].lstrip()
        if after_day.startswith(("前", "之前", "以前")):
            continue
        try:
            day = int(re.search(r"\d{1,2}", match.group(0)).group(0))
        except Exception:
            continue
        if not 1 <= day <= 31:
            continue
        if _BARE_CLOCK_PATTERN.search(after_day):
            return day
    return None


def _create_trigger_values(decision: Any) -> tuple[str, ...]:
    action = str(_decision_value(decision, "action") or "").strip()
    if action == "create":
        trigger_at = str(_decision_value(decision, "trigger_at") or "").strip()
        return (trigger_at,) if trigger_at else ()
    if action != "batch":
        return ()
    values: list[str] = []
    for operation in _decision_value(decision, "operations") or []:
        if str(_operation_value(operation, "action") or "").strip() != "create":
            continue
        trigger_at = str(_operation_value(operation, "trigger_at") or "").strip()
        if trigger_at:
            values.append(trigger_at)
    return tuple(values)


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


def _quoted_segments(text: str) -> tuple[str, ...]:
    pairs = (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"))
    segments: list[str] = []
    for opening, closing in pairs:
        start = 0
        while True:
            left = text.find(opening, start)
            if left < 0:
                break
            right = text.find(closing, left + len(opening))
            if right < 0:
                break
            segment = text[left : right + len(closing)].strip()
            if segment:
                segments.append(segment)
            start = right + len(closing)
    return tuple(segments)


def _decision_titles(decision: Any) -> tuple[str, ...]:
    titles: list[str] = []
    title = str(_decision_value(decision, "title") or "").strip()
    if title:
        titles.append(title)
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        operation_title = _decision_value(operation, "title")
        if operation_title:
            titles.append(str(operation_title).strip())
    return tuple(title for title in titles if title)


def _is_clarification_decision(decision: Any) -> bool:
    return _decision_value(decision, "intent_type") == "clarify"


def _is_unbounded_high_frequency_cadence(
    decision: Any,
    *,
    input_message: str = "",
) -> bool:
    if _input_has_high_frequency_without_deadline(input_message):
        return True
    if _has_explicit_deadline(decision):
        return False
    rrules = [str(_decision_value(decision, "rrule") or "")]
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        rrules.append(str(_decision_value(operation, "rrule") or ""))
    if any(_is_bounded_high_frequency_rrule(rrule) for rrule in rrules):
        return False
    if any(_is_unbounded_high_frequency_rrule(rrule) for rrule in rrules):
        return True
    evidence = str(_decision_value(decision, "schedule_evidence") or "")
    if _decision_value(
        decision, "schedule_basis"
    ) == "explicit_cadence" and _is_high_frequency_evidence(evidence):
        return True
    return False


def _has_explicit_deadline(decision: Any) -> bool:
    if str(_decision_value(decision, "deadline_at") or "").strip():
        return True
    operations = _decision_value(decision, "operations") or []
    return any(
        str(_decision_value(operation, "deadline_at") or "").strip()
        for operation in operations
    )


def _is_bounded_cadence_deadline_loss(input_message: str, decision: Any) -> bool:
    if not _input_has_bounded_cadence_deadline(input_message):
        return False
    if _has_explicit_deadline(decision):
        return False
    return _has_unbounded_recurring_rrule(decision)


def _has_unbounded_recurring_rrule(decision: Any) -> bool:
    rrules = [str(_decision_value(decision, "rrule") or "")]
    operations = _decision_value(decision, "operations") or []
    for operation in operations:
        rrules.append(str(_decision_value(operation, "rrule") or ""))
    return any(_is_unbounded_rrule(rrule) for rrule in rrules)


def _is_unbounded_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    if "FREQ=" not in rule:
        return False
    return "UNTIL=" not in rule and "COUNT=" not in rule


def _input_has_bounded_cadence_deadline(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    cadence_tokens = (
        "每天",
        "每日",
        "每晚",
        "每早",
        "每周",
        "每月",
        "每年",
        "每小时",
        "每个整点",
        "整点",
        "每分钟",
        "每隔",
        "daily",
        "weekly",
        "monthly",
        "hourly",
        "every ",
    )
    deadline_tokens = (
        "截止",
        "持续到",
        "结束",
        "之前",
        "以前",
        "until",
        "before",
        "through",
        " by ",
    )
    deadline_patterns = (
        r"(?:到|直到)\s*(?:今天|今晚|明天|明晚|晚上|下午|中午|早上|上午)?\s*\d{1,2}\s*(?::\s*\d{1,2}|点)",
        r"(?:到|直到)\s*(?:今天|今晚|明天|明晚|晚上|下午|中午|早上|上午)?\s*[零一二两三四五六七八九十百半]+\s*点",
        r"\d{1,2}\s*月\s*\d{1,2}\s*(?:号|日)?\s*前",
        r"\d{1,2}\s*(?:号|日)\s*前",
        r"\d{1,2}\s*(?::\s*\d{1,2}|点)\s*前",
    )
    has_deadline = any(token in normalized for token in deadline_tokens) or any(
        re.search(pattern, normalized) for pattern in deadline_patterns
    )
    return any(token in normalized for token in cadence_tokens) and has_deadline


def _is_high_frequency_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    return "FREQ=HOURLY" in rule or "FREQ=MINUTELY" in rule


def _is_unbounded_high_frequency_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    if not _is_high_frequency_rrule(rule):
        return False
    return "UNTIL=" not in rule and "COUNT=" not in rule


def _is_bounded_high_frequency_rrule(rrule: str) -> bool:
    rule = str(rrule or "").upper()
    if not _is_high_frequency_rrule(rule):
        return False
    return "UNTIL=" in rule or "COUNT=" in rule


def _is_high_frequency_evidence(evidence: str) -> bool:
    text = str(evidence or "").strip().lower()
    tokens = (
        "hourly",
        "minutely",
        "every hour",
        "every minute",
        "每小时",
        "每个小时",
        "每一小时",
        "每分钟",
        "每个整点",
        "整点",
    )
    interval_high_frequency = re.search(
        r"每隔\s*(?:\d+|[零〇一二两三四五六七八九十半]+)?\s*(?:分钟|分|小时|个小时|整点)",
        text,
    )
    return any(token in text for token in tokens) or bool(interval_high_frequency)


def _input_has_high_frequency_without_deadline(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if _input_has_next_whole_hour_reference(normalized):
        return False
    if not _is_high_frequency_evidence(normalized):
        return False
    deadline_tokens = (
        "到",
        "截止",
        "结束",
        "持续到",
        "until",
        "through",
        "ending",
        "ends",
        "end at",
    )
    return not any(token in normalized for token in deadline_tokens)


def _unbounded_high_frequency_cadence_clarification_result(
    decision: Any,
) -> DomainExecutionResult:
    title = str(_decision_value(decision, "title") or "").strip()
    if not title:
        operations = _decision_value(decision, "operations") or []
        for operation in operations:
            title = str(_decision_value(operation, "title") or "").strip()
            if title:
                break
    subject = title or "这个高频提醒"
    return _needs_clarification_result(
        summary=f"{subject}要持续到什么时候结束？请告诉我截止时间。",
        missing_fields=("end_time",),
        safety_boundary="high_frequency_requires_end",
        required_questions=("end_time",),
    )


def _bounded_cadence_deadline_loss_clarification_result(
    decision: Any,
) -> DomainExecutionResult:
    title = str(_decision_value(decision, "title") or "").strip()
    subject = title or "这个重复提醒"
    return _needs_clarification_result(
        summary=f"{subject}有截止条件，请确认截止日期和最后一次提醒时间。",
        missing_fields=("end_time",),
        safety_boundary="high_frequency_requires_end",
        required_questions=("end_time",),
    )


def _high_frequency_input_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="这个高频提醒要从什么时候开始，持续到什么时候结束？请告诉我开始时间和截止时间。",
        missing_fields=("trigger_at", "end_time"),
        safety_boundary="high_frequency_requires_end",
        required_questions=("trigger_at", "end_time"),
    )


def _timeout_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="提醒设置还没完成。请确认具体提醒时间和提醒内容。",
        missing_fields=("title", "trigger_at"),
        safety_boundary=None,
        required_questions=("title", "trigger_at"),
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
            required_questions=(),
            prohibited_claims=("reminder_created",),
            allow_rephrase=True,
        ),
    )


def _deadline_without_trigger_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="这是截止时间。你想在这个时间之前的什么时候提醒你？",
        missing_fields=("trigger_at",),
        safety_boundary="deadline_without_trigger",
        required_questions=("trigger_at",),
    )


def _date_only_missing_time_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="你想在那天几点提醒你？",
        missing_fields=("trigger_at",),
        safety_boundary="date_only_missing_time",
        required_questions=("trigger_at",),
    )


def _ambiguous_time_range_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="这个时间范围不够精确，你想在具体几点提醒你？",
        missing_fields=("trigger_at",),
        safety_boundary="ambiguous_time_range",
        required_questions=("trigger_at",),
    )


def _completion_condition_missing_time_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="我不能自动知道你什么时候完成。请告诉我具体什么时候提醒你。",
        missing_fields=("trigger_at",),
        safety_boundary="completion_condition_missing_time",
        required_questions=("trigger_at",),
    )


def _advance_offset_missing_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="你想提前多久提醒你？",
        missing_fields=("advance_offset",),
        safety_boundary="advance_offset_missing",
        required_questions=("advance_offset",),
    )


def _missing_reminder_content_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="你想让我提醒你做什么？",
        missing_fields=("title",),
        safety_boundary="missing_reminder_content",
        required_questions=("title",),
    )


def _invalid_decision_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="提醒设置还没完成。请确认具体提醒时间和提醒内容。",
        missing_fields=("title", "trigger_at"),
        safety_boundary=None,
        required_questions=("title", "trigger_at"),
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
            required_questions=(),
            prohibited_claims=("reminder_created",),
            allow_rephrase=True,
        ),
        error=error,
    )


def _needs_clarification_result(
    *,
    summary: str,
    missing_fields: Sequence[str],
    safety_boundary: str | None,
    required_questions: Sequence[str],
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
            required_questions=required_questions,
            prohibited_claims=("reminder_created",),
            allow_rephrase=True,
        ),
        error=error,
    )


def _ambiguous_request_clarification_result() -> DomainExecutionResult:
    return _needs_clarification_result(
        summary="请补充提醒信息。",
        missing_fields=("target_reminder",),
        safety_boundary="ambiguous_request",
        required_questions=("target_reminder",),
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
