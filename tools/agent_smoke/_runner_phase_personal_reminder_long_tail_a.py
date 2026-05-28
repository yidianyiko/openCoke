"""Personal reminder long-tail smoke hunt, Batch A.

Runs cases 1-13 from
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
BATCH_ID = f"personal-reminder-crud-recurring-{BATCH}"
ACCOUNT_BATCH = "prlongtaila" + BATCH.lower().replace("t", "").replace("z", "")
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
EVIDENCE_PATH = EVIDENCE_DIR / f"{BATCH_ID}.json"

SUCCESS_CLAIM_TOKENS = ("已", "已经", "成功", "帮你", "创建", "设置", "改", "删除", "取消", "完成")
CLARIFY_TOKENS = ("哪一个", "哪个", "请确认", "请明确", "具体", "目标", "是哪条", "提醒内容")
UNSUPPORTED_TOKENS = ("暂不支持", "不支持", "不能", "无法", "没法")
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
    if not text.strip():
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

    def c1_body(ctx: CaseContext) -> list[Turn]:
        before_count = len(_reminders_for(account))
        turns = [
            ctx.step("提醒我 30 分钟后喝水。", "PR-01-seed"),
        ]
        seed = _latest_added(before_count, account, "喝水")
        ctx.remember_doc("seed", seed)
        turns.append(ctx.step("再过 10 分钟提醒我。", "PR-01-snooze"))
        return turns

    def c1_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        seed = ctx.checkpoints.get("seed") or {}
        final = _doc_by_id(after["mongo"]["reminders"], seed.get("_id"))
        no_write_and_asks = bool(final) and _stable(_clean(final.get("next_fire_at"))) == _stable(seed.get("next_fire_at")) and _has_any(_reply_text(turns[-1:]), CLARIFY_TOKENS)
        updated = bool(final) and _active(final) and _title(final) == _title(seed) and str(final.get("_id")) == str(seed.get("_id")) and _stable(final.get("next_fire_at")) != _stable(seed.get("next_fire_at"))
        duplicate_active = len([doc for doc in after["mongo"]["reminders"] if "喝水" in _title(doc) and _active(doc)]) > len([doc for doc in _new_reminders(delta) if "喝水" in _title(doc) and _active(doc)])
        observed = f"seed_id={seed.get('_id')} updated={updated} asked_no_write={no_write_and_asks} duplicate_active={duplicate_active}"
        if (updated or no_write_and_asks) and not duplicate_active:
            return _passed("PR-01-snooze-existing-one-shot", "snooze updates the same reminder or asks without writing", observed, turns, delta, after)
        return _finding("PR-01-snooze-existing-one-shot", "snooze updates the same reminder or asks without writing", observed, turns, delta, after, bug_pattern="S1", mutation_expected=True, mutation_happened=updated)

    results.append(_case_result("PR-01-snooze-existing-one-shot", "snooze updates the same reminder or asks without writing", account, transcript, c1_body, c1_judge))

    def c2_body(ctx: CaseContext) -> list[Turn]:
        before_count = len(_reminders_for(account))
        turns = [ctx.step("提醒我明天早上 8 点喝水。", "PR-02-seed")]
        seed = _latest_added(before_count, account, "喝水")
        ctx.remember_doc("seed", seed)
        turns.append(ctx.step("把那个喝水提醒改成下午 4 点。", "PR-02-update-time"))
        return turns

    def c2_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        seed = ctx.checkpoints.get("seed") or {}
        final = _doc_by_id(after["mongo"]["reminders"], seed.get("_id"))
        ok = _active(final) and _title(final) == _title(seed) and _local_time(final).startswith("16:00")
        observed = f"seed_id={seed.get('_id')} final_time={_local_time(final)} title={_title(final)!r}"
        if ok:
            return _passed("PR-02-update-time", "same reminder moves to local 16:00 with title preserved", observed, turns, delta, after)
        return _finding("PR-02-update-time", "same reminder moves to local 16:00 with title preserved", observed, turns, delta, after, bug_pattern="T1", mutation_expected=True, mutation_happened=bool(final and _stable(final) != _stable(seed)))

    results.append(_case_result("PR-02-update-time", "same reminder moves to local 16:00 with title preserved", account, transcript, c2_body, c2_judge))

    def c3_body(ctx: CaseContext) -> list[Turn]:
        before_count = len(_reminders_for(account))
        turns = [ctx.step("提醒我明天 8 点喝水。", "PR-03-seed")]
        seed = _latest_added(before_count, account, "喝水")
        ctx.remember_doc("seed", seed)
        turns.append(ctx.step("把那个 8 点的提醒改成「吃药」。", "PR-03-update-title"))
        return turns

    def c3_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        seed = ctx.checkpoints.get("seed") or {}
        final = _doc_by_id(after["mongo"]["reminders"], seed.get("_id"))
        ok = _active(final) and "吃药" in _title(final) and _local_time(final) == _local_time(seed)
        observed = f"seed_id={seed.get('_id')} title={_title(final)!r} time_before={seed.get('schedule', {}).get('local_time')} time_after={_local_time(final)}"
        if ok:
            return _passed("PR-03-update-title", "same reminder title becomes 吃药 and schedule is preserved", observed, turns, delta, after)
        return _finding("PR-03-update-title", "same reminder title becomes 吃药 and schedule is preserved", observed, turns, delta, after, bug_pattern="NEW", mutation_expected=True, mutation_happened=bool(final and _stable(final) != _stable(seed)))

    results.append(_case_result("PR-03-update-title", "same reminder title becomes 吃药 and schedule is preserved", account, transcript, c3_body, c3_judge))

    def c4_body(ctx: CaseContext) -> list[Turn]:
        before_count = len(_reminders_for(account))
        turns = [ctx.step("每天 8 点提醒我喝水。", "PR-04-seed")]
        seed = _latest_added(before_count, account, "喝水")
        ctx.remember_doc("seed", seed)
        turns.append(ctx.step("把每天 8 点的提醒改成只有工作日。", "PR-04-update-recurrence"))
        return turns

    def c4_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        seed = ctx.checkpoints.get("seed") or {}
        final = _doc_by_id(after["mongo"]["reminders"], seed.get("_id"))
        rrule = _rrule(final)
        ok = _active(final) and rrule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR" and _local_time(final).startswith("08:00")
        observed = f"seed_id={seed.get('_id')} rrule={rrule!r} local_time={_local_time(final)}"
        if ok:
            return _passed("PR-04-update-recurrence", "same reminder becomes weekday weekly RRULE", observed, turns, delta, after)
        return _finding("PR-04-update-recurrence", "same reminder becomes weekday weekly RRULE", observed, turns, delta, after, bug_pattern="R1", mutation_expected=True, mutation_happened=bool(final and _stable(final) != _stable(seed)))

    results.append(_case_result("PR-04-update-recurrence", "same reminder becomes weekday weekly RRULE", account, transcript, c4_body, c4_judge))

    def c5_body(ctx: CaseContext) -> list[Turn]:
        before_count = len(_reminders_for(account))
        turns = [ctx.step("提醒我明天 9 点喝水。", "PR-05-seed")]
        seed = _latest_added(before_count, account, "喝水")
        ctx.remember_doc("seed", seed)
        turns.append(ctx.step("删掉喝水提醒。", "PR-05-delete"))
        return turns

    def c5_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        seed = ctx.checkpoints.get("seed") or {}
        final = _doc_by_id(after["mongo"]["reminders"], seed.get("_id"))
        ok = bool(final) and final.get("lifecycle_state") == "cancelled" and not final.get("next_fire_at")
        observed = f"seed_id={seed.get('_id')} lifecycle={final.get('lifecycle_state') if final else None} next_fire_at={final.get('next_fire_at') if final else None}"
        if ok:
            return _passed("PR-05-delete-by-fuzzy-name", "delete cancels the matching reminder without physical deletion", observed, turns, delta, after)
        return _finding("PR-05-delete-by-fuzzy-name", "delete cancels the matching reminder without physical deletion", observed, turns, delta, after, bug_pattern="NEW", mutation_expected=True, mutation_happened=bool(final and _stable(final) != _stable(seed)))

    results.append(_case_result("PR-05-delete-by-fuzzy-name", "delete cancels the matching reminder without physical deletion", account, transcript, c5_body, c5_judge))

    def c6_body(ctx: CaseContext) -> list[Turn]:
        hour = _future_today_hour()
        before_count = len(_reminders_for(account))
        turns = [
            ctx.step(f"提醒我今天 {hour}:00 吃药。", "PR-06-seed-today"),
            ctx.step(f"提醒我明天 {hour + 1}:00 吃药。", "PR-06-seed-tomorrow"),
        ]
        docs = _reminders_for(account)[before_count:]
        ctx.checkpoints["seed_ids"] = [str(doc.get("_id")) for doc in docs if "吃药" in _title(doc)]
        turns.append(ctx.step("完成今天的吃药提醒。", "PR-06-complete"))
        turns.append(ctx.step("删掉吃药提醒。", "PR-06-delete"))
        return turns

    def c6_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        seed_ids = set(ctx.checkpoints.get("seed_ids") or [])
        finals = [doc for doc in after["mongo"]["reminders"] if str(doc.get("_id")) in seed_ids]
        completed = [doc for doc in finals if doc.get("lifecycle_state") == "completed" and doc.get("completed_at")]
        cancelled = [doc for doc in finals if doc.get("lifecycle_state") == "cancelled" and doc.get("cancelled_at")]
        ok = len(completed) == 1 and len(cancelled) == 1
        observed = f"seed_ids={sorted(seed_ids)} completed={len(completed)} cancelled={len(cancelled)} states={[doc.get('lifecycle_state') for doc in finals]}"
        if ok:
            return _passed("PR-06-complete-vs-delete", "complete and delete produce distinct completed/cancelled states", observed, turns, delta, after)
        return _finding("PR-06-complete-vs-delete", "complete and delete produce distinct completed/cancelled states", observed, turns, delta, after, bug_pattern="NEW", mutation_expected=True, mutation_happened=bool(completed or cancelled))

    results.append(_case_result("PR-06-complete-vs-delete", "complete and delete produce distinct completed/cancelled states", account, transcript, c6_body, c6_judge))

    def recurring_create_case(case_id: str, prompt: str, expected_rrule: str, bug_pattern: str = "R1") -> tuple[Callable[[CaseContext], list[Turn]], Callable[[list[Turn], dict[str, Any], dict[str, Any], CaseContext], dict[str, Any]]]:
        def body(ctx: CaseContext) -> list[Turn]:
            return [ctx.step(prompt, case_id)]

        def judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
            added = [doc for doc in _new_reminders(delta) if _active(doc)]
            matching = [doc for doc in added if _rrule(doc) == expected_rrule]
            ok = len(matching) == 1
            observed = f"active_added={len(added)} rrules={[ _rrule(doc) for doc in added ]} times={[ _local_time(doc) for doc in added ]}"
            if ok:
                return _passed(case_id, f"creates one active reminder with {expected_rrule}", observed, turns, delta, after, product_contract_unclear=(case_id == "PR-11-monthly"))
            return _finding(case_id, f"creates one active reminder with {expected_rrule}", observed, turns, delta, after, bug_pattern=bug_pattern, mutation_expected=True, mutation_happened=bool(added), product_contract_unclear=(case_id == "PR-11-monthly"))

        return body, judge

    for case_id, prompt, rrule in [
        ("PR-07-daily-recurring", "每天早 8 点提醒我喝水。", "FREQ=DAILY"),
        ("PR-08-weekdays-only", "工作日早 8 点提醒我喝水。", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
        ("PR-09-weekly-specific-day", "每周三 14:00 提醒我开会。", "FREQ=WEEKLY;BYDAY=WE"),
        ("PR-10-bi-weekly", "每隔一周周一 10 点提醒我复盘。", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"),
        ("PR-11-monthly", "每月 1 号 09:00 提醒我交房租。", "FREQ=MONTHLY"),
    ]:
        body, judge = recurring_create_case(case_id, prompt, rrule)
        results.append(_case_result(case_id, f"creates one active reminder with {rrule}", account, transcript, body, judge))

    def c12_body(ctx: CaseContext) -> list[Turn]:
        before_count = len(_reminders_for(account))
        turns = [ctx.step("每周三 14:00 提醒我做周报。", "PR-12-seed-weekly")]
        seed = _latest_added(before_count, account, "周报")
        ctx.remember_doc("seed", seed)
        turns.append(ctx.step("这周的不用了。", "PR-12-skip"))
        return turns

    def c12_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        seed = ctx.checkpoints.get("seed") or {}
        final = _doc_by_id(after["mongo"]["reminders"], seed.get("_id"))
        wrote = bool(final and _stable(final) != _stable(seed))
        safe_reply = _has_any(_reply_text(turns[-1:]), CLARIFY_TOKENS + UNSUPPORTED_TOKENS)
        ok = bool(final) and not wrote and safe_reply
        observed = f"seed_id={seed.get('_id')} wrote_to_series={wrote} safe_reply={safe_reply} lifecycle={final.get('lifecycle_state') if final else None}"
        if ok:
            return _passed("PR-12-recurring-skip", "ask/decline unsupported occurrence skip with no write", observed, turns, delta, after, product_contract_unclear=True)
        return _finding("PR-12-recurring-skip", "ask/decline unsupported occurrence skip with no write", observed, turns, delta, after, bug_pattern="R2", mutation_expected=False, mutation_happened=wrote, product_contract_unclear=True)

    results.append(_case_result("PR-12-recurring-skip", "ask/decline unsupported occurrence skip with no write", account, transcript, c12_body, c12_judge))

    def c13_body(ctx: CaseContext) -> list[Turn]:
        before_count = len(_reminders_for(account))
        turns = [ctx.step("每天 8 点提醒我写日记。", "PR-13-seed-daily")]
        seed = _latest_added(before_count, account, "日记")
        ctx.remember_doc("seed", seed)
        turns.append(ctx.step("把每天的提醒停掉。", "PR-13-end-recurring"))
        return turns

    def c13_judge(turns: list[Turn], delta: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        seed = ctx.checkpoints.get("seed") or {}
        final = _doc_by_id(after["mongo"]["reminders"], seed.get("_id"))
        ok = bool(final) and final.get("lifecycle_state") == "cancelled" and not final.get("next_fire_at")
        observed = f"seed_id={seed.get('_id')} lifecycle={final.get('lifecycle_state') if final else None} next_fire_at={final.get('next_fire_at') if final else None}"
        if ok:
            return _passed("PR-13-end-recurring", "cancel the recurrence source with no future next_fire_at", observed, turns, delta, after)
        return _finding("PR-13-end-recurring", "cancel the recurrence source with no future next_fire_at", observed, turns, delta, after, bug_pattern="R1", mutation_expected=True, mutation_happened=bool(final and _stable(final) != _stable(seed)))

    results.append(_case_result("PR-13-end-recurring", "cancel the recurrence source with no future next_fire_at", account, transcript, c13_body, c13_judge))
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
