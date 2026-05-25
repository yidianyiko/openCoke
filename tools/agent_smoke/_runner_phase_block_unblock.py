"""Friend block/unblock lifecycle smoke.

Alice and Bob become friends. Alice blocks Bob, Bob attempts a shared
reminder, Alice unblocks Bob, and Bob retries. Verdict comes from Postgres plus
assistant replies.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pymongo import MongoClient

from tools.agent_smoke import _config
from tools.agent_smoke.account_factory import provision_account
from tools.agent_smoke.bridge_client import send_as
from tools.agent_smoke.transcript import Transcript, Turn

BATCH = "block-unblock-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")

SUCCESS_MARKERS = ("已创建", "创建了", "设置好了", "安排好了", "已经安排", "success")
BLOCKED_MARKERS = (
    "屏蔽",
    "拉黑",
    "无法",
    "不能",
    "不可以",
    "blocked",
    "block",
    "未添加",
    "不是好友",
    "先加",
)


def _postgres(sql: str) -> str:
    result = subprocess.run(
        [
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            "15432",
            "-U",
            "clawscale",
            "-d",
            "clawscale",
            "-At",
            "-F",
            "\t",
            "-c",
            sql,
        ],
        env={"PGPASSWORD": "clawscale", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or result.stderr).strip()


def _postgres_table(sql: str) -> list[list[str]]:
    output = _postgres(sql)
    if not output:
        return []
    return [line.split("\t") for line in output.splitlines() if line.strip()]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _account_block_rows(alice_id: str, bob_id: str) -> list[list[str]]:
    return _postgres_table(
        """
SELECT blocker_account_id, blocked_account_id
  FROM account_blocks
 WHERE blocker_account_id = {alice}
   AND blocked_account_id = {bob}
 ORDER BY blocker_account_id, blocked_account_id;
""".format(
            alice=_quote(alice_id),
            bob=_quote(bob_id),
        )
    )


def _shared_request_rows(batch_label: str) -> list[list[str]]:
    return _postgres_table(
        """
SELECT id, requester_account_id, invitee_account_id, title, status
  FROM shared_reminder_requests
 WHERE requester_account_id LIKE {label}
    OR invitee_account_id LIKE {label}
 ORDER BY created_at, id;
""".format(
            label=_quote(f"%{batch_label}%"),
        )
    )


def _friendship_rows(batch_label: str) -> list[list[str]]:
    return _postgres_table(
        """
SELECT account_a_id, account_b_id, status
  FROM friendships
 WHERE account_a_id LIKE {label}
    OR account_b_id LIKE {label}
 ORDER BY account_a_id, account_b_id;
""".format(
            label=_quote(f"%{batch_label}%"),
        )
    )


def _postgres_snapshot(batch_label: str) -> str:
    return _postgres(
        """
SELECT 'customers', count(*) FROM customers
 WHERE id LIKE {label}
UNION ALL
SELECT 'friendships', count(*) FROM friendships
 WHERE account_a_id LIKE {label}
    OR account_b_id LIKE {label}
UNION ALL
SELECT 'friend_requests', count(*) FROM friend_requests
 WHERE requester_account_id LIKE {label}
    OR target_account_id LIKE {label}
UNION ALL
SELECT 'shared_reminder_requests', count(*) FROM shared_reminder_requests
 WHERE requester_account_id LIKE {label}
    OR invitee_account_id LIKE {label}
UNION ALL
SELECT 'account_blocks', count(*) FROM account_blocks
 WHERE blocker_account_id LIKE {label}
    OR blocked_account_id LIKE {label};
""".format(
            label=_quote(f"%{batch_label}%"),
        )
    )


def _mongo_outputs_for_accounts(account_ids: list[str]) -> list[dict]:
    return list(
        MongoClient(_config.mongo_uri())[_config.mongo_db_name()]
        .outputmessages.find({"to_user": {"$in": account_ids}})
        .sort("_id", 1)
    )


def _doc_json(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    return json.loads(json.dumps(doc, ensure_ascii=False, default=str))


def _step(t: Transcript, speaker: str, account, text: str, note: str = "") -> str:
    start = time.monotonic()
    turn_no = len(t.turns) + 1
    print(f"\n[T{turn_no:02d} {speaker}] >> {text}", flush=True)
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(
        f"[T{turn_no:02d} {speaker}] << ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}",
        flush=True,
    )
    t.add_turn(
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


def _extract_user_link_code(reply: str) -> str | None:
    match = re.search(r"/u/([A-Za-z0-9_-]+)", reply)
    if match:
        return match.group(1)
    match = re.search(r"\b([A-Za-z0-9_-]{8,})\b", reply)
    return match.group(1) if match else None


def _validate_blocked_attempt(
    reply: str,
    *,
    shared_request_count_delta: int,
) -> list[str]:
    problems: list[str] = []
    normalized = reply.strip()
    if not normalized:
        problems.append("blocked_reply_empty")
    if re.search(r"\b(?:ck|acct)_[A-Za-z0-9_-]+", normalized):
        problems.append("blocked_reply_leaks_internal_account_id")
    if shared_request_count_delta > 0:
        problems.append("blocked_attempt_created_shared_reminder")
    lower = normalized.lower()
    looks_successful = any(marker in normalized for marker in SUCCESS_MARKERS)
    looks_blocked = any(marker in lower for marker in BLOCKED_MARKERS) or any(
        marker in normalized for marker in BLOCKED_MARKERS
    )
    if looks_successful and not looks_blocked:
        problems.append("blocked_reply_silent_fake_success")
    return problems


def _validate_final_retry(
    reply: str,
    *,
    shared_request_count_delta: int,
) -> list[str]:
    if shared_request_count_delta <= 0:
        return ["final_retry_did_not_create_shared_reminder"]
    if re.search(r"\b(?:ck|acct)_[A-Za-z0-9_-]+", reply):
        return ["final_retry_reply_leaks_internal_account_id"]
    return []


def _save_evidence(
    transcript: Transcript,
    *,
    batch_label: str,
    snapshots: dict[str, Any],
    problems: list[str],
) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"block-unblock-{BATCH}.json"
    payload = {
        "batch_id": BATCH,
        "accounts": transcript.accounts,
        "turns": [asdict(turn) for turn in transcript.turns],
        "postgres": {
            **snapshots,
            "final_snapshot": _postgres_snapshot(batch_label),
        },
        "mongo_outputs": [
            _doc_json(doc)
            for doc in _mongo_outputs_for_accounts(
                [account["coke_account_id"] for account in transcript.accounts]
            )
        ],
        "findings": [],
        "verdict": {"passed": not problems, "problems": problems},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def main() -> int:
    batch_label = BATCH.replace("block-unblock-", "").replace("z", "").lower()
    print(f"BATCH={BATCH}")
    alice = provision_account(
        "alice",
        batch_id=batch_label,
        display_name="Alice Block",
    )
    bob = provision_account("bob", batch_id=batch_label, display_name="Bob Block")
    print(f"alice={alice.coke_account_id}")
    print(f"bob={bob.coke_account_id}")

    transcript = Transcript(batch_id=BATCH)
    transcript.add_account(alice)
    transcript.add_account(bob)
    problems: list[str] = []
    snapshots: dict[str, Any] = {}

    link_reply = _step(
        transcript,
        "alice",
        alice,
        "把我自己的好友邀请链接给我，我要分享给 Bob。",
        "alice_link",
    )
    link_code = _extract_user_link_code(link_reply)
    print(f"\n[parsed alice link_code={link_code}]")
    if not link_code:
        problems.append("alice_link_code_missing")
        path = _save_evidence(
            transcript, batch_label=batch_label, snapshots=snapshots, problems=problems
        )
        print(f"\nevidence={path}")
        print("VERDICT=FAILED")
        return 1

    _step(
        transcript,
        "bob",
        bob,
        f"我想加好友。这是对方的邀请链接码：{link_code}。备注：球友。",
        "bob_send_request",
    )
    _step(
        transcript,
        "alice",
        alice,
        "通过 Bob 的好友请求。",
        "alice_accept_request",
    )
    snapshots["after_friendship"] = {
        "friendships": _friendship_rows(batch_label),
        "account_blocks": _account_block_rows(
            alice.coke_account_id, bob.coke_account_id
        ),
    }

    _step(transcript, "alice", alice, "屏蔽 Bob。", "alice_block_bob")
    block_rows = _account_block_rows(alice.coke_account_id, bob.coke_account_id)
    snapshots["after_block"] = {
        "friendships": _friendship_rows(batch_label),
        "account_blocks": block_rows,
    }
    if len(block_rows) != 1:
        problems.append(f"block_row_count_after_block={len(block_rows)}")

    before_blocked_count = len(_shared_request_rows(batch_label))
    blocked_reply = _step(
        transcript,
        "bob",
        bob,
        "提醒我和 Alice 周日打球。",
        "bob_attempt_while_blocked",
    )
    after_blocked_rows = _shared_request_rows(batch_label)
    snapshots["after_blocked_attempt"] = {
        "shared_reminder_requests": after_blocked_rows,
        "account_blocks": _account_block_rows(
            alice.coke_account_id, bob.coke_account_id
        ),
    }
    problems.extend(
        _validate_blocked_attempt(
            blocked_reply,
            shared_request_count_delta=len(after_blocked_rows) - before_blocked_count,
        )
    )

    _step(transcript, "alice", alice, "取消屏蔽 Bob。", "alice_unblock_bob")
    unblock_rows = _account_block_rows(alice.coke_account_id, bob.coke_account_id)
    snapshots["after_unblock"] = {
        "friendships": _friendship_rows(batch_label),
        "account_blocks": unblock_rows,
    }
    if unblock_rows:
        problems.append(f"block_row_count_after_unblock={len(unblock_rows)}")

    before_retry_count = len(_shared_request_rows(batch_label))
    retry_reply = _step(
        transcript,
        "bob",
        bob,
        "提醒我和 Alice 周日打球。",
        "bob_retry_after_unblock",
    )
    final_rows = _shared_request_rows(batch_label)
    snapshots["after_final_retry"] = {
        "shared_reminder_requests": final_rows,
        "account_blocks": _account_block_rows(
            alice.coke_account_id, bob.coke_account_id
        ),
        "friendships": _friendship_rows(batch_label),
    }
    problems.extend(
        _validate_final_retry(
            retry_reply,
            shared_request_count_delta=len(final_rows) - before_retry_count,
        )
    )

    path = _save_evidence(
        transcript, batch_label=batch_label, snapshots=snapshots, problems=problems
    )
    print("\n=== POSTGRES SNAPSHOT ===")
    print(_postgres_snapshot(batch_label))
    print(f"\nevidence={path}")
    print(f"VERDICT={'PASSED' if not problems else 'FAILED'}")
    if problems:
        print("problems=" + ", ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
