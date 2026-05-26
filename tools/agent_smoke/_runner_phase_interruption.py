"""Mid-conversation interruption smoke.

Sends a long first request, then sends a superseding second request within
500ms. The verdict is based on Mongo/Postgres ground truth, not just the text
reply.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from dataclasses import asdict
from datetime import UTC
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from pymongo import MongoClient

from tools.agent_smoke import _config
from tools.agent_smoke.account_factory import provision_account
from tools.agent_smoke.transcript import Transcript, Turn

BATCH = "interruption-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")

FIRST_PROMPT = "帮我把这周每天 9 点都设个喝水提醒，再给我推荐 5 个健康早餐"
SECOND_PROMPT = "等一下，先取消刚才说的，改成只设周一 9 点提醒"


def _bridge_payload(account, text: str, event_id: str, timestamp: int) -> dict[str, Any]:
    label = account.coke_account_id.replace("ck_smoke_", "").replace("ck_", "")
    payload = {
        "customer_id": account.coke_account_id,
        "coke_account_id": account.coke_account_id,
        "tenant_id": account.tenant_id or f"tnt_smoke_{label}",
        "clawscale_user_id": account.clawscale_user_id or f"csu_smoke_{label}",
        "channel_id": f"chn_smoke_{label}",
        "platform": "wechat_personal",
        "external_id": f"ext_smoke_{label}",
        "end_user_id": f"eu_smoke_{label}",
        "channel_scope": "personal",
        "input": text,
        "text": text,
        "message_type": "text",
        "timestamp": timestamp,
        "inbound_event_id": event_id,
        "business_conversation_key": f"smoke-interruption:{account.coke_account_id}",
        "coke_account_display_name": account.display_name,
    }
    return payload


def _post_bridge(account, text: str, event_id: str) -> dict[str, Any]:
    payload = _bridge_payload(account, text, event_id, int(time.time()))
    response = requests.post(
        _config.bridge_base_url() + "/bridge/inbound",
        json=payload,
        headers={
            "Authorization": f"Bearer {_config.bridge_api_key()}",
            "Content-Type": "application/json",
        },
        timeout=180,
    )
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    return {
        "status_code": response.status_code,
        "body": body,
        "payload": payload,
    }


def _output_by_event(event_id: str) -> dict | None:
    db = MongoClient(_config.mongo_uri())[_config.mongo_db_name()]
    return db.outputmessages.find_one(
        {"metadata.business_protocol.causal_inbound_event_id": event_id},
        sort=[("_id", -1)],
    )


def _wait_output_by_event(event_id: str, *, timeout_seconds: float = 45.0) -> dict | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        doc = _output_by_event(event_id)
        if doc is not None:
            return doc
        time.sleep(1.0)
    return _output_by_event(event_id)


def _outputs_for_user(coke_account_id: str) -> list[dict]:
    db = MongoClient(_config.mongo_uri())[_config.mongo_db_name()]
    return list(db.outputmessages.find({"to_user": coke_account_id}).sort("_id", 1))


def _reminders_for_user(coke_account_id: str) -> list[dict]:
    db = MongoClient(_config.mongo_uri())[_config.mongo_db_name()]
    return list(db.reminders.find({"owner_user_id": coke_account_id}).sort("_id", 1))


def _postgres_snapshot(batch_label: str) -> str:
    sql = f"""
SELECT 'customers' AS table_name, count(*) FROM customers
 WHERE id LIKE '%{batch_label}%'
UNION ALL
SELECT 'friend_requests', count(*) FROM friend_requests
 WHERE requester_account_id LIKE '%{batch_label}%'
    OR target_account_id LIKE '%{batch_label}%'
UNION ALL
SELECT 'shared_reminder_requests', count(*) FROM shared_reminder_requests
 WHERE requester_account_id LIKE '%{batch_label}%'
    OR invitee_account_id LIKE '%{batch_label}%';
"""
    result = subprocess.run(
        [
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            "15432",
            "-U",
            "clawscale",
            "-d",
            "clawscale",
            "-c",
            sql,
        ],
        env={"PGPASSWORD": "clawscale", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or result.stderr).strip()


def _doc_json(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    return json.loads(json.dumps(doc, ensure_ascii=False, default=str))


def _reply_text(response: dict[str, Any], output_doc: dict | None) -> str:
    body = response.get("body")
    if isinstance(body, dict) and isinstance(body.get("reply"), str) and body["reply"]:
        return body["reply"]
    return str((output_doc or {}).get("message") or "")


def _active_reminders(reminders: list[dict]) -> list[dict]:
    return [
        item
        for item in reminders
        if item.get("lifecycle_state") not in {"cancelled", "completed", "failed"}
    ]


def _local_weekday_and_time(reminder: dict) -> tuple[int | None, str | None]:
    schedule = reminder.get("schedule") or {}
    if schedule.get("local_time"):
        local_date = schedule.get("local_date")
        try:
            weekday = (
                time.strptime(str(local_date), "%Y-%m-%d").tm_wday
                if local_date
                else None
            )
        except ValueError:
            weekday = None
        return weekday, str(schedule.get("local_time"))

    next_fire_at = reminder.get("next_fire_at")
    if not next_fire_at:
        return None, None
    local = next_fire_at.replace(tzinfo=UTC).astimezone(ZoneInfo("Asia/Shanghai"))
    return local.weekday(), local.time().replace(microsecond=0).isoformat()


def _validate(reply2: str, second_output: dict | None, reminders: list[dict]) -> list[str]:
    problems: list[str] = []
    if not reply2:
        problems.append("second_reply_empty")
    if "周一" not in reply2 and "星期一" not in reply2 and "Monday" not in reply2:
        problems.append("second_reply_missing_monday")
    if "9" not in reply2 and "九" not in reply2:
        problems.append("second_reply_missing_9am")
    if "喝水" not in reply2 and "水" not in reply2:
        problems.append("second_reply_missing_water")
    if "早餐" in reply2 or "每天" in reply2 or "这周每天" in reply2:
        problems.append("second_reply_echoes_superseded_first_request")

    business_protocol = (second_output or {}).get("metadata", {}).get(
        "business_protocol", {}
    )
    if not second_output:
        problems.append("second_output_missing")
    elif business_protocol.get("business_conversation_key", "").startswith(
        "product-notification:"
    ):
        problems.append("second_output_bound_to_product_notification")
    if (second_output or {}).get("metadata", {}).get("product_notification"):
        problems.append("second_output_has_product_notification_metadata")

    active = _active_reminders(reminders)
    if len(active) != 1:
        problems.append(f"active_reminder_count={len(active)}")
        return problems

    reminder = active[0]
    title = str(reminder.get("title") or "")
    if "水" not in title:
        problems.append(f"corrected_reminder_title_missing_water: {title}")
    weekday, local_time = _local_weekday_and_time(reminder)
    if weekday != 0:
        problems.append(f"corrected_reminder_not_monday: weekday={weekday}")
    if local_time != "09:00:00":
        problems.append(f"corrected_reminder_not_9am: local_time={local_time}")
    schedule = reminder.get("schedule") or {}
    if schedule.get("rrule") or schedule.get("repeat"):
        problems.append(f"corrected_reminder_unexpected_recurrence: {schedule}")
    return problems


def _save_evidence(
    transcript: Transcript,
    *,
    first_response: dict[str, Any],
    second_response: dict[str, Any],
    first_output: dict | None,
    second_output: dict | None,
    reminders: list[dict],
    outputs: list[dict],
    postgres_snapshot: str,
) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"interruption-{BATCH}.json"
    payload = {
        "batch_id": BATCH,
        "accounts": transcript.accounts,
        "turns": [asdict(turn) for turn in transcript.turns],
        "bridge_responses": {
            "first": first_response,
            "second": second_response,
        },
        "mongo_outputs": {
            "first": _doc_json(first_output),
            "second": _doc_json(second_output),
            "all_user_outputs": [_doc_json(doc) for doc in outputs],
        },
        "mongo_reminders": [_doc_json(doc) for doc in reminders],
        "postgres_snapshot": postgres_snapshot,
        "findings": transcript.findings,
        "verdict": transcript.verdict,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return path


def main() -> None:
    print(f"BATCH={BATCH}\n")
    account_batch = BATCH.replace("-", "").lower()
    alice = provision_account("alice", batch_id=account_batch, display_name="Alice Interrupt")
    print(f"alice={alice.coke_account_id}")

    transcript = Transcript(batch_id=BATCH)
    transcript.add_account(alice)

    first_event_id = f"smoke_evt_{uuid.uuid4().hex}"
    second_event_id = f"smoke_evt_{uuid.uuid4().hex}"
    result_holder: dict[str, Any] = {}

    def send_first() -> None:
        start = time.monotonic()
        result_holder["first"] = _post_bridge(alice, FIRST_PROMPT, first_event_id)
        result_holder["first_elapsed_ms"] = int((time.monotonic() - start) * 1000)

    print(f"\n[T01 alice] >> {FIRST_PROMPT}", flush=True)
    worker = threading.Thread(target=send_first, daemon=True)
    worker.start()
    time.sleep(0.5)

    print(f"\n[T02 alice] >> {SECOND_PROMPT}", flush=True)
    second_start = time.monotonic()
    second_response = _post_bridge(alice, SECOND_PROMPT, second_event_id)
    second_elapsed_ms = int((time.monotonic() - second_start) * 1000)
    worker.join(timeout=180)
    first_response = result_holder.get("first") or {
        "status_code": None,
        "body": "first request did not finish before join timeout",
    }
    first_elapsed_ms = int(result_holder.get("first_elapsed_ms") or 180000)

    first_output = _wait_output_by_event(first_event_id)
    second_output = _wait_output_by_event(second_event_id)
    first_reply = _reply_text(first_response, first_output)
    second_reply = _reply_text(second_response, second_output)
    print(f"[T01 alice] << ({first_elapsed_ms}ms, out={(first_output or {}).get('_id')}) {first_reply}", flush=True)
    print(f"[T02 alice] << ({second_elapsed_ms}ms, out={(second_output or {}).get('_id')}) {second_reply}", flush=True)

    transcript.add_turn(
        Turn(
            turn=1,
            speaker="alice",
            coke_account_id=alice.coke_account_id,
            input_text=FIRST_PROMPT,
            inbound_event_id=first_event_id,
            reply_text=first_reply,
            output_id=str((first_output or {}).get("_id") or ""),
            elapsed_ms=first_elapsed_ms,
            note="interrupted_original_request",
        )
    )
    transcript.add_turn(
        Turn(
            turn=2,
            speaker="alice",
            coke_account_id=alice.coke_account_id,
            input_text=SECOND_PROMPT,
            inbound_event_id=second_event_id,
            reply_text=second_reply,
            output_id=str((second_output or {}).get("_id") or ""),
            elapsed_ms=second_elapsed_ms,
            note="superseding_request",
        )
    )

    reminders = _reminders_for_user(alice.coke_account_id)
    outputs = _outputs_for_user(alice.coke_account_id)
    postgres_snapshot = _postgres_snapshot(account_batch)
    print("\n=== POSTGRES ===")
    print(postgres_snapshot)
    print("\n=== MONGO REMINDERS ===")
    for reminder in reminders:
        print(
            f"id={reminder.get('_id')} state={reminder.get('lifecycle_state')} "
            f"title={reminder.get('title')!r} schedule={reminder.get('schedule')}"
        )

    problems = _validate(second_reply, second_output, reminders)
    for problem in problems:
        transcript.add_finding(severity="error", summary=problem)
    transcript.set_verdict(passed=not problems, problems=problems)
    path = _save_evidence(
        transcript,
        first_response=first_response,
        second_response=second_response,
        first_output=first_output,
        second_output=second_output,
        reminders=reminders,
        outputs=outputs,
        postgres_snapshot=postgres_snapshot,
    )
    print(f"\nevidence={path}")
    print(f"VERDICT={'PASSED' if not problems else 'FAILED'}")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
