"""Coach-class booking refusal smoke.

Verifies that Coke does not hallucinate coach/class booking ability after the
known "彭教练" booking claims were removed from prompts. The assistant must
refuse booking and redirect to supported reminder/friend coordination work.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path

from pymongo import MongoClient

from tools.agent_smoke import _config
from tools.agent_smoke.account_factory import provision_account
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH = "coach-booking-refusal-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")

PROMPTS = [
    "帮我约一节羽毛球教练课",
    "周日下午 3 点帮我约彭教练",
    "帮我约下周六上午的网球课",
]

REFUSAL_TOKENS = (
    "无法",
    "不能",
    "帮不了",
    "暂时不",
    "还不能",
    "没法",
    "没办法",
    "没有办法",
)
SUPPORTED_TOKENS = ("提醒", "好友", "朋友", "协调", "共享提醒", "一起")
HALLUCINATED_BOOKING_PATTERNS = (
    re.compile(r"(已经|已).{0,12}(预约|约好|约上|确认)"),
    re.compile(r"预约成功"),
    re.compile(r"(已|已经)帮你约"),
    re.compile(r"(booked|appointment confirmed)", re.IGNORECASE),
)
EMPTY_FALLBACK_TOKENS = ("我没接住你刚才的意思", "我这次没能及时整理")


def _mongo_output_for_turn(reply_output_id: str | None, causal_event_id: str) -> dict | None:
    db = MongoClient(_config.mongo_uri())[_config.mongo_db_name()]
    if reply_output_id:
        from bson import ObjectId

        try:
            doc = db.outputmessages.find_one({"_id": ObjectId(reply_output_id)})
            if doc:
                return doc
        except Exception:
            pass
    return db.outputmessages.find_one(
        {"metadata.business_protocol.causal_inbound_event_id": causal_event_id},
        sort=[("_id", -1)],
    )


def _record_turn(transcript: Transcript, account, text: str) -> tuple[str, dict | None]:
    start = time.monotonic()
    turn_no = len(transcript.turns) + 1
    print(f"\n[T{turn_no:02d} alice] >> {text}", flush=True)
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(
        f"[T{turn_no:02d} alice] << ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}",
        flush=True,
    )
    transcript.add_turn(
        Turn(
            turn=turn_no,
            speaker="alice",
            coke_account_id=account.coke_account_id,
            input_text=text,
            inbound_event_id=reply.causal_inbound_event_id,
            reply_text=reply.reply,
            output_id=reply.output_id,
            elapsed_ms=elapsed_ms,
            note="coach_booking_refusal",
        )
    )
    output_doc = _mongo_output_for_turn(reply.output_id, reply.causal_inbound_event_id)
    mongo_text = (output_doc or {}).get("message") or ""
    return mongo_text or reply.reply, output_doc


def _save_named_evidence(transcript: Transcript, mongo_outputs: list[dict | None]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    db = MongoClient(_config.mongo_uri())[_config.mongo_db_name()]
    account_ids = [account["coke_account_id"] for account in transcript.accounts]
    reminder_docs = list(db.reminders.find({"owner_user_id": {"$in": account_ids}}))
    path = EVIDENCE_DIR / f"coach-booking-refusal-{BATCH}.json"
    payload = {
        "batch_id": BATCH,
        "accounts": transcript.accounts,
        "turns": [asdict(turn) for turn in transcript.turns],
        "mongo_outputs": [
            {
                "_id": str(doc.get("_id")),
                "message": doc.get("message"),
                "status": doc.get("status"),
                "to_user": doc.get("to_user"),
                "metadata": doc.get("metadata"),
            }
            if doc
            else None
            for doc in mongo_outputs
        ],
        "mongo_reminders": [
            {
                "_id": str(doc.get("_id")),
                "owner_user_id": doc.get("owner_user_id"),
                "title": doc.get("title"),
                "schedule": doc.get("schedule"),
                "lifecycle_state": doc.get("lifecycle_state"),
                "next_fire_at": doc.get("next_fire_at"),
                "created_at": doc.get("created_at"),
                "metadata": doc.get("metadata"),
            }
            for doc in reminder_docs
        ],
        "findings": transcript.findings,
        "verdict": transcript.verdict,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return path


def _reminders_for_account(coke_account_id: str) -> list[dict]:
    db = MongoClient(_config.mongo_uri())[_config.mongo_db_name()]
    return list(db.reminders.find({"owner_user_id": coke_account_id}))


def main() -> None:
    print(f"BATCH={BATCH}\n")
    account_batch = BATCH.replace("-", "").lower()
    alice = provision_account("alice", batch_id=account_batch, display_name="Alice Booking")
    print(f"alice={alice.coke_account_id}")

    transcript = Transcript(batch_id=BATCH)
    transcript.add_account(alice)
    mongo_outputs: list[dict | None] = []
    problems: list[str] = []

    for prompt in PROMPTS:
        reply_text, output_doc = _record_turn(transcript, alice, prompt)
        mongo_outputs.append(output_doc)
        if any(token in reply_text for token in EMPTY_FALLBACK_TOKENS):
            problems.append(f"empty_fallback: {prompt}")
        if any(pattern.search(reply_text) for pattern in HALLUCINATED_BOOKING_PATTERNS):
            problems.append(f"hallucinated_booking_confirmation: {prompt}")
        if not any(token in reply_text for token in REFUSAL_TOKENS):
            problems.append(f"missing_explicit_refusal: {prompt}")
        if not any(token in reply_text for token in SUPPORTED_TOKENS):
            problems.append(f"missing_supported_capability_offer: {prompt}")

    reminder_docs = _reminders_for_account(alice.coke_account_id)
    if reminder_docs:
        titles = [str(doc.get("title") or "") for doc in reminder_docs]
        problems.append(f"unexpected_reminder_write: {titles}")

    if problems:
        for problem in problems:
            transcript.add_finding(severity="error", summary=problem)
    transcript.set_verdict(passed=not problems, problems=problems)
    path = _save_named_evidence(transcript, mongo_outputs)
    print(f"\nevidence={path}")
    print(f"VERDICT={'PASSED' if not problems else 'FAILED'}")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
