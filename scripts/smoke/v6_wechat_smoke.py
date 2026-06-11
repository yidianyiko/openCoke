"""WeChat-personal v6 behavioral smoke harness.

Drives the openCoke agent test-set v6 (``scripts/smoke/v6_cases.py``) through
the deployed clean stack over the ``wechat_personal`` channel and verifies each
turn against the clean Postgres rows.

Relationship to ``clean_smoke``:

* ``clean_smoke`` verifies infrastructure plumbing over WhatsApp/Evolution.
* This harness verifies turn-level NL behavior — that a natural-language message
  produces (or refuses) the right reminder / shared_reminder rows — over WeChat.

Verdict model (validated against the live stack on 2026-06-11):

* The HARD verdict is the row-effect diff: which active ``reminder`` /
  ``shared_reminder`` rows were created / removed for the requester across the
  turn. ``staged_command`` is a soft, execution-layer signal (a create may
  materialize as ``reminder.execute_batch`` / ``detect_and_create`` / ``create``;
  reads produce no staged_command), so we bucket it semantically, never assert
  an exact op string.

WeChat reality (validated 2026-06-11):

* wechat_personal does NOT auto-provision on first contact. An inbound MUST
  carry the ``account_id`` of an already-paired account (dashless hex form, as
  the real connector sends) or it is rejected ``identity_pairing_required`` /
  ``channel_identity_already_bound``. The requester (and any friend persona)
  must therefore be supplied as pre-paired accounts.

Env:

    COKE_SMOKE_API_BASE   e.g. https://coke.keep4oforever.com
    COKE_SMOKE_DB_URL     clean Postgres URL (verdict source)
    COKE_SMOKE_WECHAT_REQUESTER  {"account_id": "...", "wxid": "...", "display_name": "Eva"}
    COKE_SMOKE_WECHAT_FRIENDS    optional [{"account_id","wxid","display_name"}, ...]
    COKE_SMOKE_WEBHOOK_SECRET    optional
    COKE_SMOKE_TIMEZONE          default Asia/Shanghai

Modes: ``--dry-run`` (offline), default live webhook injection. Use
``--requester-only`` to run just the cases that need no friend persona.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass, field
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
APPLIED_STATUS = "materialized"

# Execution-layer staged_command ops grouped into semantic buckets. Learned
# from the live staged_command vocabulary, not the planner param schema.
REMINDER_CREATE_OPS = {"create", "detect_and_create", "execute_batch"}
REMINDER_UPDATE_OPS = {"update_reminder"}
REMINDER_DELETE_OPS = {"delete_reminder"}
SHARED_CREATE_OPS = {"create_shared_reminder", "detect_and_create_shared_reminder"}
SHARED_UPDATE_OPS = {"update_shared_reminder"}
SHARED_CANCEL_OPS = {"cancel_shared_reminder"}


# --------------------------------------------------------------------------
# Identity + payload
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class WeChatIdentity:
    """A pre-paired wechat_personal account. ``account_id`` is stored in DB
    (dashed UUID) form; the webhook payload uses the dashless hex form."""

    account_id: str  # dashed UUID, as stored in Postgres
    wxid: str
    display_name: str

    @property
    def payload_account_id(self) -> str:
        return self.account_id.replace("-", "")

    @classmethod
    def parse(cls, raw_value: str, *, default_name: str = "Eva") -> "WeChatIdentity":
        value = raw_value.strip()
        if not value.startswith("{"):
            raise ValueError(
                "wechat identity must be a JSON object with account_id+wxid"
            )
        payload = json.loads(value)
        account_id = payload.get("account_id")
        wxid = payload.get("wxid") or payload.get("provider_subject")
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("wechat identity needs account_id")
        if not isinstance(wxid, str) or not wxid.strip():
            raise ValueError("wechat identity needs wxid")
        name = payload.get("display_name") or payload.get("push_name") or default_name
        return cls(
            account_id=account_id.strip(), wxid=wxid.strip(), display_name=str(name)
        )


def wechat_payload(
    *, identity: WeChatIdentity, text: str, message_id: str
) -> dict[str, Any]:
    return {
        "wxid": identity.wxid,
        "account_id": identity.payload_account_id,
        "message_id": message_id,
        "text": text,
        "sender_name": identity.display_name,
        "session_id": f"{message_id}-sess",
        "context_token": f"{message_id}-ctx",
    }


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
@dataclass
class V6SmokeConfig:
    api_base: str
    db_url: str
    requester: WeChatIdentity
    run_id: str
    evidence_dir: Path
    friends: list[WeChatIdentity] = field(default_factory=list)
    timezone: str = "Asia/Shanghai"
    webhook_secret: str | None = None
    poll_timeout_seconds: float = 90.0
    poll_interval_seconds: float = 2.0

    @classmethod
    def from_env(cls, args: argparse.Namespace) -> "V6SmokeConfig":
        run_id = args.run_id or datetime.now(UTC).strftime("v6_%Y%m%dT%H%M%SZ")
        if args.dry_run:
            requester = WeChatIdentity(
                "00000000-0000-0000-0000-000000000000", "wxid_demo", "Eva"
            )
            return cls(
                api_base="https://dry.run",
                db_url="postgresql+psycopg://dry/run",
                requester=requester,
                run_id=run_id,
                evidence_dir=Path(args.evidence_dir),
            )
        missing = [
            name
            for name in (
                "COKE_SMOKE_API_BASE",
                "COKE_SMOKE_DB_URL",
                "COKE_SMOKE_WECHAT_REQUESTER",
            )
            if not os.environ.get(name)
        ]
        if missing:
            raise SmokeVerdictError("missing required env vars: " + ", ".join(missing))
        friends_raw = os.environ.get("COKE_SMOKE_WECHAT_FRIENDS", "").strip()
        friends: list[WeChatIdentity] = []
        if friends_raw:
            for i, entry in enumerate(json.loads(friends_raw)):
                friends.append(
                    WeChatIdentity.parse(json.dumps(entry), default_name=f"friend{i}")
                )
        return cls(
            api_base=os.environ["COKE_SMOKE_API_BASE"].rstrip("/"),
            db_url=os.environ["COKE_SMOKE_DB_URL"],
            requester=WeChatIdentity.parse(os.environ["COKE_SMOKE_WECHAT_REQUESTER"]),
            friends=friends,
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
        .where(msg.c.causal_inbound_event_id == event_id, msg.c.direction == "inbound")
        .order_by(turn.c.started_at.desc())
        .limit(1)
    )


def _ops_for_turn() -> sa.Select:
    sc = schema.staged_command
    turn_id = sa.bindparam("turn_id")
    return sa.select(sc.c.domain, sc.c.operation, sc.c.status).where(
        sc.c.turn_id == turn_id
    )


def _disposition_for_turn() -> sa.Select:
    od = schema.output_disposition
    turn_id = sa.bindparam("turn_id")
    return sa.select(od.c.disposition).where(od.c.turn_id == turn_id)


def _outbound_for_turn() -> sa.Select:
    msg = schema.message
    turn_id = sa.bindparam("turn_id")
    return sa.select(msg.c.id).where(
        msg.c.turn_id == turn_id, msg.c.direction == "outbound"
    )


def _active_reminder_ids() -> sa.Select:
    reminder = schema.reminder
    owner = sa.bindparam("owner_account_id")
    return sa.select(reminder.c.id, reminder.c.kind).where(
        reminder.c.owner_account_id == owner, reminder.c.lifecycle == "active"
    )


def _active_shared_ids() -> sa.Select:
    shared = schema.shared_reminder
    creator = sa.bindparam("creator_account_id")
    return sa.select(
        shared.c.id,
        shared.c.local_trigger_at,
        shared.c.duration_minutes,
    ).where(shared.c.creator_account_id == creator, shared.c.status == "active")


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
        self._friend_by_alias: dict[str, WeChatIdentity] = {}
        self._friend_cursor = 0

    # ---- HTTP --------------------------------------------------------------
    def _post_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.webhook_secret:
            headers["X-Coke-Webhook-Secret"] = self.config.webhook_secret
        body = json.dumps(payload).encode("utf-8")
        return _http_json(
            Request(
                f"{self.config.api_base}{WEBHOOK_PATH}",
                data=body,
                method="POST",
                headers=headers,
            )
        )

    # ---- Friend personas (pre-paired accounts from the env pool) -----------
    def _resolve_friend(self, alias: str) -> WeChatIdentity:
        if alias not in self._friend_by_alias:
            if self._friend_cursor >= len(self.config.friends):
                raise SmokeVerdictError(
                    "insufficient_friend_accounts: case needs a paired friend account; "
                    "supply more in COKE_SMOKE_WECHAT_FRIENDS"
                )
            identity = self.config.friends[self._friend_cursor]
            self._friend_cursor += 1
            self._friend_by_alias[alias] = identity
            self._befriend(self.config.requester.account_id, identity.account_id)
        return self._friend_by_alias[alias]

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
        self, owner: str, content: str, when: datetime, kind: str, duration: int | None
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
        if duration is not None:
            item["duration_minutes"] = duration
        http_post_json(
            f"{self.config.api_base}/api/reminders/batch",
            {"owner_account_id": owner, "items": [item]},
        )

    def _seed_shared(
        self, creator: str, friend: str, title: str, when: datetime
    ) -> None:
        http_post_json(
            f"{self.config.api_base}/api/shared-reminders",
            {
                "creator_account_id": creator,
                "receiver_account_ids": [friend],
                "title": f"{title} {self.config.run_id}",
                "local_trigger_at": when.replace(tzinfo=None).isoformat(),
                "captured_timezone": self.config.timezone,
                "duration_minutes": 60,
                "context": {"source": "v6_wechat_smoke"},
            },
        )

    def _seed_fixtures(self, case: V6Case) -> None:
        requester = self.config.requester.account_id
        for friend in case.fixtures.friends:
            self._resolve_friend(friend.alias)
        for rem in case.fixtures.reminders:
            self._seed_reminder(
                requester,
                rem.content,
                _resolve_phrase(rem.time_phrase),
                rem.kind,
                rem.duration_minutes,
            )
        for alias, span in case.fixtures.friend_busy:
            friend = self._resolve_friend(alias)
            start, _ = _resolve_span(span)
            self._seed_reminder(friend.account_id, f"busy {span}", start, "timed", 60)
        for sh in case.fixtures.shared:
            friend = self._resolve_friend(sh.friend_alias)
            self._seed_shared(
                requester, friend.account_id, sh.title, _resolve_phrase(sh.time_phrase)
            )

    # ---- Case execution ----------------------------------------------------
    def _snapshot(self) -> tuple[set[str], dict[str, tuple[str, int]]]:
        assert self.db is not None
        owner = self.config.requester.account_id
        reminders = {
            r["id"]
            for r in self.db.rows(_active_reminder_ids().params(owner_account_id=owner))
        }
        shared = {
            r["id"]: (
                r["local_trigger_at"].isoformat(),
                int(r["duration_minutes"]),
            )
            for r in self.db.rows(_active_shared_ids().params(creator_account_id=owner))
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
        before: tuple[set[str], dict[str, tuple[str, int]]],
    ) -> dict[str, Any]:
        assert self.db is not None
        turn_id = turn_row["turn_id"]
        ops = self.db.rows(_ops_for_turn().params(turn_id=turn_id))
        materialized = {
            f"{r['domain']}.{r['operation']}"
            for r in ops
            if r["status"] == APPLIED_STATUS
        }
        disposition = self.db.one_or_none(
            _disposition_for_turn().params(turn_id=turn_id)
        )
        outbound = self.db.rows(_outbound_for_turn().params(turn_id=turn_id))
        after = self._snapshot()
        before_shared_ids = set(before[1])
        after_shared_ids = set(after[1])
        return {
            "materialized_ops": sorted(materialized),
            "disposition": (disposition or {}).get("disposition"),
            "has_outbound": bool(outbound),
            "new_reminders": sorted(after[0] - before[0]),
            "removed_reminders": sorted(before[0] - after[0]),
            "new_shared": sorted(after_shared_ids - before_shared_ids),
            "removed_shared": sorted(before_shared_ids - after_shared_ids),
            "updated_shared": sorted(
                shared_id
                for shared_id in before_shared_ids & after_shared_ids
                if before[1][shared_id] != after[1][shared_id]
            ),
        }

    @staticmethod
    def _bucket(ops: set[str]) -> dict[str, bool]:
        def any_op(domain: str, names: set[str]) -> bool:
            return any(op == f"{domain}.{n}" for op in ops for n in names)

        return {
            "reminder_create": any_op("reminder", REMINDER_CREATE_OPS),
            "reminder_update": any_op("reminder", REMINDER_UPDATE_OPS),
            "reminder_delete": any_op("reminder", REMINDER_DELETE_OPS),
            "shared_create": any_op("social_scheduling", SHARED_CREATE_OPS),
            "shared_update": any_op("social_scheduling", SHARED_UPDATE_OPS),
            "shared_cancel": any_op("social_scheduling", SHARED_CANCEL_OPS),
        }

    def _assert_case(self, case: V6Case, verdict: dict[str, Any]) -> None:
        expect = case.expect
        ops = set(verdict["materialized_ops"])
        bucket = self._bucket(ops)

        # Negative assertions, enforced for every case (incl. gap cases).
        for tag in expect.forbid:
            if tag == "reminder_create" and (
                bucket["reminder_create"] or verdict["new_reminders"]
            ):
                self.transcript.fail_and_raise(
                    case.case_id, "forbidden: reminder created", verdict
                )
            if tag == "shared_create" and (
                bucket["shared_create"] or verdict["new_shared"]
            ):
                self.transcript.fail_and_raise(
                    case.case_id, "forbidden: shared created", verdict
                )
            if tag == "shared_cancel" and (
                bucket["shared_cancel"] or verdict["removed_shared"]
            ):
                self.transcript.fail_and_raise(
                    case.case_id, "forbidden: shared cancelled", verdict
                )

        reply_like = (
            verdict["has_outbound"] or verdict["disposition"] in REPLY_LIKE_DISPOSITIONS
        )
        if expect.reply_expected and not reply_like:
            self.transcript.fail_and_raise(
                case.case_id, "expected a reply, none produced", verdict
            )

        if expect.gap:
            self.transcript.pass_verdict(
                case.case_id,
                f"expected_gap: {expect.gap}",
                {"recorded_behavior": verdict},
            )
            return

        self._assert_outcome(case, verdict)
        self.transcript.pass_verdict(case.case_id, "verified", verdict)

    def _assert_outcome(self, case: V6Case, verdict: dict[str, Any]) -> None:
        outcome = case.expect.outcome
        bucket = self._bucket(set(verdict["materialized_ops"]))
        if outcome == "create_reminder":
            if not verdict["new_reminders"]:
                self.transcript.fail_and_raise(
                    case.case_id, "no new reminder row", verdict
                )
        elif outcome == "create_shared":
            if not verdict["new_shared"]:
                self.transcript.fail_and_raise(
                    case.case_id, "no new shared row", verdict
                )
        elif outcome == "cancel_reminder":
            if not verdict["removed_reminders"]:
                self.transcript.fail_and_raise(
                    case.case_id, "no reminder cancelled", verdict
                )
        elif outcome == "cancel_shared":
            if not verdict["removed_shared"]:
                self.transcript.fail_and_raise(
                    case.case_id, "no shared cancelled", verdict
                )
        elif outcome == "update_shared":
            if verdict["new_shared"] or verdict["removed_shared"]:
                self.transcript.fail_and_raise(
                    case.case_id, "shared update created or removed a row", verdict
                )
            if not (bucket["shared_update"] or verdict.get("updated_shared")):
                self.transcript.fail_and_raise(
                    case.case_id, "no shared reminder updated", verdict
                )
        elif outcome == "update_reminder":
            if verdict["new_reminders"]:
                self.transcript.fail_and_raise(
                    case.case_id, "update created a new row", verdict
                )
        elif outcome in {
            "clarify",
            "chat",
            "list_reminders",
            "query_availability",
            "conflict_block",
        }:
            if (
                verdict["new_reminders"]
                or verdict["new_shared"]
                or verdict.get("updated_shared")
                or verdict["removed_shared"]
            ):
                self.transcript.fail_and_raise(
                    case.case_id, f"{outcome} must not create product rows", verdict
                )

    def run_case(self, case: V6Case) -> None:
        assert self.db is not None
        self.transcript.event(case.case_id, "begin", {"message": case.message})
        self._seed_fixtures(case)
        before = self._snapshot()
        event_id = f"{self.config.run_id}_{case.case_id}_{uuid.uuid4().hex[:8]}"
        self._post_webhook(
            wechat_payload(
                identity=self.config.requester, text=case.message, message_id=event_id
            )
        )
        turn_row = self._wait_turn(event_id)
        verdict = self._collect_verdict(turn_row, before)
        self.transcript.event(case.case_id, "verdict", verdict)
        self._assert_case(case, verdict)

    def run(self, selected: list[V6Case]) -> dict[str, Any]:
        self._healthcheck()
        self.db = CleanSmokeDb(self.config.db_url)
        skipped: list[dict[str, str]] = []
        ran = 0
        try:
            for case in selected:
                try:
                    self.run_case(case)
                    ran += 1
                except SmokeVerdictError as error:
                    if "insufficient_friend_accounts" in str(error):
                        skipped.append(
                            {"case_id": case.case_id, "reason": "needs_friend_account"}
                        )
                        self.transcript.event(
                            case.case_id, "skipped", {"reason": str(error)}
                        )
                        continue
                    raise
        finally:
            self.db.dispose()
        path = self.transcript.save("passed")
        return {
            "status": "passed",
            "evidence_path": str(path),
            "ran": ran,
            "skipped": skipped,
        }

    def _healthcheck(self) -> None:
        body = http_get_json(f"{self.config.api_base}/healthz")
        if not body or body.get("ok") is False:
            raise SmokeVerdictError(f"healthz not healthy: {body}")


# --------------------------------------------------------------------------
# Fixture time-phrase resolution (NOT the case message — the agent parses that)
# --------------------------------------------------------------------------
def _resolve_phrase(phrase: str) -> datetime:
    return _resolve_span(phrase)[0]


def _resolve_span(phrase: str) -> tuple[datetime, datetime | None]:
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
        return _apply_hm(base, start_s), _apply_hm(base, end_s)
    return _apply_hm(base, text), None


def _apply_hm(base: datetime, hm: str) -> datetime:
    hour, _, minute = hm.strip().partition(":")
    return base.replace(hour=int(hour), minute=int(minute or 0))


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------
def run_dry_run(selected: list[V6Case]) -> dict[str, Any]:
    plan = [
        {
            "case_id": c.case_id,
            "group": c.group,
            "message": c.message,
            "outcome": c.expect.outcome,
            "forbid": list(c.expect.forbid),
            "needs_friends": c.needs_friends or bool(c.fixtures.shared),
            "gap": c.expect.gap,
        }
        for c in selected
    ]
    sample = wechat_payload(
        identity=WeChatIdentity(
            "11111111-2222-3333-4444-555555555555", "wxid_demo", "Eva"
        ),
        text=selected[0].message if selected else "hi",
        message_id="demo",
    )
    return {
        "status": "dry-run-ok",
        "case_count": len(selected),
        "requester_only": sum(
            1 for c in selected if not (c.needs_friends or c.fixtures.shared)
        ),
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
    if args.requester_only:
        return [case_by_id(cid) for cid in v6_cases.REQUESTER_ONLY]
    return list(CASES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WeChat-personal v6 behavioral smoke")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case", action="append", help="run specific case_id(s)")
    parser.add_argument("--group", action="append", help="run a whole group")
    parser.add_argument("--first-round", action="store_true", help="v6 recommended 14")
    parser.add_argument(
        "--requester-only",
        action="store_true",
        help="only cases needing no friend persona",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = V6SmokeConfig.from_env(args)
    selected = _select(args)
    if args.dry_run:
        print(json.dumps(run_dry_run(selected), indent=2, ensure_ascii=False))
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
