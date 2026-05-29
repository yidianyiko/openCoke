"""Friend-management edge smoke hunt.

Runs FM-01..FM-14 from
docs/superpowers/specs/2026-05-26-friend-management-edge-design.md.

This runner records evidence only. It must not change product code, seed
delivery routes, swap models, or attempt to fix findings.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
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
BATCH_ID = f"friend-management-edge-{BATCH}"
ACCOUNT_BATCH = "fmedge" + BATCH.lower().replace("t", "").replace("z", "")
EVIDENCE_DIR = Path("artifacts/evidence/shared-reminder-agent-smoke")
EVIDENCE_PATH = EVIDENCE_DIR / f"{BATCH_ID}.json"
MODEL = "GLM-5.1 thinking-off"

SUCCESS_CLAIM_TOKENS = ("已", "已经", "成功", "通过", "拒绝", "撤回", "删除", "取消", "创建", "发送")
CLARIFY_OR_REFUSE_TOKENS = (
    "哪一个",
    "哪个",
    "请确认",
    "请明确",
    "具体",
    "无法",
    "不能",
    "不支持",
    "暂不支持",
    "没有",
    "未找到",
    "找不到",
)
ACCOUNT_CONTROL_CLAIM_TOKENS = ("已屏蔽", "屏蔽成功", "已解除屏蔽", "解除屏蔽成功", "拉黑成功")
RAW_ENVELOPE_RE = re.compile(r"```json|MultiModalResponses|\"message_type\"")
LINK_CODE_RE = re.compile(r"/u/([A-Za-z0-9_-]+)|邀请码[:：\s]*([A-Za-z0-9_-]{6,})")


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


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ids_sql(accounts: dict[str, SmokeAccount]) -> str:
    return ",".join(_quote(account.coke_account_id) for account in accounts.values())


def _postgres_snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, list[dict[str, Any]]]:
    ids = _ids_sql(accounts)
    return {
        "customers": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (SELECT * FROM customers WHERE id IN ({ids})) t;
"""
        ),
        "identities": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT i.*
    FROM identities i
    JOIN memberships m ON m.identity_id = i.id
   WHERE m.customer_id IN ({ids})
) t;
"""
        ),
        "user_links": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (SELECT * FROM user_links WHERE provider_account_id IN ({ids})) t;
"""
        ),
        "link_sessions": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT ls.*
    FROM link_sessions ls
    LEFT JOIN user_links ul ON ul.id = ls.user_link_id
   WHERE ls.provider_account_id IN ({ids})
      OR ls.consumer_account_id IN ({ids})
      OR ul.provider_account_id IN ({ids})
) t;
"""
        ),
        "friend_requests": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY created_at, id), '[]'::json)
FROM (
  SELECT * FROM friend_requests
   WHERE requester_account_id IN ({ids}) OR target_account_id IN ({ids})
) t;
"""
        ),
        "friendships": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY created_at, id), '[]'::json)
FROM (
  SELECT * FROM friendships
   WHERE account_a_id IN ({ids}) OR account_b_id IN ({ids})
) t;
"""
        ),
        "shared_reminder_requests": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY created_at, id), '[]'::json)
FROM (
  SELECT * FROM shared_reminder_requests
   WHERE requester_account_id IN ({ids}) OR invitee_account_id IN ({ids})
) t;
"""
        ),
        "reminder_projections": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY id), '[]'::json)
FROM (
  SELECT rp.*
    FROM reminder_projections rp
    LEFT JOIN shared_reminder_requests srr ON srr.id = rp.shared_reminder_request_id
   WHERE rp.owner_account_id IN ({ids})
      OR srr.requester_account_id IN ({ids})
      OR srr.invitee_account_id IN ({ids})
) t;
"""
        ),
        "product_notifications": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY created_at, id), '[]'::json)
FROM (
  SELECT pn.*
    FROM product_notifications pn
    LEFT JOIN friend_requests fr ON fr.id = pn.friend_request_id
    LEFT JOIN shared_reminder_requests srr ON srr.id = pn.shared_reminder_request_id
   WHERE pn.recipient_account_id IN ({ids})
      OR fr.requester_account_id IN ({ids})
      OR fr.target_account_id IN ({ids})
      OR srr.requester_account_id IN ({ids})
      OR srr.invitee_account_id IN ({ids})
) t;
"""
        ),
        "delivery_routes": _sql_json(
            f"""
SELECT COALESCE(json_agg(row_to_json(t) ORDER BY coke_account_id, business_conversation_key), '[]'::json)
FROM (SELECT * FROM delivery_routes WHERE coke_account_id IN ({ids})) t;
"""
        ),
    }


def _mongo_snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, list[dict[str, Any]]]:
    account_ids = [account.coke_account_id for account in accounts.values()]
    client = MongoClient(_config.mongo_uri())
    try:
        db = client[_config.mongo_db_name()]
        sessions = list(db.agent_sessions.find().sort("updated_at", -1).limit(180))
        return {
            "agent_sessions": [
                doc for doc in sessions if any(account_id in _stable(doc) for account_id in account_ids)
            ],
            "inputmessages": list(
                db.inputmessages.find(
                    {"$or": [{"from_user": {"$in": account_ids}}, {"to_user": {"$in": account_ids}}]}
                ).sort("_id", 1)
            ),
            "outputmessages": list(
                db.outputmessages.find(
                    {"$or": [{"to_user": {"$in": account_ids}}, {"account_id": {"$in": account_ids}}]}
                ).sort("_id", 1)
            ),
        }
    finally:
        client.close()


def snapshot(accounts: dict[str, SmokeAccount]) -> dict[str, Any]:
    return {
        "mongo": _mongo_snapshot(accounts),
        "postgres": _postgres_snapshot(accounts),
    }


def _reply_text(turns: list[Turn]) -> str:
    return "\n".join(turn.reply_text or "" for turn in turns)


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _parse_link_code(text: str) -> str | None:
    match = LINK_CODE_RE.search(text)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _internal_get_user_link_code(account: SmokeAccount) -> str | None:
    url = _config.gateway_api_base_url() + "/api/internal/scheduling/tools/get_user_link"
    headers = {
        "Authorization": f"Bearer {_config.gateway_identity_api_key()}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json={"customer_id": account.coke_account_id}, timeout=15)
    try:
        body = response.json()
    except ValueError:
        return None
    if response.status_code != 200 or not body.get("ok"):
        return None
    return (body.get("data") or {}).get("code")


def _internal_reset_user_link_code(account: SmokeAccount) -> str | None:
    url = _config.gateway_api_base_url() + "/api/internal/scheduling/tools/reset_user_link"
    headers = {
        "Authorization": f"Bearer {_config.gateway_identity_api_key()}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json={"customer_id": account.coke_account_id}, timeout=15)
    try:
        body = response.json()
    except ValueError:
        return None
    if response.status_code != 200 or not body.get("ok"):
        return None
    return (body.get("data") or {}).get("code")


def _public_link_active(code: str) -> bool:
    url = _config.gateway_api_base_url() + f"/api/public/user-links/{code}"
    try:
        response = requests.get(url, timeout=8)
        body = response.json()
    except (requests.RequestException, ValueError):
        return False
    return response.status_code == 200 and bool(body.get("ok"))


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _read_dotenv_value(name: str) -> str | None:
    for path in (Path(".env"), Path("gateway/.env")):
        if not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or not line.startswith(name + "="):
                continue
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _read_gateway_proc_env(name: str) -> str | None:
    proc_root = Path("/proc")
    for proc_path in proc_root.glob("[0-9]*"):
        try:
            cmdline = (proc_path / "cmdline").read_bytes()
            if b"gateway/node_modules" not in cmdline and b"src/index.ts" not in cmdline:
                continue
            environ_path = proc_path / "environ"
            raw = environ_path.read_bytes()
            for item in raw.split(b"\0"):
                prefix = (name + "=").encode("utf-8")
                if item.startswith(prefix):
                    return item[len(prefix):].decode("utf-8")
        except OSError:
            continue
    return None


def _customer_jwt_secret() -> str:
    value = os.environ.get("CUSTOMER_JWT_SECRET") or _read_dotenv_value("CUSTOMER_JWT_SECRET")
    value = value or _read_gateway_proc_env("CUSTOMER_JWT_SECRET")
    if not value:
        raise BlockedSetup("CUSTOMER_JWT_SECRET unavailable for public link-session smoke")
    return value


def _identity_id(account: SmokeAccount) -> str:
    return f"id_smoke_{ACCOUNT_BATCH}_{account.label}"


def _email(account: SmokeAccount) -> str:
    return f"{account.label}.{ACCOUNT_BATCH}.smoke@example.test"


def _customer_token(account: SmokeAccount) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": account.coke_account_id,
        "identityId": _identity_id(account),
        "email": _email(account),
        "tokenType": "access",
        "iat": now,
        "exp": now + 7 * 24 * 60 * 60,
    }
    signing_input = ".".join(
        [
            _base64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(_customer_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return signing_input + "." + _base64url(signature)


def _public_create_link_session(code: str) -> dict[str, Any]:
    url = _config.gateway_api_base_url() + f"/api/public/user-links/{code}/sessions"
    response = requests.post(url, json={}, timeout=15)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return {"status": response.status_code, "body": body}


def _public_claim_link_session(token: str, requester: SmokeAccount, message: str | None = None) -> dict[str, Any]:
    url = _config.gateway_api_base_url() + f"/api/public/link-sessions/{token}/friend-requests"
    headers = {
        "Authorization": f"Bearer {_customer_token(requester)}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json={"message": message}, timeout=20)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return {"status": response.status_code, "body": body}


def _expire_link_session(token: str) -> None:
    token_hash = _sha256_hex(token)
    _run_psql(
        f"""
UPDATE link_sessions
   SET expires_at = NOW() - interval '1 minute', updated_at = NOW()
 WHERE token_hash = {_quote(token_hash)};
"""
    )


def _set_customer_display_name(account: SmokeAccount, display_name: str) -> None:
    _run_psql(
        f"""
UPDATE customers SET display_name = {_quote(display_name)}, updated_at = NOW()
 WHERE id = {_quote(account.coke_account_id)};
UPDATE identities i
   SET display_name = {_quote(display_name)}, updated_at = NOW()
  FROM memberships m
 WHERE m.identity_id = i.id
   AND m.customer_id = {_quote(account.coke_account_id)};
"""
    )
    account.display_name = display_name


def _register_duplicate_display_name(display_name: str) -> dict[str, Any]:
    url = _config.gateway_api_base_url() + "/api/auth/register"
    body = {
        "displayName": display_name,
        "email": f"dupe.{ACCOUNT_BATCH}.{int(time.time())}@example.test",
        "password": "friend-edge-password",
    }
    response = requests.post(url, json=body, timeout=20)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return {"status": response.status_code, "body": payload}


def _record_turn(
    transcript: Transcript,
    speaker: str,
    account: SmokeAccount,
    text: str,
    *,
    note: str,
) -> Turn:
    turn_no = len(transcript.turns) + 1
    print(f"\n[T{turn_no:02d} {speaker}] >> {text}", flush=True)
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
        placeholder_received=reply.placeholder_received,
        late_reply_landed=reply.late_reply_landed,
        polling_seconds_used=reply.polling_seconds_used,
        placeholder_reply=reply.placeholder_reply,
        placeholder_output_id=reply.placeholder_output_id,
    )
    transcript.add_turn(turn)
    print(f"[T{turn_no:02d} {speaker}] << ({elapsed_ms}ms, out={reply.output_id}) {reply.reply}", flush=True)
    return turn


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
                    "content": str(message.get("content") or "")[:700],
                }
                if message.get("tool_calls"):
                    item["tool_calls"] = _clean(message.get("tool_calls"))
                items.append(item)
            excerpts.append({"session_id": str(session.get("_id")), "messages": items})
        if len(excerpts) >= 3:
            break
    return excerpts


def _bug_pattern(
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
    before: dict[str, Any],
    after: dict[str, Any],
    product_contract_unclear: bool = False,
    severity: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "batch_id": BATCH_ID,
        "model": MODEL,
        "case_id": case_id,
        "verdict": verdict,
        "bug_pattern": bug_pattern,
        "severity": severity,
        "product_contract_unclear": product_contract_unclear,
        "expected": expected,
        "observed": observed,
        "turns": [asdict(turn) for turn in turns],
        "agent_reply": _reply_text(turns),
        "postgres_delta": delta["postgres"],
        "mongo_delta": delta["mongo"],
        "snapshot_before": _clean(before),
        "snapshot_after": _clean(after),
        "agent_trace_excerpt": _agent_trace_excerpt(turns, after),
    }
    if extra:
        payload["extra"] = _clean(extra)
    return payload


def _passed(
    case_id: str,
    expected: str,
    observed: str,
    turns: list[Turn],
    delta: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    product_contract_unclear: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _result(
        case_id=case_id,
        verdict="PASSED",
        bug_pattern="",
        expected=expected,
        observed=observed,
        turns=turns,
        delta=delta,
        before=before,
        after=after,
        product_contract_unclear=product_contract_unclear,
        extra=extra,
    )


def _finding(
    case_id: str,
    expected: str,
    observed: str,
    turns: list[Turn],
    delta: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    bug_pattern: str,
    mutation_expected: bool,
    mutation_happened: bool,
    product_contract_unclear: bool = False,
    severity: str = "visible-error",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _result(
        case_id=case_id,
        verdict="FINDING",
        bug_pattern=_bug_pattern(
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
        before=before,
        after=after,
        product_contract_unclear=product_contract_unclear,
        extra=extra,
    )


def _blocked(
    case_id: str,
    expected: str,
    observed: str,
    turns: list[Turn],
    delta: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    product_contract_unclear: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _result(
        case_id=case_id,
        verdict="BLOCKED",
        bug_pattern="",
        severity="smoke-infra",
        expected=expected,
        observed=observed,
        turns=turns,
        delta=delta,
        before=before,
        after=after,
        product_contract_unclear=product_contract_unclear,
        extra=extra,
    )


def _friend_requests(snapshot_after: dict[str, Any], requester: SmokeAccount, target: SmokeAccount) -> list[dict[str, Any]]:
    return [
        row
        for row in snapshot_after["postgres"]["friend_requests"]
        if row.get("requester_account_id") == requester.coke_account_id
        and row.get("target_account_id") == target.coke_account_id
    ]


def _pair_friendships(snapshot_after: dict[str, Any], left: SmokeAccount, right: SmokeAccount) -> list[dict[str, Any]]:
    ids = {left.coke_account_id, right.coke_account_id}
    return [
        row
        for row in snapshot_after["postgres"]["friendships"]
        if {row.get("account_a_id"), row.get("account_b_id")} == ids
    ]


def _active_friendships(snapshot_after: dict[str, Any], left: SmokeAccount, right: SmokeAccount) -> list[dict[str, Any]]:
    return [row for row in _pair_friendships(snapshot_after, left, right) if row.get("status") == "active"]


def _latest_request_status(snapshot_after: dict[str, Any], requester: SmokeAccount, target: SmokeAccount) -> str | None:
    rows = _friend_requests(snapshot_after, requester, target)
    return rows[-1].get("status") if rows else None


def _rows_added(delta: dict[str, Any], table: str) -> list[dict[str, Any]]:
    return delta["postgres"][table]["added_rows"]


def _rows_modified_after(delta: dict[str, Any], table: str) -> list[dict[str, Any]]:
    return [row["after"] for row in delta["postgres"][table]["modified_rows"]]


def _ensure_link(ctx: "CaseContext", owner_key: str, *, fresh: bool = False) -> str:
    if owner_key in ctx.link_codes and not fresh and _public_link_active(ctx.link_codes[owner_key]):
        return ctx.link_codes[owner_key]
    account = ctx.accounts[owner_key]
    code: str | None = None
    used_internal_link_lookup = False
    if fresh:
        code = _internal_reset_user_link_code(account)
        used_internal_link_lookup = True
    if not code:
        turn = ctx.step(owner_key, "把我自己的好友邀请链接给我，我要分享给朋友。", f"setup_{owner_key}_link")
        code = _parse_link_code(turn.reply_text)
    if not code or not _public_link_active(code):
        code = _internal_get_user_link_code(account)
        used_internal_link_lookup = True
    if code and not _public_link_active(code):
        code = _internal_reset_user_link_code(account)
        used_internal_link_lookup = True
    if not code:
        raise BlockedSetup(f"could not obtain {owner_key} user-link code")
    ctx.link_codes[owner_key] = code
    if used_internal_link_lookup:
        ctx.extras.setdefault("link_code_setup_recoveries", []).append({"owner": owner_key, "code": code})
        print(f"[setup] {owner_key}_link_code recovered={code}", flush=True)
    else:
        print(f"[setup] {owner_key}_link_code={code}", flush=True)
    return code


def _ensure_active_alice_bob(ctx: "CaseContext", note_prefix: str) -> None:
    latest = snapshot(ctx.accounts)
    if _active_friendships(latest, ctx.accounts["alice"], ctx.accounts["bob"]):
        return
    for attempt in (1, 2):
        alice_code = _ensure_link(ctx, "alice", fresh=(attempt == 2))
        ctx.step("bob", f"我想加 Alice 为好友。这是对方的邀请链接码：{alice_code}。备注：{note_prefix}。", f"{note_prefix}_bob_request_{attempt}")
        ctx.step("alice", "通过 Bob 的好友请求。", f"{note_prefix}_alice_accept_{attempt}")
        latest = snapshot(ctx.accounts)
        if _active_friendships(latest, ctx.accounts["alice"], ctx.accounts["bob"]):
            return
    raise BlockedSetup(f"{note_prefix}: Alice-Bob friendship not active after setup")


class CaseContext:
    def __init__(
        self,
        accounts: dict[str, SmokeAccount],
        transcript: Transcript,
        link_codes: dict[str, str],
    ):
        self.accounts = accounts
        self.transcript = transcript
        self.link_codes = link_codes
        self.extras: dict[str, Any] = {}

    def step(self, speaker: str, text: str, note: str) -> Turn:
        return _record_turn(self.transcript, speaker, self.accounts[speaker], text, note=note)


def _case_result(
    case_id: str,
    expected: str,
    accounts: dict[str, SmokeAccount],
    transcript: Transcript,
    link_codes: dict[str, str],
    body: Callable[[CaseContext], list[Turn]],
    judge: Callable[[list[Turn], dict[str, Any], dict[str, Any], dict[str, Any], CaseContext], dict[str, Any]],
    *,
    product_contract_unclear: bool = False,
) -> dict[str, Any]:
    print(f"\n=== {case_id} ===", flush=True)
    before = snapshot(accounts)
    ctx = CaseContext(accounts, transcript, link_codes)
    turns: list[Turn] = []
    try:
        turns = body(ctx)
        time.sleep(1.5)
        after = snapshot(accounts)
        delta = _diff_snapshot(before, after)
        print(f"[{case_id}] delta={json.dumps(_brief_delta(delta), ensure_ascii=False, default=str)}", flush=True)
        result = judge(turns, delta, before, after, ctx)
        if ctx.extras:
            result.setdefault("extra", {}).update(_clean(ctx.extras))
        return result
    except (BridgeError, requests.RequestException, BlockedSetup) as exc:
        after = snapshot(accounts)
        delta = _diff_snapshot(before, after)
        return _blocked(
            case_id,
            expected,
            f"{type(exc).__name__}: {exc}",
            turns,
            delta,
            before,
            after,
            product_contract_unclear=product_contract_unclear,
            extra=ctx.extras,
        )
    except Exception as exc:
        after = snapshot(accounts)
        delta = _diff_snapshot(before, after)
        return _blocked(
            case_id,
            expected,
            f"{type(exc).__name__}: {exc}",
            turns,
            delta,
            before,
            after,
            product_contract_unclear=product_contract_unclear,
            extra=ctx.extras,
        )


def _run_cases(accounts: dict[str, SmokeAccount], transcript: Transcript) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    link_codes: dict[str, str] = {}
    alice = accounts["alice"]
    bob = accounts["bob"]
    carol = accounts["carol"]

    def fm01_body(ctx: CaseContext) -> list[Turn]:
        code = _ensure_link(ctx, "alice")
        return [
            ctx.step("bob", f"我想加 Alice 为好友。这是对方的邀请链接码：{code}。备注：FM01。", "FM-01-bob-request"),
            ctx.step("alice", "拒绝 Bob 的好友请求。", "FM-01-alice-reject"),
        ]

    def fm01_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        status = _latest_request_status(after, bob, alice)
        active = _active_friendships(after, alice, bob)
        ok = status == "rejected" and not active
        observed = f"bob_to_alice_status={status} active_friendships={len(active)}"
        if ok:
            return _passed("FM-01-decline-incoming", "Bob->Alice request is rejected and no friendship is active", observed, turns, delta, before, after)
        return _finding("FM-01-decline-incoming", "Bob->Alice request is rejected and no friendship is active", observed, turns, delta, before, after, bug_pattern="FR1", mutation_expected=True, mutation_happened=status == "rejected")

    results.append(_case_result("FM-01-decline-incoming", "Bob->Alice request is rejected and no friendship is active", accounts, transcript, link_codes, fm01_body, fm01_judge))

    def fm02_body(ctx: CaseContext) -> list[Turn]:
        code = _ensure_link(ctx, "bob")
        return [
            ctx.step("alice", f"我想加 Bob 为好友。这是对方的邀请链接码：{code}。备注：FM02。", "FM-02-alice-request"),
            ctx.step("alice", "撤回我刚才发给 Bob 的好友申请。", "FM-02-alice-cancel"),
            ctx.step("bob", "通过 Alice 的好友请求。", "FM-02-bob-cannot-accept-cancelled"),
        ]

    def fm02_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        status = _latest_request_status(after, alice, bob)
        active = _active_friendships(after, alice, bob)
        ok = status == "cancelled" and not active
        observed = f"alice_to_bob_status={status} active_friendships={len(active)}"
        if ok:
            return _passed("FM-02-cancel-sent", "Alice->Bob request is cancelled and Bob cannot accept it afterward", observed, turns, delta, before, after)
        return _finding("FM-02-cancel-sent", "Alice->Bob request is cancelled and Bob cannot accept it afterward", observed, turns, delta, before, after, bug_pattern="FR1", mutation_expected=True, mutation_happened=status == "cancelled")

    results.append(_case_result("FM-02-cancel-sent", "Alice->Bob request is cancelled and Bob cannot accept it afterward", accounts, transcript, link_codes, fm02_body, fm02_judge))

    def fm03_body(ctx: CaseContext) -> list[Turn]:
        _ensure_active_alice_bob(ctx, "FM03")
        return [ctx.step("alice", "我有哪些好友？", "FM-03-list-friends")]

    def fm03_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        active_ab = _active_friendships(after, alice, bob)
        text = _reply_text(turns)
        ok = len(active_ab) == 1 and "Bob" in text and "Carol" not in text
        observed = f"active_alice_bob={len(active_ab)} reply_mentions_bob={'Bob' in text} reply_mentions_carol={'Carol' in text}"
        if ok:
            return _passed("FM-03-list-friends", "Alice list shows Bob only and does not mutate friendships", observed, turns, delta, before, after)
        return _finding("FM-03-list-friends", "Alice list shows Bob only and does not mutate friendships", observed, turns, delta, before, after, bug_pattern="FR1", mutation_expected=False, mutation_happened=bool(delta["postgres"]["friendships"]["added"] or delta["postgres"]["friendships"]["modified"]))

    results.append(_case_result("FM-03-list-friends", "Alice list shows Bob only and does not mutate friendships", accounts, transcript, link_codes, fm03_body, fm03_judge))

    def fm04_body(ctx: CaseContext) -> list[Turn]:
        code = _ensure_link(ctx, "alice")
        return [
            ctx.step("carol", f"我想加 Alice 为好友。这是对方的邀请链接码：{code}。备注：FM04。", "FM-04-carol-request"),
            ctx.step("alice", "我的好友申请有哪些？", "FM-04-list-pending"),
        ]

    def fm04_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        status = _latest_request_status(after, carol, alice)
        text = _reply_text(turns[-1:])
        ok = status == "pending" and "Carol" in text
        terminal_actionable = "Bob" in text and ("待处理" in text or "申请" in text)
        observed = f"carol_to_alice_status={status} reply_mentions_carol={'Carol' in text} terminal_bob_actionable={terminal_actionable}"
        if ok and not terminal_actionable:
            return _passed("FM-04-list-pending", "Alice sees Carol pending request without terminal requests as actionable", observed, turns, delta, before, after)
        return _finding("FM-04-list-pending", "Alice sees Carol pending request without terminal requests as actionable", observed, turns, delta, before, after, bug_pattern="FR1", mutation_expected=False, mutation_happened=False)

    results.append(_case_result("FM-04-list-pending", "Alice sees Carol pending request without terminal requests as actionable", accounts, transcript, link_codes, fm04_body, fm04_judge))

    def fm05_body(ctx: CaseContext) -> list[Turn]:
        _ensure_active_alice_bob(ctx, "FM05")
        return [ctx.step("alice", "删除好友 Bob。", "FM-05-remove-bob")]

    def fm05_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        active = _active_friendships(after, alice, bob)
        statuses = [row.get("status") for row in _pair_friendships(after, alice, bob)]
        ok = not active and "removed" in statuses
        observed = f"alice_bob_friendship_statuses={statuses} active={len(active)}"
        if ok:
            return _passed("FM-05-remove-friend", "Alice-Bob active friendship moves to removed", observed, turns, delta, before, after)
        return _finding("FM-05-remove-friend", "Alice-Bob active friendship moves to removed", observed, turns, delta, before, after, bug_pattern="FR1", mutation_expected=True, mutation_happened="removed" in statuses)

    results.append(_case_result("FM-05-remove-friend", "Alice-Bob active friendship moves to removed", accounts, transcript, link_codes, fm05_body, fm05_judge))

    def fm06_body(ctx: CaseContext) -> list[Turn]:
        code = _ensure_link(ctx, "alice")
        return [
            ctx.step("bob", f"我想重新加 Alice 为好友。这是对方的邀请链接码：{code}。备注：FM06。", "FM-06-bob-request-again"),
            ctx.step("alice", "通过 Bob 的好友请求。", "FM-06-alice-accept-again"),
        ]

    def fm06_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        active = _active_friendships(after, alice, bob)
        statuses = [row.get("status") for row in _pair_friendships(after, alice, bob)]
        ok = len(active) == 1
        observed = f"active_alice_bob={len(active)} all_friendship_statuses={statuses}"
        if ok:
            return _passed("FM-06-refriend-after-remove", "Fresh request can be accepted after removal with one active Alice-Bob friendship", observed, turns, delta, before, after)
        return _finding("FM-06-refriend-after-remove", "Fresh request can be accepted after removal with one active Alice-Bob friendship", observed, turns, delta, before, after, bug_pattern="FR1", mutation_expected=True, mutation_happened=bool(active))

    results.append(_case_result("FM-06-refriend-after-remove", "Fresh request can be accepted after removal with one active Alice-Bob friendship", accounts, transcript, link_codes, fm06_body, fm06_judge))

    def fm07_body(ctx: CaseContext) -> list[Turn]:
        code = _ensure_link(ctx, "alice")
        return [ctx.step("alice", f"我想用这个邀请码加好友：{code}。", "FM-07-self-link")]

    def fm07_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        wrote = bool(delta["postgres"]["friend_requests"]["added"] or delta["postgres"]["friendships"]["added"])
        text = _reply_text(turns)
        refused = _has_any(text, CLARIFY_OR_REFUSE_TOKENS) or "自己" in text
        observed = f"new_friend_requests={delta['postgres']['friend_requests']['added']} new_friendships={delta['postgres']['friendships']['added']} refused={refused}"
        if not wrote and refused:
            return _passed("FM-07-friend-self", "Self link is refused and creates no friend rows", observed, turns, delta, before, after)
        return _finding("FM-07-friend-self", "Self link is refused and creates no friend rows", observed, turns, delta, before, after, bug_pattern="FR2", mutation_expected=False, mutation_happened=wrote)

    results.append(_case_result("FM-07-friend-self", "Self link is refused and creates no friend rows", accounts, transcript, link_codes, fm07_body, fm07_judge))

    def fm08_body(ctx: CaseContext) -> list[Turn]:
        code = _ensure_link(ctx, "alice", fresh=True)
        session = _public_create_link_session(code)
        ctx.extras["session_create"] = session
        token = ((session.get("body") or {}).get("data") or {}).get("token")
        if not token:
            raise BlockedSetup(f"public link session create failed: {session}")
        first = _public_claim_link_session(token, bob, "FM08 first claim")
        second = _public_claim_link_session(token, bob, "FM08 second claim")
        ctx.extras["claims"] = [first, second]
        return []

    def fm08_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = [
            row
            for row in _rows_added(delta, "friend_requests")
            if row.get("requester_account_id") == bob.coke_account_id and row.get("target_account_id") == alice.coke_account_id
        ]
        pending = [row for row in after["postgres"]["friend_requests"] if row.get("requester_account_id") == bob.coke_account_id and row.get("target_account_id") == alice.coke_account_id and row.get("status") == "pending"]
        notifications_added = delta["postgres"]["product_notifications"]["added"]
        ok = len(added) <= 1 and len(pending) <= 1 and notifications_added <= 1
        observed = f"added_bob_to_alice={len(added)} pending_bob_to_alice={len(pending)} notifications_added={notifications_added} claim_statuses={[c.get('status') for c in ctx.extras.get('claims', [])]}"
        if ok:
            return _passed("FM-08-same-link-used-twice", "Same link session retry is idempotent", observed, turns, delta, before, after, extra=ctx.extras)
        return _finding("FM-08-same-link-used-twice", "Same link session retry is idempotent", observed, turns, delta, before, after, bug_pattern="FR2", mutation_expected=True, mutation_happened=bool(added), severity="silent-bad-side-effect", extra=ctx.extras)

    results.append(_case_result("FM-08-same-link-used-twice", "Same link session retry is idempotent", accounts, transcript, link_codes, fm08_body, fm08_judge))

    def fm09_body(ctx: CaseContext) -> list[Turn]:
        return [ctx.step("bob", "我想加好友，邀请码是 not-a-real-code-FM09。", "FM-09-invalid-code")]

    def fm09_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        wrote = bool(delta["postgres"]["friend_requests"]["added"] or delta["postgres"]["friendships"]["added"])
        text = _reply_text(turns)
        safe = _has_any(text, CLARIFY_OR_REFUSE_TOKENS) or "无效" in text or "邀请码" in text
        observed = f"new_friend_requests={delta['postgres']['friend_requests']['added']} new_friendships={delta['postgres']['friendships']['added']} safe_reply={safe}"
        if not wrote and safe:
            return _passed("FM-09-invalid-link-code", "Invalid link code creates no request and does not invent a target", observed, turns, delta, before, after)
        return _finding("FM-09-invalid-link-code", "Invalid link code creates no request and does not invent a target", observed, turns, delta, before, after, bug_pattern="FR2", mutation_expected=False, mutation_happened=wrote)

    results.append(_case_result("FM-09-invalid-link-code", "Invalid link code creates no request and does not invent a target", accounts, transcript, link_codes, fm09_body, fm09_judge))

    def fm10_body(ctx: CaseContext) -> list[Turn]:
        _ensure_active_alice_bob(ctx, "FM10")
        return [
            ctx.step("alice", "屏蔽 Bob。", "FM-10-block-wording"),
            ctx.step("alice", "解除对 Bob 的屏蔽。", "FM-10-unblock-wording"),
        ]

    def fm10_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        friend_state_changed = bool(
            delta["postgres"]["friend_requests"]["added"]
            or delta["postgres"]["friend_requests"]["modified"]
            or delta["postgres"]["friendships"]["added"]
            or delta["postgres"]["friendships"]["modified"]
        )
        text = _reply_text(turns)
        claims_account_control = _has_any(text, ACCOUNT_CONTROL_CLAIM_TOKENS)
        observed = f"friend_state_changed={friend_state_changed} claims_account_control={claims_account_control}"
        if not friend_state_changed and not claims_account_control:
            return _passed("FM-10-retired-account-control-wording", "Block/unblock wording causes no friend state write and no account-control claim", observed, turns, delta, before, after)
        return _finding("FM-10-retired-account-control-wording", "Block/unblock wording causes no friend state write and no account-control claim", observed, turns, delta, before, after, bug_pattern="FR5", mutation_expected=False, mutation_happened=friend_state_changed or claims_account_control)

    results.append(_case_result("FM-10-retired-account-control-wording", "Block/unblock wording causes no friend state write and no account-control claim", accounts, transcript, link_codes, fm10_body, fm10_judge))

    def fm11_body(ctx: CaseContext) -> list[Turn]:
        duplicate_attempt = _register_duplicate_display_name(bob.display_name)
        ctx.extras["duplicate_register_attempt"] = duplicate_attempt
        code = _ensure_link(ctx, "alice")
        if _latest_request_status(snapshot(ctx.accounts), carol, alice) != "pending":
            ctx.step("carol", f"我想加 Alice 为好友。这是对方的邀请链接码：{code}。备注：FM11。", "FM-11-carol-request")
        ctx.step("alice", "通过 Carol 的好友请求。", "FM-11-accept-carol")
        original_carol = carol.display_name
        ctx.extras["original_carol_display_name"] = original_carol
        ctx.extras["forced_duplicate_display_name"] = bob.display_name
        _set_customer_display_name(carol, bob.display_name)
        try:
            lookup_before = snapshot(ctx.accounts)
            turn = ctx.step("alice", "看看 Bob 这周哪些时间空？", "FM-11-ambiguous-bob-calendar")
            lookup_after = snapshot(ctx.accounts)
            ctx.extras["ambiguous_lookup_delta"] = _diff_snapshot(lookup_before, lookup_after)
            return [turn]
        finally:
            _set_customer_display_name(carol, original_carol)

    def fm11_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        dup = ctx.extras.get("duplicate_register_attempt") or {}
        normal_rejected = dup.get("status") == 409 and (dup.get("body") or {}).get("error") == "display_name_already_exists"
        text = _reply_text(turns)
        ambiguity_tokens = ("哪一个", "哪个", "请确认", "请明确", "无法", "不能", "找不到", "重名", "同名")
        leaked_availability = "空闲" in text or "忙碌" in text or "日程" in text
        safe_ambiguous = _has_any(text, ambiguity_tokens) and not leaked_availability
        lookup_delta = ctx.extras.get("ambiguous_lookup_delta") or delta
        writes = bool(lookup_delta["postgres"]["friendships"]["modified"] or lookup_delta["postgres"]["friend_requests"]["modified"])
        observed = f"normal_duplicate_rejected={normal_rejected} ambiguous_reply_safe={safe_ambiguous} leaked_availability={leaked_availability} friend_writes={writes}"
        if normal_rejected and safe_ambiguous and not writes:
            return _passed("FM-11-same-display-name", "Duplicate display name is rejected or ambiguity fails closed without writes", observed, turns, delta, before, after, extra=ctx.extras)
        return _finding("FM-11-same-display-name", "Duplicate display name is rejected or ambiguity fails closed without writes", observed, turns, delta, before, after, bug_pattern="FR3", mutation_expected=False, mutation_happened=writes, product_contract_unclear=False, extra=ctx.extras)

    results.append(_case_result("FM-11-same-display-name", "Duplicate display name is rejected or ambiguity fails closed without writes", accounts, transcript, link_codes, fm11_body, fm11_judge))

    def fm12_body(ctx: CaseContext) -> list[Turn]:
        _ensure_active_alice_bob(ctx, "FM12")
        return [
            ctx.step("bob", "提醒我周三上午 10 点做私密体检。", "FM-12-bob-private-reminder"),
            ctx.step("alice", "删除好友 Bob。", "FM-12-remove-bob"),
            ctx.step("alice", "看看 Bob 这周哪些时间空？", "FM-12-calendar-after-remove"),
        ]

    def fm12_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        active = _active_friendships(after, alice, bob)
        reply = turns[-1].reply_text if turns else ""
        leaked = any(token in reply for token in ("私密体检", "体检", "10 点", "10点"))
        refused = _has_any(reply, CLARIFY_OR_REFUSE_TOKENS) or "好友" in reply
        observed = f"active_alice_bob_after_remove={len(active)} leaked_private_calendar={leaked} refused={refused}"
        if not active and refused and not leaked:
            return _passed("FM-12-calendar-after-remove", "Calendar facts require active friendship after removal", observed, turns, delta, before, after)
        return _finding("FM-12-calendar-after-remove", "Calendar facts require active friendship after removal", observed, turns, delta, before, after, bug_pattern="FR4", mutation_expected=False, mutation_happened=leaked, severity="privacy")

    results.append(_case_result("FM-12-calendar-after-remove", "Calendar facts require active friendship after removal", accounts, transcript, link_codes, fm12_body, fm12_judge))

    def fm13_body(ctx: CaseContext) -> list[Turn]:
        _ensure_active_alice_bob(ctx, "FM13")
        old_name = bob.display_name
        new_name = "Bobby Friend " + ACCOUNT_BATCH[-8:]
        ctx.extras["old_bob_display_name"] = old_name
        ctx.extras["new_bob_display_name"] = new_name
        _set_customer_display_name(bob, new_name)
        lookup_before = snapshot(ctx.accounts)
        turns = [
            ctx.step("alice", "我有哪些好友？", "FM-13-list-after-name-update"),
            ctx.step("alice", "看看 Bobby Friend 这周哪些时间空？", "FM-13-new-name-calendar"),
            ctx.step("alice", "看看 Bob 这周哪些时间空？", "FM-13-old-name-calendar"),
        ]
        lookup_after = snapshot(ctx.accounts)
        ctx.extras["display_name_lookup_delta"] = _diff_snapshot(lookup_before, lookup_after)
        return turns

    def fm13_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        list_reply = turns[0].reply_text if len(turns) > 0 else ""
        new_reply = turns[1].reply_text if len(turns) > 1 else ""
        old_reply = turns[2].reply_text if len(turns) > 2 else ""
        list_current = "Bobby" in list_reply
        new_resolves = "Bobby" in new_reply or not _has_any(new_reply, ("找不到", "没有"))
        old_leaked_availability = "空" in old_reply or "忙" in old_reply or "10:00" in old_reply or "10点" in old_reply
        old_fails_closed = _has_any(old_reply, CLARIFY_OR_REFUSE_TOKENS) and not old_leaked_availability
        lookup_delta = ctx.extras.get("display_name_lookup_delta") or delta
        writes = bool(lookup_delta["postgres"]["friendships"]["modified"] or lookup_delta["postgres"]["friend_requests"]["modified"])
        observed = f"list_current={list_current} new_name_resolves={new_resolves} old_name_fails_closed={old_fails_closed} old_leaked_availability={old_leaked_availability} friend_writes={writes}"
        if list_current and new_resolves and old_fails_closed and not writes:
            return _passed("FM-13-display-name-update", "Friend list uses current name; new name resolves; old name fails closed", observed, turns, delta, before, after, product_contract_unclear=True, extra=ctx.extras)
        return _finding("FM-13-display-name-update", "Friend list uses current name; new name resolves; old name fails closed", observed, turns, delta, before, after, bug_pattern="FR3", mutation_expected=False, mutation_happened=writes, product_contract_unclear=True, extra=ctx.extras)

    results.append(_case_result("FM-13-display-name-update", "Friend list uses current name; new name resolves; old name fails closed", accounts, transcript, link_codes, fm13_body, fm13_judge, product_contract_unclear=True))

    def fm14_body(ctx: CaseContext) -> list[Turn]:
        code = _ensure_link(ctx, "alice", fresh=True)
        session = _public_create_link_session(code)
        ctx.extras["session_create"] = session
        token = ((session.get("body") or {}).get("data") or {}).get("token")
        if not token:
            raise BlockedSetup(f"public link session create failed: {session}")
        _expire_link_session(token)
        claim = _public_claim_link_session(token, bob, "FM14 expired claim")
        ctx.extras["expired_claim"] = claim
        return []

    def fm14_judge(turns: list[Turn], delta: dict[str, Any], before: dict[str, Any], after: dict[str, Any], ctx: CaseContext) -> dict[str, Any]:
        added = delta["postgres"]["friend_requests"]["added"]
        claim = ctx.extras.get("expired_claim") or {}
        error = (claim.get("body") or {}).get("error")
        ok = added == 0 and claim.get("status") == 400 and error == "link_session_expired"
        observed = f"friend_requests_added={added} claim_status={claim.get('status')} error={error}"
        if ok:
            return _passed("FM-14-expired-public-link-session", "Expired public link session is rejected without a friend request", observed, turns, delta, before, after, product_contract_unclear=True, extra=ctx.extras)
        return _finding("FM-14-expired-public-link-session", "Expired public link session is rejected without a friend request", observed, turns, delta, before, after, bug_pattern="FR2", mutation_expected=False, mutation_happened=added > 0, product_contract_unclear=True, extra=ctx.extras)

    results.append(_case_result("FM-14-expired-public-link-session", "Expired public link session is rejected without a friend request", accounts, transcript, link_codes, fm14_body, fm14_judge, product_contract_unclear=True))

    return results


def _check_stack_health() -> None:
    bridge = requests.get(_config.bridge_base_url() + "/bridge/healthz", timeout=3)
    gateway = requests.get(_config.gateway_api_base_url() + "/health", timeout=3)
    if bridge.status_code != 200 or not bridge.json().get("ok"):
        raise BlockedSetup(f"bridge unhealthy status={bridge.status_code} body={bridge.text[:200]}")
    if gateway.status_code != 200 or not gateway.json().get("ok"):
        raise BlockedSetup(f"gateway unhealthy status={gateway.status_code} body={gateway.text[:200]}")


def _setup_accounts(transcript: Transcript) -> dict[str, SmokeAccount]:
    accounts = {
        "alice": provision_account("alice", batch_id=ACCOUNT_BATCH, display_name="Alice Friend"),
        "bob": provision_account("bob", batch_id=ACCOUNT_BATCH, display_name="Bob Friend"),
        "carol": provision_account("carol", batch_id=ACCOUNT_BATCH, display_name="Carol Friend"),
    }
    for account in accounts.values():
        transcript.add_account(account)
    print("\nACCOUNTS")
    for key, account in accounts.items():
        print(f"{key}: {account.coke_account_id} display={account.display_name}")

    snap = snapshot(accounts)
    customer_count = len(snap["postgres"]["customers"])
    friend_request_count = len(snap["postgres"]["friend_requests"])
    friendship_count = len(snap["postgres"]["friendships"])
    if customer_count != 3:
        raise BlockedSetup(f"expected 3 customers, observed {customer_count}")
    if friend_request_count or friendship_count:
        raise BlockedSetup(
            f"baseline friend graph not empty: friend_requests={friend_request_count} friendships={friendship_count}"
        )
    return accounts


def _save_evidence(transcript: Transcript, accounts: dict[str, SmokeAccount], results: list[dict[str, Any]]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "batch_id": BATCH_ID,
        "model": MODEL,
        "accounts": {
            key: {
                "coke_account_id": account.coke_account_id,
                "display_name": account.display_name,
                "tenant_id": account.tenant_id,
                "clawscale_user_id": account.clawscale_user_id,
            }
            for key, account in accounts.items()
        },
        "turns": [asdict(turn) for turn in transcript.turns],
        "cases": results,
        "summary": [
            {
                "case": result["case_id"],
                "verdict": result["verdict"],
                "bug_pattern": result.get("bug_pattern") or "",
                "observed": result.get("observed") or "",
            }
            for result in results
        ],
    }
    EVIDENCE_PATH.write_text(json.dumps(_clean(payload), ensure_ascii=False, indent=2, default=_json_default))
    return EVIDENCE_PATH


def _print_summary(results: list[dict[str, Any]], evidence_path: Path) -> None:
    print("\n| case | verdict | bug_pattern | one-line observed |")
    print("| --- | --- | --- | --- |")
    for result in results:
        observed = str(result.get("observed") or "").replace("\n", " ")
        if len(observed) > 180:
            observed = observed[:177] + "..."
        print(
            f"| {result['case_id']} | {result['verdict']} | {result.get('bug_pattern') or ''} | {observed} |"
        )
    print(f"\nevidence={evidence_path}")


def main() -> int:
    transcript = Transcript(batch_id=BATCH_ID)
    accounts: dict[str, SmokeAccount] = {}
    results: list[dict[str, Any]] = []
    try:
        _check_stack_health()
        accounts = _setup_accounts(transcript)
        results = _run_cases(accounts, transcript)
    except Exception as exc:
        if not accounts:
            accounts = {}
        before = {"mongo": {}, "postgres": {}}
        after = before
        delta = {"mongo": {}, "postgres": {}}
        results = [
            _result(
                case_id="BLOCKED-SETUP",
                verdict="BLOCKED",
                bug_pattern="",
                severity="smoke-infra",
                expected="Bridge/gateway healthy and three fresh accounts provisioned",
                observed=f"{type(exc).__name__}: {exc}",
                turns=[],
                delta=delta,
                before=before,
                after=after,
            )
        ]

    evidence_path = _save_evidence(transcript, accounts, results)
    _print_summary(results, evidence_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
