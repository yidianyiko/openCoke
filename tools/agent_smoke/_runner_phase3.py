"""Phase 3: Alice checks friend requests, accepts Bob, then proposes a shared reminder."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from tools.agent_smoke.account_factory import SmokeAccount
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH_ID = sys.argv[1] if len(sys.argv) > 1 else None
if not BATCH_ID:
    print("usage: _runner_phase3.py <batch_id>")
    sys.exit(1)

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


def step(transcript: Transcript, speaker: str, account: SmokeAccount, text: str, note: str = "") -> str:
    start = time.monotonic()
    turn_no = len(transcript.turns) + 1
    print(f"\n[T{turn_no:02d} {speaker}] >> {text}", flush=True)
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(f"[T{turn_no:02d} {speaker}] <<  ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}", flush=True)
    transcript.add_turn(Turn(
        turn=turn_no,
        speaker=speaker,
        coke_account_id=account.coke_account_id,
        input_text=text,
        inbound_event_id=reply.causal_inbound_event_id,
        reply_text=reply.reply,
        output_id=reply.output_id,
        elapsed_ms=elapsed_ms,
        note=note or None,
    ))
    return reply.reply


def main() -> None:
    state = json.loads(STATE_PATH.read_text())
    alice_d = state["alice"]
    alice_d.setdefault("label", "alice")
    alice_d.setdefault("display_name", "Alice Smoke")
    alice = load_account(alice_d)

    transcript = load_transcript()
    print(f"Resumed transcript at turn={len(transcript.turns)} with batch={BATCH_ID}")

    # T7 — Alice asks for pending friend requests. Should now see Bob's.
    step(transcript, "alice", alice, "我现在有没有未处理的好友请求？", "alice_inbox_after_bob_request")

    # T8 — Alice accepts Bob's friend request.
    step(transcript, "alice", alice, "通过 Bob 的好友请求。", "alice_accept_bob")

    # T9 — Alice verifies friendship.
    step(transcript, "alice", alice, "看看我现在都有哪些好友。", "alice_list_friends")

    # T10 — Alice proposes a shared reminder with Bob.
    step(transcript, "alice", alice, "我想约 Bob 这周五晚上 19:30 一起在小区操场跑步 40 分钟，帮我们两个建一个共享提醒。", "alice_create_shared_reminder")

    transcript.save("artifacts/evidence/shared-reminder-agent-smoke")
    print(f"\nevidence={EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
