"""Daily recurring reminder smoke.

Verifies reminder schedule shape only. Delivery firing is intentionally out of
scope while docs/issues/2026-05-25-reminder-fire-missing-delivery-route.md
remains open.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from tools.agent_smoke import _config
from tools.agent_smoke.account_factory import provision_account
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH_ID = "recurring-reminder-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
PROMPT = "每天早上 8 点提醒我喝杯水"
DEFAULT_USER_TIMEZONE = "Asia/Shanghai"
DELIVERY_GAP_NOTE = (
    "Reminder fire delivery verification intentionally skipped: "
    "docs/issues/2026-05-25-reminder-fire-missing-delivery-route.md is open."
)


def _mongo_db():
    return MongoClient(_config.mongo_uri())[_config.mongo_db_name()]


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


def _as_utc_aware(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _active_reminders_for_user(coke_account_id: str) -> list[dict]:
    return list(
        _mongo_db()
        .reminders.find(
            {
                "owner_user_id": coke_account_id,
                "lifecycle_state": {"$nin": ["cancelled", "completed", "failed"]},
            }
        )
        .sort("_id", 1)
    )


def _mongo_user(coke_account_id: str) -> dict | None:
    return _mongo_db().users.find_one(
        {"id": coke_account_id}
    ) or _mongo_db().users.find_one({"_id": coke_account_id})


def _user_timezone(user_doc: dict | None) -> str:
    if not isinstance(user_doc, dict):
        return DEFAULT_USER_TIMEZONE
    for field in ("coke_tz", "effective_timezone", "timezone"):
        value = user_doc.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return DEFAULT_USER_TIMEZONE


def _has_daily_recurrence(schedule: dict) -> bool:
    repeat = schedule.get("repeat")
    if isinstance(repeat, str) and repeat.lower() == "daily":
        return True
    if isinstance(repeat, dict):
        cadence = repeat.get("cadence") or repeat.get("frequency")
        if isinstance(cadence, str) and cadence.lower() == "daily":
            return True
    rrule = str(schedule.get("rrule") or "").upper()
    return "FREQ=DAILY" in rrule


def _validate_recurring_reminder(
    reminder: dict | None,
    *,
    now: datetime | None = None,
    expected_timezone: str = DEFAULT_USER_TIMEZONE,
) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes = [DELIVERY_GAP_NOTE]
    now = now or datetime.now(UTC)

    if reminder is None:
        return ["active_reminder_missing"], notes

    schedule = reminder.get("schedule") or {}
    if "水" not in str(reminder.get("title") or ""):
        problems.append(f"title_missing_water: {reminder.get('title')!r}")
    if not _has_daily_recurrence(schedule):
        problems.append("recurrence_missing_daily")
    timezone = schedule.get("timezone")
    if timezone != expected_timezone:
        problems.append(f"timezone_mismatch: {timezone}")
    if str(schedule.get("local_time") or "") != "08:00:00":
        problems.append(f"local_time_mismatch: {schedule.get('local_time')}")

    next_fire_at = _as_utc_aware(reminder.get("next_fire_at"))
    if next_fire_at is None:
        problems.append("next_fire_at_missing")
    elif next_fire_at <= now:
        problems.append("next_fire_at_not_future")

    return problems, notes


def _save_evidence(
    transcript: Transcript,
    *,
    user_doc: dict | None,
    reminders: list[dict],
    active_reminder: dict | None,
    expected_timezone: str,
    postgres_snapshot: str,
    problems: list[str],
    notes: list[str],
) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"recurring-reminder-{BATCH_ID}.json"
    payload = {
        "batch_id": BATCH_ID,
        "accounts": transcript.accounts,
        "turns": [asdict(turn) for turn in transcript.turns],
        "mongo_user": _doc_json(user_doc),
        "expected_timezone": expected_timezone,
        "mongo_reminders": [_doc_json(doc) for doc in reminders],
        "active_reminder": _doc_json(active_reminder),
        "postgres_snapshot": postgres_snapshot,
        "findings": [],
        "verdict": {
            "passed": not problems,
            "problems": problems,
            "notes": notes,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def main() -> int:
    batch_label = BATCH_ID.replace("-", "").lower()
    print(f"BATCH={BATCH_ID}")
    alice = provision_account(
        "alice",
        batch_id=batch_label,
        display_name="Alice Recurring Reminder",
    )
    print(f"alice={alice.coke_account_id}")

    transcript = Transcript(batch_id=BATCH_ID)
    transcript.add_account(alice)

    start = time.monotonic()
    print(f"\n[T01 alice] >> {PROMPT}", flush=True)
    reply = send_as(alice.coke_account_id, PROMPT, **alice.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(
        f"[T01 alice] << ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}",
        flush=True,
    )
    transcript.add_turn(
        Turn(
            turn=1,
            speaker="alice",
            coke_account_id=alice.coke_account_id,
            input_text=PROMPT,
            inbound_event_id=reply.causal_inbound_event_id,
            reply_text=reply.reply,
            output_id=reply.output_id,
            elapsed_ms=elapsed_ms,
            note="daily_recurring_reminder_shape",
        )
    )

    user_doc = _mongo_user(alice.coke_account_id)
    expected_timezone = _user_timezone(user_doc)
    active_reminders = _active_reminders_for_user(alice.coke_account_id)
    active_reminder = active_reminders[0] if len(active_reminders) == 1 else None
    problems, notes = _validate_recurring_reminder(
        active_reminder,
        expected_timezone=expected_timezone,
    )
    if len(active_reminders) != 1:
        problems.insert(0, f"active_reminder_count={len(active_reminders)}")

    postgres_snapshot = _postgres_snapshot(batch_label)
    print("\n=== POSTGRES ===")
    print(postgres_snapshot)
    print("\n=== MONGO REMINDERS ===")
    for reminder in active_reminders:
        schedule = reminder.get("schedule") or {}
        print(
            "id={id} state={state} title={title!r} next_fire_at={next_fire_at} "
            "schedule={schedule}".format(
                id=reminder.get("_id"),
                state=reminder.get("lifecycle_state"),
                title=reminder.get("title"),
                next_fire_at=reminder.get("next_fire_at"),
                schedule=schedule,
            )
        )
    print("\n=== NOTES ===")
    for note in notes:
        print(f"- {note}")

    path = _save_evidence(
        transcript,
        user_doc=user_doc,
        reminders=active_reminders,
        active_reminder=active_reminder,
        expected_timezone=expected_timezone,
        postgres_snapshot=postgres_snapshot,
        problems=problems,
        notes=notes,
    )
    print(f"\nevidence={path}")
    print(f"VERDICT={'PASSED' if not problems else 'FAILED'}")
    if problems:
        print("problems=" + ", ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
