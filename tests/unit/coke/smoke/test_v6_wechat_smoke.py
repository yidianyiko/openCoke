from __future__ import annotations

from datetime import datetime

import pytest

from coke.turn.v2.param_schema import allowed_actions_from_schema
from scripts.smoke import v6_cases
from scripts.smoke.v6_cases import CASES, FIRST_ROUND, V6Case, case_by_id
from scripts.smoke.v6_wechat_smoke import (
    SmokeVerdictError,
    V6SmokeConfig,
    V6WeChatSmoke,
    WeChatIdentity,
    _resolve_span,
    run_dry_run,
    wechat_payload,
)


# --------------------------------------------------------------------------
# Corpus integrity
# --------------------------------------------------------------------------
def test_corpus_has_unique_ids_and_full_v6_coverage():
    ids = [c.case_id for c in CASES]
    assert len(ids) == len(set(ids))
    groups: dict[str, int] = {}
    for c in CASES:
        groups[c.group] = groups.get(c.group, 0) + 1
    # The v6 doc: A5 B3 C3 D5 E8 F2 = 26 cases.
    assert groups == {
        "A_personal_reminder": 5,
        "B_recurring": 3,
        "C_availability": 3,
        "D_self_schedule": 5,
        "E_scheduling": 8,
        "F_chat": 2,
    }
    assert len(CASES) == 26


def test_all_ops_exist_in_live_action_schema():
    valid = {
        f"{d}.{op}"
        for d, ops in allowed_actions_from_schema().items()
        for op in ops
    }
    for c in CASES:
        for op in (*c.expect.staged_ops, *c.expect.forbid_ops):
            assert op in valid, f"{c.case_id}: {op} not in action schema"


def test_first_round_ids_all_resolve():
    for cid in FIRST_ROUND:
        assert case_by_id(cid).case_id == cid


def test_gap_cases_are_the_known_capability_gaps():
    gap_ids = {c.case_id for c in CASES if c.expect.gap}
    assert gap_ids == {
        "reminder_005",
        "calendar_self_create_002",
        "scheduling_conflict_001",
        "scheduling_reschedule_001",
        "scheduling_reschedule_002",
    }


# --------------------------------------------------------------------------
# Channel payload / identity
# --------------------------------------------------------------------------
def test_wechat_payload_uses_provider_field_names():
    identity = WeChatIdentity("requester", "wxid_abc", "Eva")
    payload = wechat_payload(identity=identity, text="hi", message_id="m1")
    assert set(payload) == {"wxid", "message_id", "text", "sender_name"}
    assert payload["wxid"] == "wxid_abc"
    assert payload["sender_name"] == "Eva"


def test_identity_parse_plain_and_json():
    plain = WeChatIdentity.parse("requester", "wxid_plain")
    assert plain.wxid == "wxid_plain"
    rich = WeChatIdentity.parse("requester", '{"wxid": "wxid_j", "push_name": "李"}')
    assert rich.wxid == "wxid_j"
    assert rich.display_name == "李"
    with pytest.raises(ValueError):
        WeChatIdentity.parse("requester", "   ")


# --------------------------------------------------------------------------
# Fixture time-phrase resolution
# --------------------------------------------------------------------------
def test_resolve_span_handles_v6_phrase_shapes():
    start, end = _resolve_span("今天 08:00", "Asia/Shanghai")
    assert start.hour == 8 and end is None
    s2, e2 = _resolve_span("14:00-15:00", "Asia/Shanghai")
    assert s2.hour == 14 and e2 is not None and e2.hour == 15
    s3, _ = _resolve_span("明天 16:00-17:00", "Asia/Shanghai")
    today = datetime.now().astimezone()
    assert s3.day != today.day or s3.hour == 16  # shifted a day


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------
def test_dry_run_full_corpus_validates():
    report = run_dry_run(list(CASES))
    assert report["status"] == "dry-run-ok"
    assert report["case_count"] == 26
    assert set(report["sample_webhook_payload"]) == {
        "wxid",
        "message_id",
        "text",
        "sender_name",
    }


# --------------------------------------------------------------------------
# Verdict assertion logic (offline, no network/DB)
# --------------------------------------------------------------------------
def _smoke(tmp_path) -> V6WeChatSmoke:
    config = V6SmokeConfig(
        api_base="https://dry.run",
        db_url="postgresql+psycopg://dry/run",
        requester=WeChatIdentity("requester", "wxid_x", "Eva"),
        mode="webhook",
        run_id="test",
        evidence_dir=tmp_path,
    )
    return V6WeChatSmoke(config)


_PASS_VERDICT = {
    "materialized_ops": [],
    "disposition": "replied",
    "has_outbound": True,
    "has_pending_clarification": False,
    "new_reminders": [],
    "new_shared": [],
}


def test_forbidden_op_fails_even_for_gap_case(tmp_path):
    smoke = _smoke(tmp_path)
    case = case_by_id("scheduling_conflict_001")  # gap case, forbids reminder.create
    verdict = {**_PASS_VERDICT, "materialized_ops": ["reminder.create"]}
    with pytest.raises(SmokeVerdictError):
        smoke._assert_case(case, verdict)


def test_gap_case_records_without_asserting_desired_behavior(tmp_path):
    smoke = _smoke(tmp_path)
    case = case_by_id("scheduling_reschedule_001")
    verdict = {**_PASS_VERDICT, "materialized_ops": []}
    smoke._assert_case(case, verdict)  # must not raise
    assert smoke.transcript.verdicts[-1]["status"] == "passed"
    assert "expected_gap" in smoke.transcript.verdicts[-1]["message"]


def test_create_reminder_requires_a_new_row(tmp_path):
    smoke = _smoke(tmp_path)
    case = case_by_id("reminder_001")
    no_row = {**_PASS_VERDICT, "materialized_ops": ["reminder.create"]}
    with pytest.raises(SmokeVerdictError):
        smoke._assert_case(case, no_row)
    with_row = {
        **_PASS_VERDICT,
        "materialized_ops": ["reminder.create"],
        "new_reminders": ["r1"],
    }
    smoke._assert_case(case, with_row)
    assert smoke.transcript.verdicts[-1]["status"] == "passed"


def test_chat_case_must_not_create_rows(tmp_path):
    smoke = _smoke(tmp_path)
    case = case_by_id("chat_001")
    bad = {**_PASS_VERDICT, "new_reminders": ["r1"]}
    with pytest.raises(SmokeVerdictError):
        smoke._assert_case(case, bad)
    good = {**_PASS_VERDICT}
    smoke._assert_case(case, good)
    assert smoke.transcript.verdicts[-1]["status"] == "passed"
