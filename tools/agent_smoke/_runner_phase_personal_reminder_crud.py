"""Single-user personal reminder CRUD smoke. No friend graph involved.

Drives the reminder_domain (not scheduling_domain) path via the agent's
`visible_reminder_tool` capability. Backend is `ReminderRuntimeContract`.

Expected post-conditions per turn — verify with mongo `reminders` directly:
- T1 create  → 1 active row with title 跑步 + next_fire_at ~ tomorrow 07:00
- T2 list    → assistant lists it
- T3 update  → same _id, next_fire_at shifted to 07:30
- T4 cancel  → lifecycle_state=cancelled, next_fire_at=null
- T5 create recurring → rrule set on new row
- T6 ambiguous reference (multiple reminders exist) → assistant ASKS which one
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from tools.agent_smoke.account_factory import SmokeAccount, provision_account
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

# Two modes:
#   <batch_id>                    resume from existing batch_id (uses state)
#   --fresh                       provision a single Alice for a fresh batch
BATCH_ID = sys.argv[1] if len(sys.argv) > 1 else None
FRESH = BATCH_ID == "--fresh"

EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")


def step(transcript, account, text, note=""):
    start = time.monotonic()
    turn_no = len(transcript.turns) + 1
    print(f"\n[T{turn_no:02d} alice] >> {text}", flush=True)
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(
        f"[T{turn_no:02d} alice] <<  ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}",
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
            note=note or None,
        )
    )
    return reply.reply


def main():
    if FRESH or not BATCH_ID:
        batch_id = "reminder-crud-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
        alice = provision_account(
            "alice",
            batch_id=batch_id.replace("-", "").lower(),
            display_name="Alice Reminder",
        )
        t = Transcript(batch_id=batch_id)
        t.add_account(alice)
        state_path = EVIDENCE_DIR / f"_state-{batch_id}.json"
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "alice": {
                        "coke_account_id": alice.coke_account_id,
                        "tenant_id": alice.tenant_id,
                        "clawscale_user_id": alice.clawscale_user_id,
                    }
                },
                indent=2,
            )
        )
    else:
        state = json.loads((EVIDENCE_DIR / f"_state-{BATCH_ID}.json").read_text())
        alice_d = state["alice"]
        alice_d.setdefault("label", "alice")
        alice_d.setdefault("display_name", "Alice Smoke")
        alice = SmokeAccount(
            coke_account_id=alice_d["coke_account_id"],
            display_name=alice_d["display_name"],
            label=alice_d.get("label") or "alice",
            tenant_id=alice_d.get("tenant_id"),
            clawscale_user_id=alice_d.get("clawscale_user_id"),
        )
        evid = EVIDENCE_DIR / f"shared-reminder-agent-smoke-{BATCH_ID}.json"
        if evid.exists():
            raw = json.loads(evid.read_text())
            t = Transcript(batch_id=raw["batch_id"])
            t.accounts = raw.get("accounts", [])
            for tr in raw.get("turns", []):
                t.turns.append(Turn(**tr))
            t.findings = raw.get("findings", [])
        else:
            t = Transcript(batch_id=BATCH_ID)
            t.add_account(alice)

    print(f"alice={alice.coke_account_id} batch={t.batch_id}")

    step(t, alice, "提醒我明天早上 7 点跑步 30 分钟。", "crud_create")
    step(t, alice, "看看我有哪些提醒？", "crud_list_one")
    step(t, alice, "把刚才那个跑步提醒改到早上 7 点半。", "crud_update_time")
    step(t, alice, "看看现在跑步提醒是几点？", "crud_verify_update")
    step(t, alice, "取消跑步提醒。", "crud_cancel")
    step(t, alice, "再帮我设两个提醒：每周一早上 8 点拉伸；明天下午 3 点喝水。", "crud_two_more")
    step(t, alice, "改一下提醒时间。", "crud_ambiguous_should_ask")

    t.save("artifacts/evidence/shared-reminder-agent-smoke")
    print(f"\nevidence=artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-{t.batch_id}.json")


if __name__ == "__main__":
    main()
