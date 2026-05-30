from __future__ import annotations

from coke.turn.output_protocol import OutputProtocolValidator


def test_output_protocol_accepts_reply_segments_and_intentional_no_reply():
    validator = OutputProtocolValidator()

    reply = validator.validate_first_answer(
        {"type": "reply", "segments": ["one", "two"]}
    )
    no_reply = validator.validate_first_answer(
        {"type": "no_reply", "reason": "intentional_no_reply"}
    )

    assert reply.valid is True
    assert reply.kind == "reply"
    assert reply.segments == ("one", "two")
    assert no_reply.valid is True
    assert no_reply.kind == "no_reply"
    assert no_reply.reason_code == "intentional_no_reply"
    assert validator.rewrite_invocations == 0


def test_output_protocol_rejects_empty_malformed_and_structurally_blocked_output():
    validator = OutputProtocolValidator()

    empty = validator.validate_first_answer(None)
    malformed = validator.validate_first_answer({"type": "reply", "segments": []})
    blocked = validator.validate_first_answer(
        {"type": "blocked", "reason": "tool_policy"}
    )

    assert empty.valid is False
    assert empty.reason_code == "invalid_output_protocol"
    assert malformed.valid is False
    assert malformed.reason_code == "invalid_output_protocol"
    assert blocked.valid is False
    assert blocked.reason_code == "invalid_output_protocol"
    assert validator.rewrite_invocations == 0
