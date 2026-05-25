"""Mirror of phase 3 but Alice rejects Bob's incoming friend request.

Pre-condition: phases 1+2 ran; postgres has Bob → Alice friend_request
with status=pending. This runner verifies the negative path.

Expected post-condition:
- friend_requests.status = rejected
- friendships: 0 rows
- Bob (in his own conversation) should NOT subsequently see Alice as a friend
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
    alice_d = state["alice"]
    alice_d.setdefault("label", "alice")
    alice_d.setdefault("display_name", "Alice Smoke")
    bob_d = state["bob"]
    bob_d.setdefault("label", "bob")
    bob_d.setdefault("display_name", "Bob Smoke")
    alice = load_account(alice_d)
    bob = load_account(bob_d)

    t = load_transcript()
    print(f"Resumed transcript at turn={len(t.turns)} with batch={BATCH_ID}")

    # Alice rejects Bob's friend request.
    step(t, "alice", alice, "拒绝 Bob 的好友请求。", "alice_reject_bob")

    # Alice verifies no friend in her list.
    step(t, "alice", alice, "看看我现在的好友列表。", "alice_friends_after_reject")

    # Bob asks if his request went through. Honest answer should be: it was rejected
    # / nothing pending. NOT a fabricated success.
    step(
        t,
        "bob",
        bob,
        "我之前发给 Alice 的好友请求她有反应了吗？",
        "bob_check_request_status",
    )

    t.save("artifacts/evidence/shared-reminder-agent-smoke")
    print(f"\nevidence={EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
