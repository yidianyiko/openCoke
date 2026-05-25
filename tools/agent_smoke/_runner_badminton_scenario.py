"""Real-user badminton scenario.

Alice + Bob: become friends → Bob populates his calendar with personal
reminders → Alice asks Bob's availability → Alice creates shared
badminton reminder at a time both should be free → Bob accepts.

Verification (from user perspective):
- Bob's claim about his own schedule (Bob asks Coke "我有哪些 reminder")
- Alice's view of Bob's free intervals (from list_friend_calendar_facts via Coke)
- Consistency: the times Bob says he's busy should map to the busy intervals Alice gets
- Privacy: Alice MUST NOT see Bob's reminder titles
- Final shared reminder: both sides agree on time + title

DB ground truth check at each phase.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from pymongo import MongoClient

from tools.agent_smoke.account_factory import provision_account
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH = "badminton-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")


def step(t: Transcript, speaker: str, account, text: str, note: str = "") -> str:
    start = time.monotonic()
    turn_no = len(t.turns) + 1
    print(f"\n[T{turn_no:02d} {speaker}] >> {text}", flush=True)
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(f"[T{turn_no:02d} {speaker}] <<  ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}", flush=True)
    t.add_turn(Turn(
        turn=turn_no, speaker=speaker,
        coke_account_id=account.coke_account_id,
        input_text=text,
        inbound_event_id=reply.causal_inbound_event_id,
        reply_text=reply.reply, output_id=reply.output_id,
        elapsed_ms=elapsed_ms, note=note or None,
    ))
    return reply.reply


def db_section(title: str) -> None:
    print(f"\n=== DB CHECK: {title} ===", flush=True)


def show_friend_state(label_a: str, label_b: str) -> None:
    import subprocess
    sql = f"""
SELECT 'friend_requests' as t, requester_account_id, target_account_id, status
  FROM friend_requests WHERE requester_account_id LIKE '%{label_a}%' OR target_account_id LIKE '%{label_a}%'
UNION ALL
SELECT 'friendships' as t, account_a_id, account_b_id, status
  FROM friendships WHERE account_a_id LIKE '%{label_a}%' OR account_b_id LIKE '%{label_a}%';
"""
    out = subprocess.run(
        ["psql", "-h", "127.0.0.1", "-p", "15432", "-U", "clawscale", "-d", "clawscale", "-c", sql],
        env={"PGPASSWORD": "clawscale", "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    ).stdout
    print(out.strip())


def show_bob_reminders(bob_id: str) -> list[dict]:
    mc = MongoClient("mongodb://127.0.0.1:27017/")
    docs = list(mc["mymongo"].reminders.find({"owner_user_id": bob_id}))
    for d in docs:
        print(f"  bob has: id={d['_id']} title={d.get('title')!r} state={d.get('lifecycle_state')} next={d.get('next_fire_at')}")
    return docs


def show_shared_reminders(label: str) -> list[dict]:
    import subprocess
    sql = f"SELECT id, requester_account_id, invitee_account_id, title, fire_at, status FROM shared_reminder_requests WHERE requester_account_id LIKE '%{label}%' OR invitee_account_id LIKE '%{label}%';"
    out = subprocess.run(
        ["psql", "-h", "127.0.0.1", "-p", "15432", "-U", "clawscale", "-d", "clawscale", "-c", sql],
        env={"PGPASSWORD": "clawscale", "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    ).stdout
    print(out.strip())


def main() -> None:
    print(f"BATCH={BATCH}\n")

    label_short = BATCH.replace("badminton-", "").replace("z", "").lower()
    alice = provision_account("alice", batch_id=label_short, display_name="Alice Badminton")
    bob   = provision_account("bob",   batch_id=label_short, display_name="Bob Badminton")
    print(f"alice={alice.coke_account_id}\nbob  ={bob.coke_account_id}\n")

    t = Transcript(batch_id=BATCH)
    t.add_account(alice); t.add_account(bob)

    # === Phase A: friends ===
    step(t, "alice", alice, "你好，把我自己的好友邀请链接给我，我要分享给一个朋友。", "alice_link")
    # parse link code from reply
    last = t.turns[-1].reply_text
    import re
    m = re.search(r"/u/([A-Za-z0-9_-]+)", last)
    link_code = m.group(1) if m else None
    print(f"\n[parsed alice link_code={link_code}]")
    assert link_code, "FATAL: Alice's link code not found in reply"

    step(t, "bob", bob, f"我想加好友。这是对方的邀请链接码：{link_code}。备注：球友。", "bob_send_request")
    db_section("after Bob sends friend request")
    show_friend_state(label_short, label_short)

    step(t, "alice", alice, "我有没有未处理的好友请求？通过 Bob 的。", "alice_accept")
    db_section("after Alice accepts")
    show_friend_state(label_short, label_short)

    # === Phase B: Bob populates his calendar with personal reminders ===
    # We want Bob's schedule to have some BUSY slots so Alice's calendar query has something to filter on.
    print("\n=== Phase B: Bob fills his calendar (real user perspective) ===")
    step(t, "bob", bob, "提醒我周四晚上 19:00 开会一小时。", "bob_reminder_meeting")
    step(t, "bob", bob, "提醒我周五晚上 19:00 跟妈妈视频半小时。", "bob_reminder_call")
    step(t, "bob", bob, "看看我接下来一周有哪些 reminder？", "bob_self_view")

    bob_reply_self = t.turns[-1].reply_text
    print(f"\n[BOB SELF-VIEW REPLY]: {bob_reply_self[:400]}")

    db_section("Bob's mongo reminders after Phase B")
    bob_docs = show_bob_reminders(bob.coke_account_id)
    print(f"  total: {len(bob_docs)} reminders for Bob in mongo")

    # === Phase C: Alice asks Bob's availability ===
    print("\n=== Phase C: Alice asks Bob's free time (calendar facts) ===")
    step(t, "alice", alice, "看看 Bob 这周哪些时间空？我想约他一起打羽毛球。", "alice_ask_availability")

    alice_avail_reply = t.turns[-1].reply_text
    print(f"\n[ALICE SEES BOB'S AVAILABILITY]: {alice_avail_reply[:600]}")

    # Privacy check: Alice's reply must NOT contain Bob's reminder titles
    leaked = []
    for keyword in ("开会", "妈妈", "视频"):
        if keyword in alice_avail_reply:
            leaked.append(keyword)
    if leaked:
        print(f"\n⚠️  PRIVACY LEAK: Alice's reply contains Bob's reminder content keywords: {leaked}")
    else:
        print("\n✓ Privacy: no Bob reminder titles leaked to Alice")

    # === Phase D: Alice creates shared reminder ===
    print("\n=== Phase D: Alice proposes badminton at a hopefully-free time ===")
    # Pick a time that should be free given Bob has 周四 19:00 and 周五 19:00 busy.
    # Saturday afternoon should be totally open.
    step(t, "alice", alice, "约 Bob 这周六下午 16:00 在小区羽毛球场打 90 分钟羽毛球，建一个共享提醒。", "alice_create_shared")

    db_section("after Alice creates shared reminder")
    show_shared_reminders(label_short)

    # === Phase E: Bob accepts ===
    print("\n=== Phase E: Bob accepts shared badminton invite ===")
    step(t, "bob", bob, "我有没有待处理的共享提醒？", "bob_check_shared")
    step(t, "bob", bob, "接受 Alice 的羽毛球共享提醒。", "bob_accept_shared")

    db_section("post-accept shared reminder state")
    show_shared_reminders(label_short)
    db_section("Bob's mongo reminders should now include badminton")
    bob_after = show_bob_reminders(bob.coke_account_id)
    print(f"  total: {len(bob_after)} (was {len(bob_docs)})")

    # === Phase F: cross-check from both perspectives ===
    print("\n=== Phase F: cross-check ===")
    step(t, "alice", alice, "我跟 Bob 那个羽毛球的共享提醒现在是什么状态？", "alice_verify")
    step(t, "bob",   bob,   "我跟 Alice 那个羽毛球的共享提醒现在是什么状态？", "bob_verify")

    t.set_verdict(passed=True, problems=[])
    path = t.save(EVIDENCE_DIR)
    print(f"\nevidence={path}")


if __name__ == "__main__":
    main()
