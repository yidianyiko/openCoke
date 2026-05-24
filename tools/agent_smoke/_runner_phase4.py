"""Phase 4: retry Alice's accept + close the loop or document failure."""

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
    print(f"[T{turn_no:02d} {speaker}] <<  ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}", flush=True)
    transcript.add_turn(Turn(
        turn=turn_no, speaker=speaker,
        coke_account_id=account.coke_account_id,
        input_text=text,
        inbound_event_id=reply.causal_inbound_event_id,
        reply_text=reply.reply, output_id=reply.output_id,
        elapsed_ms=elapsed_ms, note=note or None,
    ))
    return reply.reply


def main():
    state = json.loads(STATE_PATH.read_text())
    alice_d = state["alice"]; alice_d.setdefault("label", "alice"); alice_d.setdefault("display_name", "Alice Smoke")
    bob_d = state["bob"]; bob_d.setdefault("label", "bob"); bob_d.setdefault("display_name", "Bob Smoke")
    alice = load_account(alice_d)
    bob = load_account(bob_d)

    t = load_transcript()
    print(f"Resumed transcript at turn={len(t.turns)} with batch={BATCH_ID}")

    # T11 — Alice retries: explicit re-request to see if bug is transient or persistent.
    step(t, "alice", alice, "好像刚才有问题。再帮我看一下：我现在的好友请求列表，把 Bob 的通过。", "retry_after_empty_response")

    # T12 — Alice lists friends again to verify the accept landed.
    step(t, "alice", alice, "现在我的好友里有谁？", "alice_friends_after_retry")

    # T13 — If alice has friends, try shared reminder again.
    step(t, "alice", alice, "约 Bob 这周五晚上 19:30 在小区操场跑步 40 分钟，帮我们俩建一个共享提醒。", "alice_shared_reminder_after_friend")

    # T14 — Bob: check pending shared reminders.
    step(t, "bob", bob, "我有没有待处理的共享提醒？只列待处理的。", "bob_pending_shared_reminders")

    t.save("artifacts/evidence/shared-reminder-agent-smoke")
    print(f"\nevidence={EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
