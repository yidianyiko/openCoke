"""Phase 1: provision + Alice greeting + Alice asks for her user link."""

from __future__ import annotations

import json
import time
from pathlib import Path

from tools.agent_smoke.account_factory import provision_account
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH_ID = time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
STATE_PATH = Path("artifacts/evidence/shared-reminder-agent-smoke") / f"_state-{BATCH_ID}.json"


def step(transcript: Transcript, speaker: str, account, text: str, note: str = "") -> str:
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
    print(f"BATCH_ID={BATCH_ID}")
    alice = provision_account("alice", batch_id=BATCH_ID, display_name="Alice Smoke")
    bob = provision_account("bob", batch_id=BATCH_ID, display_name="Bob Smoke")
    print(f"alice ck_id={alice.coke_account_id} tenant={alice.tenant_id} csu={alice.clawscale_user_id}")
    print(f"bob   ck_id={bob.coke_account_id} tenant={bob.tenant_id} csu={bob.clawscale_user_id}")

    transcript = Transcript(batch_id=BATCH_ID)
    transcript.add_account(alice)
    transcript.add_account(bob)

    # T1 — Alice greets and asks the assistant to summarize what it can help with.
    step(transcript, "alice", alice, "你好，我刚登录。能简单介绍一下你能帮我做什么吗？", "greeting")

    # T2 — Alice explicitly asks if she has any pending notifications / friend requests.
    step(transcript, "alice", alice, "我现在有没有未处理的好友请求或系统通知？只列待处理的。", "inbox_check")

    # T3 — Alice asks the assistant for her own user link so she can share it with Bob.
    step(transcript, "alice", alice, "把我自己的好友邀请链接给我，我要分享给一个朋友。", "request_user_link")

    # Save evidence + state
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({
        "batch_id": BATCH_ID,
        "alice": {
            "coke_account_id": alice.coke_account_id,
            "tenant_id": alice.tenant_id,
            "clawscale_user_id": alice.clawscale_user_id,
        },
        "bob": {
            "coke_account_id": bob.coke_account_id,
            "tenant_id": bob.tenant_id,
            "clawscale_user_id": bob.clawscale_user_id,
        },
    }, indent=2))
    transcript.set_verdict(passed=False, problems=["phase1_only_no_verdict_yet"])
    path = transcript.save("artifacts/evidence/shared-reminder-agent-smoke")
    print(f"\nevidence={path}")
    print(f"state={STATE_PATH}")


if __name__ == "__main__":
    main()
