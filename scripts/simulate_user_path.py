#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import user_path_normal_eval as normal_eval

DEFAULT_EVIDENCE_DIR = Path("artifacts/evidence/user-path")


def default_evidence_path(*, run_id: str) -> Path:
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", run_id).strip("-")
    return DEFAULT_EVIDENCE_DIR / f"{safe_run_id}.json"


def build_message_case(
    *, message: str, expectation: str
) -> normal_eval.ReminderNormalPathCase:
    metadata: dict[str, Any] = {"_case_index": 0, "source_id": "manual-user-path"}
    if expectation == "reminder_created":
        metadata.update(
            {
                "evaluation_expectation": "crud",
                "expected_operation": "create",
            }
        )
    elif expectation == "reminder_deleted":
        metadata.update(
            {
                "evaluation_expectation": "crud",
                "expected_operation": "delete",
                "allow_clarification": True,
            }
        )
    elif expectation == "clarification":
        metadata["evaluation_expectation"] = "clarify"
    else:
        metadata["evaluation_expectation"] = "discussion"
    return normal_eval.ReminderNormalPathCase(
        input=message,
        expected_intent="reminder" if "reminder" in expectation else "",
        matched_keywords=[],
        metadata=metadata,
    )


def evidence_from_payload(
    *,
    payload: dict[str, Any],
    mode: str,
    runtime: str,
    transport: str,
    message: str | None,
) -> dict[str, Any]:
    results = list(payload.get("results") or [])
    replies = [
        str(output.get("message") or "")
        for result in results
        for output in list(result.get("outputs") or [])
        if str(output.get("message") or "")
    ]
    reminders = [
        reminder
        for result in results
        for reminder in list(result.get("reminders") or [])
    ]
    errors = [error for result in results for error in list(result.get("errors") or [])]
    summary = dict(payload.get("summary") or {})
    passed = int(summary.get("failed") or 0) == 0
    input_statuses = sorted(
        {str(result.get("input_status") or "") for result in results if result}
    )
    if len(input_statuses) == 1:
        input_status = input_statuses[0]
    elif input_statuses:
        input_status = "mixed"
    else:
        input_status = None
    return {
        "input": {
            "mode": mode,
            "runtime": runtime,
            "transport": transport,
            "batch_id": payload.get("batch_id") or payload.get("run_id"),
            "message": message,
            "offset": payload.get("offset"),
            "limit": payload.get("limit"),
            "run_all": bool(payload.get("run_all", False)),
        },
        "observed": {
            "input_status": input_status,
            "user_visible_replies": replies,
            "created_reminders": reminders,
            "updated_reminders": [],
            "fired_events": [],
            "errors": errors,
            "summary": summary,
        },
        "raw_results": results,
        "verdict": {
            "passed": passed,
            "failure_layer": classify_failure_layer(errors),
            "reason": "passed" if passed else ", ".join(errors[:5]),
        },
    }


def classify_failure_layer(errors: list[str]) -> str | None:
    if not errors:
        return None
    if any(error.startswith("input_") or error == "timeout" for error in errors):
        return "input_or_runtime"
    if any(
        error in {"no_user_output", "user_output_missing_crud_ack"} for error in errors
    ):
        return "user_visible_reply"
    if any("reminder" in error for error in errors):
        return "functional_side_effect"
    return "evaluation"


def run_local(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.batch_id or f"user-path-{uuid.uuid4().hex[:10]}"
    platform = "business"
    client = normal_eval.mongo_client()
    client.admin.command("ping")
    db = client[normal_eval.CONF["mongodb"]["mongodb_name"]]

    if args.message:
        cases = [build_message_case(message=args.message, expectation=args.expect)]
        batch_payload = normal_eval.run_batch(
            db,
            cases,
            offset=0,
            limit=1,
            timeout_seconds=args.timeout_seconds,
            platform=platform,
            batch_id=run_id,
            character_alias=args.character_alias,
            timezone_name=args.timezone,
            use_case_timestamp=False,
            transport="business-clawscale",
            serial=True,
        )
        return {
            "mode": "message",
            "runtime": args.runtime,
            "transport": "business-clawscale",
            **batch_payload,
        }

    all_cases = normal_eval.load_cases(args.cases)
    offset = args.case_index if args.case_index is not None else args.offset
    if args.run_all:
        all_cases = normal_eval.select_expectation_cases(all_cases)
    batch_payload = normal_eval.run_batch(
        db,
        all_cases,
        offset=offset,
        limit=args.limit or 1,
        timeout_seconds=args.timeout_seconds,
        platform=platform,
        batch_id=run_id,
        character_alias=args.character_alias,
        timezone_name=args.timezone,
        use_case_timestamp=args.use_case_timestamps,
        transport="business-clawscale",
        serial=not args.parallel_submit,
    )
    return {
        "mode": "corpus",
        "runtime": args.runtime,
        "transport": "business-clawscale",
        "run_all": args.run_all,
        **batch_payload,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Simulate the canonical Coke user path: business-clawscale inbound "
            "shape -> inputmessages -> agent_runner -> outputmessages and side effects."
        )
    )
    parser.add_argument("--message", help="Run one ad hoc user message.")
    parser.add_argument(
        "--expect",
        choices=("reply", "reminder_created", "reminder_deleted", "clarification"),
        default="reply",
        help="Expected behavior for --message mode.",
    )
    parser.add_argument("--cases", type=Path, default=normal_eval.DEFAULT_CASES_PATH)
    parser.add_argument("--case-index", type=int)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--parallel-submit", action="store_true")
    parser.add_argument(
        "--case-timeout-seconds", type=float, dest="timeout_seconds", default=180
    )
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--use-case-timestamps", action="store_true")
    parser.add_argument("--batch-id")
    parser.add_argument("--character-alias")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--runtime",
        choices=("local",),
        default="local",
        help="Runtime backend. The canonical local backend uses the PM2/worker normal path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_local(args)
    evidence = evidence_from_payload(
        payload=payload,
        mode=str(payload.get("mode") or "corpus"),
        runtime=args.runtime,
        transport="business-clawscale",
        message=args.message,
    )
    output_path = args.output or default_evidence_path(
        run_id=str(payload.get("batch_id") or payload.get("run_id") or "user-path")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["verdict"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
