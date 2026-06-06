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


def test_output_protocol_reports_segment_count_guidance_for_retry():
    validator = OutputProtocolValidator()

    too_many_segments = validator.validate_first_answer(
        {"type": "reply", "segments": ["one", "two", "three", "four"]}
    )

    assert too_many_segments.valid is False
    assert too_many_segments.reason_code == "invalid_output_protocol"
    assert (
        too_many_segments.retry_guidance
        == "reply_segments_must_contain_1_to_3_non_empty_strings"
    )


def test_output_protocol_reports_serialized_tool_call_guidance_for_retry():
    validator = OutputProtocolValidator()

    serialized_tool_call = validator.validate_first_answer(
        {
            "type": "invalid_output_protocol",
            "reason": "serialized_tool_call_output",
        }
    )

    assert serialized_tool_call.valid is False
    assert serialized_tool_call.reason_code == "invalid_output_protocol"
    assert (
        serialized_tool_call.retry_guidance
        == "serialized_tool_call_output_requires_native_tool_call"
    )


def test_output_protocol_reports_state_change_without_tool_guidance_for_retry():
    validator = OutputProtocolValidator()

    state_change_claim = validator.validate_first_answer(
        {
            "type": "invalid_output_protocol",
            "reason": "state_change_reply_without_tool_call",
        }
    )

    assert state_change_claim.valid is False
    assert state_change_claim.reason_code == "invalid_output_protocol"
    assert (
        state_change_claim.retry_guidance
        == "state_change_reply_requires_native_tool_call"
    )


def test_social_scheduling_claim_matches_created_outcome():
    validator = OutputProtocolValidator()
    validated = validator.validate_first_answer(
        {
            "type": "reply",
            "segments": ["done"],
            "domain_claim": {
                "domain": "social_scheduling",
                "outcome_id": "outcome-1",
                "status": "created_active",
                "claim": "active_created",
            },
        }
    )

    result = validator.validate_social_scheduling_claim(
        validated,
        outcomes=[
            {
                "outcome_id": "outcome-1",
                "operation": "shared_reminder_create",
                "status": "created_active",
            }
        ],
    )

    assert result.valid is True
    assert result.domain_claim["claim"] == "active_created"


def test_social_scheduling_claim_rejects_staged_pending_close_success():
    validator = OutputProtocolValidator()
    validated = validator.validate_first_answer(
        {
            "type": "reply",
            "segments": ["done"],
            "domain_claim": {
                "domain": "social_scheduling",
                "outcome_id": "outcome-1",
                "status": "staged_pending_close",
                "claim": "active_created",
            },
        }
    )

    result = validator.validate_social_scheduling_claim(
        validated,
        outcomes=[
            {
                "outcome_id": "outcome-1",
                "operation": "shared_reminder_create",
                "status": "staged_pending_close",
            }
        ],
    )

    assert result.valid is False
    assert result.retry_guidance == "social_scheduling_claim_not_allowed"


def test_social_scheduling_claim_rejects_missing_claim_when_required():
    validator = OutputProtocolValidator()
    validated = validator.validate_first_answer({"type": "reply", "segments": ["ok"]})

    result = validator.validate_social_scheduling_claim(
        validated,
        outcomes=[
            {
                "outcome_id": "outcome-1",
                "operation": "shared_reminder_create",
                "status": "blocked_unmatched_friend",
                "blocker": "unmatched_friend",
            }
        ],
    )

    assert result.valid is False
    assert result.retry_guidance == "social_scheduling_claim_required"


def test_social_scheduling_claim_rejects_blocker_mismatch():
    validator = OutputProtocolValidator()
    validated = validator.validate_first_answer(
        {
            "type": "reply",
            "segments": ["blocked"],
            "domain_claim": {
                "domain": "social_scheduling",
                "outcome_id": "outcome-1",
                "status": "blocked_unmatched_friend",
                "claim": "blocked_unmatched_friend",
                "blocker": "ambiguous_friend",
            },
        }
    )

    result = validator.validate_social_scheduling_claim(
        validated,
        outcomes=[
            {
                "outcome_id": "outcome-1",
                "operation": "shared_reminder_create",
                "status": "blocked_unmatched_friend",
                "blocker": "unmatched_friend",
            }
        ],
    )

    assert result.valid is False
    assert result.retry_guidance == "social_scheduling_claim_blocker_mismatch"
