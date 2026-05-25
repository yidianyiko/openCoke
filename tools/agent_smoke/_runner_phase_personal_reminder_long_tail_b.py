"""Personal reminder long-tail smoke hunt, Batch B.

Runs cases 14-25 from
docs/superpowers/specs/2026-05-26-personal-reminder-long-tail-design.md.

This is a hunt runner: it records findings and keeps going unless the live
stack or account setup prevents the case from exercising the target behavior.
It must not change product code.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import MongoClient

from tools.agent_smoke import _config
from tools.agent_smoke.account_factory import SmokeAccount, provision_account
from tools.agent_smoke.bridge_client import BridgeError, send_as
from tools.agent_smoke.postgres_seed import _run_psql
from tools.agent_smoke.transcript import Transcript, Turn

BATCH = time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())
BATCH_ID = f"personal-reminder-time-content-list-{BATCH}"
ACCOUNT_BATCH = "prlongtailb" + BATCH.lower().replace("t", "").replace("z", "")
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
EVIDENCE_PATH = EVIDENCE_DIR / f"{BATCH_ID}.json"

EMPTY_FALLBACK_TOKENS = ("我没接住你刚才的意思", "我这次没能及时整理")
SUCCESS_CLAIM_TOKENS = ("已", "已经", "成功", "帮你", "创建", "设置", "改", "删除", "取消", "完成")
CLARIFY_TOKENS = ("哪一个", "哪个", "请确认", "请明确", "具体", "目标", "是哪条", "提醒内容")
UNSUPPORTED_TOKENS = ("暂不支持", "不支持", "不能", "无法", "没法")
EMPTY_LIST_TOKENS = ("没有", "暂无", "空", "还没", "未找到", "没看到")
PAST_TIME_TOKENS = ("过去", "已经过", "已过", "已经结束", "结束", "不能", "无法", "未来", "重新", "之后")
RAW_ENVELOPE_RE = re.compile(r"```json|MultiModalResponses|\"message_type\"")
LONG_TITLE = "喝水" * 100


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


def _sql_json(sql: str) -> list[dict[str, Any]]:
    raw = _run_psql(sql).strip()
    if not raw:
        return []
    return json.loads(raw)


def _postgres_snapshot(account: SmokeAccount) -> dict[str, list[dict[str, Any]]]:
    account_id = account.coke_account_id.replace("'", "''")
    identity_id = f"id_smoke_{ACCOUNT_BATCH}_alice".replace("'", "''")
    return {
        "customers": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (SELECT * FROM customers WHERE id = '{account_id}') t;
"""
        ),
        "identities": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (SELECT * FROM identities WHERE id = '{identity_id}') t;
"""
        ),
        "memberships": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (SELECT * FROM memberships WHERE customer_id = '{account_id}') t;
"""
        ),
        "reminder_projections": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (SELECT * FROM reminder_projections WHERE owner_account_id = '{account_id}') t;
"""
        ),
    }


def _mongo_client() -> MongoClient:
    return MongoClient(_config.mongo_uri())


def _mongo_snapshot(account: SmokeAccount) -> dict[str, list[dict[str, Any]]]:
    client = _mongo_client()
    db = client[_config.mongo_db_name()]
    account_id = account.coke_account_id
    try:
        sessions = list(db.agent_sessions.find().sort("updated_at", -1).limit(120))
        return {
            "reminders": list(db.reminders.find({"owner_user_id": account_id}).sort("_id", 1)),
            "outputmessages": list(
                db.outputmessages.find(
                    {"$or": [{"to_user": account_id}, {"account_id": account_id}]}
                ).sort("_id", 1)
            ),
            "inputmessages": list(
                db.inputmessages.find(
                    {"$or": [{"from_user": account_id}, {"to_user": account_id}]}
                ).sort("_id", 1)
            ),
            "agent_sessions": [
                doc for doc in sessions if account_id in _stable(doc)
            ],
        }
    finally:
        client.close()


def snapshot(account: SmokeAccount) -> dict[str, Any]:
    return {
        "mongo": _mongo_snapshot(account),
        "postgres": _postgres_snapshot(account),
    }


def _reminders_for(account: SmokeAccount) -> list[dict[str, Any]]:
    client = _mongo_client()
    try:
        db = client[_config.mongo_db_name()]
        return list(db.reminders.find({"owner_user_id": account.coke_account_id}).sort("_id", 1))
    finally:
        client.close()


def _record_turn(transcript: Transcript, account: SmokeAccount, text: str, *, note: str) -> Turn:
    turn_no = len(transcript.turns) + 1
    print(f"\n[T{turn_no:02d} alice] >> {text}", flush=True)
    start = time.monotonic()
    reply = send_as(account.coke_account_id, text, **account.send_kwargs())
    elapsed_ms = int((time.monotonic() - start) * 1000)
    turn = Turn(
        turn=turn_no,
        speaker="alice",
        coke_account_id=account.coke_account_id,
        input_text=text,
        inbound_event_id=reply.causal_inbound_event_id,
        reply_text=reply.reply,
        output_id=reply.output_id,
        elapsed_ms=elapsed_ms,
        note=note,
        placeholder_received=reply.placeholder_received,
        late_reply_landed=reply.late_reply_landed,
        polling_seconds_used=reply.polling_seconds_used,
        placeholder_reply=reply.placeholder_reply,
        placeholder_output_id=reply.placeholder_output_id,
    )
    transcript.add_turn(turn)
    print(f"[T{turn_no:02d} alice] << ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}", flush=True)
    return turn


def _reply_text(turns: list[Turn]) -> str:
    return "\n".join(turn.reply_text or "" for turn in turns)


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _active(doc: dict[str, Any] | None) -> bool:
    return bool(doc) and doc.get("lifecycle_state") == "active" and bool(doc.get("next_fire_at"))


def _schedule(doc: dict[str, Any] | None) -> dict[str, Any]:
    value = (doc or {}).get("schedule") or {}
    return value if isinstance(value, dict) else {}


def _rrule(doc: dict[str, Any] | None) -> str:
    return str(_schedule(doc).get("rrule") or "")


def _local_time(doc: dict[str, Any] | None) -> str:
    return str(_schedule(doc).get("local_time") or "")


def _local_date(doc: dict[str, Any] | None) -> str:
    return str(_schedule(doc).get("local_date") or "")


def _title(doc: dict[str, Any] | None) -> str:
    return str((doc or {}).get("title") or "")


def _doc_by_id(docs: list[dict[str, Any]], doc_id: Any) -> dict[str, Any] | None:
    target = str(doc_id)
    for doc in docs:
        if str(doc.get("_id")) == target:
            return doc
    return None


def _new_reminders(delta: dict[str, Any]) -> list[dict[str, Any]]:
    return delta["mongo"]["reminders"]["added_rows"]


def _changed_reminders(delta: dict[str, Any]) -> list[dict[str, Any]]:
    return [row["after"] for row in delta["mongo"]["reminders"]["modified_rows"]]


def _agent_trace_excerpt(turns: list[Turn], after: dict[str, Any]) -> list[dict[str, Any]]:
    snippets = [turn.input_text for turn in turns if turn.input_text]
    excerpts: list[dict[str, Any]] = []
    for session in after["mongo"].get("agent_sessions", []):
        stable = _stable(session)
        if not any(snippet in stable for snippet in snippets):
            continue
        runs = session.get("runs") or []
        for run in runs[-3:]:
            messages = run.get("messages") or []
            items = []
            for message in messages[-20:]:
                item = {
                    "role": message.get("role"),
                    "tool_name": message.get("tool_name"),
                    "content": str(message.get("content") or "")[:500],
                }
                if message.get("tool_calls"):
                    item["tool_calls"] = _clean(message.get("tool_calls"))
                items.append(item)
            excerpts.append({"session_id": str(session.get("_id")), "messages": items})
        if len(excerpts) >= 3:
            break
    return excerpts


def _base_bug_pattern(
    turns: list[Turn],
    *,
    default: str,
    mutation_expected: bool,
    mutation_happened: bool,
) -> str:
    text = _reply_text(turns)
    if RAW_ENVELOPE_RE.search(text):
        return "A"
    if _has_any(text, EMPTY_FALLBACK_TOKENS) or not text.strip():
        return "B"
    if "ValidationError" in text or "Tool call limit" in text:
        return "D1"
    if "not_found" in text or "找不到" in text:
        return "D2"
    if any(turn.elapsed_ms >= 180000 and not turn.reply_text for turn in turns):
        return "F"
    if mutation_expected and not mutation_happened and _has_any(text, SUCCESS_CLAIM_TOKENS):
        return "C"
    return default


def _result(
    *,
    case_id: str,
    verdict: str,
    bug_pattern: str,
    expected: str,
    observed: str,
    turns: list[Turn],
    delta: dict[str, Any],
    after: dict[str, Any],
    product_contract_unclear: bool = False,
    severity: str = "",
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "verdict": verdict,
        "bug_pattern": bug_pattern,
        "severity": severity,
        "product_contract_unclear": product_contract_unclear,
        "expected": expected,
        "observed": observed,
        "turns": [asdict(turn) for turn in turns],
        "agent_reply": _reply_text(turns),
        "mongo_delta": delta["mongo"],
        "postgres_delta": delta["postgres"],
        "agent_trace_excerpt": _agent_trace_excerpt(turns, after),
    }


def _passed(case_id: str, expected: str, observed: str, turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], *, product_contract_unclear: bool = False) -> dict[str, Any]:
    return _result(
        case_id=case_id,
        verdict="PASSED",
        bug_pattern="",
        expected=expected,
        observed=observed,
        turns=turns,
        delta=delta,
        after=after,
        product_contract_unclear=product_contract_unclear,
    )


def _finding(case_id: str, expected: str, observed: str, turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], *, bug_pattern: str, mutation_expected: bool, mutation_happened: bool, product_contract_unclear: bool = False, severity: str = "visible-error") -> dict[str, Any]:
    return _result(
        case_id=case_id,
        verdict="FINDING",
        bug_pattern=_base_bug_pattern(
            turns,
            default=bug_pattern,
            mutation_expected=mutation_expected,
            mutation_happened=mutation_happened,
        ),
        severity=severity,
        expected=expected,
        observed=observed,
        turns=turns,
        delta=delta,
        after=after,
        product_contract_unclear=product_contract_unclear,
    )


def _blocked(case_id: str, expected: str, observed: str, turns: list[Turn], delta: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return _result(
        case_id=case_id,
        verdict="BLOCKED",
        bug_pattern="",
        expected=expected,
        observed=observed,
        turns=turns,
        delta=delta,
        after=after,
        severity="smoke-infra",
    )


def _latest_added(before_count: int, account: SmokeAccount, title_token: str | None = None) -> dict[str, Any] | None:
    docs = _reminders_for(account)
    candidates = docs[before_count:]
    if title_token:
        candidates = [doc for doc in candidates if title_token in _title(doc)]
    return candidates[-1] if candidates else None


def _future_today_hour() -> int:
    now = time.localtime()
    hour = max(now.tm_hour + 2, 8)
    return min(hour, 22)


def _future_clock(offset_hours: int = 2) -> tuple[int, int]:
    now = datetime.now()
    future = now + timedelta(hours=offset_hours)
    return future.hour, future.minute


def _past_bare_clock_hour() -> int:
    now = datetime.now()
    return now.hour - 1 if now.hour > 0 else 0


def _just_past_clock() -> tuple[int, int]:
    past = datetime.now() - timedelta(minutes=5)
    return past.hour, past.minute


def _next_year() -> int:
    return datetime.now().year + 1


def _next_fire_text(doc: dict[str, Any] | None) -> str:
    return str((doc or {}).get("next_fire_at") or "")


def _active_added(delta: dict[str, Any]) -> list[dict[str, Any]]:
    return [doc for doc in _new_reminders(delta) if _active(doc)]


def _active_reminders(after: dict[str, Any], title_token: str | None = None) -> list[dict[str, Any]]:
    docs = [doc for doc in after["mongo"]["reminders"] if _active(doc)]
    if title_token:
        docs = [doc for doc in docs if title_token in _title(doc)]
    return docs


def _no_write(delta: dict[str, Any]) -> bool:
    reminder_delta = delta["mongo"]["reminders"]
    return (
        reminder_delta["added"] == 0
        and reminder_delta["modified"] == 0
        and reminder_delta["removed"] == 0
    )


def _looks_like_empty_list(text: str) -> bool:
    return _has_any(text, EMPTY_LIST_TOKENS)


def _contains_date_or_time_reply(text: str) -> bool:
    return bool(re.search(r"\d{1,2}\s*[:：点]\s*\d{0,2}|今天|明天|后天|\d{4}[-年]\d{1,2}[-月]\d{1,2}", text))


class CaseContext:
    def __init__(self, account: SmokeAccount, transcript: Transcript):
        self.account = account
        self.transcript = transcript
        self.checkpoints: dict[str, Any] = {}

    def step(self, text: str, note: str) -> Turn:
        return _record_turn(self.transcript, self.account, text, note=note)

    def remember_doc(self, key: str, doc: dict[str, Any] | None) -> None:
        self.checkpoints[key] = _clean(doc)


def _case_result(
    case_id: str,
    expected: str,
    account: SmokeAccount,
    transcript: Transcript,
    body: Callable[[CaseContext], list[Turn]],
    judge: Callable[[list[Turn], dict[str, Any], dict[str, Any], CaseContext], dict[str, Any]],
) -> dict[str, Any]:
    print(f"\n=== {case_id} ===", flush=True)
    before = snapshot(account)
    ctx = CaseContext(account, transcript)
    turns: list[Turn] = []
    try:
        turns = body(ctx)
        time.sleep(1.5)
        after = snapshot(account)
        delta = _diff_snapshot(before, after)
        print(f"[{case_id}] delta={json.dumps(_brief_delta(delta), ensure_ascii=False, default=str)}", flush=True)
        result = judge(turns, delta, after, ctx)
        if result["verdict"] == "PASSED" and (
            RAW_ENVELOPE_RE.search(_reply_text(turns)) or _has_any(_reply_text(turns), EMPTY_FALLBACK_TOKENS)
        ):
            result = _finding(
                result["case_id"],
                result["expected"],
                f"{result['observed']} visible_reply_bug=True",
                turns,
                delta,
                after,
                bug_pattern="NEW",
                mutation_expected=False,
                mutation_happened=False,
                product_contract_unclear=bool(result.get("product_contract_unclear")),
            )
        if ctx.checkpoints:
            result["checkpoints"] = ctx.checkpoints
        return result
    except BridgeError as exc:
        after = snapshot(account)
        delta = _diff_snapshot(before, after)
        return _blocked(case_id, expected, f"bridge_error status={exc.status} body={exc.body!r}", turns, delta, after)
    except Exception as exc:
        after = snapshot(account)
        delta = _diff_snapshot(before, after)
        return _blocked(case_id, expected, f"{type(exc).__name__}: {exc}", turns, delta, after)


def _run_cases(account: SmokeAccount, transcript: Transcript) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def c25_body(ctx: CaseContext) -> list[Turn]:
        return [ctx.step("我有什么提醒？", "PR-25-empty-list")]

    def c25_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        active = _active_reminders(after)
        no_write = _no_write(delta)
        empty_reply = _looks_like_empty_list(_reply_text(turns))
        observed = f"active_after={len(active)} no_write={no_write} empty_reply={empty_reply}"
        if not active and no_write and empty_reply:
            return _passed("PR-25-empty-list", "fresh account list says no reminders and makes no write", observed, turns, delta, after)
        return _finding("PR-25-empty-list", "fresh account list says no reminders and makes no write", observed, turns, delta, after, bug_pattern="L1", mutation_expected=False, mutation_happened=not no_write)

    results.append(_case_result("PR-25-empty-list", "fresh account list says no reminders and makes no write", account, transcript, c25_body, c25_judge))

    def no_create_case(case_id: str, prompt: str, expected: str, *, product_contract_unclear: bool = False) -> tuple[Callable[[CaseContext], list[Turn]], Callable[[list[Turn], dict[str, Any], dict[str, Any], CaseContext], dict[str, Any]]]:
        def body(ctx: CaseContext) -> list[Turn]:
            return [ctx.step(prompt, case_id)]

        def judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
            added = _active_added(delta)
            no_write = _no_write(delta)
            text = _reply_text(turns)
            safe_reply = _has_any(text, PAST_TIME_TOKENS + CLARIFY_TOKENS + UNSUPPORTED_TOKENS)
            observed = f"active_added={len(added)} no_write={no_write} safe_reply={safe_reply}"
            if no_write and safe_reply:
                return _passed(case_id, expected, observed, turns, delta, after, product_contract_unclear=product_contract_unclear)
            return _finding(case_id, expected, observed, turns, delta, after, bug_pattern="T1", mutation_expected=False, mutation_happened=bool(added) or not no_write, product_contract_unclear=product_contract_unclear)

        return body, judge

    body, judge = no_create_case(
        "PR-14-past-time",
        "提醒我昨天 10 点开会。",
        "refuse/report invalid past schedule with no reminder created",
    )
    results.append(_case_result("PR-14-past-time", "refuse/report invalid past schedule with no reminder created", account, transcript, body, judge))

    past_hour, past_minute = _just_past_clock()
    body, judge = no_create_case(
        "PR-15-just-past",
        f"提醒我今天 {past_hour:02d}:{past_minute:02d} 喝水。",
        "clarify/refuse just-past schedule with no reminder created",
        product_contract_unclear=True,
    )
    results.append(_case_result("PR-15-just-past", "clarify/refuse just-past schedule with no reminder created", account, transcript, body, judge))

    def c16_body(ctx: CaseContext) -> list[Turn]:
        return [ctx.step("明年 1 月 1 日 0:00 提醒我写年度计划。", "PR-16-far-future")]

    def c16_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = _active_added(delta)
        expected_year = str(_next_year())
        expected_date = f"{expected_year}-01-01"
        matching = [doc for doc in added if "年度计划" in _title(doc) and _local_date(doc) == expected_date and _local_time(doc).startswith("00:00")]
        observed = f"active_added={len(added)} expected_date={expected_date} local_dates={[ _local_date(doc) for doc in added ]} local_times={[ _local_time(doc) for doc in added ]} next_fire={[ _next_fire_text(doc) for doc in added ]} titles={[ _title(doc) for doc in added ]}"
        if len(matching) == 1:
            return _passed("PR-16-far-future", "create one-shot reminder on next Jan 1 00:00", observed, turns, delta, after)
        return _finding("PR-16-far-future", "create one-shot reminder on next Jan 1 00:00", observed, turns, delta, after, bug_pattern="T1", mutation_expected=True, mutation_happened=bool(added))

    results.append(_case_result("PR-16-far-future", "create one-shot reminder on next Jan 1 00:00", account, transcript, c16_body, c16_judge))

    def c17_body(ctx: CaseContext) -> list[Turn]:
        past_hour = _past_bare_clock_hour()
        future_hour, future_minute = _future_clock()
        ctx.checkpoints["past_hour"] = past_hour
        ctx.checkpoints["future_hour"] = future_hour
        ctx.checkpoints["future_minute"] = future_minute
        return [
            ctx.step(f"{past_hour} 点提醒我喝水。", "PR-17-bare-clock-past"),
            ctx.step(f"{future_hour} 点 {future_minute} 分提醒我拉伸。", "PR-17-bare-clock-future"),
        ]

    def c17_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = _active_added(delta)
        water = [doc for doc in added if "喝水" in _title(doc) and _local_time(doc).startswith(f"{ctx.checkpoints['past_hour']:02d}:00")]
        stretch = [doc for doc in added if "拉伸" in _title(doc) and _local_time(doc).startswith(f"{ctx.checkpoints['future_hour']:02d}:{ctx.checkpoints['future_minute']:02d}")]
        one_shots = all(not _rrule(doc) for doc in water + stretch)
        replies_include_choice = all(
            _contains_date_or_time_reply(turn.reply_text or "") and "每天" not in (turn.reply_text or "")
            for turn in turns
        )
        observed = f"active_added={len(added)} water_past_hour={len(water)} stretch_future={len(stretch)} one_shots={one_shots} rrules={[ _rrule(doc) for doc in water + stretch ]} replies_include_choice={replies_include_choice}"
        if len(water) == 1 and len(stretch) == 1 and one_shots and replies_include_choice:
            return _passed("PR-17-bare-clock", "bare clocks resolve to tomorrow if past and today if future, with chosen time in reply", observed, turns, delta, after)
        return _finding("PR-17-bare-clock", "bare clocks resolve to tomorrow if past and today if future, with chosen time in reply", observed, turns, delta, after, bug_pattern="T1", mutation_expected=True, mutation_happened=bool(added))

    results.append(_case_result("PR-17-bare-clock", "bare clocks resolve to tomorrow if past and today if future, with chosen time in reply", account, transcript, c17_body, c17_judge))

    def c18_body(ctx: CaseContext) -> list[Turn]:
        return [
            ctx.step("5 分钟后提醒我喝水。", "PR-18-relative-five-minutes"),
            ctx.step("明早提醒我喝水。", "PR-18-relative-morning-missing-clock"),
            ctx.step("下下周三提醒我喝水。", "PR-18-relative-day-missing-clock"),
        ]

    def c18_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = _active_added(delta)
        water_adds = [doc for doc in added if "喝水" in _title(doc)]
        later_replies = _reply_text(turns[1:])
        later_ask = _has_any(later_replies, CLARIFY_TOKENS) or "几点" in later_replies or "时间" in later_replies
        observed = f"active_added={len(added)} water_adds={len(water_adds)} later_ask={later_ask} local_times={[ _local_time(doc) for doc in added ]}"
        if len(water_adds) == 1 and later_ask:
            return _passed("PR-18-relative-time", "5 minutes creates; missing-clock relative dates ask without extra writes", observed, turns, delta, after)
        return _finding("PR-18-relative-time", "5 minutes creates; missing-clock relative dates ask without extra writes", observed, turns, delta, after, bug_pattern="T1", mutation_expected=True, mutation_happened=bool(added))

    results.append(_case_result("PR-18-relative-time", "5 minutes creates; missing-clock relative dates ask without extra writes", account, transcript, c18_body, c18_judge))

    def c19_body(ctx: CaseContext) -> list[Turn]:
        hour, minute = _future_clock()
        second = 45
        ctx.checkpoints.update({"hour": hour, "minute": minute, "second": second})
        return [ctx.step(f"{hour} 点 {minute} 分 {second} 秒提醒我喝水。", "PR-19-sub-minute-precision")]

    def c19_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = _active_added(delta)
        local_times = [_local_time(doc) for doc in added]
        reply = _reply_text(turns)
        preserved = any(value.endswith(":45") for value in local_times)
        rounded_with_notice = any(value.endswith(":00") for value in local_times) and ("秒" in reply or "分钟" in reply or "精确到" in reply)
        observed = f"active_added={len(added)} local_times={local_times} preserved={preserved} rounded_with_notice={rounded_with_notice}"
        if len(added) == 1 and (preserved or rounded_with_notice):
            return _passed("PR-19-sub-minute-precision", "preserve seconds or visibly explain minute rounding", observed, turns, delta, after, product_contract_unclear=True)
        return _finding("PR-19-sub-minute-precision", "preserve seconds or visibly explain minute rounding", observed, turns, delta, after, bug_pattern="T1", mutation_expected=True, mutation_happened=bool(added), product_contract_unclear=True)

    results.append(_case_result("PR-19-sub-minute-precision", "preserve seconds or visibly explain minute rounding", account, transcript, c19_body, c19_judge))

    def c20_body(ctx: CaseContext) -> list[Turn]:
        return [
            ctx.step(f"明天 9 点提醒我 {LONG_TITLE}。", "PR-20-long-title-create"),
            ctx.step("列一下我的提醒。", "PR-20-long-title-list"),
        ]

    def c20_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = _active_added(delta)
        matching = [doc for doc in added if _title(doc) == LONG_TITLE]
        listed = LONG_TITLE in _reply_text(turns[-1:])
        observed = f"active_added={len(added)} exact_title_matches={len(matching)} title_lengths={[len(_title(doc)) for doc in added]} listed_exact={listed}"
        if len(matching) == 1 and listed:
            return _passed("PR-20-long-title", "200-char title is preserved in Mongo and list reply", observed, turns, delta, after)
        return _finding("PR-20-long-title", "200-char title is preserved in Mongo and list reply", observed, turns, delta, after, bug_pattern="NEW", mutation_expected=True, mutation_happened=bool(added))

    results.append(_case_result("PR-20-long-title", "200-char title is preserved in Mongo and list reply", account, transcript, c20_body, c20_judge))

    def c21_body(ctx: CaseContext) -> list[Turn]:
        return [ctx.step("明天 9 点提醒我 🍅 番茄钟 ⏰。", "PR-21-emoji-chinese")]

    def c21_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = _active_added(delta)
        matching = [doc for doc in added if _title(doc) == "🍅 番茄钟 ⏰" or "🍅 番茄钟 ⏰" in _title(doc)]
        reply_preserved = "🍅" in _reply_text(turns) and "⏰" in _reply_text(turns)
        observed = f"active_added={len(added)} matching={len(matching)} titles={[ _title(doc) for doc in added ]} reply_preserved={reply_preserved}"
        if len(matching) == 1 and reply_preserved:
            return _passed("PR-21-emoji-chinese", "emoji and Chinese title content are preserved", observed, turns, delta, after)
        return _finding("PR-21-emoji-chinese", "emoji and Chinese title content are preserved", observed, turns, delta, after, bug_pattern="NEW", mutation_expected=True, mutation_happened=bool(added))

    results.append(_case_result("PR-21-emoji-chinese", "emoji and Chinese title content are preserved", account, transcript, c21_body, c21_judge))

    def c22_body(ctx: CaseContext) -> list[Turn]:
        return [ctx.step("提醒我每天 8 点和 12 点喝水。", "PR-22-multiple-at-once")]

    def c22_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = _active_added(delta)
        water = [doc for doc in added if "喝水" in _title(doc)]
        times = sorted(_local_time(doc)[:5] for doc in water)
        rrules = [_rrule(doc) for doc in water]
        ok = len(water) == 2 and times == ["08:00", "12:00"] and all(rrule == "FREQ=DAILY" for rrule in rrules)
        observed = f"active_added={len(added)} water={len(water)} times={times} rrules={rrules}"
        if ok:
            return _passed("PR-22-multiple-at-once", "creates two daily reminders at 08:00 and 12:00", observed, turns, delta, after)
        return _finding("PR-22-multiple-at-once", "creates two daily reminders at 08:00 and 12:00", observed, turns, delta, after, bug_pattern="M1", mutation_expected=True, mutation_happened=bool(added))

    results.append(_case_result("PR-22-multiple-at-once", "creates two daily reminders at 08:00 and 12:00", account, transcript, c22_body, c22_judge))

    def c23_body(ctx: CaseContext) -> list[Turn]:
        hour = _future_today_hour()
        turns = [
            ctx.step(f"提醒我今天 {hour}:00 买菜。", "PR-23-seed-today"),
            ctx.step(f"提醒我明天 {hour}:00 洗车。", "PR-23-seed-tomorrow"),
            ctx.step("我今天有什么提醒？", "PR-23-list-today"),
        ]
        return turns

    def c23_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        reply = _reply_text(turns[-1:])
        includes_today = "买菜" in reply
        excludes_tomorrow = "洗车" not in reply
        observed = f"includes_today={includes_today} excludes_tomorrow={excludes_tomorrow} reply={reply[:120]!r}"
        if includes_today and excludes_tomorrow:
            return _passed("PR-23-list-todays-reminders", "today list includes today reminder and excludes tomorrow reminder", observed, turns, delta, after, product_contract_unclear=True)
        return _finding("PR-23-list-todays-reminders", "today list includes today reminder and excludes tomorrow reminder", observed, turns, delta, after, bug_pattern="L1", mutation_expected=False, mutation_happened=False, product_contract_unclear=True)

    results.append(_case_result("PR-23-list-todays-reminders", "today list includes today reminder and excludes tomorrow reminder", account, transcript, c23_body, c23_judge))

    def c24_body(ctx: CaseContext) -> list[Turn]:
        hour = _future_today_hour()
        return [
            ctx.step(f"提醒我明天 {hour}:00 喝水。", "PR-24-seed-water"),
            ctx.step(f"提醒我明天 {hour + 1}:00 读书。", "PR-24-seed-other"),
            ctx.step("我设过哪些喝水提醒？", "PR-24-list-fuzzy-title"),
        ]

    def c24_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        reply = _reply_text(turns[-1:])
        includes_water = "喝水" in reply
        excludes_other = "读书" not in reply
        lists_existing = includes_water and _contains_date_or_time_reply(reply) and "查不到" not in reply and "没有" not in reply
        no_write_on_list = delta["mongo"]["reminders"]["added"] == 2 and delta["mongo"]["reminders"]["modified"] == 0 and delta["mongo"]["reminders"]["removed"] == 0
        observed = f"includes_water={includes_water} excludes_other={excludes_other} lists_existing={lists_existing} no_write_on_list={no_write_on_list} reply={reply[:120]!r}"
        if lists_existing and excludes_other and no_write_on_list:
            return _passed("PR-24-list-by-fuzzy-title", "fuzzy title list only mentions matching active reminders and makes no list write", observed, turns, delta, after)
        return _finding("PR-24-list-by-fuzzy-title", "fuzzy title list only mentions matching active reminders and makes no list write", observed, turns, delta, after, bug_pattern="L1", mutation_expected=False, mutation_happened=not no_write_on_list)

    results.append(_case_result("PR-24-list-by-fuzzy-title", "fuzzy title list only mentions matching active reminders and makes no list write", account, transcript, c24_body, c24_judge))
    return results


def _setup_account(transcript: Transcript) -> SmokeAccount:
    account = provision_account("alice", batch_id=ACCOUNT_BATCH, display_name="Alice Personal Reminder")
    transcript.add_account(account)
    print(f"alice={account.coke_account_id} display={account.display_name}")
    if not account.tenant_id or not account.clawscale_user_id:
        raise BlockedSetup("BLOCKED-SETUP: account provisioning did not return tenant/user ids")
    return account


def _write_evidence(transcript: Transcript, account: SmokeAccount | None, results: list[dict[str, Any]], setup_status: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    findings = [result for result in results if result["verdict"] == "FINDING"]
    blocked = [result for result in results if str(result["verdict"]).startswith("BLOCKED")]
    transcript.set_verdict(
        passed=not findings and not blocked and setup_status == "PASSED",
        problems=[f"{item['case_id']}: {item['observed']}" for item in findings + blocked],
    )
    payload = {
        "batch": BATCH,
        "batch_id": BATCH_ID,
        "account_batch": ACCOUNT_BATCH,
        "setup_status": setup_status,
        "account": transcript.accounts[0] if transcript.accounts else None,
        "timezone": str(ZoneInfo("Asia/Shanghai")),
        "turns": [asdict(turn) for turn in transcript.turns],
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
    transcript = Transcript(batch_id=BATCH_ID)
    setup_status = "PASSED"
    results: list[dict[str, Any]] = []
    account: SmokeAccount | None = None
    try:
        account = _setup_account(transcript)
    except BlockedSetup as exc:
        setup_status = "BLOCKED-SETUP"
        print(str(exc))
        path = _write_evidence(transcript, account, results, setup_status)
        print(f"\nevidence={path}")
        return 2

    results = _run_cases(account, transcript)
    path = _write_evidence(transcript, account, results, setup_status)
    _print_summary(results)
    print(f"\nevidence={path}")
    return 0 if all(not str(result["verdict"]).startswith("BLOCKED") for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
