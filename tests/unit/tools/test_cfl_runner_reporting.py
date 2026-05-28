from types import SimpleNamespace

from tools.agent_smoke import _runner_phase_cross_feature_long_conversation as cfl
from tools.agent_smoke.transcript import Turn


def _turn(
    reply_text: str,
    *,
    turn: int = 1,
    note: str = "note",
    placeholder_received: bool = False,
    late_reply_landed: bool = False,
) -> Turn:
    return Turn(
        turn=turn,
        speaker="alice",
        coke_account_id="ck_alice",
        input_text="input",
        inbound_event_id=f"evt_{turn}",
        reply_text=reply_text,
        output_id=f"out_{turn}",
        elapsed_ms=10,
        note=note,
        placeholder_received=placeholder_received,
        late_reply_landed=late_reply_landed,
    )


def test_base_bug_pattern_late_timeout_precedes_empty_reply():
    turns = [
        _turn(
            "",
            placeholder_received=True,
            late_reply_landed=False,
        )
    ]

    assert (
        cfl._base_bug_pattern(
            turns,
            default="X1",
            mutation_expected=True,
            mutation_happened=False,
        )
        == "BLOCKED-LATE-REPLY-TIMEOUT"
    )


def test_base_bug_pattern_keeps_specific_primary_tag_for_incidental_empty_reply():
    turns = [
        _turn("", note="incidental_empty"),
        _turn("已创建共享提醒。", note="contract_failure"),
    ]

    assert (
        cfl._base_bug_pattern(
            turns,
            default="X5",
            mutation_expected=False,
            mutation_happened=True,
        )
        == "X5"
    )


def test_delivery_anomaly_turns_capture_per_turn_placeholder_and_empty_reply():
    turns = [
        _turn(
            "",
            turn=19,
            note="late_empty",
            placeholder_received=True,
            late_reply_landed=True,
        ),
        _turn(
            "正常回复",
            turn=20,
            note="normal_late",
            placeholder_received=True,
            late_reply_landed=True,
        ),
        _turn("", turn=21, note="real_empty"),
    ]

    assert cfl._delivery_anomaly_turns(turns) == [
        {
            "turn": 1,
            "global_turn": 19,
            "note": "late_empty",
            "reply_text": "",
            "placeholder_received": True,
            "late_reply_landed": True,
            "is_empty_reply": True,
            "output_kind": "empty_reply",
        },
        {
            "turn": 2,
            "global_turn": 20,
            "note": "normal_late",
            "reply_text": "正常回复",
            "placeholder_received": True,
            "late_reply_landed": True,
            "is_empty_reply": False,
            "output_kind": "late_real_reply",
        },
        {
            "turn": 3,
            "global_turn": 21,
            "note": "real_empty",
            "reply_text": "",
            "placeholder_received": False,
            "late_reply_landed": False,
            "is_empty_reply": True,
            "output_kind": "empty_reply",
        },
    ]


def test_reply_records_keep_l3_tail_turns_separate():
    turns = [
        _turn("第一个是 7 点。", turn=19, note="L3_19"),
        _turn("最后一个是 16 点。", turn=20, note="L3_20"),
    ]
    ctx = SimpleNamespace(turns=turns)

    assert cfl._reply_records(ctx, turns) == [
        {"turn": 1, "global_turn": 19, "note": "L3_19", "reply_text": "第一个是 7 点。"},
        {"turn": 2, "global_turn": 20, "note": "L3_20", "reply_text": "最后一个是 16 点。"},
    ]
