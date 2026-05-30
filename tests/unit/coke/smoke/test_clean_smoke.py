from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.smoke.clean_smoke import (
    SenderIdentity,
    SmokeTranscript,
    SmokeVerdictError,
    evolution_payload,
    run_dry_run,
)


def test_sender_env_accepts_plain_jid_and_json_identity():
    plain = SenderIdentity.parse("alice", "15555550123@s.whatsapp.net")
    rich = SenderIdentity.parse(
        "bob",
        json.dumps(
            {
                "remote_jid": "15555550456@s.whatsapp.net",
                "push_name": "Bob Smoke",
            }
        ),
    )

    assert plain.remote_jid == "15555550123@s.whatsapp.net"
    assert plain.provider_subject == "15555550123"
    assert plain.push_name == "alice"
    assert rich.remote_jid == "15555550456@s.whatsapp.net"
    assert rich.provider_subject == "15555550456"
    assert rich.push_name == "Bob Smoke"


def test_evolution_payload_matches_clean_provider_shape():
    sender = SenderIdentity.parse("alice", "15555550123@s.whatsapp.net")

    payload = evolution_payload(
        sender=sender,
        text="RR8 hello",
        event_id="rr8_msg_1",
        timestamp=1_779_999_999,
        instance="coke",
    )

    assert payload == {
        "event": "messages.upsert",
        "instance": "coke",
        "data": {
            "key": {
                "remoteJid": "15555550123@s.whatsapp.net",
                "fromMe": False,
                "id": "rr8_msg_1",
            },
            "pushName": "alice",
            "message": {"conversation": "RR8 hello"},
            "messageTimestamp": 1_779_999_999,
        },
    }


def test_dry_run_compiles_all_verdict_queries_against_schema(tmp_path: Path):
    report = run_dry_run(evidence_dir=tmp_path)

    assert report["status"] == "passed"
    query_names = {item["name"] for item in report["compiled_queries"]}
    assert {
        "first_contact_account",
        "first_contact_turn_disposition",
        "personal_reminder_unique",
        "active_friendship",
        "shared_reminder_projections",
        "notification_fact_without_text_payload",
        "reminder_fire_delivered",
    } <= query_names
    compiled_sql = "\n".join(item["sql"] for item in report["compiled_queries"])
    assert "inputmessages" not in compiled_sql
    assert "outputmessages" not in compiled_sql
    assert "gateway" not in compiled_sql.lower()
    assert Path(report["evidence_path"]).is_file()


def test_verdict_failure_is_recorded_and_stops(tmp_path: Path):
    transcript = SmokeTranscript(run_id="rr8_test", evidence_dir=tmp_path)

    with pytest.raises(SmokeVerdictError) as exc_info:
        transcript.fail_and_raise(
            phase="personal_reminder",
            message="expected exactly one active reminder",
            details={"count": 0},
        )

    assert "personal_reminder" in str(exc_info.value)
    assert transcript.evidence_path is not None
    evidence = json.loads(transcript.evidence_path.read_text())
    assert evidence["status"] == "failed"
    assert evidence["verdicts"][-1] == {
        "phase": "personal_reminder",
        "status": "failed",
        "message": "expected exactly one active reminder",
        "details": {"count": 0},
    }
