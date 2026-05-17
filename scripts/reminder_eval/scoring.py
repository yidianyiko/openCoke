from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable

from scripts.reminder_eval.dataset import (
    DEFAULT_EXPECTATIONS_PATH,
    ExpectedReminderCreate,
    ReminderNormalPathCase,
    ReminderNormalPathResult,
    load_case_expectations,
)
from scripts.reminder_eval.judges import (
    run_clarification_output_judge,
    run_unconfirmed_reminder_judge,
)

SEVERITY_THRESHOLDS = {"critical": 1.0, "important": 0.95, "nice": 0.80}


def validate_observations(
    case: ReminderNormalPathCase,
    input_status: str,
    outputs: list[dict[str, Any]],
    reminders: list[dict[str, Any]],
    *,
    clarification_judge: Callable[[str, str], bool] | None = None,
    unconfirmed_reminder_judge: Callable[[str], bool] | None = None,
) -> list[str]:
    errors: list[str] = []
    expectation = case_evaluation_expectation(case)
    expected_operation = case_expected_crud_operation(case)
    allow_crud_clarification = case_allows_crud_clarification(case)
    expected_creates = (
        expected_created_reminders_for_case(case)
        if expectation == "crud" and expected_operation == "create"
        else []
    )
    if input_status != "handled":
        errors.append(f"input_{input_status}")
    if not outputs:
        errors.append("no_user_output")
    if expectation == "crud" and expected_operation == "create" and not reminders:
        errors.append("no_reminder_created")
    if not reminders and output_implies_unconfirmed_reminder(
        outputs,
        judge=unconfirmed_reminder_judge,
    ):
        if not output_is_pure_reminder_clarification(
            outputs,
            case_input=case.input,
            judge=clarification_judge,
        ):
            errors.append("user_output_implies_unconfirmed_reminder")
    if expectation in {"clarify", "capability", "discussion", "query"}:
        if reminders:
            errors.append("unexpected_reminder_created")
        if expectation == "discussion" and output_is_pure_reminder_clarification(
            outputs,
            case_input=case.input,
            judge=clarification_judge,
        ):
            errors.append("unexpected_reminder_clarification")
        if expectation == "clarify" and not output_mentions_clarification(
            outputs,
            case_input=case.input,
            judge=clarification_judge,
        ):
            errors.append("user_output_missing_clarification")
        expected_terms = case.metadata.get("expected_clarification_terms") or []
        if expectation == "clarify" and expected_terms:
            output_text = combined_output_text(outputs)
            if not any(str(term) in output_text for term in expected_terms):
                errors.append("user_output_wrong_clarification_focus")
    for reminder in reminders:
        if (
            reminder.get("next_fire_at") is None
            and reminder.get("lifecycle_state") == "active"
        ):
            errors.append("active_reminder_missing_next_fire_at")
        if not reminder.get("title"):
            errors.append("reminder_missing_title")
    if duplicate_reminder_keys(reminders):
        errors.append("duplicate_reminder_created")
    errors.extend(validate_expected_creates(expected_creates, reminders, outputs))
    if (
        expectation == "crud"
        and expected_operation != "create"
        and not (
            allow_crud_clarification
            and output_mentions_crud_operation_clarification(
                outputs, expected_operation
            )
        )
        and not output_mentions_crud_ack(outputs, reminders)
    ):
        errors.append("user_output_missing_crud_ack")
    if reminders and not output_mentions_crud_ack(outputs, reminders):
        errors.append("user_output_missing_crud_ack")
    return errors


def case_expected_crud_operation(case: ReminderNormalPathCase) -> str:
    operation = str(case.metadata.get("expected_operation") or "create").strip().lower()
    return operation or "create"


def case_allows_crud_clarification(case: ReminderNormalPathCase) -> bool:
    return case.metadata.get("allow_clarification") is True


def expected_created_reminders_for_case(
    case: ReminderNormalPathCase,
) -> list[ExpectedReminderCreate]:
    fixture_creates = case.metadata.get("expected_creates")
    if isinstance(fixture_creates, list):
        expected: list[ExpectedReminderCreate] = []
        for item in fixture_creates:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            local_time = item.get("local_time")
            recurring = item.get("recurring")
            title_variants = item.get("title_variants") or ()
            if isinstance(title_variants, str):
                title_variants = (title_variants,)
            elif isinstance(title_variants, list):
                title_variants = tuple(
                    str(variant).strip()
                    for variant in title_variants
                    if str(variant).strip()
                )
            else:
                title_variants = ()
            rrule_contains = _string_tuple(item.get("rrule_contains"))
            output_terms = _string_tuple(item.get("output_terms"))
            expected.append(
                ExpectedReminderCreate(
                    title=title,
                    local_time=str(local_time) if local_time else None,
                    recurring=recurring if isinstance(recurring, bool) else None,
                    local_date=str(item.get("local_date") or "").strip() or None,
                    title_variants=title_variants,
                    rrule_contains=rrule_contains,
                    output_terms=output_terms,
                )
            )
        return expected
    return expected_created_reminders(case.input)


def expected_created_reminders(text: str) -> list[ExpectedReminderCreate]:
    if not str(text or "").strip():
        return []

    normalized = normalize_text(text)
    matches = list(
        re.finditer(
            r"(?<!\d)(?P<hour>\d{1,2})\s*:\s*(?P<minute>\d{1,2})(?!\d)", normalized
        )
    )
    expected: list[ExpectedReminderCreate] = []
    for index, match in enumerate(matches):
        if time_match_starts_range(normalized, match.end()):
            continue
        hour = apply_day_period_to_hour(
            normalized,
            match_start=match.start(),
            hour=int(match.group("hour")),
        )
        minute = int(match.group("minute"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            continue
        segment_start = previous_clause_boundary(normalized, match.start())
        segment_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        )
        recurrence_segment = normalized[segment_start : match.start()]
        title = extract_expected_title(normalized[match.end() : segment_end])
        if not title:
            continue
        expected.append(
            ExpectedReminderCreate(
                title=title,
                local_time=f"{hour:02d}:{minute:02d}:00",
                recurring=segment_has_recurring_signal(recurrence_segment),
            )
        )
    return expected


_TIME_RANGE_SEPARATOR_AFTER_TIME = re.compile(r"^\s*(?:[-~—–]|到|至)")


def time_match_starts_range(text: str, match_end: int) -> bool:
    return bool(_TIME_RANGE_SEPARATOR_AFTER_TIME.search(str(text or "")[match_end:]))


_PM_DAY_PERIOD_PATTERN = re.compile(r"(下午|晚上|今晚|傍晚)")


def apply_day_period_to_hour(text: str, *, match_start: int, hour: int) -> int:
    prefix = str(text or "")[max(0, match_start - 6) : match_start]
    if 1 <= hour < 12 and _PM_DAY_PERIOD_PATTERN.search(prefix):
        return hour + 12
    return hour


def validate_expected_creates(
    expected_creates: list[ExpectedReminderCreate],
    reminders: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
) -> list[str]:
    if not expected_creates:
        return []

    errors: list[str] = []
    if len(reminders) < len(expected_creates):
        errors.append(
            f"expected_reminder_count_mismatch:{len(expected_creates)}>{len(reminders)}"
        )
    if len(reminders) > len(expected_creates):
        errors.append(
            f"unexpected_reminder_count_mismatch:{len(reminders)}>{len(expected_creates)}"
        )

    for expected in expected_creates:
        reminder = find_matching_reminder(expected, reminders)
        if reminder is None:
            errors.append(f"missing_expected_reminder_title:{expected.title}")
            continue
        schedule = reminder.get("schedule") or {}
        if not isinstance(schedule, dict):
            schedule = {}
        actual_local_time = str(schedule.get("local_time") or "")
        if (
            expected.local_time
            and actual_local_time
            and not local_time_matches_expected(expected.local_time, actual_local_time)
        ):
            errors.append(f"expected_reminder_time_mismatch:{expected.title}")
        actual_local_date = str(schedule.get("local_date") or "")
        if (
            expected.local_date
            and actual_local_date
            and actual_local_date != expected.local_date
        ):
            errors.append(f"expected_reminder_date_mismatch:{expected.title}")
        rrule = str(schedule.get("rrule") or "").strip()
        if expected.recurring is True and not rrule:
            errors.append(f"expected_recurring_reminder_not_recurring:{expected.title}")
        if expected.recurring is False and rrule:
            errors.append(f"expected_one_shot_reminder_is_recurring:{expected.title}")
        for token in expected.rrule_contains:
            if token not in rrule:
                errors.append(f"expected_rrule_missing:{expected.title}:{token}")

    output_text = combined_output_text(outputs)
    for expected in expected_creates:
        if not output_mentions_expected_title(output_text, expected):
            errors.append(f"user_output_missing_expected_title:{expected.title}")
        for token in expected.output_terms:
            if token not in output_text:
                errors.append(
                    f"user_output_missing_expected_term:{expected.title}:{token}"
                )
        output_segment = output_segment_for_expected(output_text, expected)
        if not output_segment:
            continue
        if expected.recurring is True and not segment_has_recurring_signal(
            output_segment
        ):
            errors.append(f"user_output_missing_recurring:{expected.title}")
        if expected.recurring is False and segment_has_recurring_signal(output_segment):
            errors.append(f"user_output_unexpected_recurring:{expected.title}")
    return errors


def local_time_matches_expected(
    expected_local_time: str, actual_local_time: str
) -> bool:
    expected = str(expected_local_time or "").strip()
    actual = str(actual_local_time or "").strip()
    if expected == actual:
        return True
    if expected.endswith(":00") and len(expected) >= 5 and len(actual) >= 5:
        return expected[:5] == actual[:5]
    return False


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


_COMMON_TITLE_LEADING_VERBS = frozenset("喝吃学背看写做跑练买拿取打出睡起读来")
_COMMON_TITLE_LEADING_PREFIXES = ("开始", "一下")


def output_mentions_expected_title(
    output_text: str, expected: ExpectedReminderCreate
) -> bool:
    normalized_output = normalize_expected_title(output_text)
    variants = expected_title_variants(expected)
    for variant in variants:
        if variant in normalized_output:
            return True
    for candidate in output_created_title_candidates(output_text):
        if title_matches_expected_variants(candidate, variants):
            return True
    return False


def output_created_title_candidates(output_text: str) -> list[str]:
    normalized = normalize_expected_title(output_text.replace("\n", "；"))
    candidates: list[str] = []
    marker_re = re.compile(
        r"(?:已创建提醒|提醒(?:已经|已)?(?:设好|设置好了|安排好了)|已经安排好了)[:：]?"
    )
    for match in marker_re.finditer(normalized):
        suffix = normalized[match.end() :]
        segment = re.split(r"[，,。；;！？!?]", suffix, maxsplit=1)[0]
        segment = re.sub(
            r"（(?:\d{4}|每天|每日|每周|每月|每两周|循环规则|FREQ=).*",
            "",
            segment,
        )
        candidate = normalize_expected_title(segment)
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def output_segment_for_expected(
    output_text: str,
    expected: ExpectedReminderCreate,
) -> str:
    positions: list[tuple[int, int]] = []
    output_text = normalize_expected_title(output_text.replace("\n", "；"))
    local_time = (expected.local_time or "")[:5]
    if local_time:
        index = output_text.find(local_time)
        if index >= 0:
            positions.append((index, index + len(local_time)))
    for variant in expected_title_variants(expected):
        index = output_text.find(variant)
        if index >= 0:
            positions.append((index, index + len(variant)))
    if not positions:
        return ""

    position = min(index for index, _end in positions)
    matched_end = max(end for index, end in positions if index == position)
    start = 0
    end = len(output_text)
    for separator in "，,。；;！？!?\n":
        left = output_text.rfind(separator, 0, position)
        if left >= start:
            start = left + 1
        right = output_text.find(separator, matched_end)
        if right != -1 and right < end:
            end = right
    left_paren = output_text.rfind("（", start, position + 1)
    right_paren = output_text.rfind("）", start, position + 1)
    if left_paren > right_paren:
        closing = output_text.find("）", position)
        if closing != -1:
            end = max(end, closing + 1)
    next_paren = output_text.find("（", position, end)
    if next_paren != -1:
        closing = output_text.find("）", next_paren)
        if closing != -1:
            end = max(end, closing + 1)
    return output_text[start:end]


def expected_title_variants(expected: ExpectedReminderCreate) -> list[str]:
    raw_titles = (expected.title, *expected.title_variants)
    variants: list[str] = []
    for title in raw_titles:
        normalized_title = normalize_expected_title(title)
        if normalized_title and normalized_title not in variants:
            variants.append(normalized_title)
        for prefix in _COMMON_TITLE_LEADING_PREFIXES:
            if normalized_title.startswith(prefix):
                stripped = normalized_title[len(prefix) :]
                if stripped and stripped not in variants:
                    variants.append(stripped)
        stripped_leading_verb = strip_common_title_leading_verb(normalized_title)
        if stripped_leading_verb and stripped_leading_verb not in variants:
            variants.append(stripped_leading_verb)
        compacted_light_connector = compact_title_light_connectors(normalized_title)
        if compacted_light_connector and compacted_light_connector not in variants:
            variants.append(compacted_light_connector)
        compacted_structural_de = compact_title_structural_de(normalized_title)
        if compacted_structural_de and compacted_structural_de not in variants:
            variants.append(compacted_structural_de)
    return variants


def strip_common_title_leading_verb(normalized_title: str) -> str:
    if len(normalized_title) < 2:
        return ""
    if normalized_title[0] not in _COMMON_TITLE_LEADING_VERBS:
        return ""
    if normalized_title[0] == "来" and len(normalized_title) < 3:
        return ""
    return normalized_title[1:]


def compact_title_light_connectors(normalized_title: str) -> str:
    compacted = re.sub(r"(?:并|然后|再)开始", "", normalized_title)
    compacted = re.sub(r"(?:并|然后|再)(?=[\u4e00-\u9fffA-Za-z0-9])", "", compacted)
    return compacted if compacted != normalized_title else ""


def compact_title_structural_de(normalized_title: str) -> str:
    if len(normalized_title) < 4 or "的" not in normalized_title:
        return ""
    compacted = normalized_title.replace("的", "")
    return compacted if compacted != normalized_title else ""


def _normalized_expected_title_variants(
    expected: ExpectedReminderCreate,
) -> list[str]:
    return expected_title_variants(expected)


def find_matching_reminder(
    expected: ExpectedReminderCreate,
    reminders: list[dict[str, Any]],
) -> dict[str, Any] | None:
    normalized_expected_variants = _normalized_expected_title_variants(expected)
    for reminder in reminders:
        reminder_title = normalize_expected_title(str(reminder.get("title") or ""))
        if not title_matches_expected_variants(
            reminder_title,
            normalized_expected_variants,
        ):
            continue
        if expected.local_time:
            schedule = reminder.get("schedule") or {}
            if not isinstance(schedule, dict):
                schedule = {}
            actual_local_time = str(schedule.get("local_time") or "")
            if actual_local_time and not local_time_matches_expected(
                expected.local_time, actual_local_time
            ):
                continue
            return reminder
        return reminder
    return None


def title_matches_expected_variants(
    reminder_title: str,
    expected_variants: list[str],
) -> bool:
    if reminder_title in expected_variants:
        return True
    for variant in expected_variants:
        if len(variant) >= 3 and (
            reminder_title.startswith(f"{variant}:")
            or reminder_title.startswith(f"{variant}：")
        ):
            return True
        if len(variant) >= 4 and (
            variant in reminder_title or reminder_title in variant
        ):
            return True
    return False


def normalize_text(text: str) -> str:
    return str(text or "").replace("：", ":")


def previous_clause_boundary(text: str, position: int) -> int:
    boundary = 0
    for separator in "，,。；;！？!?\n":
        index = text.rfind(separator, 0, position)
        if index >= boundary:
            boundary = index + 1
    return boundary


def segment_has_recurring_signal(segment: str) -> bool:
    return bool(
        re.search(
            r"每天|每日|每个小时|每小时|每周|每月|"
            r"循环规则|FREQ=|"
            r"每(?:隔)?[一二三四五六七八九十两\d]+(?:个)?(?:分钟|小时|天|日|周|星期|礼拜|月)",
            segment,
        )
    )


def extract_expected_title(suffix: str) -> str:
    candidate = suffix.strip()
    candidate = re.sub(
        r"^(?:你可以|可以|可不可以|能不能|能否|能|麻烦你|麻烦|请你|请|帮我|帮忙)+",
        "",
        candidate,
    ).strip()
    candidate = re.sub(
        r"^(?:提醒我|提醒一下我|提醒|叫我|喊我|让我|帮我|记得|去|要)+", "", candidate
    )
    candidate = re.sub(
        r"^的?提醒(?:一下)?(?:我)?[，,。；;：:\s]+", "", candidate
    ).strip()
    candidate = re.sub(
        r"(?:请)?在?(?:上述|这些|这个|各个)?时间点?提醒我.*$", "", candidate
    ).strip()
    candidate = re.split(r"[，,。；;！？!?\n]", candidate, maxsplit=1)[0]
    candidate = re.sub(
        r"^(?:一个是|一是|二是|三是|还有|再|去|要)+", "", candidate
    ).strip()
    candidate = re.sub(r"(?:呀|啊|哦|呢|么|吗|吧|啦|了)+$", "", candidate).strip()
    return normalize_expected_title(candidate)


def normalize_expected_title(title: str) -> str:
    text = str(title or "").strip().translate(_TITLE_PUNCTUATION_TRANSLATION)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"(?:一下)+$", "", text)
    return re.sub(r"(?:的)?提醒$", "", text)


_TITLE_PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "：": ":",
        "“": '"',
        "”": '"',
        "＂": '"',
        "‘": "'",
        "’": "'",
        "＇": "'",
    }
)


def duplicate_reminder_keys(reminders: list[dict[str, Any]]) -> set[tuple[Any, ...]]:
    seen: set[tuple[Any, ...]] = set()
    duplicates: set[tuple[Any, ...]] = set()
    for reminder in reminders:
        schedule = reminder.get("schedule") or {}
        if not isinstance(schedule, dict):
            schedule = {}
        key = (
            str(reminder.get("title") or "").strip(),
            str(reminder.get("lifecycle_state") or reminder.get("status") or ""),
            str(schedule.get("anchor_at") or ""),
            str(schedule.get("local_date") or ""),
            str(schedule.get("local_time") or ""),
            str(schedule.get("timezone") or ""),
            str(schedule.get("rrule") or ""),
        )
        if key in seen:
            duplicates.add(key)
        else:
            seen.add(key)
    return duplicates


def output_mentions_crud_ack(
    outputs: list[dict[str, Any]],
    reminders: list[dict[str, Any]],
) -> bool:
    output_text = combined_output_text(outputs)
    if not output_text.strip():
        return False

    action_ack = re.search(
        r"(已|已经|成功|失败|没有|未能|无法).{0,12}(创建|设置|新增|更新|修改|取消|删除|完成|安排).{0,12}提醒|"
        r"提醒.{0,12}(已|已经|成功|失败|没有|未能|无法).{0,12}(创建|设置|新增|更新|修改|取消|删除|完成|安排)|"
        r"(创建|设置|新增|更新|修改|取消|删除|完成|安排).{0,12}提醒.{0,12}(已|已经|成功|失败|没有|未能|无法)",
        output_text,
    )
    if action_ack:
        return True
    if (
        "安排上" in output_text or "设好" in output_text or "记好" in output_text
    ) and "提醒" in output_text:
        return True

    titles = [str(reminder.get("title") or "").strip() for reminder in reminders]
    return "提醒" in output_text and any(
        title and title in output_text for title in titles
    )


def combined_output_text(outputs: list[dict[str, Any]]) -> str:
    return "\n".join(
        str(output.get("message") or output.get("content") or "") for output in outputs
    )


def output_mentions_clarification(
    outputs: list[dict[str, Any]],
    *,
    case_input: str = "",
    judge: Callable[[str, str], bool] | None = None,
) -> bool:
    output_text = combined_output_text(outputs)
    if not output_text.strip():
        return False
    if judge is None and deterministic_output_mentions_clarification(
        case_input, output_text
    ):
        return True
    return bool((judge or run_clarification_output_judge)(case_input, output_text))


def deterministic_output_mentions_clarification(
    case_input: str, output_text: str
) -> bool:
    """Recognize clear reminder clarification replies without an LLM judge."""
    normalized = output_text.strip()
    if not normalized:
        return False
    if re.search(
        r"(已创建提醒|提醒(已经|已)?(设好|设置好了|安排好了)|已经安排好了)", normalized
    ):
        return False
    asks_question = bool(
        re.search(
            r"[?？]|请问|告诉我|确认|你希望|你想|想要|要不要|是否|还是|几点|"
            r"什么时间|什么内容|哪天|哪条|哪个|多久|多频繁|频率|提前多久|怎么样|对吗",
            normalized,
        )
    )
    if not asks_question:
        return False

    reminder_word = bool(
        re.search(r"提醒|叫|通知|remind|alarm|notification", normalized, re.I)
    )
    schedule_detail = bool(
        re.search(
            r"几点|日期|哪天|什么时候|频率|多频繁|多久|每小时|每天|"
            r"结束|开始|提前|取消|删除|停止|关掉",
            normalized,
        )
    )
    generic_detail = bool(re.search(r"时间|内容|事情|具体", normalized))
    user_requested_reminder = bool(re.search(r"提醒|叫|通知|remind", case_input, re.I))
    if not user_requested_reminder and not reminder_word:
        return False
    return reminder_word or schedule_detail or generic_detail


def output_is_pure_reminder_clarification(
    outputs: list[dict[str, Any]],
    *,
    case_input: str = "",
    judge: Callable[[str, str], bool] | None = None,
) -> bool:
    output_text = combined_output_text(outputs)
    if not deterministic_output_mentions_clarification(case_input, output_text):
        return False
    if not (judge or run_clarification_output_judge)(case_input, output_text):
        return False
    first_segment = next(
        (
            segment.strip()
            for segment in re.split(r"[\n。.!！?？]+", output_text)
            if segment.strip()
        ),
        "",
    )
    if first_segment and not re.search(
        r"提醒|叫|通知|remind|alarm|notification|几点|什么时候|什么时间|"
        r"什么内容|哪天|多久|多频繁|频率|提前多久",
        first_segment,
        re.IGNORECASE,
    ):
        return False
    return not bool(
        re.search(
            r"已创建提醒|"
            r"提醒(已经|已)?(设好|设置好了|安排好了)|"
            r"已经安排好了|"
            r"我(会|准时|到时候|按时).{0,12}(提醒|通知|叫|喊|催|call|nudge)|"
            r"(到时候|准时|按时).{0,12}(提醒|通知|叫|喊|催)|"
            r"帮你(设|设置|安排|记).{0,12}提醒|"
            r"(记下|记好了|记好|安排上|设好)",
            output_text,
            re.IGNORECASE,
        )
    )


def output_mentions_crud_operation_clarification(
    outputs: list[dict[str, Any]], expected_operation: str
) -> bool:
    if expected_operation in {"delete", "cancel", "remove"}:
        return output_mentions_delete_target_clarification(outputs)
    return output_mentions_clarification(outputs)


def output_mentions_delete_target_clarification(outputs: list[dict[str, Any]]) -> bool:
    output_text = combined_output_text(outputs)
    if not output_text.strip():
        return False
    return bool(
        re.search(
            r"(什么提醒|哪条提醒|哪个提醒|哪一个提醒|哪项提醒|哪一个|哪个|哪条).{0,18}"
            r"(取消|删除|停掉|停止|关掉|不提醒|不用提醒|不用叫|别提醒|不要打扰|别打扰)?"
            r"|(?:取消|删除|停掉|停止|关掉|不提醒|不用提醒|不用叫|别提醒|不要打扰|别打扰)"
            r".{0,24}(哪一个|哪个|哪条|什么提醒|哪项|具体哪)"
            r"|(?:取消|删除|停掉|停止|关掉).{0,30}(具体.{0,8}提醒)"
            r"|(?:是指|你是说).{0,30}"
            r"(?:取消|删除|停掉|停止|关掉|不提醒|不用提醒|不用叫|别提醒|不要打扰|别打扰)"
            r".{0,8}吗"
            r"|(?:取消|删除|停掉|停止|关掉|不提醒|不用提醒|不用叫|别提醒|不要打扰|别打扰)"
            r".{0,30}(?:是说|是指).{0,30}吗"
            r"|which.{0,24}(reminder|alarm|notification).{0,24}(cancel|delete|stop|disable)"
            r"|(?:cancel|delete|stop|disable).{0,24}which.{0,24}(reminder|alarm|notification)",
            output_text,
            re.IGNORECASE,
        )
    )


def output_implies_unconfirmed_reminder(
    outputs: list[dict[str, Any]],
    *,
    judge: Callable[[str], bool] | None = None,
) -> bool:
    output_text = combined_output_text(outputs)
    if not output_text.strip():
        return False
    return bool((judge or run_unconfirmed_reminder_judge)(output_text))


def reminder_case_requires_crud(case: ReminderNormalPathCase) -> bool:
    return case_evaluation_expectation(case) == "crud"


def case_evaluation_expectation(case: ReminderNormalPathCase) -> str:
    explicit_expectation = str(
        case.metadata.get("evaluation_expectation")
        or case.metadata.get("eval_expectation")
        or ""
    ).strip()
    if explicit_expectation:
        return explicit_expectation
    return "discussion"


def summarize(results: list[ReminderNormalPathResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    by_error: dict[str, int] = {}
    expectations = load_case_expectations(DEFAULT_EXPECTATIONS_PATH)
    per_severity: dict[str, dict[str, int | float]] = {
        severity: {"total": 0, "pass": 0, "failed": 0, "pass_rate": 0.0}
        for severity in SEVERITY_THRESHOLDS
    }
    for result in results:
        severity = str(
            expectations.get(result.index, {}).get("severity") or "important"
        ).strip()
        if severity not in per_severity:
            severity = "important"
        per_severity[severity]["total"] += 1
        if result.passed:
            per_severity[severity]["pass"] += 1
        else:
            per_severity[severity]["failed"] += 1
            for error in result.errors:
                by_error[error] = by_error.get(error, 0) + 1
    severity_violations = []
    for severity, stats in per_severity.items():
        if stats["total"] == 0:
            continue
        pass_rate = stats["pass"] / stats["total"]
        stats["pass_rate"] = pass_rate
        threshold = SEVERITY_THRESHOLDS[severity]
        if pass_rate < threshold:
            severity_violations.append(
                f"{severity}: {pass_rate * 100:.1f}% < {threshold * 100:.0f}%"
            )
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0,
        "by_error": dict(sorted(by_error.items())),
        "per_severity": per_severity,
        "severity_thresholds": SEVERITY_THRESHOLDS,
        "severity_violations": severity_violations,
        "failures": [asdict(result) for result in results if not result.passed],
    }
