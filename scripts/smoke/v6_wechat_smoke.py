"""WeChat-personal v6 behavioral smoke harness.

Drives the openCoke agent test-set v6 (``scripts/smoke/v6_cases.py``) through
the deployed clean stack over the ``wechat_personal`` channel and verifies each
turn against the clean Postgres rows.

Relationship to ``clean_smoke``:

* ``clean_smoke`` verifies infrastructure plumbing (first-contact provisioning,
  friendship/shared APIs, reminder fire) over the WhatsApp/Evolution channel.
* This harness verifies *turn-level NL behavior* — that a natural-language
  message routes to the correct ``domain.operation`` and produces (or refuses
  to produce) the right domain rows — over the ``wechat_personal`` channel.

Core principle (shared with ``clean_smoke``): the assistant reply is a
hypothesis; the clean Postgres rows are the verdict. The structural intent of a
turn is its materialized ``staged_command`` rows (``domain.operation``).

Channel payload (see ``coke/providers/wechat_personal.py``)::

    POST /webhooks/wechat/personal
    {"wxid": "...", "message_id": "...", "text": "...", "sender_name": "..."}

Requester identity comes from ``COKE_SMOKE_SENDER_A`` (the real account being
simulated, e.g. olivers). Friend personas required by a case ("张三", two
"Oliver"s, ...) are provisioned as run-scoped synthetic ``wechat_personal``
accounts so the smoke never mutates the real friend account.

Modes:

* ``--dry-run``   offline: validate corpus, print the execution plan, build and
  show a sample payload. No network, no DB.
* ``--mode webhook`` (default live): inject each case message via the webhook
  and assert the DB verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request

import sqlalchemy as sa

from coke import schema
from scripts.smoke import v6_cases
from scripts.smoke.clean_smoke import (
    CleanSmokeDb,
    SmokeTranscript,
    SmokeVerdictError,
    _http_json,
    http_get_json,
    http_post_json,
)
from scripts.smoke.v6_cases import CASES, V6Case, case_by_id

DEFAULT_EVIDENCE_DIR = Path("artifacts/evidence/v6-wechat-smoke")
PROVIDER_TYPE = "wechat_personal"
WEBHOOK_PATH = "/webhooks/wechat/personal"
REPLY_LIKE_DISPOSITIONS = {"replied", "pending_async_reply"}
# staged_command.status that means the action was actually applied.
APPLIED_STATUS = "materialized"


# --------------------------------------------------------------------------
# Identity + payload
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class WeChatIdentity:
    label: str
    wxid: str
    display_name: str

    @classmethod
    def parse(cls, label: str, raw_value: str) -> "WeChatIdentity":
        value = raw_value.strip()
        if not value:
            raise ValueError(f"identity {label} is blank")
        if value.startswith("{"):
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError(f"identity {label} JSON must be an object")
            wxid = payload.get("wxid") or payload.get("provider_subject")
            if not isinstance(wxid, str) or not wxid.strip():
                raise ValueError(f"identity {label} JSON needs wxid")
            display = payload.get("push_name") or payload.get("sender_name") or label
            return cls(label=label, wxid=wxid.strip(), display_name=str(display))
        return cls(label=label, wxid=value, display_name=label)


def wechat_payload(
    *, identity: WeChatIdentity, text: str, message_id: str
) -> dict[str, Any]:
    return {
        "wxid": identity.wxid,
        "message_id": message_id,
        "text": text,
        "sender_name": identity.display_name,
    }


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
@dataclass
class V6SmokeConfig:
    api_base: str
    db_url: str
    requester: WeChatIdentity
    mode: str
    run_id: str
    evidence_dir: Path
    timezone: str = "Asia/Shanghai"
    webhook_secret: str | None = None
    poll_timeout_seconds: float = 90.0
    poll_interval_seconds: float = 2.0

    @classmethod
    def from_env(cls, args: argparse.Namespace) -> "V6SmokeConfig":
        missing = [
            name
            for name in (
                "COKE_SMOKE_API_BASE",
                "COKE_SMOKE_DB_URL",
                "COKE_SMOKE_SENDER_A",
            )
            if not os.environ.get(name)
        ]
        if missing and not args.dry_run:
            raise SmokeVerdictError(
                "missing required env vars: " + ", ".join(sorted(missing))
            )
        run_id = args.run_id or datetime.now(UTC).strftime("v6_%Y%m%dT%H%M%SZ")
        requester_raw = os.environ.get("COKE_SMOKE_SENDER_A") or json.dumps(
            {"wxid": f"dryrun_requester_{run_id}", "push_name": "Eva"}
        )
        return cls(
            api_base=(
                os.environ.get("COKE_SMOKE_API_BASE") or "https://dry.run"
            ).rstrip("/"),
            db_url=os.environ.get("COKE_SMOKE_DB_URL")
            or "postgresql+psycopg://dry/run",
            requester=WeChatIdentity.parse("requester", requester_raw),
            mode=args.mode,
            run_id=run_id,
            evidence_dir=Path(args.evidence_dir),
            timezone=os.environ.get("COKE_SMOKE_TIMEZONE", "Asia/Shanghai"),
            webhook_secret=os.environ.get("COKE_SMOKE_WEBHOOK_SECRET"),
            poll_timeout_seconds=float(os.environ.get("COKE_SMOKE_POLL_TIMEOUT", "90")),
            poll_interval_seconds=float(
                os.environ.get("COKE_SMOKE_POLL_INTERVAL", "2")
            ),
        )


# --------------------------------------------------------------------------
# Verdict queries
# --------------------------------------------------------------------------
def _turn_for_event() -> sa.Select:
    """Resolve the turn that consumed a given inbound webhook event."""
    msg = schema.message
    turn = schema.turn
    event_id = sa.bindparam("event_id")
    return (
        sa.select(
            turn.c.id.label("turn_id"), turn.c.conversation_id, turn.c.completed_at
        )
        .select_from(
            msg.join(
                turn,
                sa.and_(
                    msg.c.conversation_id == turn.c.conversation_id,
                    msg.c.seq >= turn.c.input_from_seq,
                    msg.c.seq <= turn.c.input_to_seq,
                ),
            )
        )
        .where(
            msg.c.causal_inbound_event_id == event_id,
            msg.c.direction == "inbound",
        )
        .order_by(turn.c.started_at.desc())
        .limit(1)
    )


def _materialized_ops_for_turn() -> sa.Select:
    sc = schema.staged_command
    turn_id = sa.bindparam("turn_id")
    return sa.select(sc.c.domain, sc.c.operation, sc.c.status).where(
        sc.c.turn_id == turn_id
    )


def _disposition_for_turn() -> sa.Select:
    od = schema.output_disposition
    turn_id = sa.bindparam("turn_id")
    return sa.select(od.c.disposition, od.c.reason_code).where(od.c.turn_id == turn_id)


def _outbound_for_turn() -> sa.Select:
    msg = schema.message
    turn_id = sa.bindparam("turn_id")
    return sa.select(msg.c.id).where(
        msg.c.turn_id == turn_id, msg.c.direction == "outbound"
    )


def _pending_clarification_for_conversation() -> sa.Select:
    pc = schema.pending_clarification
    conversation_id = sa.bindparam("conversation_id")
    return sa.select(pc.c.id).where(pc.c.conversation_id == conversation_id)


def _active_reminder_ids_for_owner() -> sa.Select:
    reminder = schema.reminder
    owner = sa.bindparam("owner_account_id")
    return sa.select(reminder.c.id, reminder.c.kind, reminder.c.content).where(
        reminder.c.owner_account_id == owner,
        reminder.c.lifecycle == "active",
    )


def _shared_ids_for_creator() -> sa.Select:
    shared = schema.shared_reminder
    creator = sa.bindparam("creator_account_id")
    return sa.select(shared.c.id, shared.c.status, shared.c.title).where(
        shared.c.creator_account_id == creator
    )


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
class V6WeChatSmoke:
    def __init__(self, config: V6SmokeConfig) -> None:
        self.config = config
        self.transcript = SmokeTranscript(
            run_id=config.run_id, evidence_dir=config.evidence_dir
        )
        self.db: CleanSmokeDb | None = None
        # alias -> provisioned account_id, cached per run.
        self._friend_accounts: dict[str, str] = {}
        self._requester_account_id: str | None = None

    # ---- HTTP --------------------------------------------------------------
    def _post_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.webhook_secret:
            headers["X-Webhook-Secret"] = self.config.webhook_secret
        body = json.dumps(payload).encode("utf-8")
        return _http_json(
            Request(
                f"{self.config.api_base}{WEBHOOK_PATH}",
                data=body,
                method="POST",
                headers=headers,
            )
        )

    # ---- Provisioning ------------------------------------------------------
    def _provision(self, identity: WeChatIdentity, first_text: str) -> str:
        message_id = f"{self.config.run_id}_{identity.wxid}_provision"
        result = self._post_webhook(
            wechat_payload(identity=identity, text=first_text, message_id=message_id)
        )
        account_id = result.get("account_id")
        if not isinstance(account_id, str) or not account_id:
            raise SmokeVerdictError(
                f"provision did not return account_id for {identity.wxid}: {result}"
            )
        return account_id

    def _requester_account(self) -> str:
        if self._requester_account_id is None:
            self._requester_account_id = self._provision(self.config.requester, "hi")
        return self._requester_account_id

    def _friend_account(self, alias: str, display_name: str) -> str:
        if alias not in self._friend_accounts:
            wxid = f"{self.config.run_id}_friend_{_slug(alias)}"
            identity = WeChatIdentity(label=alias, wxid=wxid, display_name=display_name)
            account_id = self._provision(identity, "hi")
            self._friend_accounts[alias] = account_id
            self._befriend(self._requester_account(), account_id)
        return self._friend_accounts[alias]

    def _befriend(self, owner_account_id: str, friend_account_id: str) -> None:
        link = http_get_json(
            f"{self.config.api_base}/api/friends/link?"
            + urlencode({"owner_account_id": owner_account_id})
        )
        link_code = link.get("link_code")
        if not isinstance(link_code, str) or not link_code:
            raise SmokeVerdictError(f"friend link returned no code: {link}")
        http_post_json(
            f"{self.config.api_base}/api/friends/join",
            {"joiner_account_id": friend_account_id, "link_code": link_code},
        )

    # ---- Fixture seeding ---------------------------------------------------
    def _seed_reminder(
        self,
        owner_account_id: str,
        content: str,
        when: datetime,
        kind: str,
        duration_minutes: int | None,
    ) -> None:
        item: dict[str, Any] = {
            "operation": "create",
            "content": f"{content} {self.config.run_id}",
            "raw_text": content,
            "trigger_time": when.isoformat(),
            "captured_timezone": self.config.timezone,
            "kind": kind,
            "entry_point": "v6_wechat_smoke",
        }
        if duration_minutes is not None:
            item["duration_minutes"] = duration_minutes
        http_post_json(
            f"{self.config.api_base}/api/reminders/batch",
            {"owner_account_id": owner_account_id, "items": [item]},
        )

    def _seed_shared(
        self,
        creator_account_id: str,
        friend_account_id: str,
        title: str,
        when: datetime,
    ) -> None:
        http_post_json(
            f"{self.config.api_base}/api/shared-reminders",
            {
                "creator_account_id": creator_account_id,
                "receiver_account_ids": [friend_account_id],
                "title": f"{title} {self.config.run_id}",
                "local_trigger_at": when.replace(tzinfo=None).isoformat(),
                "captured_timezone": self.config.timezone,
                "duration_minutes": 60,
                "context": {"source": "v6_wechat_smoke"},
            },
        )

    def _seed_fixtures(self, case: V6Case) -> None:
        requester = self._requester_account()
        for friend in case.fixtures.friends:
            self._friend_account(friend.alias, friend.display_name)
        for rem in case.fixtures.reminders:
            self._seed_reminder(
                requester,
                rem.content,
                _resolve_phrase(rem.time_phrase, self.config.timezone),
                rem.kind,
                rem.duration_minutes,
            )
        for busy in case.fixtures.friend_busy:
            alias, span = busy
            friend_id = self._friend_account(alias, alias)
            start, _ = _resolve_span(span, self.config.timezone)
            self._seed_reminder(friend_id, f"busy {span}", start, "timed", 60)
        for sh in case.fixtures.shared:
            friend_id = self._friend_account(sh.friend_alias, sh.friend_alias)
            self._seed_shared(
                requester,
                friend_id,
                sh.title,
                _resolve_phrase(sh.time_phrase, self.config.timezone),
            )

    # ---- Case execution ----------------------------------------------------
    def _snapshot_rows(self, requester: str) -> tuple[set[str], set[str]]:
        assert self.db is not None
        reminders = {
            row["id"]
            for row in self.db.rows(
                _active_reminder_ids_for_owner().params(owner_account_id=requester)
            )
        }
        shared = {
            row["id"]
            for row in self.db.rows(
                _shared_ids_for_creator().params(creator_account_id=requester)
            )
        }
        return reminders, shared

    def _wait_turn(self, event_id: str) -> dict[str, Any]:
        assert self.db is not None
        deadline = time.monotonic() + self.config.poll_timeout_seconds
        while time.monotonic() < deadline:
            row = self.db.one_or_none(_turn_for_event().params(event_id=event_id))
            if row and row.get("completed_at") is not None:
                return row
            time.sleep(self.config.poll_interval_seconds)
        raise SmokeVerdictError(f"timed out waiting for completed turn for {event_id}")

    def _collect_verdict(
        self,
        turn_row: dict[str, Any],
        requester: str,
        before: tuple[set[str], set[str]],
    ) -> dict[str, Any]:
        assert self.db is not None
        turn_id = turn_row["turn_id"]
        ops = self.db.rows(_materialized_ops_for_turn().params(turn_id=turn_id))
        materialized = {
            f"{r['domain']}.{r['operation']}"
            for r in ops
            if r["status"] == APPLIED_STATUS
        }
        disposition = self.db.one_or_none(
            _disposition_for_turn().params(turn_id=turn_id)
        )
        outbound = self.db.rows(_outbound_for_turn().params(turn_id=turn_id))
        clarifications = self.db.rows(
            _pending_clarification_for_conversation().params(
                conversation_id=turn_row["conversation_id"]
            )
        )
        after = self._snapshot_rows(requester)
        return {
            "materialized_ops": sorted(materialized),
            "disposition": (disposition or {}).get("disposition"),
            "has_outbound": bool(outbound),
            "has_pending_clarification": bool(clarifications),
            "new_reminders": sorted(after[0] - before[0]),
            "new_shared": sorted(after[1] - before[1]),
        }

    def _assert_case(self, case: V6Case, verdict: dict[str, Any]) -> None:
        expect = case.expect
        ops = set(verdict["materialized_ops"])

        # Negative assertions ("不允许发生") are enforced for every case,
        # including capability-gap cases.
        forbidden = ops & set(expect.forbid_ops)
        if forbidden:
            self.transcript.fail_and_raise(
                case.case_id,
                "forbidden ops materialized",
                {"forbidden": sorted(forbidden), **verdict},
            )

        reply_like = (
            verdict["has_outbound"]
            or verdict["has_pending_clarification"]
            or verdict["disposition"] in REPLY_LIKE_DISPOSITIONS
        )
        if expect.reply_expected and not reply_like:
            self.transcript.fail_and_raise(
                case.case_id, "expected a reply but none was produced", verdict
            )

        if expect.gap:
            # Record current behavior; do not assert the v6-desired behavior.
            self.transcript.pass_verdict(
                case.case_id,
                f"expected_gap: {expect.gap}",
                {"recorded_behavior": verdict},
            )
            return

        missing = set(expect.staged_ops) - ops
        if missing:
            self.transcript.fail_and_raise(
                case.case_id,
                "expected ops not materialized",
                {"missing": sorted(missing), **verdict},
            )

        self._assert_outcome_rows(case, verdict)
        self.transcript.pass_verdict(case.case_id, "verified", verdict)

    def _assert_outcome_rows(self, case: V6Case, verdict: dict[str, Any]) -> None:
        outcome = case.expect.outcome
        if outcome == "create_reminder":
            if not verdict["new_reminders"]:
                self.transcript.fail_and_raise(
                    case.case_id, "no new reminder row created", verdict
                )
        elif outcome == "create_shared":
            if not verdict["new_shared"]:
                self.transcript.fail_and_raise(
                    case.case_id, "no new shared reminder created", verdict
                )
        elif outcome in {"clarify", "chat"}:
            if verdict["new_reminders"] or verdict["new_shared"]:
                self.transcript.fail_and_raise(
                    case.case_id,
                    f"{outcome} must not create product rows",
                    verdict,
                )

    def run_case(self, case: V6Case) -> None:
        assert self.db is not None
        self.transcript.event(case.case_id, "begin", {"message": case.message})
        self._seed_fixtures(case)
        requester = self._requester_account()
        before = self._snapshot_rows(requester)
        event_id = f"{self.config.run_id}_{case.case_id}_{uuid.uuid4().hex[:8]}"
        self._post_webhook(
            wechat_payload(
                identity=self.config.requester, text=case.message, message_id=event_id
            )
        )
        turn_row = self._wait_turn(event_id)
        verdict = self._collect_verdict(turn_row, requester, before)
        self.transcript.event(case.case_id, "verdict", verdict)
        self._assert_case(case, verdict)

    def run(self, selected: list[V6Case]) -> dict[str, Any]:
        self._healthcheck()
        self.db = CleanSmokeDb(self.config.db_url)
        try:
            for case in selected:
                self.run_case(case)
        finally:
            self.db.dispose()
        path = self.transcript.save("passed")
        return {"status": "passed", "evidence_path": str(path), "cases": len(selected)}

    def _healthcheck(self) -> None:
        body = http_get_json(f"{self.config.api_base}/healthz")
        if body.get("status") not in {None, "ok", "healthy"} and not body:
            raise SmokeVerdictError(f"healthz not healthy: {body}")


# --------------------------------------------------------------------------
# Time helpers for fixture phrases (NOT the case message — the agent parses
# that itself). Phrases are constrained to the shapes used in v6_cases.
# --------------------------------------------------------------------------
def _resolve_phrase(phrase: str, timezone: str) -> datetime:
    start, _ = _resolve_span(phrase, timezone)
    return start


def _resolve_span(phrase: str, timezone: str) -> tuple[datetime, datetime | None]:
    text = phrase.strip()
    day_offset = 0
    for token, offset in (("今天", 0), ("明天", 1), ("后天", 2)):
        if text.startswith(token):
            day_offset = offset
            text = text[len(token) :].strip()
            break
    now = datetime.now(UTC) + timedelta(hours=8)  # Asia/Shanghai wall clock
    base = (now + timedelta(days=day_offset)).replace(minute=0, second=0, microsecond=0)
    if "-" in text:
        start_s, end_s = text.split("-", 1)
        start = _apply_hm(base, start_s)
        end = _apply_hm(base, end_s)
        return start, end
    return _apply_hm(base, text), None


def _apply_hm(base: datetime, hm: str) -> datetime:
    hm = hm.strip()
    hour, _, minute = hm.partition(":")
    return base.replace(hour=int(hour), minute=int(minute or 0))


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower()


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------
def run_dry_run(selected: list[V6Case]) -> dict[str, Any]:
    from coke.turn.v2.param_schema import allowed_actions_from_schema

    valid_ops = {
        f"{d}.{op}" for d, ops in allowed_actions_from_schema().items() for op in ops
    }
    plan: list[dict[str, Any]] = []
    for case in selected:
        for op in (*case.expect.staged_ops, *case.expect.forbid_ops):
            if op not in valid_ops:
                raise SmokeVerdictError(f"{case.case_id}: unknown op {op}")
        plan.append(
            {
                "case_id": case.case_id,
                "group": case.group,
                "message": case.message,
                "outcome": case.expect.outcome,
                "staged_ops": list(case.expect.staged_ops),
                "forbid_ops": list(case.expect.forbid_ops),
                "fixtures": {
                    "friends": [f.alias for f in case.fixtures.friends],
                    "reminders": len(case.fixtures.reminders),
                    "shared": len(case.fixtures.shared),
                },
                "gap": case.expect.gap,
            }
        )
    sample = wechat_payload(
        identity=WeChatIdentity("requester", "wxid_demo", "Eva"),
        text=selected[0].message if selected else "hi",
        message_id="demo",
    )
    return {
        "status": "dry-run-ok",
        "case_count": len(selected),
        "gap_cases": [c.case_id for c in selected if c.expect.gap],
        "sample_webhook_payload": sample,
        "plan": plan,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _select(args: argparse.Namespace) -> list[V6Case]:
    if args.case:
        return [case_by_id(cid) for cid in args.case]
    if args.group:
        return [c for c in CASES if c.group in args.group]
    if args.first_round:
        return [case_by_id(cid) for cid in v6_cases.FIRST_ROUND]
    return list(CASES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WeChat-personal v6 behavioral smoke")
    parser.add_argument("--mode", choices=["webhook"], default="webhook")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case", action="append", help="run specific case_id(s)")
    parser.add_argument("--group", action="append", help="run a whole group")
    parser.add_argument("--first-round", action="store_true", help="v6 recommended 14")
    parser.add_argument("--run-id")
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = V6SmokeConfig.from_env(args)
    selected = _select(args)
    if args.dry_run:
        report = run_dry_run(selected)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    smoke = V6WeChatSmoke(config)
    try:
        report = smoke.run(selected)
    except SmokeVerdictError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
