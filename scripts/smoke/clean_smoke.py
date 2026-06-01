from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from coke import schema

DEFAULT_EVIDENCE_DIR = Path("artifacts/evidence/clean-smoke")
PROVIDER_TYPE = "whatsapp_evolution"
REPLY_LIKE_DISPOSITIONS = {"replied", "pending_async_reply"}


class SmokeVerdictError(RuntimeError):
    pass


@dataclass(frozen=True)
class SenderIdentity:
    label: str
    remote_jid: str
    push_name: str

    @property
    def provider_subject(self) -> str:
        return strip_evolution_jid(self.remote_jid)

    @classmethod
    def parse(cls, label: str, raw_value: str) -> "SenderIdentity":
        value = raw_value.strip()
        if not value:
            raise ValueError(f"COKE_SMOKE_SENDER_{label.upper()} is blank")
        if value.startswith("{"):
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError(f"sender {label} JSON must be an object")
            remote_jid = payload.get("remote_jid") or payload.get("jid")
            subject = payload.get("provider_subject")
            if not isinstance(remote_jid, str):
                if not isinstance(subject, str):
                    raise ValueError(
                        f"sender {label} JSON needs remote_jid or provider_subject"
                    )
                remote_jid = ensure_evolution_jid(subject)
            push_name = payload.get("push_name", label)
            if not isinstance(push_name, str) or not push_name.strip():
                raise ValueError(f"sender {label} push_name must be a string")
            return cls(
                label=label,
                remote_jid=ensure_evolution_jid(remote_jid),
                push_name=push_name.strip(),
            )
        return cls(label=label, remote_jid=ensure_evolution_jid(value), push_name=label)


@dataclass
class SmokeConfig:
    api_base: str
    db_url: str
    sender_a: SenderIdentity
    sender_b: SenderIdentity
    mode: str
    run_id: str
    evidence_dir: Path
    instance: str = "coke"
    timezone: str = "UTC"
    poll_timeout_seconds: float = 180.0
    poll_interval_seconds: float = 2.0
    fire_delay_seconds: int = 45

    @classmethod
    def from_env(cls, args: argparse.Namespace) -> "SmokeConfig":
        missing = [
            name
            for name in (
                "COKE_SMOKE_API_BASE",
                "COKE_SMOKE_DB_URL",
                "COKE_SMOKE_SENDER_A",
                "COKE_SMOKE_SENDER_B",
            )
            if not os.environ.get(name)
        ]
        if missing:
            raise SmokeVerdictError(
                "missing required env vars: " + ", ".join(sorted(missing))
            )
        run_id = args.run_id or datetime.now(UTC).strftime("rr8_%Y%m%dT%H%M%SZ")
        return cls(
            api_base=os.environ["COKE_SMOKE_API_BASE"].rstrip("/"),
            db_url=os.environ["COKE_SMOKE_DB_URL"],
            sender_a=SenderIdentity.parse("alice", os.environ["COKE_SMOKE_SENDER_A"]),
            sender_b=SenderIdentity.parse("bob", os.environ["COKE_SMOKE_SENDER_B"]),
            mode=args.mode,
            run_id=run_id,
            evidence_dir=Path(args.evidence_dir),
            instance=os.environ.get("COKE_SMOKE_EVOLUTION_INSTANCE", "coke"),
            timezone=os.environ.get("COKE_SMOKE_TIMEZONE", "UTC"),
            poll_timeout_seconds=float(
                os.environ.get("COKE_SMOKE_POLL_TIMEOUT", "180")
            ),
            poll_interval_seconds=float(
                os.environ.get("COKE_SMOKE_POLL_INTERVAL", "2")
            ),
            fire_delay_seconds=int(
                os.environ.get("COKE_SMOKE_FIRE_DELAY_SECONDS", "45")
            ),
        )


@dataclass
class SmokeTranscript:
    run_id: str
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR
    events: list[dict[str, Any]] = field(default_factory=list)
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    evidence_path: Path | None = None

    def event(
        self, phase: str, action: str, details: dict[str, Any] | None = None
    ) -> None:
        self.events.append(
            {
                "at": datetime.now(UTC).isoformat(),
                "phase": phase,
                "action": action,
                "details": details or {},
            }
        )

    def pass_verdict(self, phase: str, message: str, details: dict[str, Any]) -> None:
        self.verdicts.append(
            {
                "phase": phase,
                "status": "passed",
                "message": message,
                "details": details,
            }
        )

    def fail_and_raise(
        self, phase: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        self.verdicts.append(
            {
                "phase": phase,
                "status": "failed",
                "message": message,
                "details": details or {},
            }
        )
        path = self.save("failed")
        raise SmokeVerdictError(f"{phase}: {message}; evidence={path}")

    def save(self, status: str) -> Path:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        safe_run_id = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in self.run_id
        )
        path = self.evidence_dir / f"{safe_run_id}.json"
        path.write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "status": status,
                    "created_at": datetime.now(UTC).isoformat(),
                    "events": self.events,
                    "verdicts": self.verdicts,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
            + "\n"
        )
        self.evidence_path = path
        return path


class CleanSmokeDb:
    def __init__(self, db_url: str) -> None:
        self.engine = sa.create_engine(db_url)

    def rows(self, statement: sa.Select) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def one_or_none(self, statement: sa.Select) -> dict[str, Any] | None:
        rows = self.rows(statement)
        if len(rows) > 1:
            raise SmokeVerdictError(f"expected at most one row, got {len(rows)}")
        return rows[0] if rows else None

    def dispose(self) -> None:
        self.engine.dispose()


def ensure_evolution_jid(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("sender jid is blank")
    if text.endswith("@s.whatsapp.net") or text.endswith("@g.us"):
        return text
    return f"{text}@s.whatsapp.net"


def strip_evolution_jid(remote_jid: str) -> str:
    for suffix in ("@s.whatsapp.net", "@g.us"):
        if remote_jid.endswith(suffix):
            return remote_jid[: -len(suffix)]
    return remote_jid


def evolution_payload(
    *,
    sender: SenderIdentity,
    text: str,
    event_id: str,
    timestamp: int,
    instance: str,
) -> dict[str, Any]:
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {
                "remoteJid": sender.remote_jid,
                "fromMe": False,
                "id": event_id,
            },
            "pushName": sender.push_name,
            "message": {"conversation": text},
            "messageTimestamp": timestamp,
        },
    }


def run_dry_run(evidence_dir: Path = DEFAULT_EVIDENCE_DIR) -> dict[str, Any]:
    transcript = SmokeTranscript(run_id="dry-run", evidence_dir=evidence_dir)
    compiled = []
    for name, statement in verdict_query_specs().items():
        compiled.append(
            {
                "name": name,
                "sql": str(
                    statement.compile(
                        dialect=postgresql.dialect(),
                        compile_kwargs={"literal_binds": False},
                    )
                ),
            }
        )
    _assert_clean_schema_contract()
    transcript.pass_verdict(
        "dry_run",
        "compiled clean-schema verdict queries",
        {"query_count": len(compiled)},
    )
    path = transcript.save("passed")
    return {
        "status": "passed",
        "compiled_queries": compiled,
        "evidence_path": str(path),
    }


def verdict_query_specs() -> dict[str, sa.Select]:
    account = schema.account
    channel_identity = schema.channel_identity
    conversation = schema.conversation
    message = schema.message
    turn = schema.turn
    output_disposition = schema.output_disposition
    reminder = schema.reminder
    friendship = schema.friendship
    shared_reminder = schema.shared_reminder
    reminder_projection = schema.reminder_projection
    notification_fact = schema.notification_fact
    reminder_fire = schema.reminder_fire

    account_id = sa.bindparam("account_id")
    provider_subject = sa.bindparam("provider_subject")
    event_id = sa.bindparam("event_id")
    title_like = sa.bindparam("title_like")
    low_id = sa.bindparam("account_low_id")
    high_id = sa.bindparam("account_high_id")
    shared_id = sa.bindparam("shared_reminder_id")
    reminder_id = sa.bindparam("reminder_id")

    return {
        "first_contact_account": (
            sa.select(
                account.c.id.label("account_id"),
                account.c.origin,
                channel_identity.c.id.label("channel_identity_id"),
                channel_identity.c.is_account_anchor,
            )
            .select_from(
                channel_identity.join(
                    account, channel_identity.c.account_id == account.c.id
                )
            )
            .where(
                channel_identity.c.provider_type == PROVIDER_TYPE,
                channel_identity.c.provider_subject == provider_subject,
                channel_identity.c.lifecycle == "active",
            )
        ),
        "first_contact_message": (
            sa.select(
                conversation.c.id.label("conversation_id"),
                message.c.id.label("message_id"),
                message.c.seq,
                message.c.text,
                message.c.causal_inbound_event_id,
            )
            .select_from(
                conversation.join(
                    message, message.c.conversation_id == conversation.c.id
                )
            )
            .where(
                conversation.c.account_id == account_id,
                message.c.direction == "inbound",
                message.c.causal_inbound_event_id == event_id,
            )
            .order_by(message.c.created_at.desc())
        ),
        "first_contact_message_by_text": (
            sa.select(
                conversation.c.id.label("conversation_id"),
                message.c.id.label("message_id"),
                message.c.seq,
                message.c.text,
                message.c.causal_inbound_event_id,
            )
            .select_from(
                conversation.join(
                    message, message.c.conversation_id == conversation.c.id
                )
            )
            .where(
                conversation.c.account_id == account_id,
                message.c.direction == "inbound",
                message.c.text.ilike(sa.bindparam("text_like")),
            )
            .order_by(message.c.created_at.desc())
        ),
        "first_contact_turn_disposition": (
            sa.select(
                turn.c.id.label("turn_id"),
                turn.c.trigger_type,
                turn.c.mode,
                output_disposition.c.disposition,
                output_disposition.c.reason_code,
            )
            .select_from(
                turn.join(
                    output_disposition,
                    output_disposition.c.turn_id == turn.c.id,
                )
            )
            .where(turn.c.conversation_id == sa.bindparam("conversation_id"))
            .order_by(turn.c.created_at.desc())
        ),
        "first_contact_outbound": (
            sa.select(message.c.id, message.c.text, message.c.payload)
            .where(
                message.c.turn_id == sa.bindparam("turn_id"),
                message.c.direction == "outbound",
            )
            .order_by(message.c.segment_index)
        ),
        "personal_reminder_unique": (
            sa.select(reminder)
            .where(
                reminder.c.owner_account_id == account_id,
                reminder.c.lifecycle == "active",
                reminder.c.kind.in_(["timed", "recurring"]),
                reminder.c.content.ilike(title_like),
            )
            .order_by(reminder.c.created_at.desc())
        ),
        "active_friendship": (
            sa.select(friendship).where(
                friendship.c.account_low_id == low_id,
                friendship.c.account_high_id == high_id,
                friendship.c.lifecycle == "active",
            )
        ),
        "shared_reminder_active": (
            sa.select(shared_reminder).where(
                shared_reminder.c.id == shared_id,
                shared_reminder.c.status == "active",
            )
        ),
        "shared_reminder_projections": (
            sa.select(reminder_projection)
            .where(
                reminder_projection.c.shared_reminder_id == shared_id,
                reminder_projection.c.lifecycle == "active",
            )
            .order_by(reminder_projection.c.account_id)
        ),
        "notification_fact_without_text_payload": (
            sa.select(
                notification_fact.c.id,
                notification_fact.c.type,
                notification_fact.c.object_id,
                notification_fact.c.facts,
                notification_fact.c.facts_hash,
            )
            .where(
                notification_fact.c.object_id == shared_id,
                notification_fact.c.facts_hash.is_not(None),
            )
            .order_by(notification_fact.c.created_at.desc())
        ),
        "reminder_fire_delivered": (
            sa.select(reminder_fire, reminder.c.content)
            .select_from(
                reminder_fire.join(
                    reminder, reminder_fire.c.reminder_id == reminder.c.id
                )
            )
            .where(
                reminder_fire.c.reminder_id == reminder_id,
                reminder_fire.c.delivery_result == "delivered",
            )
            .order_by(reminder_fire.c.created_at.desc())
        ),
        "outbound_message_containing_title": (
            sa.select(message.c.id, message.c.text)
            .select_from(
                message.join(turn, message.c.turn_id == turn.c.id).join(
                    conversation, turn.c.conversation_id == conversation.c.id
                )
            )
            .where(
                conversation.c.account_id == account_id,
                message.c.direction == "outbound",
                message.c.text.ilike(title_like),
            )
            .order_by(message.c.created_at.desc())
        ),
    }


def _assert_clean_schema_contract() -> None:
    tables = schema.metadata.tables
    legacy_tables = {
        "inputmessages",
        "outputmessages",
        "agent_sessions",
        "memo_runtime",
    }
    present_legacy = legacy_tables & set(tables)
    if present_legacy:
        raise SmokeVerdictError(
            f"legacy tables present in clean schema: {present_legacy}"
        )
    notification_columns = tables["notification_fact"].columns
    for forbidden in ("text", "payload", "payload_text"):
        if forbidden in notification_columns:
            raise SmokeVerdictError(
                f"notification_fact has forbidden {forbidden} column"
            )


class CleanSmokeRunner:
    def __init__(self, config: SmokeConfig) -> None:
        self.config = config
        self.transcript = SmokeTranscript(
            run_id=config.run_id,
            evidence_dir=config.evidence_dir,
        )
        self.db = CleanSmokeDb(config.db_url)

    def run(self) -> Path:
        try:
            self._health_check()
            a = self._first_contact(self.config.sender_a, "hello")
            b = self._first_contact(self.config.sender_b, "hello")
            reminder = self._personal_reminder(a)
            friendship = self._friendship(a, b)
            shared = self._shared_reminder(a, b, friendship)
            self._fire_path(a)
            self.transcript.pass_verdict(
                "summary",
                "clean smoke completed",
                {
                    "account_a": a["account_id"],
                    "account_b": b["account_id"],
                    "personal_reminder_id": reminder["id"],
                    "friendship_id": friendship["id"],
                    "shared_reminder_id": shared["id"],
                },
            )
            return self.transcript.save("passed")
        finally:
            self.db.dispose()

    def _health_check(self) -> None:
        try:
            body = http_get_json(f"{self.config.api_base}/healthz")
        except SmokeVerdictError:
            raise
        except Exception as error:
            self.transcript.fail_and_raise(
                "healthz",
                "clean stack is down or unreachable",
                {"error": str(error), "api_base": self.config.api_base},
            )
        if body.get("ok") is not True:
            self.transcript.fail_and_raise(
                "healthz", "unexpected healthz response", {"body": body}
            )
        self.transcript.pass_verdict("healthz", "clean API healthz ok", body)

    def _first_contact(self, sender: SenderIdentity, greeting: str) -> dict[str, Any]:
        phase = f"first_contact_{sender.label}"
        text = f"RR8 {self.config.run_id} {greeting} from {sender.label}"
        event_id = f"{self.config.run_id}_{sender.label}_first_contact"
        if self.config.mode == "webhook":
            payload = evolution_payload(
                sender=sender,
                text=text,
                event_id=event_id,
                timestamp=int(datetime.now(UTC).timestamp()),
                instance=self.config.instance,
            )
            response = http_post_json(
                f"{self.config.api_base}/webhooks/whatsapp/evolution", payload
            )
            self.transcript.event(phase, "posted_webhook", response)
        else:
            self.transcript.event(
                phase,
                "awaiting_real_whatsapp",
                {
                    "sender": sender.provider_subject,
                    "message_to_send": text,
                    "expected_raw_event_id": event_id,
                },
            )
        snapshot = self._wait_for(
            phase,
            "first contact clean DB rows",
            lambda: self._first_contact_snapshot(sender, event_id, text),
        )
        self.transcript.pass_verdict(phase, "first contact rows verified", snapshot)
        return snapshot

    def _first_contact_snapshot(
        self, sender: SenderIdentity, event_id: str, text: str
    ) -> dict[str, Any] | None:
        queries = verdict_query_specs()
        account_row = self.db.one_or_none(
            queries["first_contact_account"].params(
                provider_subject=sender.provider_subject
            )
        )
        if account_row is None:
            return None
        if (
            account_row["origin"] != "messaging_first"
            or not account_row["is_account_anchor"]
        ):
            self.transcript.fail_and_raise(
                "first_contact",
                "sender is not bound to a messaging_first anchor account",
                account_row,
            )
        if self.config.mode == "webhook":
            message_query = queries["first_contact_message"].params(
                account_id=account_row["account_id"],
                event_id=event_id,
            )
        else:
            message_query = queries["first_contact_message_by_text"].params(
                account_id=account_row["account_id"],
                text_like=f"%{text}%",
            )
        message_rows = self.db.rows(message_query)
        if not message_rows:
            return None
        message_row = message_rows[0]
        disposition_rows = self.db.rows(
            queries["first_contact_turn_disposition"].params(
                conversation_id=message_row["conversation_id"]
            )
        )
        if not disposition_rows:
            return None
        disposition = disposition_rows[0]
        outbound_count = 0
        if disposition["disposition"] in REPLY_LIKE_DISPOSITIONS:
            outbound_rows = self.db.rows(
                queries["first_contact_outbound"].params(turn_id=disposition["turn_id"])
            )
            if not outbound_rows:
                return None
            outbound_count = len(outbound_rows)
        return {
            **account_row,
            "conversation_id": message_row["conversation_id"],
            "message_id": message_row["message_id"],
            "turn_id": disposition["turn_id"],
            "disposition": disposition["disposition"],
            "outbound_count": outbound_count,
        }

    def _personal_reminder(self, account: dict[str, Any]) -> dict[str, Any]:
        phase = "personal_reminder"
        title = f"check clean smoke {self.config.run_id}"
        text = f"Remind me in 10 minutes to {title}"
        event_id = f"{self.config.run_id}_personal_reminder"
        if self.config.mode == "webhook":
            payload = evolution_payload(
                sender=self.config.sender_a,
                text=text,
                event_id=event_id,
                timestamp=int(datetime.now(UTC).timestamp()),
                instance=self.config.instance,
            )
            self.transcript.event(
                phase,
                "posted_webhook",
                http_post_json(
                    f"{self.config.api_base}/webhooks/whatsapp/evolution", payload
                ),
            )
        else:
            self.transcript.event(
                phase,
                "awaiting_real_whatsapp",
                {"message_to_send": text, "expected_raw_event_id": event_id},
            )
        rows = self._wait_for(
            phase,
            "exactly one active owner-scoped personal reminder",
            lambda: self._personal_reminder_rows(account["account_id"], title),
        )
        if len(rows) != 1:
            self.transcript.fail_and_raise(
                phase, "expected exactly one active reminder", {"count": len(rows)}
            )
        row = rows[0]
        if row["next_fire_at"] is None or row["captured_timezone"] is None:
            self.transcript.fail_and_raise(
                phase,
                "reminder missing next_fire_at or timezone",
                dict(row),
            )
        self.transcript.pass_verdict(phase, "personal reminder verified", dict(row))
        return row

    def _personal_reminder_rows(
        self, account_id: str, title: str
    ) -> list[dict[str, Any]] | None:
        rows = self.db.rows(
            verdict_query_specs()["personal_reminder_unique"].params(
                account_id=account_id,
                title_like=f"%{title}%",
            )
        )
        return rows if rows else None

    def _friendship(
        self, account_a: dict[str, Any], account_b: dict[str, Any]
    ) -> dict[str, Any]:
        phase = "friendship"
        link = http_get_json(
            f"{self.config.api_base}/api/friends/link?"
            + urlencode({"owner_account_id": account_a["account_id"]})
        )
        link_code = link.get("link_code")
        if not isinstance(link_code, str) or not link_code:
            self.transcript.fail_and_raise(
                phase, "friend link API did not return a link_code", link
            )
        join = http_post_json(
            f"{self.config.api_base}/api/friends/join",
            {"joiner_account_id": account_b["account_id"], "link_code": link_code},
        )
        self.transcript.event(phase, "joined_link_code", {"link": link, "join": join})
        low, high = unordered_pair(account_a["account_id"], account_b["account_id"])
        rows = self._wait_for(
            phase,
            "exactly one active unordered friendship",
            lambda: self.db.rows(
                verdict_query_specs()["active_friendship"].params(
                    account_low_id=low,
                    account_high_id=high,
                )
            )
            or None,
        )
        if len(rows) != 1:
            self.transcript.fail_and_raise(
                phase, "expected exactly one active friendship", {"count": len(rows)}
            )
        self.transcript.pass_verdict(phase, "active friendship verified", dict(rows[0]))
        return rows[0]

    def _shared_reminder(
        self,
        account_a: dict[str, Any],
        account_b: dict[str, Any],
        friendship: dict[str, Any],
    ) -> dict[str, Any]:
        phase = "shared_reminder"
        title = f"RR8 shared smoke {self.config.run_id}"
        local_trigger_at = (
            datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
        ).replace(microsecond=0)
        result = http_post_json(
            f"{self.config.api_base}/api/shared-reminders",
            {
                "creator_account_id": account_a["account_id"],
                "receiver_account_ids": [account_b["account_id"]],
                "title": title,
                "local_trigger_at": local_trigger_at.isoformat(),
                "captured_timezone": self.config.timezone,
                "duration_minutes": 15,
                "context": {
                    "source": "rr8_clean_smoke",
                    "friendship_id": friendship["id"],
                },
            },
        )
        shared = result.get("shared_reminder") or {}
        shared_id = shared.get("shared_reminder_id")
        if not isinstance(shared_id, str):
            self.transcript.fail_and_raise(
                phase, "shared reminder API did not return shared_reminder_id", result
            )
        snapshot = self._wait_for(
            phase,
            "shared reminder active with projections and notification fact",
            lambda: self._shared_snapshot(
                shared_id, {account_a["account_id"], account_b["account_id"]}
            ),
        )
        self.transcript.pass_verdict(phase, "shared reminder verified", snapshot)
        return snapshot

    def _shared_snapshot(
        self, shared_id: str, participant_ids: set[str]
    ) -> dict[str, Any] | None:
        queries = verdict_query_specs()
        shared = self.db.one_or_none(
            queries["shared_reminder_active"].params(shared_reminder_id=shared_id)
        )
        if shared is None:
            return None
        projections = self.db.rows(
            queries["shared_reminder_projections"].params(shared_reminder_id=shared_id)
        )
        if {row["account_id"] for row in projections} != participant_ids:
            return None
        facts = self.db.rows(
            queries["notification_fact_without_text_payload"].params(
                shared_reminder_id=shared_id
            )
        )
        if not facts:
            return None
        for fact in facts:
            if not fact["facts_hash"]:
                self.transcript.fail_and_raise(
                    "shared_reminder",
                    "notification_fact missing facts_hash",
                    dict(fact),
                )
            facts_payload = fact.get("facts")
            if isinstance(facts_payload, dict) and isinstance(
                facts_payload.get("payload"), dict
            ):
                if "text" in facts_payload["payload"]:
                    self.transcript.fail_and_raise(
                        "shared_reminder",
                        "notification_fact contains payload.text",
                        dict(fact),
                    )
        return {
            "id": shared["id"],
            "projection_account_ids": sorted(row["account_id"] for row in projections),
            "notification_fact_ids": [row["id"] for row in facts],
        }

    def _fire_path(self, account: dict[str, Any]) -> None:
        phase = "reminder_fire"
        title = f"RR8 fire smoke {self.config.run_id}"
        trigger_time = datetime.now(UTC) + timedelta(
            seconds=self.config.fire_delay_seconds
        )
        result = http_post_json(
            f"{self.config.api_base}/api/reminders/batch",
            {
                "owner_account_id": account["account_id"],
                "items": [
                    {
                        "operation": "create",
                        "content": title,
                        "raw_text": f"Remind me to {title}",
                        "trigger_time": trigger_time.isoformat(),
                        "captured_timezone": self.config.timezone,
                        "duration_minutes": 15,
                        "kind": "timed",
                        "entry_point": "rr8_clean_smoke",
                    }
                ],
            },
        )
        items = result.get("items")
        if (
            not isinstance(items, list)
            or not items
            or items[0].get("state") != "succeeded"
        ):
            self.transcript.fail_and_raise(
                phase, "reminder batch API did not create due reminder", result
            )
        reminder_id = items[0].get("reminder_id")
        if not isinstance(reminder_id, str):
            self.transcript.fail_and_raise(
                phase, "reminder batch API did not return reminder_id", result
            )
        snapshot = self._wait_for(
            phase,
            "scheduler fired reminder and outbound included title",
            lambda: self._fire_snapshot(account["account_id"], reminder_id, title),
            timeout_seconds=max(
                self.config.poll_timeout_seconds,
                self.config.fire_delay_seconds + 120,
            ),
        )
        self.transcript.pass_verdict(phase, "reminder fire verified", snapshot)

    def _fire_snapshot(
        self, account_id: str, reminder_id: str, title: str
    ) -> dict[str, Any] | None:
        queries = verdict_query_specs()
        fire_rows = self.db.rows(
            queries["reminder_fire_delivered"].params(reminder_id=reminder_id)
        )
        if not fire_rows:
            return None
        outbound_rows = self.db.rows(
            queries["outbound_message_containing_title"].params(
                account_id=account_id,
                title_like=f"%{title}%",
            )
        )
        if not outbound_rows:
            return None
        return {
            "reminder_id": reminder_id,
            "fire_ids": [row["id"] for row in fire_rows],
            "outbound_message_ids": [row["id"] for row in outbound_rows],
        }

    def _wait_for(
        self,
        phase: str,
        description: str,
        probe,
        timeout_seconds: float | None = None,
    ):
        deadline = time.monotonic() + (
            timeout_seconds or self.config.poll_timeout_seconds
        )
        last_error = None
        while time.monotonic() < deadline:
            try:
                result = probe()
                if result:
                    return result
            except SmokeVerdictError:
                raise
            except Exception as error:
                last_error = str(error)
            time.sleep(self.config.poll_interval_seconds)
        self.transcript.fail_and_raise(
            phase,
            f"timed out waiting for {description}",
            {"last_error": last_error},
        )


def unordered_pair(account_a: str, account_b: str) -> tuple[str, str]:
    if account_a <= account_b:
        return account_a, account_b
    return account_b, account_a


def http_get_json(url: str) -> dict[str, Any]:
    return _http_json(Request(url, method="GET"))


def http_post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    return _http_json(
        Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
    )


def _http_json(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=15) as response:
            data = response.read()
            if not data:
                return {}
            parsed = json.loads(data.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise SmokeVerdictError("HTTP response JSON body is not an object")
            return parsed
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise SmokeVerdictError(
            f"HTTP {error.code} from {request.full_url}: {body}"
        ) from error
    except URLError as error:
        raise SmokeVerdictError(
            f"cannot reach {request.full_url}: {error.reason}"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clean Coke real-account smoke harness"
    )
    parser.add_argument("--mode", choices=["webhook", "real"], default="webhook")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--evidence-dir",
        default=str(DEFAULT_EVIDENCE_DIR),
        help="JSON transcript output directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        report = run_dry_run(Path(args.evidence_dir))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    config = SmokeConfig.from_env(args)
    runner = CleanSmokeRunner(config)
    path = runner.run()
    print(json.dumps({"status": "passed", "evidence_path": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeVerdictError as error:
        print(
            json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(1)
