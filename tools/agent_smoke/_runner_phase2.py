"""Phase 2: Bob greets + Bob inbox + Bob adds Alice via her link.

Reads accounts and link code from phase 1's state file.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from tools.agent_smoke.account_factory import SmokeAccount
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH_ID = sys.argv[1] if len(sys.argv) > 1 else None
if not BATCH_ID:
    print("usage: _runner_phase2.py <batch_id>")
    sys.exit(1)

EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
STATE_PATH = EVIDENCE_DIR / f"_state-{BATCH_ID}.json"
EVIDENCE_PATH = EVIDENCE_DIR / f"shared-reminder-agent-smoke-{BATCH_ID}.json"

# Alice's link code from T3 in phase 1 — pass via env or hardcode here.
ALICE_LINK_CODE = sys.argv[2] if len(sys.argv) > 2 else None
if not ALICE_LINK_CODE:
    print("usage: _runner_phase2.py <batch_id> <alice_link_code>")
    sys.exit(1)


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
    # Bring back the SmokeAccount objects (label info isn't in the state file)
    bob_d = state["bob"]
    bob_d.setdefault("label", "bob")
    bob_d.setdefault("display_name", "Bob Smoke")
    bob = load_account(bob_d)

    transcript = load_transcript()
    print(f"Resumed transcript at turn={len(transcript.turns)} with batch={BATCH_ID}")

    # T4 — Bob greets, mirror of Alice's T1 to test if raw JSON envelope is universal.
    step(transcript, "bob", bob, "你好，我是 Bob，我刚登录。", "first_turn_repro")

    # T5 — Bob asks for inbox / pending notifications.
    step(transcript, "bob", bob, "我现在有没有未处理的好友请求或通知？只列待处理的。", "inbox_check")

    # T6 — Bob uses Alice's user link to send a friend request.
    step(transcript, "bob", bob, f"我想加好友。这是对方的邀请链接码：{ALICE_LINK_CODE}。备注：跑步搭子。", "friend_request_via_link")

    transcript.save("artifacts/evidence/shared-reminder-agent-smoke")
    print(f"\nevidence={EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
