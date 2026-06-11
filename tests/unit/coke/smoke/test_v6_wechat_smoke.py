from __future__ import annotations

import pytest

from scripts.smoke.v6_cases import CASES, FIRST_ROUND, REQUESTER_ONLY, case_by_id
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
def test_corpus_full_v6_coverage():
    groups: dict[str, int] = {}
    for c in CASES:
        groups[c.group] = groups.get(c.group, 0) + 1
    assert groups == {
        "A_personal_reminder": 5,
        "B_recurring": 3,
        "C_availability": 3,
        "D_self_schedule": 5,
        "E_scheduling": 8,
        "F_chat": 2,
    }
    assert len(CASES) == 26
    assert len({c.case_id for c in CASES}) == 26


def test_first_round_and_requester_only_resolve():
    for cid in (*FIRST_ROUND, *REQUESTER_ONLY):
        assert case_by_id(cid).case_id == cid
    # requester-only must exclude any friend/shared case
    for cid in REQUESTER_ONLY:
        c = case_by_id(cid)
        assert not c.needs_friends and not c.fixtures.shared


def test_gap_cases_are_known():
    assert {c.case_id for c in CASES if c.expect.gap} == {
        "reminder_005",
        "scheduling_conflict_001",
    }


# --------------------------------------------------------------------------
# WeChat channel payload (validated against the real connector shape)
# --------------------------------------------------------------------------
def test_payload_uses_dashless_account_and_connector_fields():
    ident = WeChatIdentity(
        "ae02ff01-6fcd-4d39-a189-e51c8c8a31e6", "o9cq@im.wechat", "olivers"
    )
    p = wechat_payload(identity=ident, text="hi", message_id="m1")
    assert set(p) == {
        "wxid",
        "account_id",
        "message_id",
        "text",
        "sender_name",
        "session_id",
        "context_token",
    }
    assert p["account_id"] == "ae02ff016fcd4d39a189e51c8c8a31e6"  # dashless


def test_identity_parse_requires_account_and_wxid():
    ident = WeChatIdentity.parse('{"account_id":"a-b","wxid":"w","display_name":"X"}')
    assert ident.account_id == "a-b" and ident.wxid == "w"
    with pytest.raises(ValueError):
        WeChatIdentity.parse('{"wxid":"w"}')


def test_resolve_span_shapes():
    s, e = _resolve_span("今天 08:00")
    assert s.hour == 8 and e is None
    s2, e2 = _resolve_span("14:00-15:00")
    assert s2.hour == 14 and e2.hour == 15


def test_dry_run_validates():
    r = run_dry_run(list(CASES))
    assert r["status"] == "dry-run-ok" and r["case_count"] == 26
    assert set(r["sample_webhook_payload"]) >= {"wxid", "account_id", "session_id"}


# --------------------------------------------------------------------------
# Verdict logic (offline)
# --------------------------------------------------------------------------
def _smoke(tmp_path) -> V6WeChatSmoke:
    cfg = V6SmokeConfig(
        api_base="https://dry.run",
        db_url="postgresql+psycopg://dry/run",
        requester=WeChatIdentity("a-b-c", "w", "Eva"),
        run_id="t",
        evidence_dir=tmp_path,
    )
    return V6WeChatSmoke(cfg)


_BASE = {
    "materialized_ops": [],
    "disposition": "replied",
    "has_outbound": True,
    "new_reminders": [],
    "removed_reminders": [],
    "new_shared": [],
    "removed_shared": [],
    "updated_shared": [],
}


def test_forbidden_create_fails_even_for_gap(tmp_path):
    smoke = _smoke(tmp_path)
    case = case_by_id("scheduling_conflict_001")  # gap; forbids reminder_create
    with pytest.raises(SmokeVerdictError):
        smoke._assert_case(case, {**_BASE, "new_reminders": ["r1"]})


def test_gap_case_records_behavior(tmp_path):
    smoke = _smoke(tmp_path)
    smoke._assert_case(case_by_id("scheduling_conflict_001"), {**_BASE})
    assert "expected_gap" in smoke.transcript.verdicts[-1]["message"]


def test_create_reminder_needs_new_row(tmp_path):
    smoke = _smoke(tmp_path)
    case = case_by_id("reminder_001")
    with pytest.raises(SmokeVerdictError):
        smoke._assert_case(case, {**_BASE})
    smoke._assert_case(case, {**_BASE, "new_reminders": ["r1"]})
    assert smoke.transcript.verdicts[-1]["status"] == "passed"


def test_chat_must_not_create(tmp_path):
    smoke = _smoke(tmp_path)
    case = case_by_id("chat_001")
    with pytest.raises(SmokeVerdictError):
        smoke._assert_case(case, {**_BASE, "new_reminders": ["r1"]})
    smoke._assert_case(case, {**_BASE})
    assert smoke.transcript.verdicts[-1]["status"] == "passed"


def test_update_shared_requires_existing_row_update_without_create_or_cancel(tmp_path):
    smoke = _smoke(tmp_path)
    case = case_by_id("scheduling_reschedule_001")
    with pytest.raises(SmokeVerdictError):
        smoke._assert_case(case, {**_BASE})
    smoke._assert_case(
        case,
        {
            **_BASE,
            "materialized_ops": ["social_scheduling.update_shared_reminder"],
            "updated_shared": ["sr1"],
        },
    )
    assert smoke.transcript.verdicts[-1]["status"] == "passed"
