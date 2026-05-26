"""Cross-feature long-conversation smoke hunt.

Runs L1-L10 from
docs/superpowers/specs/2026-05-26-cross-feature-long-conversation-design.md.

Evidence only: no product-code changes, no model swap, no delivery-route seed.
"""

from __future__ import annotations

import json
import re
import time
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
BATCH_ID = f"cross-feature-long-{BATCH}"
ACCOUNT_BATCH = "cflong" + BATCH.lower().replace("t", "").replace("z", "")
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
EVIDENCE_PATH = EVIDENCE_DIR / f"{BATCH_ID}.json"
MODEL = "GLM-5.1 thinking-off"
CASE_TIMEOUT_SECONDS = 15 * 60

LINK_CODE_RE = re.compile(r"/u/([A-Za-z0-9_-]+)|邀请码[:：\s]*([A-Za-z0-9_-]{6,})")
RAW_ENVELOPE_RE = re.compile(r"```json|MultiModalResponses|\"message_type\"")
EMPTY_FALLBACK_TOKENS = ("我没接住你刚才的意思", "我这次没能及时整理")
SUCCESS_CLAIM_TOKENS = ("已", "已经", "成功", "帮你", "创建", "设置", "发送", "通过", "改", "删除", "取消", "完成")
CLARIFY_OR_REFUSE_TOKENS = ("哪一个", "哪个", "请确认", "请明确", "无法", "不能", "不支持", "没有", "未找到", "找不到", "先加")


class BlockedSetup(RuntimeError):
    pass


class CaseTimeout(RuntimeError):
    pass


def _clean(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _stable(value: Any) -> str:
    return json.dumps(_clean(value), ensure_ascii=False, sort_keys=True, default=str)


def _doc_key(doc: dict[str, Any]) -> str:
    return str(doc.get("_id") or doc.get("id") or "|".join(f"{k}={doc[k]}" for k in sorted(doc)))


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
        group: {name: _diff_rows(before[group][name], after[group][name]) for name in before[group]}
        for group in before
    }


def _brief_delta(delta: dict[str, Any]) -> dict[str, Any]:
    return {
        group: {
            name: {"added": item["added"], "modified": item["modified"], "removed": item["removed"]}
            for name, item in tables.items()
        }
        for group, tables in delta.items()
    }


def _sql_json(sql: str) -> list[dict[str, Any]]:
    raw = _run_psql(sql).strip()
    return json.loads(raw) if raw else []


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ids_sql(accounts: dict[str, SmokeAccount]) -> str:
    return ",".join(_quote(account.coke_account_id) for account in accounts.values())


def _postgres_snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, list[dict[str, Any]]]:
    ids = _ids_sql(accounts)
    return {
        "customers": _sql_json(f"SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json) FROM (SELECT * FROM customers WHERE id IN ({ids})) t;"),
        "identities": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT i.* FROM identities i JOIN memberships m ON m.identity_id = i.id
   WHERE m.customer_id IN ({ids})
) t;
"""
        ),
        "memberships": _sql_json(f"SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json) FROM (SELECT * FROM memberships WHERE customer_id IN ({ids})) t;"),
        "user_links": _sql_json(f"SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json) FROM (SELECT * FROM user_links WHERE provider_account_id IN ({ids})) t;"),
        "link_sessions": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT ls.* FROM link_sessions ls LEFT JOIN user_links ul ON ul.id = ls.user_link_id
   WHERE ls.provider_account_id IN ({ids}) OR ls.consumer_account_id IN ({ids}) OR ul.provider_account_id IN ({ids})
) t;
"""
        ),
        "friend_requests": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY created_at, id), '[]'::json)
FROM (SELECT * FROM friend_requests WHERE requester_account_id IN ({ids}) OR target_account_id IN ({ids})) t;
"""
        ),
        "friendships": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY created_at, id), '[]'::json)
FROM (SELECT * FROM friendships WHERE account_a_id IN ({ids}) OR account_b_id IN ({ids})) t;
"""
        ),
        "shared_reminder_requests": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY created_at, id), '[]'::json)
FROM (SELECT * FROM shared_reminder_requests WHERE requester_account_id IN ({ids}) OR invitee_account_id IN ({ids})) t;
"""
        ),
        "reminder_projections": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT rp.* FROM reminder_projections rp
  LEFT JOIN shared_reminder_requests srr ON srr.id = rp.shared_reminder_request_id
   WHERE rp.owner_account_id IN ({ids}) OR srr.requester_account_id IN ({ids}) OR srr.invitee_account_id IN ({ids})
) t;
"""
        ),
        "product_notifications": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY created_at, id), '[]'::json)
FROM (
  SELECT pn.* FROM product_notifications pn
  LEFT JOIN friend_requests fr ON fr.id = pn.friend_request_id
  LEFT JOIN shared_reminder_requests srr ON srr.id = pn.shared_reminder_request_id
   WHERE pn.recipient_account_id IN ({ids})
      OR fr.requester_account_id IN ({ids}) OR fr.target_account_id IN ({ids})
      OR srr.requester_account_id IN ({ids}) OR srr.invitee_account_id IN ({ids})
) t;
"""
        ),
        "delivery_routes": _sql_json(f"SELECT COALESCE(json_agg(row_to_json(t) ORDER BY coke_account_id, business_conversation_key), '[]'::json) FROM (SELECT * FROM delivery_routes WHERE coke_account_id IN ({ids})) t;"),
    }


def _mongo_snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, list[dict[str, Any]]]:
    account_ids = [account.coke_account_id for account in accounts.values()]
    client = MongoClient(_config.mongo_uri())
    try:
        db = client[_config.mongo_db_name()]
        sessions = list(db.agent_sessions.find().sort("updated_at", -1).limit(220))
        return {
            "reminders": list(db.reminders.find({"owner_user_id": {"$in": account_ids}}).sort("_id", 1)),
            "outputmessages": list(db.outputmessages.find({"$or": [{"to_user": {"$in": account_ids}}, {"account_id": {"$in": account_ids}}]}).sort("_id", 1)),
            "inputmessages": list(db.inputmessages.find({"$or": [{"from_user": {"$in": account_ids}}, {"to_user": {"$in": account_ids}}]}).sort("_id", 1)),
            "agent_sessions": [doc for doc in sessions if any(account_id in _stable(doc) for account_id in account_ids)],
        }
    finally:
        client.close()


def snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, Any]:
    return {"mongo": _mongo_snapshot(accounts), "postgres": _postgres_snapshot(accounts)}


def _parse_link_code(text: str) -> str | None:
    match = LINK_CODE_RE.search(text or "")
    return (match.group(1) or match.group(2)) if match else None


def _internal_link(account: SmokeAccount, endpoint: str) -> str | None:
    url = _config.gateway_api_base_url() + f"/api/internal/scheduling/tools/{endpoint}"
    headers = {"Authorization": f"Bearer {_config.gateway_identity_api_key()}", "Content-Type": "application/json"}
    response = requests.post(url, json={"customer_id": account.coke_account_id}, headers=headers, timeout=10)
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code != 200 or not isinstance(data, dict):
        return None
    payload = data.get("data") if data.get("data") is not None else data
    return payload.get("link_code") or payload.get("code") or payload.get("user_link_code")


def _public_link_active(code: str) -> bool:
    response = requests.get(_config.gateway_api_base_url() + f"/api/public/user-links/{code}", timeout=10)
    return response.status_code == 200 and bool(response.json().get("ok"))


def _reply_text(turns: list[Turn]) -> str:
    return "\n".join(turn.reply_text or "" for turn in turns)


def _agent_trace_excerpt(turn: Turn, after: dict[str, Any]) -> list[dict[str, Any]]:
    excerpts: list[dict[str, Any]] = []
    for session in after["mongo"].get("agent_sessions", []):
        stable = _stable(session)
        if turn.input_text not in stable and turn.inbound_event_id not in stable:
            continue
        for run in (session.get("runs") or [])[-2:]:
            items = []
            for message in (run.get("messages") or [])[-16:]:
                item = {"role": message.get("role"), "tool_name": message.get("tool_name"), "content": str(message.get("content") or "")[:650]}
                if message.get("tool_calls"):
                    item["tool_calls"] = _clean(message.get("tool_calls"))
                items.append(item)
            excerpts.append({"session_id": str(session.get("_id")), "messages": items})
        if len(excerpts) >= 2:
            break
    return excerpts


def _base_bug_pattern(turns: list[Turn], default: str, mutation_expected: bool, mutation_happened: bool) -> str:
    text = _reply_text(turns)
    if RAW_ENVELOPE_RE.search(text):
        return "A"
    if any(token in text for token in EMPTY_FALLBACK_TOKENS) or not text.strip():
        return "B"
    if "ValidationError" in text or "Tool call limit" in text:
        return "D1"
    if "not_found" in text or "找不到" in text:
        return "D2"
    if any(turn.placeholder_received and not turn.late_reply_landed for turn in turns):
        return "BLOCKED-LATE-REPLY-TIMEOUT"
    if mutation_expected and not mutation_happened and any(token in text for token in SUCCESS_CLAIM_TOKENS):
        return "C"
    return default


def _active_friendships(after: dict[str, Any], left: SmokeAccount, right: SmokeAccount) -> list[dict[str, Any]]:
    ids = {left.coke_account_id, right.coke_account_id}
    return [row for row in after["postgres"]["friendships"] if row.get("status") == "active" and {row.get("account_a_id"), row.get("account_b_id")} == ids]


def _shared_rows(after: dict[str, Any], *accounts: SmokeAccount) -> list[dict[str, Any]]:
    ids = {account.coke_account_id for account in accounts}
    return [row for row in after["postgres"]["shared_reminder_requests"] if row.get("requester_account_id") in ids or row.get("invitee_account_id") in ids]


def _reminders_for(after: dict[str, Any], account: SmokeAccount) -> list[dict[str, Any]]:
    return [row for row in after["mongo"]["reminders"] if row.get("owner_user_id") == account.coke_account_id]


def _active_reminders(after: dict[str, Any], account: SmokeAccount) -> list[dict[str, Any]]:
    return [row for row in _reminders_for(after, account) if row.get("lifecycle_state") == "active"]


def _result(ctx: "CaseContext", before: dict[str, Any], after: dict[str, Any], *, verdict: str, expected: str, observed: str, bug_pattern: str = "", severity: str = "", product_contract_unclear: bool = False, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    delta = _diff_snapshot(before, after)
    payload = {
        "batch_id": BATCH_ID,
        "model": MODEL,
        "case_id": ctx.case_id,
        "verdict": verdict,
        "bug_pattern": bug_pattern,
        "severity": severity,
        "product_contract_unclear": product_contract_unclear,
        "expected": expected,
        "observed": observed,
        "turns": [asdict(turn) for turn in ctx.turns],
        "turn_evidence": ctx.turn_evidence,
        "agent_reply": _reply_text(ctx.turns),
        "case_delta_summary": _brief_delta(delta),
        "mongo_delta": delta["mongo"],
        "postgres_delta": delta["postgres"],
        "snapshot_before": _clean(before),
        "snapshot_after": _clean(after),
    }
    if extra:
        payload["extra"] = _clean(extra)
    return payload


def _judge_result(ctx: "CaseContext", before: dict[str, Any], after: dict[str, Any], *, expected: str, observed: str, ok: bool, bug_pattern: str, mutation_expected: bool, mutation_happened: bool, severity: str = "visible-error", product_contract_unclear: bool = False, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    text = _reply_text(ctx.turns)
    if any(turn.placeholder_received and not turn.late_reply_landed for turn in ctx.turns):
        return _result(ctx, before, after, verdict="BLOCKED", expected=expected, observed="BLOCKED-LATE-REPLY-TIMEOUT", bug_pattern="BLOCKED-LATE-REPLY-TIMEOUT", severity="smoke-infra", product_contract_unclear=product_contract_unclear, extra=extra)
    bad = "raw envelope leaked" if RAW_ENVELOPE_RE.search(text) else None
    if not bad and any(token in text for token in EMPTY_FALLBACK_TOKENS):
        bad = "empty fallback surfaced"
    if ok and not bad:
        return _result(ctx, before, after, verdict="PASSED", expected=expected, observed=observed, product_contract_unclear=product_contract_unclear, extra=extra)
    if bad:
        observed = f"{observed}; {bad}"
    return _result(
        ctx,
        before,
        after,
        verdict="FINDING",
        expected=expected,
        observed=observed,
        bug_pattern=_base_bug_pattern(ctx.turns, bug_pattern, mutation_expected, mutation_happened),
        severity=severity,
        product_contract_unclear=product_contract_unclear,
        extra=extra,
    )


class CaseContext:
    def __init__(self, case_id: str, accounts: dict[str, SmokeAccount], transcript: Transcript):
        self.case_id = case_id
        self.accounts = accounts
        self.transcript = transcript
        self.started_at = time.monotonic()
        self.turns: list[Turn] = []
        self.turn_evidence: list[dict[str, Any]] = []
        self.link_codes: dict[str, str] = {}
        self.extras: dict[str, Any] = {}

    def step(self, speaker: str, text: str, note: str) -> Turn:
        if time.monotonic() - self.started_at > CASE_TIMEOUT_SECONDS:
            raise CaseTimeout(f"{self.case_id}: exceeded {CASE_TIMEOUT_SECONDS}s")
        case_turn = len(self.turns) + 1
        global_turn = len(self.transcript.turns) + 1
        account = self.accounts[speaker]
        before = snapshot(self.accounts)
        print(f"\n[{self.case_id} T{case_turn:02d}/{global_turn:03d} {speaker}] >> {text}", flush=True)
        start = time.monotonic()
        reply = send_as(account.coke_account_id, text, **account.send_kwargs())
        elapsed_ms = int((time.monotonic() - start) * 1000)
        turn = Turn(
            turn=global_turn,
            speaker=speaker,
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
        self.transcript.add_turn(turn)
        self.turns.append(turn)
        time.sleep(0.5)
        after = snapshot(self.accounts)
        delta = _diff_snapshot(before, after)
        evidence = {
            "turn": case_turn,
            "global_turn": global_turn,
            "speaker": speaker,
            "input_text": text,
            "reply_text": turn.reply_text,
            "elapsed_ms": elapsed_ms,
            "output_id": turn.output_id,
            "placeholder_received": turn.placeholder_received,
            "late_reply_landed": turn.late_reply_landed,
            "polling_seconds_used": turn.polling_seconds_used,
            "before_snapshot_ref": f"{self.case_id}-turn-{case_turn:02d}-before",
            "after_snapshot_ref": f"{self.case_id}-turn-{case_turn:02d}-after",
            "snapshot_before": _clean(before),
            "snapshot_after": _clean(after),
            "mongo_delta": delta["mongo"],
            "postgres_delta": delta["postgres"],
            "delta_summary": _brief_delta(delta),
            "agent_trace_excerpt": _agent_trace_excerpt(turn, after),
            "assertions": {"late_reply_ok": not (turn.placeholder_received and not turn.late_reply_landed)},
        }
        self.turn_evidence.append(evidence)
        print(f"[{self.case_id} T{case_turn:02d}/{global_turn:03d} {speaker}] << ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}", flush=True)
        print(f"[{self.case_id} T{case_turn:02d}] delta={json.dumps(evidence['delta_summary'], ensure_ascii=False, default=str)}", flush=True)
        return turn

    def ensure_link(self, owner_key: str) -> str:
        if owner_key in self.link_codes and _public_link_active(self.link_codes[owner_key]):
            return self.link_codes[owner_key]
        account = self.accounts[owner_key]
        turn = self.step(owner_key, "把我自己的好友邀请链接给我，我要分享给朋友。", f"{self.case_id}_setup_{owner_key}_link")
        code = _parse_link_code(turn.reply_text)
        fallback = False
        if not code or not _public_link_active(code):
            code = _internal_link(account, "get_user_link")
            fallback = True
        if code and not _public_link_active(code):
            code = _internal_link(account, "reset_user_link")
            fallback = True
        if not code:
            raise BlockedSetup(f"{self.case_id}: could not obtain {owner_key} link")
        self.link_codes[owner_key] = code
        if fallback:
            self.extras.setdefault("link_fallbacks", []).append({"owner": owner_key, "code": code})
        print(f"[{self.case_id} setup] {owner_key}_link_code={code}", flush=True)
        return code

    def ensure_active_friendship(self, left_key: str, right_key: str) -> None:
        latest = snapshot(self.accounts)
        left, right = self.accounts[left_key], self.accounts[right_key]
        if _active_friendships(latest, left, right):
            return
        code = self.ensure_link(left_key)
        left_name = left.display_name.split()[0]
        right_name = right.display_name.split()[0]
        self.step(right_key, f"我想加 {left_name} 为好友。这是对方的邀请码：{code}。", f"{self.case_id}_setup_{right_key}_request_{left_key}")
        self.step(left_key, f"通过 {right_name} 的好友请求。", f"{self.case_id}_setup_{left_key}_accept_{right_key}")
        latest = snapshot(self.accounts)
        if not _active_friendships(latest, left, right):
            raise BlockedSetup(f"{self.case_id}: {left_key}-{right_key} friendship not active")


def _case_result(case_id: str, account_specs: dict[str, str], transcript: Transcript, body: Callable[[CaseContext], None], judge: Callable[[CaseContext, dict[str, Any], dict[str, Any]], dict[str, Any]], expected: str, *, product_contract_unclear: bool = False) -> dict[str, Any]:
    print(f"\n=== {case_id} ===", flush=True)
    accounts: dict[str, SmokeAccount] = {}
    before = {"mongo": {}, "postgres": {}}
    ctx: CaseContext | None = None
    try:
        short = case_id.split("-", 1)[0].lower()
        for label, display_name in account_specs.items():
            account = provision_account(f"{short}_{label}", batch_id=ACCOUNT_BATCH, display_name=display_name)
            accounts[label] = account
            transcript.add_account(account)
        print(f"[{case_id}] accounts={json.dumps({k: v.coke_account_id for k, v in accounts.items()}, ensure_ascii=False)}", flush=True)
        before = snapshot(accounts)
        ctx = CaseContext(case_id, accounts, transcript)
        body(ctx)
        after = snapshot(accounts)
        result = judge(ctx, before, after)
        if ctx.extras:
            result.setdefault("extra", {}).update(_clean(ctx.extras))
        return result
    except CaseTimeout as exc:
        after = snapshot(accounts) if accounts else before
        assert ctx is not None
        return _result(ctx, before, after, verdict="BLOCKED", expected=expected, observed=f"BLOCKED-CASE-TIMEOUT: {exc}", bug_pattern="BLOCKED-CASE-TIMEOUT", severity="smoke-infra", product_contract_unclear=product_contract_unclear, extra=ctx.extras)
    except (BridgeError, requests.RequestException, BlockedSetup, ValueError) as exc:
        after = snapshot(accounts) if accounts else before
        if ctx is None:
            ctx = CaseContext(case_id, accounts, transcript)
        return _result(ctx, before, after, verdict="BLOCKED", expected=expected, observed=f"{type(exc).__name__}: {exc}", severity="smoke-infra", product_contract_unclear=product_contract_unclear, extra=ctx.extras)
    except Exception as exc:
        after = snapshot(accounts) if accounts else before
        if ctx is None:
            ctx = CaseContext(case_id, accounts, transcript)
        return _result(ctx, before, after, verdict="BLOCKED", expected=expected, observed=f"{type(exc).__name__}: {exc}", severity="smoke-infra", product_contract_unclear=product_contract_unclear, extra=ctx.extras)


def _run_turns(ctx: CaseContext, speaker: str, turns: list[str], prefix: str) -> None:
    for index, text in enumerate(turns, start=1):
        ctx.step(speaker, text, f"{prefix}_{index:02d}")


def _run_cases(transcript: Transcript) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def l1(ctx: CaseContext) -> None:
        _run_turns(ctx, "alice", ["每天 8 点提醒我喝水。", "看看我有哪些提醒？", "刚才那个提醒晚 10 分钟。", "刚才那个提醒现在是什么状态？", "把喝水提醒改到 09:00。", "你今天忙吗？", "再看看我的提醒列表。", "把下一次喝水提醒标记完成。", "刚才完成的是哪个提醒？", "取消剩下的喝水系列提醒。", "刚才那个提醒还在吗？", "最后再列一下我的提醒。", "用自然语言帮我总结一下数据库里现在和喝水有关的提醒状态。"], "L1")

    def l1j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        docs = _reminders_for(after, ctx.accounts["alice"])
        active = _active_reminders(after, ctx.accounts["alice"])
        replies = [turn.reply_text or "" for turn in ctx.turns]
        unresolved_backrefs = []
        for index in (2, 3, 8, 10):
            if index < len(replies) and (
                "哪个" in replies[index]
                or "哪条" in replies[index]
                or "不确定" in replies[index]
                or "找不到" in replies[index]
                or "没看到" in replies[index]
                or "没查到" in replies[index]
            ):
                unresolved_backrefs.append(index + 1)
        if len(replies) > 8 and "喝水" not in replies[8]:
            unresolved_backrefs.append(9)
        ok = len(docs) >= 1 and not active and not unresolved_backrefs
        observed = f"reminders={len(docs)} active={len(active)} unresolved_backref_turns={sorted(set(unresolved_backrefs))}"
        return _judge_result(ctx, before, after, expected="Daily reminder remains coherent through update, completion/cancel, and backreferences", observed=observed, ok=ok, bug_pattern="X2", mutation_expected=True, mutation_happened=bool(docs), severity="silent-bad-side-effect", product_contract_unclear=True)

    results.append(_case_result("L1-reminder-lifecycle-full", {"alice": "Alice Long"}, transcript, l1, l1j, "L1 lifecycle", product_contract_unclear=True))

    def l2(ctx: CaseContext) -> None:
        _run_turns(ctx, "alice", ["提醒我明天 9 点交报告。", "每天 8 点提醒我喝水。", "每周三 14 点提醒我复盘。", "列出我的全部提醒。", "把每天喝水那个改到 08:30。", "你能做什么？", "删掉交报告那个提醒。", "再列出我的全部提醒。", "每周三那个还在吗？", "喝水现在几点？", "删掉喝水那个提醒。", "最后列出我的提醒。"], "L2")

    def l2j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        titles = [str(row.get("title") or "") for row in _active_reminders(after, ctx.accounts["alice"])]
        replies = [turn.reply_text or "" for turn in ctx.turns]
        weekly_reply_ok = len(replies) > 8 and "复盘" in replies[8] and "14" in replies[8]
        daily_reply_ok = len(replies) > 9 and ("08:30" in replies[9] or "8:30" in replies[9] or "八点半" in replies[9])
        final_reply_ok = len(replies) > 11 and "复盘" in replies[11] and not any(token in replies[11] for token in ("卡", "没能", "失败"))
        ok = (
            any("复盘" in title for title in titles)
            and not any("交报告" in title or "喝水" in title for title in titles)
            and weekly_reply_ok
            and daily_reply_ok
            and final_reply_ok
        )
        observed = f"active_titles={titles} weekly_reply_ok={weekly_reply_ok} daily_reply_ok={daily_reply_ok} final_reply_ok={final_reply_ok}"
        return _judge_result(ctx, before, after, expected="Mixed reminder types remain distinct; fuzzy delete only affects intended reminders and status queries stay grounded", observed=observed, ok=ok, bug_pattern="X2", mutation_expected=True, mutation_happened=len(_reminders_for(after, ctx.accounts["alice"])) >= 3, severity="silent-bad-side-effect")

    results.append(_case_result("L2-mixed-reminder-types", {"alice": "Alice Long"}, transcript, l2, l2j, "L2 mixed reminders"))

    def l3(ctx: CaseContext) -> None:
        creates = ["明天 7 点提醒我浇花。", "明天 8 点提醒我读书。", "明天 9 点提醒我开晨会。", "明天 10 点提醒我回邮件。", "明天 11 点提醒我买咖啡。", "明天 12 点提醒我吃午饭。", "明天 13 点提醒我散步。", "明天 14 点提醒我写周报。", "明天 15 点提醒我整理桌面。", "明天 16 点提醒我备份文件。"]
        _run_turns(ctx, "alice", creates + ["列一下我的提醒。", "你是谁？", "你能帮我订机票吗？", "我现在有哪些明天的安排？", "你今天忙吗？", "不要改任何提醒，只告诉我现在有几个。", "刚才有没有设置买咖啡？", "你能帮我点外卖吗？", "我刚才设的第一个提醒是几点？", "最后一个呢？"], "L3")

    def l3j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        docs = _reminders_for(after, ctx.accounts["alice"])
        tail = _reply_text(ctx.turns[-2:])
        ok = len(docs) == 10 and "7" in tail and "16" in tail
        return _judge_result(ctx, before, after, expected="Ten-reminder long context preserves first/last backreferences", observed=f"reminders={len(docs)} tail_reply={tail[:160]}", ok=ok, bug_pattern="X2", mutation_expected=True, mutation_happened=len(docs) >= 10, severity="silent-bad-side-effect")

    results.append(_case_result("L3-long-context-backreference", {"alice": "Alice Long"}, transcript, l3, l3j, "L3 long context"))

    def l4(ctx: CaseContext) -> None:
        code = ctx.ensure_link("alice")
        for speaker, text, note in [("bob", f"我要加 Alice 为好友，这是邀请码：{code}。", "L4_bob_link"), ("alice", "通过 Bob 的好友请求。", "L4_accept"), ("alice", "约 Bob 明天 10 点喝咖啡。", "L4_create_shared"), ("bob", "接受 Alice 刚才发来的喝咖啡提醒。", "L4_bob_accept"), ("alice", "我和 Bob 明天喝咖啡是几点？", "L4_alice_fact"), ("bob", "我和 Alice 明天喝咖啡是几点？", "L4_bob_fact"), ("alice", "把刚才和 Bob 的喝咖啡改到 10:30。", "L4_modify"), ("bob", "刚才那个改了吗？", "L4_backref"), ("alice", "最后列一下我和 Bob 的共享提醒。", "L4_final")]:
            ctx.step(speaker, text, note)

    def l4j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        alice, bob = ctx.accounts["alice"], ctx.accounts["bob"]
        shared = _shared_rows(after, alice, bob)
        reminders = _reminders_for(after, alice) + _reminders_for(after, bob)
        ok = bool(_active_friendships(after, alice, bob)) and any(row.get("status") == "accepted" for row in shared) and len(reminders) >= 2
        return _judge_result(ctx, before, after, expected="Friend bootstrap plus accepted shared reminder is visible to both users", observed=f"shared={[(r.get('status'), r.get('requester_reminder_id'), r.get('invitee_reminder_id')) for r in shared]} reminders={len(reminders)}", ok=ok, bug_pattern="X1", mutation_expected=True, mutation_happened=bool(shared), severity="silent-bad-side-effect")

    results.append(_case_result("L4-friend-shared-reminder-bootstrap", {"alice": "Alice Long", "bob": "Bob Long"}, transcript, l4, l4j, "L4 friend shared"))

    def l5(ctx: CaseContext) -> None:
        ctx.ensure_active_friendship("alice", "bob")
        ctx.ensure_active_friendship("alice", "carol")
        for speaker, text, note in [("alice", "我有哪些好友？", "L5_friends"), ("alice", "约 Bob 和 Carol 周日 14:00 一起打球。", "L5_create"), ("alice", "刚才发给几个人了？", "L5_count"), ("bob", "我有哪些待确认的共享提醒？", "L5_bob_pending"), ("carol", "我有哪些待确认的共享提醒？", "L5_carol_pending"), ("bob", "接受 Alice 刚才发来的打球提醒。", "L5_bob_accept"), ("carol", "接受 Alice 刚才发来的打球提醒。", "L5_carol_accept"), ("alice", "现在 Bob 和 Carol 都确认了吗？", "L5_status"), ("alice", "把打球改到周日 15:00。", "L5_modify"), ("alice", "Bob 那边现在是几点？", "L5_bob_time"), ("alice", "Carol 那边现在是几点？", "L5_carol_time")]:
            ctx.step(speaker, text, note)

    def l5j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        alice, bob, carol = ctx.accounts["alice"], ctx.accounts["bob"], ctx.accounts["carol"]
        shared = _shared_rows(after, alice, bob, carol)
        invitees = {row.get("invitee_account_id") for row in shared if row.get("requester_account_id") == alice.coke_account_id}
        refused = not shared and any(token in _reply_text(ctx.turns) for token in CLARIFY_OR_REFUSE_TOKENS)
        ok = invitees == {bob.coke_account_id, carol.coke_account_id} or refused
        return _judge_result(ctx, before, after, expected="Three-way request creates one request per invitee or refuses/clarifies without writes", observed=f"invitee_count={len(invitees)} statuses={[r.get('status') for r in shared]} refused={refused}", ok=ok, bug_pattern="X5", mutation_expected=False, mutation_happened=bool(shared), severity="silent-bad-side-effect", product_contract_unclear=True)

    results.append(_case_result("L5-three-way-coordination", {"alice": "Alice Long", "bob": "Bob Long", "carol": "Carol Long"}, transcript, l5, l5j, "L5 three-way", product_contract_unclear=True))

    def l6(ctx: CaseContext) -> None:
        ctx.ensure_active_friendship("alice", "bob")
        for speaker, text, note in [("alice", "约 Bob 明天 18:00 讨论方案。", "L6_create"), ("bob", "我先不处理，看看有哪些待确认提醒？", "L6_bob_pending"), ("alice", "我有哪些待 Bob 确认的提醒？", "L6_alice_pending"), ("alice", "把 Bob 从我的好友里删掉。", "L6_remove"), ("alice", "我和 Bob 的提醒还在吗？", "L6_alice_after"), ("bob", "我有哪些待确认的共享提醒？", "L6_bob_after"), ("alice", "把我和 Bob 的方案提醒改到 19:00。", "L6_modify_after"), ("bob", "接受 Alice 刚才发来的方案提醒。", "L6_accept_after"), ("alice", "列出我的共享提醒。", "L6_alice_final"), ("bob", "列出我的共享提醒。", "L6_bob_final")]:
            ctx.step(speaker, text, note)

    def l6j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        alice, bob = ctx.accounts["alice"], ctx.accounts["bob"]
        shared = _shared_rows(after, alice, bob)
        ok = not _active_friendships(after, alice, bob) and not any(row.get("status") == "accepted" for row in shared)
        return _judge_result(ctx, before, after, expected="Removed friendship makes pending shared reminders non-actionable", observed=f"active_friendships={len(_active_friendships(after, alice, bob))} shared_statuses={[r.get('status') for r in shared]}", ok=ok, bug_pattern="X4", mutation_expected=True, mutation_happened=not _active_friendships(after, alice, bob), severity="privacy-leak")

    results.append(_case_result("L6-friend-remove-mid-flow", {"alice": "Alice Long", "bob": "Bob Long"}, transcript, l6, l6j, "L6 remove mid-flow"))

    def l7(ctx: CaseContext) -> None:
        ctx.ensure_active_friendship("alice", "mei")
        for speaker, text, note in [("alice", "我有哪些好友？", "L7_friends"), ("alice", "约 Mei 明天 10 点。", "L7_mei"), ("alice", "刚才是加好友还是约提醒？", "L7_route"), ("mei", "我有哪些待确认的共享提醒？", "L7_mei_pending"), ("alice", "约 Jin 明天 11 点。", "L7_jin"), ("alice", "为什么不能约 Jin？", "L7_why"), ("alice", "我现在有哪些好友？", "L7_final_friends"), ("alice", "我有哪些共享提醒？", "L7_final_shared"), ("alice", "Mei 那边待确认状态是什么？", "L7_status")]:
            ctx.step(speaker, text, note)

    def l7j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        shared = _shared_rows(after, ctx.accounts["alice"], ctx.accounts["mei"])
        ok = bool(shared)
        return _judge_result(ctx, before, after, expected="Friend Mei routes to shared reminder; non-friend Jin fails closed", observed=f"shared_rows={len(shared)} statuses={[r.get('status') for r in shared]}", ok=ok, bug_pattern="X1", mutation_expected=True, mutation_happened=bool(shared), severity="silent-bad-side-effect")

    results.append(_case_result("L7-friend-vs-shared-reminder", {"alice": "Alice Long", "mei": "Mei Long"}, transcript, l7, l7j, "L7 friend vs shared"))

    def l8(ctx: CaseContext) -> None:
        ctx.ensure_active_friendship("alice", "bob")
        for speaker, text, note in [("alice", "提醒我明天 14:00 去开会。", "L8_personal"), ("alice", "列出我的个人提醒。", "L8_list_personal"), ("alice", "提醒我和 Bob 明天 15:00 一起开会。", "L8_shared"), ("bob", "我有哪些待确认的共享提醒？", "L8_bob_pending"), ("alice", "我自己的 14 点还在吗？", "L8_personal_still"), ("bob", "接受 Alice 刚才发来的开会提醒。", "L8_accept"), ("alice", "列出我的个人提醒。", "L8_personal_after"), ("alice", "列出我和 Bob 的共享提醒。", "L8_shared_list"), ("alice", "把和 Bob 的开会改到明天 15:30。", "L8_modify_shared"), ("alice", "确认我自己的 14 点和 Bob 的 15:30 都还在。", "L8_verify")]:
            ctx.step(speaker, text, note)

    def l8j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        alice, bob = ctx.accounts["alice"], ctx.accounts["bob"]
        shared = _shared_rows(after, alice, bob)
        reminders = _reminders_for(after, alice)
        ok = bool(shared) and len(reminders) >= 1
        return _judge_result(ctx, before, after, expected="Personal and shared reminders remain independent", observed=f"alice_reminders={len(reminders)} shared_rows={len(shared)} statuses={[r.get('status') for r in shared]}", ok=ok, bug_pattern="X1", mutation_expected=True, mutation_happened=bool(shared or reminders), severity="silent-bad-side-effect")

    results.append(_case_result("L8-reminder-vs-shared-reminder", {"alice": "Alice Long", "bob": "Bob Long"}, transcript, l8, l8j, "L8 reminder vs shared"))

    def l9(ctx: CaseContext) -> None:
        ctx.ensure_active_friendship("alice", "alex")
        for speaker, text, note in [("alice", "你能帮我订机票吗？", "L9_flight"), ("alice", "提醒我明天 9 点喝水。", "L9_personal"), ("alice", "帮我点外卖。", "L9_food"), ("alice", "帮我查一下茅台股价。", "L9_stock"), ("alice", "帮我约 Alex 教练明天 10 点。", "L9_shared"), ("alex", "我有哪些待确认的共享提醒？", "L9_alex_pending"), ("alex", "接受 Alice 刚才发来的教练提醒。", "L9_accept"), ("alice", "Alex 确认了吗？", "L9_status"), ("alice", "顺便帮我订酒店。", "L9_hotel"), ("alice", "我有哪些提醒？", "L9_list"), ("alice", "你能直接替我付款吗？", "L9_pay"), ("alice", "Alex 明天 10 点那条还在吗？", "L9_shared_status"), ("alice", "取消喝水提醒。", "L9_cancel"), ("alice", "再列出我的提醒和共享提醒。", "L9_final"), ("alice", "你刚才哪些事情不能做？", "L9_recap")]:
            ctx.step(speaker, text, note)

    def l9j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        alice, alex = ctx.accounts["alice"], ctx.accounts["alex"]
        text = _reply_text(ctx.turns)
        bad_claim = any(token in text for token in ("机票已订", "外卖已下单", "酒店已订", "付款成功", "股票价格是"))
        ok = bool(_shared_rows(after, alice, alex)) and len(_reminders_for(after, alice)) >= 1 and not bad_claim
        return _judge_result(ctx, before, after, expected="Unsupported asks refused without blocking supported reminder/shared-reminder flows", observed=f"shared_rows={len(_shared_rows(after, alice, alex))} reminders={len(_reminders_for(after, alice))} unsupported_claim={bad_claim}", ok=ok, bug_pattern="X6", mutation_expected=True, mutation_happened=bool(_shared_rows(after, alice, alex) or _reminders_for(after, alice)))

    results.append(_case_result("L9-capability-boundary-stretch", {"alice": "Alice Long", "alex": "Alex Long"}, transcript, l9, l9j, "L9 boundary"))

    def l10(ctx: CaseContext) -> None:
        _run_turns(ctx, "alice", ["你是谁？", "你能做什么？", "你今天忙吗？", "提醒我明天 8 点喝水。", "列出我的提醒。", "把喝水提醒改到明天 8 点半。", "你刚才说你能做什么？", "帮我订一张去上海的机票。", "取消喝水提醒。", "喝水提醒还在吗？", "再说一遍你能帮我处理哪些事。", "最后列出我的提醒。"], "L10")

    def l10j(ctx: CaseContext, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        text = _reply_text(ctx.turns)
        bad_claim = any(token in text for token in ("机票已订", "外卖已下单", "付款成功"))
        docs = _reminders_for(after, ctx.accounts["alice"])
        ok = len(docs) >= 1 and not _active_reminders(after, ctx.accounts["alice"]) and not bad_claim
        return _judge_result(ctx, before, after, expected="Persona remains consistent and reminder CRUD still works", observed=f"reminders={len(docs)} active={len(_active_reminders(after, ctx.accounts['alice']))} unsupported_claim={bad_claim}", ok=ok, bug_pattern="X7", mutation_expected=True, mutation_happened=bool(docs))

    results.append(_case_result("L10-persona-consistency", {"alice": "Alice Long"}, transcript, l10, l10j, "L10 persona"))
    return results


def _check_stack_health() -> None:
    bridge = requests.get(_config.bridge_base_url() + "/bridge/healthz", timeout=3)
    gateway = requests.get(_config.gateway_api_base_url() + "/health", timeout=3)
    if bridge.status_code != 200 or not bridge.json().get("ok"):
        raise BlockedSetup(f"bridge unhealthy status={bridge.status_code} body={bridge.text[:200]}")
    if gateway.status_code != 200 or not gateway.json().get("ok"):
        raise BlockedSetup(f"gateway unhealthy status={gateway.status_code} body={gateway.text[:200]}")


def _save_evidence(transcript: Transcript, results: list[dict[str, Any]], setup_status: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    findings = [result for result in results if result["verdict"] == "FINDING"]
    blocked = [result for result in results if str(result["verdict"]).startswith("BLOCKED")]
    transcript.set_verdict(passed=not findings and not blocked and setup_status == "PASSED", problems=[f"{item['case_id']}: {item['observed']}" for item in findings + blocked])
    payload = {
        "batch": BATCH,
        "batch_id": BATCH_ID,
        "account_batch": ACCOUNT_BATCH,
        "model": MODEL,
        "setup_status": setup_status,
        "accounts": transcript.accounts,
        "turns": [asdict(turn) for turn in transcript.turns],
        "cases": results,
        "summary": [{"case": result["case_id"], "verdict": result["verdict"], "bug_pattern": result.get("bug_pattern") or "", "observed": result.get("observed") or ""} for result in results],
        "verdict": transcript.verdict,
    }
    EVIDENCE_PATH.write_text(json.dumps(_clean(payload), ensure_ascii=False, indent=2, default=str))
    return EVIDENCE_PATH


def _print_summary(results: list[dict[str, Any]], evidence_path: Path) -> None:
    print("\n| case | verdict | bug_pattern | one-line observed |")
    print("| --- | --- | --- | --- |")
    for result in results:
        observed = str(result.get("observed") or "").replace("\n", " ")
        if len(observed) > 180:
            observed = observed[:177] + "..."
        print(f"| {result['case_id']} | {result['verdict']} | {result.get('bug_pattern') or ''} | {observed} |")
    print("\nEvidence paths:")
    print(f"- {evidence_path}")


def main() -> int:
    print(f"BATCH={BATCH}")
    transcript = Transcript(batch_id=BATCH_ID)
    setup_status = "PASSED"
    try:
        _check_stack_health()
        results = _run_cases(transcript)
    except Exception as exc:
        setup_status = "BLOCKED-SETUP"
        ctx = CaseContext("BLOCKED-SETUP", {}, transcript)
        results = [_result(ctx, {"mongo": {}, "postgres": {}}, {"mongo": {}, "postgres": {}}, verdict="BLOCKED", expected="Bridge and gateway healthy before L1-L10", observed=f"{type(exc).__name__}: {exc}", severity="smoke-infra")]
    path = _save_evidence(transcript, results, setup_status)
    _print_summary(results, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
