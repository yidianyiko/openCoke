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


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[ReminderNormalPathCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        ReminderNormalPathCase(
            input=str(item["input"]),
            expected_intent=str(item.get("expected_intent", "")),
            matched_keywords=list(item.get("matched_keywords") or []),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in data["test_cases"]
    ]


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
        user_id = normal_path_user_id(case, case_index)
        user_ids.append(user_id)
        db.characters.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "name": f"reminder-e2e-user-{case_index}",
                    "nickname": f"reminder-e2e-user-{case_index}",
                    "status": "normal",
                    "user_info": {
                        "description": "Reminder normal-path E2E user",
                        "status": {"place": "test", "action": "chatting"},
                    },
                },
                "$setOnInsert": {"_id": ObjectId(user_id)},
            },
            upsert=True,
        )
    return character_id, user_ids


def normal_path_user_id(case: ReminderNormalPathCase, case_index: int) -> str:
    original_user = str(case.metadata.get("from_user") or "")
    if ObjectId.is_valid(original_user):
        return original_user
    source_id = str(case.metadata.get("source_id") or "")
    seed = f"reminder-normal-path:{case_index}:{original_user}:{source_id}"
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
        user_id = normal_path_user_id(case, case_index)
        input_timestamp = case_input_timestamp(
            case,
            timezone_name=timezone_name,
            use_case_timestamp=use_case_timestamp,
        )
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
    outputs = list(
        db.outputmessages.find(
            {
                "platform": platform,
                "from_user": character_id,
                "to_user": user_id,
                "expect_output_timestamp": {"$gte": submitted_at - 1},
            }
        ).sort("expect_output_timestamp", 1)
    )
    submitted_dt = datetime.fromtimestamp(submitted_at - 1, tz=timezone.utc)
    reminders = list(
        db.reminders.find(
            {
                "owner_user_id": user_id,
                "$or": [
                    {"created_at": {"$gte": submitted_dt}},
                    {"updated_at": {"$gte": submitted_dt}},
                    {"cancelled_at": {"$gte": submitted_dt}},
                    {"completed_at": {"$gte": submitted_dt}},
                ],
            }
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


def validate_observations(
    case: ReminderNormalPathCase,
    input_status: str,
    outputs: list[dict[str, Any]],
    reminders: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if input_status != "handled":
        errors.append(f"input_{input_status}")
    if not outputs:
        errors.append("no_user_output")
    if explicit_reminder_request(case.input) and not reminders:
        errors.append("no_reminder_created")
    for reminder in reminders:
        if reminder.get("next_fire_at") is None and reminder.get("lifecycle_state") == "active":
            errors.append("active_reminder_missing_next_fire_at")
        if not reminder.get("title"):
            errors.append("reminder_missing_title")
    if duplicate_reminder_keys(reminders):
        errors.append("duplicate_reminder_created")
    if reminders and not output_mentions_crud_ack(outputs, reminders):
        errors.append("user_output_missing_crud_ack")
    return errors


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
    output_text = "\n".join(
        str(output.get("message") or output.get("content") or "") for output in outputs
    )
    if not output_text.strip():
        return False

    action_ack = re.search(
        r"(已|已经|成功|失败|没有|未能|无法).{0,12}(创建|设置|新增|更新|修改|取消|删除|完成).{0,12}提醒|"
        r"提醒.{0,12}(已|已经|成功|失败|没有|未能|无法).{0,12}(创建|设置|新增|更新|修改|取消|删除|完成)",
        output_text,
    )
    if action_ack:
        return True

    titles = [str(reminder.get("title") or "").strip() for reminder in reminders]
    return "提醒" in output_text and any(title and title in output_text for title in titles)


def explicit_reminder_request(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(
        keyword in normalized
        for keyword in (
            "提醒",
            "remind",
            "叫我",
            "喊我",
            "每天",
            "每个小时",
            "每周",
            "每月",
        )
    )


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
            if (
                batch_payload["summary"]["failed"] > 0
                and not args.continue_on_failure
            ):
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
