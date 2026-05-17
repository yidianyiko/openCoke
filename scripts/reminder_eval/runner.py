from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import MongoClient

from agent.role.bootstrap import ensure_default_character_seeded
from conf.config import CONF
from dao.user_dao import UserDAO
from scripts.reminder_eval.dataset import (
    DEFAULT_CASES_PATH,
    ReminderNormalPathCase,
    ReminderNormalPathResult,
    iter_case_batches,
    load_cases,
    pending_workflow_two_turn_eval_manifest,
    runtime_case_index,
    select_cases,
    select_expectation_cases,
)
from scripts.reminder_eval.scoring import summarize, validate_observations


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
    if payload["run_all"]:
        return 0 if not payload["summary"]["severity_violations"] else 1
    return 0 if payload["summary"]["failed"] == 0 else 1
