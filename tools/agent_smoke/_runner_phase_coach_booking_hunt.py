"""Stateful coach-booking smoke hunt.

This runner intentionally does not change product code. It drives the live
bridge as four synthetic Coke accounts, snapshots mongo/postgres before and
after each case, classifies observed behavior, and writes one evidence file.
"""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import requests
from bson import ObjectId
from pymongo import MongoClient

from tools.agent_smoke import _config
from tools.agent_smoke.account_factory import SmokeAccount, provision_account
from tools.agent_smoke.bridge_client import BridgeError, send_as
from tools.agent_smoke.postgres_seed import _run_psql
from tools.agent_smoke.transcript import Transcript, Turn

BATCH = time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
ACCOUNT_BATCH = "coachbooking" + BATCH.lower().replace("t", "").replace("z", "")
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
EVIDENCE_PATH = EVIDENCE_DIR / f"coach-booking-{BATCH}.json"

EMPTY_FALLBACK_TOKENS = ("我没接住你刚才的意思", "我这次没能及时整理")
SUCCESS_CLAIM_TOKENS = ("已", "已经", "成功", "帮你约", "约好了", "创建", "提交", "接受")
REFUSAL_TOKENS = ("不能", "无法", "不可以", "没法", "不能约", "过去", "昨天", "请明确", "具体")
CLARIFY_TOKENS = ("几点", "具体", "哪一个", "哪位", "哪个", "请确认", "请明确", "上午几点")
INVENTED_AVAILABILITY_TOKENS = ("工作时间", "营业时间", "上课时间", "9点以后", "09:00", "太早")
RAW_ENVELOPE_RE = re.compile(r"```json|MultiModalResponses|\"message_type\"")


class BlockedSetup(RuntimeError):
    pass


def _json_default(value: Any) -> str:
    return str(value)


def _clean(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _stable(value: Any) -> str:
    return json.dumps(_clean(value), ensure_ascii=False, sort_keys=True, default=_json_default)


def _doc_key(doc: dict[str, Any]) -> str:
    return str(doc.get("_id") or doc.get("id"))


def _diff_rows(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    before_by_id = {_doc_key(row): _clean(row) for row in before}
    after_by_id = {_doc_key(row): _clean(row) for row in after}
    added = [after_by_id[k] for k in sorted(after_by_id.keys() - before_by_id.keys())]
    removed = [before_by_id[k] for k in sorted(before_by_id.keys() - after_by_id.keys())]
    modified = [
        {"before": before_by_id[k], "after": after_by_id[k]}
        for k in sorted(before_by_id.keys() & after_by_id.keys())
        if _stable(before_by_id[k]) != _stable(after_by_id[k])
    ]
    return {
        "added": len(added),
        "modified": len(modified),
        "removed": len(removed),
        "added_rows": added,
        "modified_rows": modified,
        "removed_rows": removed,
    }


def _diff_snapshot(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        group: {
            name: _diff_rows(before[group][name], after[group][name])
            for name in before[group]
        }
        for group in before
    }


def _sql_json(sql: str) -> list[dict[str, Any]]:
    raw = _run_psql(sql).strip()
    if not raw:
        return []
    return json.loads(raw)


def _ids_sql(accounts: dict[str, SmokeAccount]) -> str:
    values = []
    for account in accounts.values():
        values.append("'" + account.coke_account_id.replace("'", "''") + "'")
    return ",".join(values)


def _postgres_snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, list[dict[str, Any]]]:
    ids = _ids_sql(accounts)
    return {
        "friendships": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT id, account_a_id, account_b_id, friend_request_id, status::text,
         removed_at::text, created_at::text, updated_at::text
    FROM friendships
   WHERE account_a_id IN ({ids}) OR account_b_id IN ({ids})
) t;
"""
        ),
        "shared_reminder_requests": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT id, requester_account_id, invitee_account_id, friendship_id, title,
         fire_at::text, timezone, duration_minutes, idempotency_key,
         status::text, requester_reminder_id, invitee_reminder_id,
         resolved_at::text, created_at::text, updated_at::text
    FROM shared_reminder_requests
   WHERE requester_account_id IN ({ids}) OR invitee_account_id IN ({ids})
) t;
"""
        ),
        "account_blocks": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT id, blocker_account_id, blocked_account_id, created_at::text
    FROM account_blocks
   WHERE blocker_account_id IN ({ids}) OR blocked_account_id IN ({ids})
) t;
"""
        ),
        "customers": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT id, kind::text, display_name, created_at::text, updated_at::text,
         avatar_url, tagline
    FROM customers
   WHERE id IN ({ids})
) t;
"""
        ),
    }


def _mongo_snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, list[dict[str, Any]]]:
    account_ids = [account.coke_account_id for account in accounts.values()]
    db = MongoClient(_config.mongo_uri())[_config.mongo_db_name()]
    return {
        "reminders": list(db.reminders.find({"owner_user_id": {"$in": account_ids}}).sort("_id", 1)),
        "outputmessages": list(db.outputmessages.find({"to_user": {"$in": account_ids}}).sort("_id", 1)),
        "inputmessages": list(
            db.inputmessages.find(
                {"$or": [{"from_user": {"$in": account_ids}}, {"to_user": {"$in": account_ids}}]}
            ).sort("_id", 1)
        ),
        "agent_sessions": list(db.agent_sessions.find().sort("updated_at", -1).limit(80)),
    }


def snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, Any]:
    return {
        "mongo": _mongo_snapshot(accounts),
        "postgres": _postgres_snapshot(accounts),
    }


def _brief_delta(delta: dict[str, Any]) -> dict[str, Any]:
    return {
        group: {
            name: {
                "added": item["added"],
                "modified": item["modified"],
                "removed": item["removed"],
            }
            for name, item in tables.items()
        }
        for group, tables in delta.items()
    }


def _print_turn(turn_no: int, speaker: str, text: str) -> None:
    print(f"\n[T{turn_no:02d} {speaker}] >> {text}", flush=True)


def _record_turn(
    transcript: Transcript,
    speaker: str,
    account: SmokeAccount,
    text: str,
    *,
    note: str,
    lock: threading.Lock | None = None,
) -> Turn:
    guard = lock or threading.Lock()
    with guard:
        turn_no = len(transcript.turns) + 1
        _print_turn(turn_no, speaker, text)
    start = time.monotonic()
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    turn = Turn(
        turn=turn_no,
        speaker=speaker,
        coke_account_id=account.coke_account_id,
        input_text=text,
        inbound_event_id=reply.causal_inbound_event_id,
        reply_text=reply.reply,
        output_id=reply.output_id,
        elapsed_ms=elapsed_ms,
        note=note,
    )
    with guard:
        transcript.add_turn(turn)
        print(
            f"[T{turn_no:02d} {speaker}] << ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}",
            flush=True,
        )
    return turn


def _reply_text(turns: list[Turn]) -> str:
    return "\n".join(turn.reply_text or "" for turn in turns)


def _bug_pattern(turns: list[Turn], *, mutation_expected: bool, mutation_happened: bool) -> str:
    text = _reply_text(turns)
    if RAW_ENVELOPE_RE.search(text):
        return "A"
    if any(token in text for token in EMPTY_FALLBACK_TOKENS) or not text.strip():
        return "B"
    if any("ValidationError" in turn.reply_text or "Tool call limit" in turn.reply_text for turn in turns):
        return "D1"
    if "not_found" in text or "找不到" in text:
        return "D2"
    if any(turn.elapsed_ms >= 180000 and not turn.reply_text for turn in turns):
        return "F"
    if mutation_expected and not mutation_happened and any(token in text for token in SUCCESS_CLAIM_TOKENS):
        return "C"
    return "NEW"


def _finding(
    case_id: str,
    expected: str,
    observed: str,
    turns: list[Turn],
    delta: dict[str, Any],
    *,
    mutation_expected: bool,
    mutation_happened: bool,
    severity: str = "visible-error",
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "verdict": "FINDING",
        "bug_pattern": _bug_pattern(
            turns,
            mutation_expected=mutation_expected,
            mutation_happened=mutation_happened,
        ),
        "severity": severity,
        "expected": expected,
        "observed": observed,
        "agent_reply": _reply_text(turns),
        "mongo_delta": delta["mongo"],
        "postgres_delta": delta["postgres"],
    }


def _passed(case_id: str, expected: str, observed: str, turns: list[Turn], delta: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "verdict": "PASSED",
        "bug_pattern": "",
        "severity": "",
        "expected": expected,
        "observed": observed,
        "agent_reply": _reply_text(turns),
        "mongo_delta": delta["mongo"],
        "postgres_delta": delta["postgres"],
    }


def _blocked(case_id: str, expected: str, observed: str, turns: list[Turn], delta: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "verdict": "BLOCKED",
        "bug_pattern": "",
        "severity": "",
        "expected": expected,
        "observed": observed,
        "agent_reply": _reply_text(turns),
        "mongo_delta": (delta or {}).get("mongo", {}),
        "postgres_delta": (delta or {}).get("postgres", {}),
    }


def _shared_added(delta: dict[str, Any]) -> list[dict[str, Any]]:
    return delta["postgres"]["shared_reminder_requests"]["added_rows"]


def _shared_modified_after(delta: dict[str, Any]) -> list[dict[str, Any]]:
    return [row["after"] for row in delta["postgres"]["shared_reminder_requests"]["modified_rows"]]


def _reminders_added(delta: dict[str, Any]) -> list[dict[str, Any]]:
    return delta["mongo"]["reminders"]["added_rows"]


def _reminders_modified_after(delta: dict[str, Any]) -> list[dict[str, Any]]:
    return [row["after"] for row in delta["mongo"]["reminders"]["modified_rows"]]


def _has_shared_status(rows: list[dict[str, Any]], status: str) -> bool:
    return any(str(row.get("status")) == status for row in rows)


def _has_active_reminders_for(accounts: tuple[SmokeAccount, SmokeAccount], snapshot_after: dict[str, Any]) -> bool:
    ids = {accounts[0].coke_account_id, accounts[1].coke_account_id}
    docs = snapshot_after["mongo"]["reminders"]
    active = [
        doc
        for doc in docs
        if doc.get("owner_user_id") in ids and doc.get("lifecycle_state") == "active"
    ]
    return len(active) >= 2


def _public_get_user_link_code(account: SmokeAccount) -> str | None:
    url = _config.gateway_api_base_url() + "/api/internal/scheduling/tools/get_user_link"
    headers = {
        "Authorization": f"Bearer {_config.gateway_identity_api_key()}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json={"customer_id": account.coke_account_id}, timeout=15)
    body = response.json()
    if response.status_code != 200 or not body.get("ok"):
        return None
    data = body.get("data") or {}
    return data.get("code")


def _parse_link_code(text: str) -> str | None:
    match = re.search(r"/u/([A-Za-z0-9_-]+)", text)
    if match:
        return match.group(1)
    match = re.search(r"邀请码[:：\s]*([A-Za-z0-9_-]{6,})", text)
    return match.group(1) if match else None


def _setup_accounts(transcript: Transcript) -> dict[str, SmokeAccount]:
    accounts = {
        "coach": provision_account("coach", batch_id=ACCOUNT_BATCH, display_name="Coach Alex"),
        "mei": provision_account("mei", batch_id=ACCOUNT_BATCH, display_name="Student Mei"),
        "jin": provision_account("jin", batch_id=ACCOUNT_BATCH, display_name="Student Jin"),
        "kai": provision_account("kai", batch_id=ACCOUNT_BATCH, display_name="Student Kai"),
    }
    for account in accounts.values():
        transcript.add_account(account)
    print("\nACCOUNTS")
    for name, account in accounts.items():
        print(f"{name}: {account.coke_account_id} display={account.display_name}")

    link_reply = _record_turn(
        transcript,
        "coach",
        accounts["coach"],
        "生成我的好友邀请码，我要发给学生。",
        note="setup_coach_link",
    )
    link_code = _parse_link_code(link_reply.reply_text) or _public_get_user_link_code(accounts["coach"])
    if not link_code:
        raise BlockedSetup("BLOCKED-SETUP: could not obtain Coach Alex user-link code")
    print(f"\n[setup] coach_link_code={link_code}")

    for student_key in ("mei", "jin", "kai"):
        student = accounts[student_key]
        _record_turn(
            transcript,
            student_key,
            student,
            f"我想加教练 Alex 为好友。这是对方的邀请链接码：{link_code}。备注：约课学生。",
            note=f"setup_{student_key}_send_friend_request",
        )
        _record_turn(
            transcript,
            "coach",
            accounts["coach"],
            f"通过 {student.display_name.split()[1]} 的好友请求。",
            note=f"setup_coach_accept_{student_key}",
        )

    active = _active_friendships_with_coach(accounts)
    if active != 3:
        raise BlockedSetup(f"BLOCKED-SETUP: expected 3 active Coach Alex friendships, observed {active}")
    print("[setup] active Coach Alex friendships=3")
    return accounts


def _active_friendships_with_coach(accounts: dict[str, SmokeAccount]) -> int:
    coach_id = accounts["coach"].coke_account_id
    student_ids = [accounts[key].coke_account_id for key in ("mei", "jin", "kai")]
    ids = ",".join("'" + value.replace("'", "''") + "'" for value in student_ids)
    raw = _run_psql(
        f"""
SELECT count(*)::int
  FROM friendships
 WHERE status = 'active'
   AND ((account_a_id = '{coach_id}' AND account_b_id IN ({ids}))
     OR (account_b_id = '{coach_id}' AND account_a_id IN ({ids})));
"""
    ).strip()
    return int(raw or "0")


def _case_result(
    case_id: str,
    expected: str,
    accounts: dict[str, SmokeAccount],
    transcript: Transcript,
    body: Callable[[], list[Turn]],
    judge: Callable[[list[Turn], dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    print(f"\n=== {case_id} ===", flush=True)
    before = snapshot(accounts)
    turns: list[Turn] = []
    try:
        turns = body()
        time.sleep(1.5)
        after = snapshot(accounts)
        delta = _diff_snapshot(before, after)
        print(f"[{case_id}] delta={json.dumps(_brief_delta(delta), ensure_ascii=False, default=str)}", flush=True)
        return judge(turns, delta, after)
    except BridgeError as exc:
        after = snapshot(accounts)
        delta = _diff_snapshot(before, after)
        return _blocked(case_id, expected, f"bridge_error status={exc.status} body={exc.body!r}", turns, delta)
    except Exception as exc:
        after = snapshot(accounts)
        delta = _diff_snapshot(before, after)
        return _blocked(case_id, expected, f"{type(exc).__name__}: {exc}", turns, delta)


def _run_cases(accounts: dict[str, SmokeAccount], transcript: Transcript) -> list[dict[str, Any]]:
    coach = accounts["coach"]
    mei = accounts["mei"]
    jin = accounts["jin"]
    kai = accounts["kai"]
    lock = threading.Lock()
    results: list[dict[str, Any]] = []

    def step(speaker: str, account: SmokeAccount, text: str, note: str) -> Turn:
        return _record_turn(transcript, speaker, account, text, note=note, lock=lock)

    def c1_body() -> list[Turn]:
        return [
            step("mei", mei, "约教练 Alex 明天 10:00 上一节课。", "C1_request"),
            step("coach", coach, "接受 Mei 明天 10 点的预约。", "C1_accept"),
        ]

    def c1_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        added = _shared_added(delta)
        modified = _shared_modified_after(delta)
        ok = (bool(added) or bool(modified)) and _has_shared_status(added + modified, "accepted")
        ok = ok and _has_active_reminders_for((coach, mei), after)
        observed = f"shared added={len(added)} modified={len(modified)} reminders added={len(_reminders_added(delta))}"
        if ok:
            return _passed("C1-happy-path", "pending request accepted with reminders for Mei and Coach Alex", observed, turns, delta)
        return _finding("C1-happy-path", "pending request accepted with reminders for Mei and Coach Alex", observed, turns, delta, mutation_expected=True, mutation_happened=bool(added or modified), severity="silent-bad-side-effect")

    results.append(_case_result("C1-happy-path", "pending request accepted with reminders for Mei and Coach Alex", accounts, transcript, c1_body, c1_judge))

    def c5_body() -> list[Turn]:
        return [
            step("mei", mei, "约 Alex 教练 明天下午 15:00 上课。", "C5_alex_coach"),
            step("mei", mei, "约 alex 后天下午 15:00 上课。", "C5_lower_alex"),
            step("mei", mei, "约 Coach 大后天下午 15:00 上课。", "C5_coach_alias"),
            step("mei", mei, "约张教练明天下午 16:00 上课。", "C5_missing_coach"),
        ]

    def c5_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        added = _shared_added(delta)
        ok = len(added) == 3 and all(row.get("invitee_account_id") == coach.coke_account_id for row in added)
        observed = f"shared requests added={len(added)}"
        if ok:
            return _passed("C5-fuzzy-name", "three Coach Alex aliases resolve; Zhang coach is refused/clarified", observed, turns, delta)
        return _finding("C5-fuzzy-name", "three Coach Alex aliases resolve; Zhang coach is refused/clarified", observed, turns, delta, mutation_expected=True, mutation_happened=bool(added), severity="visible-error")

    results.append(_case_result("C5-fuzzy-name", "three Coach Alex aliases resolve; Zhang coach is refused/clarified", accounts, transcript, c5_body, c5_judge))

    def c4_body() -> list[Turn]:
        return [step("jin", jin, "约教练 Alex 周三上午。", "C4_vague_time")]

    def c4_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        added = _shared_added(delta)
        clarified = any(token in _reply_text(turns) for token in CLARIFY_TOKENS)
        ok = not added and clarified
        observed = f"shared requests added={len(added)} clarified={clarified}"
        if ok:
            return _passed("C4-vague-time", "asks for a specific hour without creating a request", observed, turns, delta)
        return _finding("C4-vague-time", "asks for a specific hour without creating a request", observed, turns, delta, mutation_expected=False, mutation_happened=bool(added), severity="UX-rough")

    results.append(_case_result("C4-vague-time", "asks for a specific hour without creating a request", accounts, transcript, c4_body, c4_judge))

    def c3_body() -> list[Turn]:
        return [step("kai", kai, "约教练 Alex 凌晨 3 点。", "C3_outside_window")]

    def c3_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        added = _shared_added(delta)
        invented = any(token in _reply_text(turns) for token in INVENTED_AVAILABILITY_TOKENS)
        ok = bool(added) and not invented
        observed = f"shared requests added={len(added)} invented_availability={invented}"
        if ok:
            return _passed("C3-outside-window", "creates the 03:00 request; no invented working-hours refusal", observed, turns, delta)
        return _finding("C3-outside-window", "creates the 03:00 request; no invented working-hours refusal", observed, turns, delta, mutation_expected=True, mutation_happened=bool(added), severity="visible-error")

    results.append(_case_result("C3-outside-window", "creates the 03:00 request; no invented working-hours refusal", accounts, transcript, c3_body, c3_judge))

    def c11_body() -> list[Turn]:
        return [step("mei", mei, "约教练 Alex 昨天 10 点。", "C11_past_time")]

    def c11_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        added = _shared_added(delta)
        refused = any(token in _reply_text(turns) for token in REFUSAL_TOKENS)
        ok = not added and refused
        observed = f"shared requests added={len(added)} refused={refused}"
        if ok:
            return _passed("C11-past-time", "refuses past time and creates no request", observed, turns, delta)
        return _finding("C11-past-time", "refuses past time and creates no request", observed, turns, delta, mutation_expected=False, mutation_happened=bool(added), severity="visible-error")

    results.append(_case_result("C11-past-time", "refuses past time and creates no request", accounts, transcript, c11_body, c11_judge))

    def c7_body() -> list[Turn]:
        return [step("mei", mei, "把和教练 Alex 明天 10 点改成 11 点。", "C7_modify")]

    def c7_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        shared_changed = _shared_modified_after(delta) + _shared_added(delta)
        reminder_changed = _reminders_modified_after(delta) + _reminders_added(delta)
        has_11 = "11:" in _stable(shared_changed + reminder_changed) or "11点" in _reply_text(turns)
        ok = bool(shared_changed or reminder_changed) and has_11
        observed = f"shared changed={len(shared_changed)} reminders changed={len(reminder_changed)} has_11={has_11}"
        if ok:
            return _passed("C7-modify", "C1 accepted lesson moves to 11:00 on both sides", observed, turns, delta)
        return _finding("C7-modify", "C1 accepted lesson moves to 11:00 on both sides", observed, turns, delta, mutation_expected=True, mutation_happened=bool(shared_changed or reminder_changed), severity="visible-error")

    results.append(_case_result("C7-modify", "C1 accepted lesson moves to 11:00 on both sides", accounts, transcript, c7_body, c7_judge))

    def c6_body() -> list[Turn]:
        return [
            step("jin", jin, "约教练 Alex 后天 14:00 上一节训练课。", "C6_create"),
            step("coach", coach, "接受 Jin 后天 14 点的预约。", "C6_accept"),
            step("jin", jin, "取消跟教练的训练课。", "C6_cancel"),
        ]

    def c6_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        rows = _shared_added(delta) + _shared_modified_after(delta)
        ok = _has_shared_status(rows, "cancelled")
        observed = f"shared changed={len(rows)} cancelled={ok}"
        if ok:
            return _passed("C6-cancel", "accepted Jin lesson is cancelled and reminders removed/cancelled", observed, turns, delta)
        return _finding("C6-cancel", "accepted Jin lesson is cancelled and reminders removed/cancelled", observed, turns, delta, mutation_expected=True, mutation_happened=bool(rows), severity="visible-error")

    results.append(_case_result("C6-cancel", "accepted Jin lesson is cancelled and reminders removed/cancelled", accounts, transcript, c6_body, c6_judge))

    def c8_body() -> list[Turn]:
        return [
            step("coach", coach, "提醒明天 14:00 给 Student Mei 上一节课。", "C8_coach_create"),
            step("mei", mei, "接受教练 Alex 明天 14 点的上课提醒。", "C8_mei_accept"),
        ]

    def c8_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        rows = _shared_added(delta) + _shared_modified_after(delta)
        coach_to_mei = any(row.get("requester_account_id") == coach.coke_account_id and row.get("invitee_account_id") == mei.coke_account_id for row in rows)
        ok = coach_to_mei and _has_shared_status(rows, "accepted") and _has_active_reminders_for((coach, mei), after)
        observed = f"coach_to_mei={coach_to_mei} accepted={_has_shared_status(rows, 'accepted')}"
        if ok:
            return _passed("C8-coach-initiated", "coach creates pending request for Mei and Mei accepts", observed, turns, delta)
        return _finding("C8-coach-initiated", "coach creates pending request for Mei and Mei accepts", observed, turns, delta, mutation_expected=True, mutation_happened=bool(rows), severity="visible-error")

    results.append(_case_result("C8-coach-initiated", "coach creates pending request for Mei and Mei accepts", accounts, transcript, c8_body, c8_judge))

    def c9_body() -> list[Turn]:
        return [
            step("kai", kai, "约教练 Alex 后天 16:00 上一节课。", "C9_create"),
            step("coach", coach, "拒绝 Kai 的预约。", "C9_reject"),
        ]

    def c9_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        rows = _shared_added(delta) + _shared_modified_after(delta)
        rejected = _has_shared_status(rows, "rejected") or _has_shared_status(rows, "declined")
        observed = f"shared changed={len(rows)} rejected={rejected}"
        if rejected:
            return _passed("C9-coach-declines", "coach rejection leaves request rejected/declined with no phantom acceptance", observed, turns, delta)
        return _finding("C9-coach-declines", "coach rejection leaves request rejected/declined with no phantom acceptance", observed, turns, delta, mutation_expected=True, mutation_happened=bool(rows), severity="visible-error")

    results.append(_case_result("C9-coach-declines", "coach rejection leaves request rejected/declined with no phantom acceptance", accounts, transcript, c9_body, c9_judge))

    def c10_body() -> list[Turn]:
        return [step("mei", mei, "教练 Alex 明天什么时候有空？", "C10_calendar_facts")]

    def c10_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        mutated = bool(_shared_added(delta) or _shared_modified_after(delta) or _reminders_added(delta))
        expected_tomorrow = _accepted_on_date_count(after, coach, days_from_now=1)
        claims_busy = any(token in _reply_text(turns) for token in ("排满", "有空", "10:00", "14:00"))
        invented = any(token in _reply_text(turns) for token in INVENTED_AVAILABILITY_TOKENS)
        ok = not mutated and not invented and not (expected_tomorrow == 0 and claims_busy)
        observed = (
            f"expected_tomorrow_accepted={expected_tomorrow} mutated={mutated} "
            f"claims_busy={claims_busy} invented_availability={invented}"
        )
        if ok:
            return _passed("C10-calendar-facts", "availability answer is read-only and does not invent a working-hours product", observed, turns, delta)
        return _finding("C10-calendar-facts", "availability answer is read-only and does not invent a working-hours product", observed, turns, delta, mutation_expected=False, mutation_happened=mutated, severity="UX-rough")

    results.append(_case_result("C10-calendar-facts", "availability answer is read-only and does not invent a working-hours product", accounts, transcript, c10_body, c10_judge))

    def c13_body() -> list[Turn]:
        return [step("coach", coach, "我今天有几节课？列一下我今天的课程。", "C13_overview")]

    def c13_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        mutated = bool(_shared_added(delta) or _shared_modified_after(delta) or _reminders_added(delta))
        reply = _reply_text(turns)
        expected_today = _accepted_today_count(after, coach)
        says_none = any(token in reply for token in ("没有", "0", "零"))
        ok = not mutated and (expected_today > 0 or says_none)
        observed = f"expected_today={expected_today} mutated={mutated} says_none={says_none}"
        if ok:
            return _passed("C13-coach-overview", "today overview matches accepted shared reminders for Alex", observed, turns, delta)
        return _finding("C13-coach-overview", "today overview matches accepted shared reminders for Alex", observed, turns, delta, mutation_expected=False, mutation_happened=mutated, severity="UX-rough")

    results.append(_case_result("C13-coach-overview", "today overview matches accepted shared reminders for Alex", accounts, transcript, c13_body, c13_judge))

    def c2_body() -> list[Turn]:
        return [
            step("jin", jin, "约教练 Alex 大后天 10:00 上一节课。", "C2_jin_collision"),
            step("kai", kai, "约教练 Alex 大后天 10:00 上一节课。", "C2_kai_collision"),
        ]

    def c2_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        added = _shared_added(delta)
        pending_count = sum(1 for row in added if row.get("status") == "pending_invitee_confirmation")
        accepted_count = sum(1 for row in added if row.get("status") == "accepted")
        ok = len(added) == 2 and pending_count == 2
        observed = f"shared added={len(added)} pending={pending_count} accepted={accepted_count}"
        if ok:
            return _passed("C2-slot-collision", "two same-slot requests both remain pending for coach review", observed, turns, delta)
        return _finding("C2-slot-collision", "two same-slot requests both remain pending for coach review", observed, turns, delta, mutation_expected=True, mutation_happened=bool(added), severity="silent-bad-side-effect")

    results.append(_case_result("C2-slot-collision", "two same-slot requests both remain pending for coach review", accounts, transcript, c2_body, c2_judge))

    def c12_body() -> list[Turn]:
        prompts = [
            ("mei", mei, "约教练 Alex 下周一 11:00 上一节课。", "C12_mei"),
            ("jin", jin, "约教练 Alex 下周一 12:00 上一节课。", "C12_jin"),
            ("kai", kai, "约教练 Alex 下周一 13:00 上一节课。", "C12_kai"),
        ]

        def concurrent_step(turn_no: int, speaker: str, account: SmokeAccount, text: str, note: str) -> Turn:
            _print_turn(turn_no, speaker, text)
            start = time.monotonic()
            reply = send_as(account.coke_account_id, text, **account.send_kwargs())
            elapsed_ms = int((time.monotonic() - start) * 1000)
            turn = Turn(
                turn=turn_no,
                speaker=speaker,
                coke_account_id=account.coke_account_id,
                input_text=text,
                inbound_event_id=reply.causal_inbound_event_id,
                reply_text=reply.reply,
                output_id=reply.output_id,
                elapsed_ms=elapsed_ms,
                note=note,
            )
            print(
                f"[T{turn_no:02d} {speaker}] << ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}",
                flush=True,
            )
            return turn

        base_turn = len(transcript.turns)
        case_turns: list[Turn] = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(concurrent_step, base_turn + index, speaker, account, prompt, note)
                for index, (speaker, account, prompt, note) in enumerate(prompts, start=1)
            ]
            for future in as_completed(futures):
                case_turns.append(future.result())
        case_turns = sorted(case_turns, key=lambda item: item.turn)
        for turn in case_turns:
            transcript.add_turn(turn)
        return case_turns

    def c12_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        added = _shared_added(delta)
        empty = any(not turn.reply_text.strip() or any(token in turn.reply_text for token in EMPTY_FALLBACK_TOKENS) for turn in turns)
        slow_empty = any(turn.elapsed_ms >= 180000 and not turn.reply_text.strip() for turn in turns)
        ok = len(added) == 3 and not empty and not slow_empty
        observed = f"shared added={len(added)} empty={empty} slow_empty={slow_empty}"
        if ok:
            return _passed("C12-concurrent-burst", "all three parallel requests land without empty fallback or causal hijack", observed, turns, delta)
        return _finding("C12-concurrent-burst", "all three parallel requests land without empty fallback or causal hijack", observed, turns, delta, mutation_expected=True, mutation_happened=bool(added), severity="silent-bad-side-effect")

    results.append(_case_result("C12-concurrent-burst", "all three parallel requests land without empty fallback or causal hijack", accounts, transcript, c12_body, c12_judge))
    return results


def _accepted_today_count(snapshot_after: dict[str, Any], coach: SmokeAccount) -> int:
    return _accepted_on_date_count(snapshot_after, coach, days_from_now=0)


def _accepted_on_date_count(snapshot_after: dict[str, Any], coach: SmokeAccount, *, days_from_now: int) -> int:
    target_date = time.strftime("%Y-%m-%d", time.gmtime(time.time() + days_from_now * 86400))
    rows = snapshot_after["postgres"]["shared_reminder_requests"]
    return sum(
        1
        for row in rows
        if row.get("status") == "accepted"
        and (row.get("requester_account_id") == coach.coke_account_id or row.get("invitee_account_id") == coach.coke_account_id)
        and str(row.get("fire_at", "")).startswith(target_date)
    )


def _write_evidence(transcript: Transcript, results: list[dict[str, Any]], setup_status: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    findings = [result for result in results if result["verdict"] == "FINDING"]
    blocked = [result for result in results if result["verdict"] == "BLOCKED"]
    transcript.set_verdict(
        passed=not findings and not blocked and setup_status == "PASSED",
        problems=[f"{item['case_id']}: {item['observed']}" for item in findings + blocked],
    )
    payload = {
        "batch": BATCH,
        "account_batch": ACCOUNT_BATCH,
        "setup_status": setup_status,
        "accounts": transcript.accounts,
        "turns": [asdict(turn) for turn in sorted(transcript.turns, key=lambda item: item.turn)],
        "cases": results,
        "summary": {
            "passed": sum(1 for result in results if result["verdict"] == "PASSED"),
            "findings": len(findings),
            "blocked": len(blocked),
        },
        "verdict": transcript.verdict,
    }
    EVIDENCE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return EVIDENCE_PATH


def _print_summary(results: list[dict[str, Any]]) -> None:
    print("\n| case | verdict | bug_pattern | one-line observed |")
    print("|------|---------|-------------|-------------------|")
    for result in results:
        observed = str(result.get("observed") or "").replace("\n", " ")[:120]
        print(
            f"| {result['case_id']} | {result['verdict']} | {result.get('bug_pattern', '')} | {observed} |"
        )


def main() -> int:
    print(f"BATCH={BATCH}")
    transcript = Transcript(batch_id=f"coach-booking-{BATCH}")
    setup_status = "PASSED"
    results: list[dict[str, Any]] = []
    try:
        accounts = _setup_accounts(transcript)
    except BlockedSetup as exc:
        setup_status = "BLOCKED-SETUP"
        print(str(exc))
        path = _write_evidence(transcript, results, setup_status)
        print(f"\nevidence={path}")
        return 2

    results = _run_cases(accounts, transcript)
    path = _write_evidence(transcript, results, setup_status)
    _print_summary(results)
    print(f"\nevidence={path}")
    return 0 if all(result["verdict"] != "BLOCKED" for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
