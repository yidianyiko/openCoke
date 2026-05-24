"""Phase 4: Bob receives the shared-reminder notification, lists pending,
and accepts Alice's invitation. Closes the loop.

Pre-condition: phases 1-3 ran in this batch_id; postgres has
`shared_reminder_requests.status=pending_invitee_confirmation` from Alice
to Bob. If that's not true, this phase will have nothing to accept and
the assistant should honestly say so — that itself is a finding.

Post-condition expected by SKILL.md:
- shared_reminder_requests.status=accepted
- both requester_reminder_id and invitee_reminder_id populated
- mongo `reminders` has two active docs (one per owner)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from tools.agent_smoke.account_factory import SmokeAccount
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH_ID = sys.argv[1]
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
STATE_PATH = EVIDENCE_DIR / f"_state-{BATCH_ID}.json"
EVIDENCE_PATH = EVIDENCE_DIR / f"shared-reminder-agent-smoke-{BATCH_ID}.json"


def load_account(d: dict) -> SmokeAccount:
    return SmokeAccount(
        coke_account_id=d["coke_account_id"],
        display_name=d.get("display_name") or d["coke_account_id"],
        label=d.get("label") or "",
        tenant_id=d.get("tenant_id"),
        clawscale_user_id=d.get("clawscale_user_id"),
    )


def load_transcript() -> Transcript:
    raw = json.loads(EVIDENCE_PATH.read_text())
    t = Transcript(batch_id=raw["batch_id"])
    t.accounts = raw.get("accounts", [])
    for tr in raw.get("turns", []):
        t.turns.append(Turn(**tr))
    t.findings = raw.get("findings", [])
    return t


def step(transcript, speaker, account, text, note=""):
    start = time.monotonic()
    turn_no = len(transcript.turns) + 1
    print(f"\n[T{turn_no:02d} {speaker}] >> {text}", flush=True)
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(
        f"[T{turn_no:02d} {speaker}] <<  ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}",
        flush=True,
    )
    transcript.add_turn(
        Turn(
            turn=turn_no,
            speaker=speaker,
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
    state = json.loads(STATE_PATH.read_text())
    bob_d = state["bob"]
    bob_d.setdefault("label", "bob")
    bob_d.setdefault("display_name", "Bob Smoke")
    bob = load_account(bob_d)

    t = load_transcript()
    print(f"Resumed transcript at turn={len(t.turns)} with batch={BATCH_ID}")

    # T11 — Bob asks for pending shared reminders. Should see Alice's invite.
    step(
        t,
        "bob",
        bob,
        "我现在有没有待处理的共享提醒？只列待处理的，告诉我是谁发的、什么内容。",
        "bob_list_pending_shared_reminders",
    )

    # T12 — Bob explicitly accepts Alice's shared reminder. The scheduling
    # backend resolves the single matching invite by requester_name="Alice"
    # (gateway resolveSharedReminderRequestId fuzzy lookup); fails closed if
    # ambiguous.
    step(
        t,
        "bob",
        bob,
        "接受 Alice 发来的共享提醒。",
        "bob_accept_shared_reminder",
    )

    # T13 — Bob confirms his own reminder list now contains the event.
    step(
        t,
        "bob",
        bob,
        "看看我现在所有的提醒，特别是和 Alice 的那条。",
        "bob_verify_own_reminders",
    )

    # T14 — Friendly close-out turn so the transcript ends on a clean reply
    # rather than a write action. Useful when the next codex inspects history.
    step(
        t,
        "bob",
        bob,
        "搞定了，谢谢～",
        "bob_close_out",
    )

    t.save("artifacts/evidence/shared-reminder-agent-smoke")
    print(f"\nevidence={EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
