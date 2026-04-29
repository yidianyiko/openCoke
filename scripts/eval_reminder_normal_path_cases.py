#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.role.bootstrap import ensure_default_character_seeded
from conf.config import CONF
from dao.user_dao import UserDAO

DEFAULT_CASES_PATH = Path("scripts/reminder_test_cases.json")
DEFAULT_EXPECTATIONS_PATH = Path("scripts/reminder_normal_path_expectations.json")


@dataclass(frozen=True)
class ReminderNormalPathCase:
    input: str
    expected_intent: str
    matched_keywords: list[str]
    metadata: dict[str, Any]


@dataclass
class ReminderNormalPathResult:
    index: int
    input: str
    user_id: str
    original_from_user: str
    input_message_id: str
    input_status: str
    passed: bool
    errors: list[str]
    outputs: list[dict[str, Any]]
    reminders: list[dict[str, Any]]
    elapsed_seconds: float


@dataclass(frozen=True)
class CaseBatch:
    offset: int
    limit: int


@dataclass(frozen=True)
class ExpectedReminderCreate:
    title: str
    local_time: str | None
    recurring: bool | None
    title_variants: tuple[str, ...] = ()


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[ReminderNormalPathCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    expectations = load_case_expectations(DEFAULT_EXPECTATIONS_PATH)
    return [
        ReminderNormalPathCase(
            input=str(item["input"]),
            expected_intent=str(item.get("expected_intent", "")),
            matched_keywords=list(item.get("matched_keywords") or []),
            metadata=merge_case_expectation_metadata(
                dict(item.get("metadata") or {}),
                expectations.get(index, {}),
            ),
        )
        for index, item in enumerate(data["test_cases"])
    ]


def load_case_expectations(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = data.get("cases", data)
    return {int(index): dict(value) for index, value in raw_cases.items()}


def merge_case_expectation_metadata(
    metadata: dict[str, Any],
    expectation: dict[str, Any],
) -> dict[str, Any]:
    if not expectation:
        return metadata
    merged = dict(metadata)
    for key in (
        "evaluation_expectation",
        "evaluation_reason",
        "expected_operation",
        "allow_clarification",
        "expected_creates",
    ):
        if key in expectation:
            merged[key] = expectation[key]
    return merged


def select_cases(
    cases: list[ReminderNormalPathCase],
    *,
    offset: int,
    limit: int | None,
) -> list[ReminderNormalPathCase]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    selected = cases[offset:]
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        selected = selected[:limit]
    return selected


def iter_case_batches(
    *,
    total_count: int,
    offset: int,
    limit: int | None,
    batch_size: int,
):
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0")

    remaining_total = max(total_count - offset, 0)
    remaining = remaining_total if limit is None else min(limit, remaining_total)
    next_offset = offset
    while remaining > 0:
        next_limit = min(batch_size, remaining)
        yield CaseBatch(offset=next_offset, limit=next_limit)
        next_offset += next_limit
        remaining -= next_limit


def mongo_client() -> MongoClient:
    mongo_uri = (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )
    return MongoClient(mongo_uri, tz_aware=True)


def seed_normal_path_identities(
    cases: list[ReminderNormalPathCase],
    *,
    offset: int,
    batch_id: str,
    timezone_name: str,
    character_alias: str | None = None,
) -> tuple[str, list[str]]:
    user_dao = UserDAO()
    character_id = ensure_default_character_seeded(
        user_dao=user_dao,
        character_alias=character_alias,
    )
    db = user_dao.db
    user_ids: list[str] = []
    for local_index, case in enumerate(cases):
        case_index = offset + local_index
        user_id = normal_path_user_id(case, case_index, batch_id=batch_id)
        user_ids.append(user_id)
        db.characters.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": normal_path_user_seed(
                    user_id=user_id,
                    case_index=case_index,
                    timezone_name=timezone_name,
                ),
                "$setOnInsert": {"_id": ObjectId(user_id)},
            },
            upsert=True,
        )
        db.relations.update_one(
            {"uid": user_id, "cid": character_id},
            {
                "$set": normal_path_relation_seed(
                    user_id=user_id,
                    character_id=character_id,
                    case_index=case_index,
                ),
                "$setOnInsert": {"_id": ObjectId()},
            },
            upsert=True,
        )
    return character_id, user_ids


def normal_path_user_seed(
    *, user_id: str, case_index: int, timezone_name: str
) -> dict[str, Any]:
    return {
        "name": f"reminder-e2e-user-{case_index}",
        "nickname": f"reminder-e2e-user-{case_index}",
        "status": "normal",
        "timezone": timezone_name,
        "effective_timezone": timezone_name,
        "timezone_source": "reminder_normal_path_eval",
        "timezone_status": "explicit",
        "user_info": {
            "description": "Reminder normal-path E2E user",
            "status": {"place": "test", "action": "chatting"},
        },
    }


def normal_path_relation_seed(
    *, user_id: str, character_id: str, case_index: int
) -> dict[str, Any]:
    return {
        "uid": user_id,
        "cid": character_id,
        "user_info": {
            "realname": "",
            "hobbyname": f"reminder-e2e-user-{case_index}",
            "description": "already-known reminder normal-path eval user",
        },
        "character_info": {
            "longterm_purpose": "Supervise the user's goals and handle reminder CRUD requests.",
            "shortterm_purpose": "Handle the current reminder normal-path eval request directly.",
            "attitude": "focused",
            "status": "空闲",
        },
        "relationship": {
            "description": "already-known reminder normal-path eval contact",
            "closeness": 50,
            "trustness": 50,
            "dislike": 0,
            "status": "空闲",
        },
    }


def normal_path_user_id(
    case: ReminderNormalPathCase, case_index: int, *, batch_id: str
) -> str:
    original_user = str(case.metadata.get("from_user") or "")
    source_id = str(case.metadata.get("source_id") or "")
    seed = f"reminder-normal-path:{batch_id}:{case_index}:{original_user}:{source_id}"
    return hashlib.md5(seed.encode("utf-8")).hexdigest()[:24]


def case_input_timestamp(
    case: ReminderNormalPathCase,
    *,
    timezone_name: str,
    use_case_timestamp: bool = False,
) -> int:
    if not use_case_timestamp:
        return int(time.time())
    raw_timestamp = str(case.metadata.get("timestamp") or "").strip()
    if not raw_timestamp:
        return int(time.time())
    try:
        parsed = datetime.strptime(raw_timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return int(time.time())
    return int(parsed.replace(tzinfo=ZoneInfo(timezone_name)).timestamp())


def submit_cases(
    db,
    cases: list[ReminderNormalPathCase],
    *,
    offset: int,
    character_id: str,
    platform: str,
    batch_id: str,
    timezone_name: str,
    use_case_timestamp: bool,
    transport: str,
) -> dict[int, dict[str, Any]]:
    submitted: dict[int, dict[str, Any]] = {}
    for local_index, case in enumerate(cases):
        case_index = offset + local_index
        user_id = normal_path_user_id(case, case_index, batch_id=batch_id)
        input_timestamp = case_input_timestamp(
            case,
            timezone_name=timezone_name,
            use_case_timestamp=use_case_timestamp,
        )
        submitted_wall_at = datetime.now(timezone.utc)
        metadata = build_input_metadata(
            batch_id=batch_id,
            case_index=case_index,
            case=case,
            transport=transport,
        )
        document = {
            "input_timestamp": input_timestamp,
            "handled_timestamp": input_timestamp,
            "status": "pending",
            "from_user": user_id,
            "platform": platform,
            "chatroom_name": None,
            "to_user": character_id,
            "message_type": "text",
            "message": case.input,
            "metadata": metadata,
        }
        inserted_id = db.inputmessages.insert_one(document).inserted_id
        submitted[case_index] = {
            "case": case,
            "user_id": user_id,
            "input_message_id": str(inserted_id),
            "submitted_at": input_timestamp,
            "submitted_wall_at": submitted_wall_at,
            "batch_id": batch_id,
            "conversation_key": case_conversation_key(
                batch_id=batch_id,
                case_index=case_index,
                transport=transport,
            ),
        }
    return submitted


def build_input_metadata(
    *,
    batch_id: str,
    case_index: int,
    case: ReminderNormalPathCase,
    transport: str,
) -> dict[str, Any]:
    metadata = {
        "source": "reminder_normal_path_eval",
        "batch_id": batch_id,
        "case_index": case_index,
        "original_from_user": case.metadata.get("from_user"),
        "source_id": case.metadata.get("source_id"),
    }
    if transport == "plain":
        return metadata
    if transport != "business-clawscale":
        raise ValueError(f"unsupported transport: {transport}")

    conversation_key = f"{batch_id}-case-{case_index}"
    metadata.update(
        {
            "source": "clawscale",
            "source_eval": "reminder_normal_path_eval",
            "delivery_mode": "request_response",
            "business_protocol": {
                "delivery_mode": "request_response",
                "gateway_conversation_id": conversation_key,
                "business_conversation_key": conversation_key,
                "causal_inbound_event_id": f"{conversation_key}-inbound",
            },
        }
    )
    return metadata


def case_conversation_key(
    *,
    batch_id: str,
    case_index: int,
    transport: str,
) -> str | None:
    if transport != "business-clawscale":
        return None
    return f"{batch_id}-case-{case_index}"


def collect_results(
    db,
    submitted: dict[int, dict[str, Any]],
    *,
    character_id: str,
    platform: str,
    timeout_seconds: float,
) -> list[ReminderNormalPathResult]:
    started = time.monotonic()
    pending = set(submitted)
    results: dict[int, ReminderNormalPathResult] = {}
    while pending and time.monotonic() - started < timeout_seconds:
        for case_index in list(pending):
            item = submitted[case_index]
            input_doc = db.inputmessages.find_one(
                {"_id": ObjectId(item["input_message_id"])}
            )
            if not input_doc or input_doc.get("status") == "pending":
                continue
            result = build_result(
                db,
                case_index=case_index,
                item=item,
                input_status=str(input_doc.get("status") or ""),
                character_id=character_id,
                platform=platform,
                elapsed_seconds=time.monotonic() - started,
            )
            results[case_index] = result
            pending.remove(case_index)
        if pending:
            time.sleep(1)

    for case_index in sorted(pending):
        item = submitted[case_index]
        input_doc = db.inputmessages.find_one(
            {"_id": ObjectId(item["input_message_id"])}
        )
        results[case_index] = build_result(
            db,
            case_index=case_index,
            item=item,
            input_status=str((input_doc or {}).get("status") or "timeout"),
            character_id=character_id,
            platform=platform,
            elapsed_seconds=time.monotonic() - started,
        )
    return [results[index] for index in sorted(results)]


def build_result(
    db,
    *,
    case_index: int,
    item: dict[str, Any],
    input_status: str,
    character_id: str,
    platform: str,
    elapsed_seconds: float,
) -> ReminderNormalPathResult:
    case: ReminderNormalPathCase = item["case"]
    user_id = item["user_id"]
    submitted_at = item["submitted_at"]
    submitted_wall_at = item.get("submitted_wall_at")
    outputs = list(
        db.outputmessages.find(
            build_output_query(
                case_index=case_index,
                item=item,
                user_id=user_id,
                character_id=character_id,
                platform=platform,
                submitted_at=submitted_at,
            )
        ).sort("expect_output_timestamp", 1)
    )
    submitted_dt = (
        submitted_wall_at
        if isinstance(submitted_wall_at, datetime)
        else datetime.fromtimestamp(submitted_at, tz=timezone.utc)
    )
    reminders = list(
        db.reminders.find(
            build_reminder_query(
                db,
                item=item,
                user_id=user_id,
                character_id=character_id,
                platform=platform,
                submitted_dt=submitted_dt,
            )
        ).sort("updated_at", 1)
    )
    errors = validate_observations(case, input_status, outputs, reminders)
    return ReminderNormalPathResult(
        index=case_index,
        input=case.input,
        user_id=user_id,
        original_from_user=str(case.metadata.get("from_user") or ""),
        input_message_id=item["input_message_id"],
        input_status=input_status,
        passed=not errors,
        errors=errors,
        outputs=[json_safe(output) for output in outputs],
        reminders=[json_safe(reminder) for reminder in reminders],
        elapsed_seconds=round(elapsed_seconds, 3),
    )


def build_output_query(
    *,
    case_index: int,
    item: dict[str, Any],
    user_id: str,
    character_id: str,
    platform: str,
    submitted_at: int,
) -> dict[str, Any]:
    query = {
        "platform": platform,
        "from_user": character_id,
        "to_user": user_id,
    }
    batch_id = item.get("batch_id")
    if batch_id:
        query.update(
            {
                "metadata.batch_id": batch_id,
                "metadata.case_index": case_index,
            }
        )
    else:
        query["expect_output_timestamp"] = {"$gte": submitted_at}
    return query


def build_reminder_query(
    db,
    *,
    item: dict[str, Any],
    user_id: str,
    character_id: str,
    platform: str,
    submitted_dt: datetime,
) -> dict[str, Any]:
    query: dict[str, Any] = {"owner_user_id": user_id}
    conversation_ids = resolve_case_conversation_ids(
        db,
        item=item,
        character_id=character_id,
        platform=platform,
    )
    if conversation_ids:
        query["agent_output_target.conversation_id"] = {"$in": conversation_ids}
        return query

    query["$or"] = [
        {"created_at": {"$gte": submitted_dt}},
        {"updated_at": {"$gte": submitted_dt}},
        {"cancelled_at": {"$gte": submitted_dt}},
        {"completed_at": {"$gte": submitted_dt}},
    ]
    return query


def resolve_case_conversation_ids(
    db,
    *,
    item: dict[str, Any],
    character_id: str,
    platform: str,
) -> list[str]:
    conversation_key = item.get("conversation_key")
    if not conversation_key:
        return []

    conversations = list(
        db.conversations.find(
            {
                "platform": platform,
                "chatroom_name": None,
                "talkers.id": {
                    "$all": [
                        f"clawscale:{conversation_key}",
                        f"clawscale-character:{character_id}",
                    ]
                },
            }
        )
    )
    return [
        str(conversation["_id"])
        for conversation in conversations
        if conversation.get("_id")
    ]


def validate_observations(
    case: ReminderNormalPathCase,
    input_status: str,
    outputs: list[dict[str, Any]],
    reminders: list[dict[str, Any]],
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
    if expectation in {"clarify", "capability", "discussion", "query"}:
        if reminders:
            errors.append("unexpected_reminder_created")
        if expectation == "clarify" and not output_mentions_clarification(outputs):
            errors.append("user_output_missing_clarification")
        if expectation == "clarify" and output_implies_unconfirmed_reminder(outputs):
            errors.append("user_output_implies_unconfirmed_reminder")
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
            expected.append(
                ExpectedReminderCreate(
                    title=title,
                    local_time=str(local_time) if local_time else None,
                    recurring=recurring if isinstance(recurring, bool) else None,
                    title_variants=title_variants,
                )
            )
        return expected
    return expected_created_reminders(case.input)


def expected_created_reminders(text: str) -> list[ExpectedReminderCreate]:
    if not explicit_reminder_request(text):
        return []

    normalized = normalize_text(text)
    matches = list(
        re.finditer(
            r"(?<!\d)(?P<hour>\d{1,2})\s*:\s*(?P<minute>\d{1,2})(?!\d)", normalized
        )
    )
    expected: list[ExpectedReminderCreate] = []
    for index, match in enumerate(matches):
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
            and actual_local_time != expected.local_time
        ):
            errors.append(f"expected_reminder_time_mismatch:{expected.title}")
        rrule = str(schedule.get("rrule") or "").strip()
        if expected.recurring is True and not rrule:
            errors.append(f"expected_recurring_reminder_not_recurring:{expected.title}")
        if expected.recurring is False and rrule:
            errors.append(f"expected_one_shot_reminder_is_recurring:{expected.title}")

    output_text = combined_output_text(outputs)
    for expected in expected_creates:
        if not output_mentions_expected_title(output_text, expected):
            errors.append(f"user_output_missing_expected_title:{expected.title}")
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


_COMMON_TITLE_LEADING_VERBS = frozenset("喝吃学背看写做跑练买拿取打出睡起读")


def output_mentions_expected_title(
    output_text: str, expected: ExpectedReminderCreate
) -> bool:
    normalized_output = normalize_expected_title(output_text)
    for variant in expected_title_variants(expected):
        if variant in normalized_output:
            return True
    return False


def output_segment_for_expected(
    output_text: str,
    expected: ExpectedReminderCreate,
) -> str:
    positions: list[int] = []
    output_text = normalize_expected_title(output_text)
    local_time = (expected.local_time or "")[:5]
    if local_time:
        index = output_text.find(local_time)
        if index >= 0:
            positions.append(index)
    for variant in expected_title_variants(expected):
        index = output_text.find(variant)
        if index >= 0:
            positions.append(index)
    if not positions:
        return ""

    position = min(positions)
    start = 0
    end = len(output_text)
    for separator in "，,。；;！？!?\n":
        left = output_text.rfind(separator, 0, position)
        if left >= start:
            start = left + 1
        right = output_text.find(separator, position)
        if right != -1 and right < end:
            end = right
    return output_text[start:end]


def expected_title_variants(expected: ExpectedReminderCreate) -> list[str]:
    raw_titles = (expected.title, *expected.title_variants)
    variants: list[str] = []
    for title in raw_titles:
        normalized_title = normalize_expected_title(title)
        if normalized_title and normalized_title not in variants:
            variants.append(normalized_title)
        if (
            len(normalized_title) >= 2
            and normalized_title[0] in _COMMON_TITLE_LEADING_VERBS
            and normalized_title[1:] not in variants
        ):
            variants.append(normalized_title[1:])
    return variants


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
        if reminder_title not in normalized_expected_variants:
            continue
        if expected.local_time:
            schedule = reminder.get("schedule") or {}
            if not isinstance(schedule, dict):
                schedule = {}
            actual_local_time = str(schedule.get("local_time") or "")
            if actual_local_time and actual_local_time != expected.local_time:
                continue
            return reminder
        return reminder
    return None


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
    return bool(re.search(r"每天|每日|每个小时|每小时|每周|每月", segment))


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
    candidate = re.split(r"[，,。；;！？!?\n]", candidate, maxsplit=1)[0]
    candidate = re.sub(
        r"^(?:一个是|一是|二是|三是|还有|再|去|要)+", "", candidate
    ).strip()
    candidate = re.sub(r"(?:呀|啊|哦|呢|么|吗|吧|啦|了)+$", "", candidate).strip()
    return normalize_expected_title(candidate)


def normalize_expected_title(title: str) -> str:
    text = str(title or "").strip().translate(_TITLE_PUNCTUATION_TRANSLATION)
    return re.sub(r"\s+", "", text)


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


def output_mentions_clarification(outputs: list[dict[str, Any]]) -> bool:
    output_text = combined_output_text(outputs)
    if re.search(
        r"(几点|什么时候|啥时候|什么时间|具体时间|哪天|多久后|提醒内容|提醒什么|要不要|要我|需要我|是否|"
        r"每隔多久|多久一次|多长时间一次|提醒频率|提醒间隔|"
        r"什么提醒|哪条提醒|哪个提醒|"
        r"(?:是说|你是说).{0,30}吗|"
        r"(?:今天|今晚|早上|上午|下午|晚上|明天).{0,20}还是.{0,20}(?:今天|今晚|早上|上午|下午|晚上|明天)|"
        r"(?:是指|你是说).{0,30}(?:取消|删除|不用叫|不用提醒).{0,8}吗|"
        r"(?:取消|删除).{0,12}(?:哪一个|哪个|哪条)|"
        r"when|what time)",
        output_text,
        re.IGNORECASE,
    ):
        return True

    return bool(
        re.search(
            r"(?:半小时|一小时|小时|分钟|每天|每周|频率|间隔|多久|多长时间|每隔).{0,30}"
            r"(?:怎么样|可以吗|行吗|合适吗|确认|觉得可以|觉得呢|想按)|"
            r"(?:怎么样|可以吗|行吗|合适吗|确认|觉得可以|觉得呢|想按).{0,30}"
            r"(?:半小时|一小时|小时|分钟|每天|每周|频率|间隔|多久|多长时间|每隔)",
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


def output_implies_unconfirmed_reminder(outputs: list[dict[str, Any]]) -> bool:
    output_text = combined_output_text(outputs)
    return bool(
        re.search(
            r"(?:准时|到时|到时候|到点|按时).{0,12}(?:催|叫|喊|提醒|通知)"
            r"|(?:每隔|每\s*\d|每半|分钟|小时|半小时|一小时).{0,24}(?:催你|叫你|喊你|提醒你|通知你)",
            output_text,
        )
    )


def explicit_reminder_request(text: str) -> bool:
    normalized = str(text or "").lower()
    if any(
        keyword in normalized
        for keyword in (
            "提醒",
            "remind",
            "闹钟",
            "通知我",
            "每天",
            "每个小时",
            "每周",
            "每月",
        )
    ):
        return True
    if re.search(r"(叫我|喊我)", normalized):
        return actionable_call_me_reminder_request(normalized)
    return False


_ACTIONABLE_IMPLICIT_TIME_PATTERN = re.compile(
    r"(\d{1,2}\s*[:：]\s*[0-5]\d|[零〇一二两三四五六七八九十\d]{1,3}点)"
    r".{0,12}(开始|背书|学习|起床|出门|跑步|乐跑|喝水|吃饭)"
)
_ACTIONABLE_IMPLICIT_DEADLINE_PATTERN = re.compile(
    r"明天下班前.*(?:必须|要|得|需要).*(?:学完|完成|做完|弄完)|"
    r".*(?:学完|完成|做完|弄完).*明天下班前"
)


def actionable_implicit_reminder_request(text: str) -> bool:
    normalized = normalize_text(text)
    return bool(
        _ACTIONABLE_IMPLICIT_TIME_PATTERN.search(normalized)
        or _ACTIONABLE_IMPLICIT_DEADLINE_PATTERN.search(normalized)
    )


_ACTIONABLE_CALL_ME_TIME_PATTERN = re.compile(
    r"(\d{1,2}\s*[:：]\s*[0-5]\d|[零〇一二两三四五六七八九十\d]{1,3}点"
    r"|点半|明早|明天|今天|今晚|早上|上午|中午|下午|晚上|凌晨|一会|分钟|min|小时)"
)
_ACTIONABLE_CALL_ME_TASK_PATTERN = re.compile(
    r"(起床|出门|离开|吃药|吃饭|睡觉|背书|学习|打卡|工作)"
)


def actionable_call_me_reminder_request(text: str) -> bool:
    normalized = normalize_text(text)
    return bool(
        _ACTIONABLE_CALL_ME_TIME_PATTERN.search(normalized)
        or _ACTIONABLE_CALL_ME_TASK_PATTERN.search(normalized)
    )


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
    if explicit_reminder_request(case.input) or actionable_implicit_reminder_request(
        case.input
    ):
        return "crud"
    return "discussion"


def summarize(results: list[ReminderNormalPathResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    by_error: dict[str, int] = {}
    for result in results:
        if result.passed:
            continue
        for error in result.errors:
            by_error[error] = by_error.get(error, 0) + 1
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0,
        "by_error": dict(sorted(by_error.items())),
        "failures": [asdict(result) for result in results if not result.passed],
    }


def run_batch(
    db,
    all_cases: list[ReminderNormalPathCase],
    *,
    offset: int,
    limit: int,
    timeout_seconds: float,
    platform: str,
    batch_id: str,
    character_alias: str | None,
    timezone_name: str,
    use_case_timestamp: bool,
    transport: str,
) -> dict[str, Any]:
    cases = select_cases(all_cases, offset=offset, limit=limit)
    character_id, user_ids = seed_normal_path_identities(
        cases,
        offset=offset,
        batch_id=batch_id,
        timezone_name=timezone_name,
        character_alias=character_alias,
    )
    submitted = submit_cases(
        db,
        cases,
        offset=offset,
        character_id=character_id,
        platform=platform,
        batch_id=batch_id,
        timezone_name=timezone_name,
        use_case_timestamp=use_case_timestamp,
        transport=transport,
    )
    results = collect_results(
        db,
        submitted,
        character_id=character_id,
        platform=platform,
        timeout_seconds=timeout_seconds,
    )
    return {
        "offset": offset,
        "limit": limit,
        "batch_id": batch_id,
        "platform": platform,
        "character_id": character_id,
        "user_ids": user_ids,
        "summary": summarize(results),
        "results": [asdict(result) for result in results],
    }


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run reminder corpus cases through the normal agent path: Mongo "
            "inputmessages -> agent_runner workers -> outputmessages/reminders."
        )
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument(
        "--case-timeout-seconds",
        type=float,
        dest="timeout_seconds",
        help="Alias for --timeout-seconds. Use this for one-case-at-a-time runs.",
    )
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument(
        "--use-case-timestamps",
        action="store_true",
        help=(
            "Use timestamps from the corpus metadata. Disabled by default because "
            "the real worker ignores inputmessages older than its max handle age."
        ),
    )
    parser.add_argument("--platform", default=None)
    parser.add_argument(
        "--transport",
        choices=("business-clawscale", "plain"),
        default="business-clawscale",
    )
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--character-alias", default=None)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    all_cases = load_cases(args.cases)
    run_id = args.batch_id or f"reminder-normal-{uuid.uuid4().hex[:10]}"
    batch_id = run_id
    platform = args.platform or (
        "business" if args.transport == "business-clawscale" else batch_id
    )
    client = mongo_client()
    client.admin.command("ping")
    db = client[CONF["mongodb"]["mongodb_name"]]

    if args.run_all:
        batches = []
        all_results = []
        for batch in iter_case_batches(
            total_count=len(all_cases),
            offset=args.offset,
            limit=args.limit,
            batch_size=args.batch_size,
        ):
            batch_payload = run_batch(
                db,
                all_cases,
                offset=batch.offset,
                limit=batch.limit,
                timeout_seconds=args.timeout_seconds,
                platform=platform,
                batch_id=f"{run_id}-{batch.offset}",
                character_alias=args.character_alias,
                timezone_name=args.timezone,
                use_case_timestamp=args.use_case_timestamps,
                transport=args.transport,
            )
            batches.append(batch_payload)
            all_results.extend(batch_payload["results"])
            if batch_payload["summary"]["failed"] > 0 and not args.continue_on_failure:
                break
        summary = summarize(
            [ReminderNormalPathResult(**result) for result in all_results]
        )
        payload = {
            "cases": str(args.cases),
            "offset": args.offset,
            "limit": args.limit,
            "run_all": True,
            "batch_size": args.batch_size,
            "timeout_seconds": args.timeout_seconds,
            "timezone": args.timezone,
            "use_case_timestamps": args.use_case_timestamps,
            "run_id": run_id,
            "platform": platform,
            "transport": args.transport,
            "summary": summary,
            "batches": batches,
            "results": all_results,
        }
    else:
        batch_payload = run_batch(
            db,
            all_cases,
            offset=args.offset,
            limit=args.limit,
            timeout_seconds=args.timeout_seconds,
            platform=platform,
            batch_id=batch_id,
            character_alias=args.character_alias,
            timezone_name=args.timezone,
            use_case_timestamp=args.use_case_timestamps,
            transport=args.transport,
        )
        payload = {
            "cases": str(args.cases),
            "offset": args.offset,
            "limit": args.limit,
            "run_all": False,
            "batch_size": args.batch_size,
            "timeout_seconds": args.timeout_seconds,
            "timezone": args.timezone,
            "use_case_timestamps": args.use_case_timestamps,
            "transport": args.transport,
            **batch_payload,
        }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
