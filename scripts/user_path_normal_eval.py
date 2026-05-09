#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from bson import ObjectId
from pydantic import BaseModel, Field
from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.role.bootstrap import ensure_default_character_seeded
from conf.config import CONF
from dao.user_dao import UserDAO

DEFAULT_CASES_PATH = Path("scripts/reminder_test_cases.json")
DEFAULT_EXPECTATIONS_PATH = Path("scripts/reminder_normal_path_expectations.json")
UNCONFIRMED_REMINDER_JUDGE_TIMEOUT_SECONDS = float(
    os.environ.get("REMINDER_NORMAL_PATH_JUDGE_TIMEOUT_SECONDS", "20")
)
CLARIFICATION_OUTPUT_JUDGE_TIMEOUT_SECONDS = float(
    os.environ.get(
        "REMINDER_NORMAL_PATH_CLARIFICATION_JUDGE_TIMEOUT_SECONDS",
        os.environ.get("REMINDER_NORMAL_PATH_JUDGE_TIMEOUT_SECONDS", "90"),
    )
)
LLM_JUDGE_PROCESS_START_METHOD = os.environ.get(
    "REMINDER_NORMAL_PATH_JUDGE_PROCESS_START_METHOD", "spawn"
)
PENDING_WORKFLOW_TWO_TURN_CASE_NAME = "pending-workflow-hourly-checkin-two-turn"
PENDING_WORKFLOW_TWO_TURN_TURNS = (
    "每个整点喊我打卡吧",
    "从现在到晚上七点",
)
PENDING_WORKFLOW_TWO_TURN_GUARD_MODES = (
    "high_frequency_guards_enabled",
    "high_frequency_guards_bypassed",
)


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
                {
                    **dict(item.get("metadata") or {}),
                    "_case_index": index,
                },
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
        "expected_clarification_terms",
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


def select_expectation_cases(
    cases: list[ReminderNormalPathCase],
) -> list[ReminderNormalPathCase]:
    return [
        case
        for case in cases
        if str(case.metadata.get("evaluation_expectation") or "").strip()
    ]


def pending_workflow_two_turn_eval_manifest() -> dict[str, Any]:
    return {
        "name": PENDING_WORKFLOW_TWO_TURN_CASE_NAME,
        "turns": list(PENDING_WORKFLOW_TWO_TURN_TURNS),
        "guard_modes": list(PENDING_WORKFLOW_TWO_TURN_GUARD_MODES),
        "transport": "business-clawscale",
        "expected_path": (
            "turn 1 persists an awaiting_user pending workflow; turn 2 loads "
            "the same workflow, advances it to execution, creates bounded "
            "reminders, and leaves the workflow terminal"
        ),
        "evidence_status": "open_real_model_business_clawscale_run_required",
    }


def runtime_case_index(case: ReminderNormalPathCase, fallback_index: int) -> int:
    try:
        return int(case.metadata.get("_case_index", fallback_index))
    except (TypeError, ValueError):
        return fallback_index


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
        case_index = runtime_case_index(case, offset + local_index)
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
    now_timestamp = int(time.time())
    if not use_case_timestamp:
        return fresh_case_input_timestamp(
            case,
            timezone_name=timezone_name,
            now_timestamp=now_timestamp,
        )
    raw_timestamp = str(case.metadata.get("timestamp") or "").strip()
    if not raw_timestamp:
        return now_timestamp
    try:
        parsed = datetime.strptime(raw_timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return now_timestamp
    return int(parsed.replace(tzinfo=ZoneInfo(timezone_name)).timestamp())


def fresh_case_input_timestamp(
    case: ReminderNormalPathCase,
    *,
    timezone_name: str,
    now_timestamp: int,
) -> int:
    raw_timestamp = str(case.metadata.get("timestamp") or "").strip()
    if not raw_timestamp:
        return now_timestamp
    try:
        parsed = datetime.strptime(raw_timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return now_timestamp
    timezone = ZoneInfo(timezone_name)
    now_dt = datetime.fromtimestamp(now_timestamp, timezone)
    replay_dt = now_dt.replace(
        hour=parsed.hour,
        minute=parsed.minute,
        second=parsed.second,
        microsecond=0,
    )
    replay_timestamp = int(replay_dt.timestamp())
    if replay_timestamp <= now_timestamp:
        replay_timestamp = int((replay_dt + timedelta(days=1)).timestamp())
    return replay_timestamp


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
        case_index = runtime_case_index(case, offset + local_index)
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
        ):
            errors.append("user_output_implies_unconfirmed_reminder")
    if expectation in {"clarify", "capability", "discussion", "query"}:
        if reminders:
            errors.append("unexpected_reminder_created")
        if expectation == "discussion" and output_is_pure_reminder_clarification(
            outputs,
            case_input=case.input,
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


_COMMON_TITLE_LEADING_VERBS = frozenset("喝吃学背看写做跑练买拿取打出睡起读来")
_COMMON_TITLE_LEADING_PREFIXES = ("开始", "一下")


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
    output_text = normalize_expected_title(output_text.replace("\n", "；"))
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
            if actual_local_time and actual_local_time != expected.local_time:
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
) -> bool:
    output_text = combined_output_text(outputs)
    if not deterministic_output_mentions_clarification(case_input, output_text):
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


class UnconfirmedReminderJudgeResponse(BaseModel):
    implies_unconfirmed_reminder: bool = Field(
        description=(
            "True only when the assistant claims or strongly implies a future "
            "reminder/check-in/notification will happen even though no reminder "
            "tool result confirms it."
        )
    )
    reason: str = Field(default="", description="Brief reason for the judgment.")


class ClarificationOutputJudgeResponse(BaseModel):
    is_clarification: bool = Field(
        description=(
            "True when the assistant asks the user to provide, choose, or confirm "
            "missing reminder details instead of claiming the reminder is set."
        )
    )
    reason: str = Field(default="", description="Brief reason for the judgment.")


class UnconfirmedReminderJudgeTimeout(Exception):
    pass


class ClarificationOutputJudgeTimeout(Exception):
    pass


def run_clarification_output_judge(case_input: str, output_text: str) -> bool:
    prompt = build_clarification_output_judge_prompt(case_input, output_text)
    try:
        return _run_clarification_output_judge_with_timeout(prompt)
    except ClarificationOutputJudgeTimeout:
        print("clarification output LLM judge timed out", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"clarification output LLM judge failed: {exc}", file=sys.stderr)
        return False


def build_clarification_output_judge_prompt(case_input: str, output_text: str) -> str:
    return f"""Judge whether the assistant reply is a reminder clarification.

Return true only if it asks the user for missing details or confirmation before
a reminder create/update/cancel/complete action. Missing details can include
date, time, cadence/frequency, reminder content, target reminder, or whether to
set a related reminder. A proposed option is true if it asks for confirmation.
Return false for acknowledgements, unrelated chat, capability explanations, or
promises that a reminder is already set. Answer with the structured schema only.

User: {case_input}
Assistant: {output_text}"""


def _parse_clarification_output_judge_response(response) -> bool:
    content = getattr(response, "content", None)
    if isinstance(content, ClarificationOutputJudgeResponse):
        return content.is_clarification
    if isinstance(content, dict):
        return bool(content.get("is_clarification"))
    try:
        parsed = ClarificationOutputJudgeResponse.model_validate_json(str(content))
    except Exception:
        print(
            "clarification output LLM judge returned unparsable output",
            file=sys.stderr,
        )
        return False
    return parsed.is_clarification


def _run_clarification_output_judge_with_timeout(prompt: str) -> bool:
    timeout_seconds = max(0.01, CLARIFICATION_OUTPUT_JUDGE_TIMEOUT_SECONDS)
    context = get_context(LLM_JUDGE_PROCESS_START_METHOD)
    queue = context.Queue()
    process = context.Process(
        target=_clarification_output_judge_worker,
        args=(prompt, queue),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1)
        raise ClarificationOutputJudgeTimeout()
    if queue.empty():
        raise RuntimeError("clarification output LLM judge produced no result")
    status, payload = queue.get()
    if status == "ok":
        return bool(payload)
    raise RuntimeError(str(payload))


def _clarification_output_judge_worker(prompt: str, queue) -> None:
    try:
        response = _clarification_output_judge_agent().run(prompt)
        queue.put(("ok", _parse_clarification_output_judge_response(response)))
    except Exception as exc:
        queue.put(("error", repr(exc)))


@lru_cache(maxsize=1)
def _clarification_output_judge_agent():
    from agno.agent import Agent

    return Agent(
        id="reminder-normal-path-clarification-output-judge",
        name="ReminderNormalPathClarificationOutputJudge",
        model=_create_unconfirmed_reminder_judge_model(max_tokens=150),
        instructions=(
            "You are an evaluation judge. Decide only whether an assistant reply "
            "is asking for missing information or confirmation before a reminder "
            "CRUD action. Do not judge whether the final reminder would be correct."
        ),
        output_schema=ClarificationOutputJudgeResponse,
        use_json_mode=True,
        markdown=False,
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


def run_unconfirmed_reminder_judge(output_text: str) -> bool:
    prompt = build_unconfirmed_reminder_judge_prompt(output_text)
    try:
        return _run_unconfirmed_reminder_judge_with_timeout(prompt)
    except UnconfirmedReminderJudgeTimeout:
        print("unconfirmed reminder LLM judge timed out", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"unconfirmed reminder LLM judge failed: {exc}", file=sys.stderr)
        return False


def build_unconfirmed_reminder_judge_prompt(output_text: str) -> str:
    return f"""Judge whether this assistant reply claims or strongly implies an unconfirmed reminder action.

Context:
- No successful reminder tool result is present.
- A clarification or proposal is allowed.
- A question asking whether the user wants a reminder, what frequency to use,
  or whether to set a reminder for another item is a clarification, not a
  claimed reminder action.
- A reply that says the assistant remembers, knows, or recalls the user's
  stated plan or prior message is not a claimed reminder action unless it also
  says a future reminder/check-in will happen.
- A promise that the assistant will remind, notify, call, nudge, check in, or avoid disturbing the user later is not allowed.
- Return true only for declarative claims or strong implications that a future
  reminder/check-in will happen without further user confirmation.
- Answer with the structured schema only.

Assistant reply:
{output_text}"""


def _parse_unconfirmed_reminder_judge_response(response) -> bool:
    content = getattr(response, "content", None)
    if isinstance(content, UnconfirmedReminderJudgeResponse):
        return content.implies_unconfirmed_reminder
    if isinstance(content, dict):
        return bool(content.get("implies_unconfirmed_reminder"))
    try:
        parsed = UnconfirmedReminderJudgeResponse.model_validate_json(str(content))
    except Exception:
        print(
            "unconfirmed reminder LLM judge returned unparsable output", file=sys.stderr
        )
        return False
    return parsed.implies_unconfirmed_reminder


def _run_unconfirmed_reminder_judge_with_timeout(prompt: str) -> bool:
    timeout_seconds = max(0.01, UNCONFIRMED_REMINDER_JUDGE_TIMEOUT_SECONDS)
    context = get_context(LLM_JUDGE_PROCESS_START_METHOD)
    queue = context.Queue()
    process = context.Process(
        target=_unconfirmed_reminder_judge_worker,
        args=(prompt, queue),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1)
        raise UnconfirmedReminderJudgeTimeout()
    if queue.empty():
        raise RuntimeError("unconfirmed reminder LLM judge produced no result")
    status, payload = queue.get()
    if status == "ok":
        return bool(payload)
    raise RuntimeError(str(payload))


def _unconfirmed_reminder_judge_worker(prompt: str, queue) -> None:
    try:
        response = _unconfirmed_reminder_judge_agent().run(prompt)
        queue.put(("ok", _parse_unconfirmed_reminder_judge_response(response)))
    except Exception as exc:
        queue.put(("error", repr(exc)))


@lru_cache(maxsize=1)
def _unconfirmed_reminder_judge_agent():
    from agno.agent import Agent

    return Agent(
        id="reminder-normal-path-unconfirmed-reminder-judge",
        name="ReminderNormalPathUnconfirmedReminderJudge",
        model=_create_unconfirmed_reminder_judge_model(max_tokens=500),
        instructions=(
            "You are an evaluation judge. Decide only whether an assistant reply "
            "claims or strongly implies an unconfirmed future reminder action. "
            "Do not judge politeness or reminder correctness."
        ),
        output_schema=UnconfirmedReminderJudgeResponse,
        use_json_mode=True,
        markdown=False,
    )


def _create_unconfirmed_reminder_judge_model(*, max_tokens: int):
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_api_key:
        try:
            from agno.models.anthropic import Claude
        except ImportError:
            print(
                "ANTHROPIC_API_KEY is set but anthropic is not installed; "
                "falling back to configured prepare_fast judge model",
                file=sys.stderr,
            )
        else:
            return Claude(
                id=os.getenv(
                    "REMINDER_EVAL_JUDGE_MODEL_ID",
                    "claude-haiku-4-5-20251001",
                ),
                api_key=anthropic_api_key,
                max_tokens=max_tokens,
            )

    from agent.agno_agent.model_factory import create_llm_model

    return create_llm_model(max_tokens=max_tokens, role="prepare_fast")


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
    serial: bool = True,
) -> dict[str, Any]:
    cases = select_cases(all_cases, offset=offset, limit=limit)
    character_id, user_ids = seed_normal_path_identities(
        cases,
        offset=offset,
        batch_id=batch_id,
        timezone_name=timezone_name,
        character_alias=character_alias,
    )
    if serial:
        submitted: dict[int, dict[str, Any]] = {}
        results: list[ReminderNormalPathResult] = []
        for local_index, case in enumerate(cases):
            case_offset = offset + local_index
            case_submitted = submit_cases(
                db,
                [case],
                offset=case_offset,
                character_id=character_id,
                platform=platform,
                batch_id=batch_id,
                timezone_name=timezone_name,
                use_case_timestamp=use_case_timestamp,
                transport=transport,
            )
            submitted.update(case_submitted)
            results.extend(
                collect_results(
                    db,
                    case_submitted,
                    character_id=character_id,
                    platform=platform,
                    timeout_seconds=timeout_seconds,
                )
            )
    else:
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
        "serial": serial,
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
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument(
        "--parallel-submit",
        action="store_true",
        help=(
            "Submit all cases in a batch before collecting results. By default, "
            "cases run serially so the normal single-worker PM2 runtime is not "
            "measured as input_pending/no_user_output queue starvation."
        ),
    )
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
            "Use exact timestamps from the corpus metadata. Disabled by default; "
            "normal runs replay the corpus wall-clock time on a fresh worker-eligible date."
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


def default_evidence_path(*, run_id: str) -> Path:
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", run_id).strip("-")
    return Path("artifacts/evidence/reminder-normal") / f"{safe_run_id}.json"


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
        run_cases = select_expectation_cases(all_cases)
        batches = []
        all_results = []
        for batch in iter_case_batches(
            total_count=len(run_cases),
            offset=args.offset,
            limit=args.limit,
            batch_size=args.batch_size,
        ):
            batch_payload = run_batch(
                db,
                run_cases,
                offset=batch.offset,
                limit=batch.limit,
                timeout_seconds=args.timeout_seconds,
                platform=platform,
                batch_id=f"{run_id}-{batch.offset}",
                character_alias=args.character_alias,
                timezone_name=args.timezone,
                use_case_timestamp=args.use_case_timestamps,
                transport=args.transport,
                serial=not args.parallel_submit,
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
            "serial": not args.parallel_submit,
            "pending_workflow_two_turn_eval": pending_workflow_two_turn_eval_manifest(),
            "summary": summary,
            "batches": batches,
            "results": all_results,
        }
    else:
        single_limit = args.limit if args.limit is not None else 20
        batch_payload = run_batch(
            db,
            all_cases,
            offset=args.offset,
            limit=single_limit,
            timeout_seconds=args.timeout_seconds,
            platform=platform,
            batch_id=batch_id,
            character_alias=args.character_alias,
            timezone_name=args.timezone,
            use_case_timestamp=args.use_case_timestamps,
            transport=args.transport,
            serial=not args.parallel_submit,
        )
        payload = {
            "cases": str(args.cases),
            "offset": args.offset,
            "limit": single_limit,
            "run_all": False,
            "batch_size": args.batch_size,
            "timeout_seconds": args.timeout_seconds,
            "timezone": args.timezone,
            "use_case_timestamps": args.use_case_timestamps,
            "transport": args.transport,
            "pending_workflow_two_turn_eval": pending_workflow_two_turn_eval_manifest(),
            **batch_payload,
        }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    output_path = args.output or default_evidence_path(run_id=run_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
