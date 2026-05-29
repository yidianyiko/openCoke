"""Reminder fire end-to-end. Fast-forward via mongo.

Step:
 1. Provision Alice
 2. Alice creates a reminder for 1 hour in the future
 3. We FAST-FORWARD by writing next_fire_at = now - 5s in mongo, simulating
    "time has come" without real-time waiting
 4. Wait up to 45s for the ReminderScheduler to tick + fire
 5. Check: db.outputmessages has a fresh row from Coke → Alice with the
    reminder's title and metadata.reminder_id matching
 6. Check: db.reminders for the same _id has lifecycle_state=completed,
    last_fired_at recent
 7. Also send Alice a chat turn so she would see the fire delivered
    naturally — verify the bridge / output_dispatcher path
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from bson import ObjectId

from tools.agent_smoke.account_factory import provision_account
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH = "fire-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
MONGO = MongoClient("mongodb://127.0.0.1:27017/")["mymongo"]


def step(t: Transcript, account, text, note=""):
    start = time.monotonic()
    turn_no = len(t.turns) + 1
    print(f"\n[T{turn_no:02d} alice] >> {text}", flush=True)
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(f"[T{turn_no:02d} alice] << ({elapsed_ms}ms) {reply.reply}", flush=True)
    t.add_turn(Turn(
        turn=turn_no, speaker="alice",
        coke_account_id=account.coke_account_id,
        input_text=text,
        inbound_event_id=reply.causal_inbound_event_id,
        reply_text=reply.reply, output_id=reply.output_id,
        elapsed_ms=elapsed_ms, note=note or None,
    ))
    return reply.reply


def main():
    print(f"BATCH={BATCH}\n")
    label_short = BATCH.replace("fire-", "").replace("z", "").lower()
    alice = provision_account("alice", batch_id=label_short, display_name="Alice Fire")
    print(f"alice={alice.coke_account_id}\n")

    t = Transcript(batch_id=BATCH)
    t.add_account(alice)

    # T0: warm-up greeting — fresh-account first turns can produce an empty
    # reply before the model has seen chat history.
    step(t, alice, "你好。", "warmup_greeting")

    # T1: create a reminder for ~75 seconds in the future.
    from datetime import timedelta
    target = datetime.now(timezone.utc) + timedelta(seconds=75)
    local = target + timedelta(hours=8)
    minute_str = f"{local.hour:02d}:{local.minute:02d}"
    step(
        t,
        alice,
        f"提醒我今天 {minute_str} 喝杯水，就一分钟之后。",
        "create_future_reminder_75s",
    )

    # Find the reminder Alice just created
    time.sleep(2)
    rem = MONGO.reminders.find_one(
        {"owner_user_id": alice.coke_account_id, "lifecycle_state": "active"},
        sort=[("_id", -1)],
    )
    if not rem:
        print("FATAL: no active reminder found for Alice")
        return
    rem_id = rem["_id"]
    print(f"\n[CREATED] reminder _id={rem_id} title={rem.get('title')!r} next_fire_at={rem.get('next_fire_at')} (UTC)")

    # Wait for scheduler tick (real-time; APScheduler holds an in-memory job
    # with run_date=next_fire_at; should fire within ~5s of that moment).
    print("\n=== WAITING for scheduler to fire (≤90s real-time) ===")
    deadline = time.monotonic() + 90
    fire_output = None
    while time.monotonic() < deadline:
        time.sleep(2)
        # Check mongo reminders for state transition
        cur = MONGO.reminders.find_one({"_id": rem_id})
        if cur and cur.get("lifecycle_state") == "completed":
            print(f"  ✓ reminder lifecycle_state=completed, last_fired_at={cur.get('last_fired_at')}")
            break
        # Also check for outputmessages
        out = MONGO.outputmessages.find_one(
            {"to_user": alice.coke_account_id, "metadata.reminder_id": str(rem_id)},
            sort=[("_id", -1)],
        )
        if out:
            print(f"  ✓ outputmessage written: id={out.get('_id')} status={out.get('status')}")
            fire_output = out
            break
        print(f"  ... waiting (elapsed {int(45 - (deadline - time.monotonic()))}s)")
    else:
        print("  ✗ TIMEOUT: no fire detected in 45s")

    # === Inspect ===
    print("\n=== POST-FIRE STATE ===")
    final = MONGO.reminders.find_one({"_id": rem_id})
    print(f"reminder: lifecycle={final.get('lifecycle_state')}, "
          f"next_fire_at={final.get('next_fire_at')}, "
          f"last_fired_at={final.get('last_fired_at')}, "
          f"last_error={final.get('last_error')}")

    outputs = list(MONGO.outputmessages.find(
        {"to_user": alice.coke_account_id},
        sort=[("_id", -1)],
    ).limit(5))
    print(f"\nrecent outputmessages to alice ({len(outputs)}):")
    for o in outputs:
        meta = o.get("metadata", {})
        rid = meta.get("reminder_id")
        is_fire = "★FIRE" if rid == str(rem_id) else ""
        msg = (o.get("message") or "")[:100]
        print(f"  {is_fire} {o['_id']} status={o.get('status')} msg={msg!r}")

    # T2: Alice queries her reminders — should reflect the completed state now
    step(t, alice, "我今天的喝水提醒怎么样了？已经完成了吗？", "verify_completed")

    t.set_verdict(
        passed=bool(fire_output),
        problems=[] if fire_output else ["fire_not_observed_within_45s"],
    )
    path = t.save(EVIDENCE_DIR)
    print(f"\nevidence={path}")
    print(f"\n=== VERDICT: {'PASSED' if fire_output else 'FAILED'} ===")


if __name__ == "__main__":
    main()
