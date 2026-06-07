from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

OutputKind = Literal["reply", "no_reply"]

SOCIAL_SCHEDULING_ALLOWED_CLAIMS: dict[str, set[str]] = {
    "created_active": {"active_created"},
    "duplicate_active": {"active_duplicate"},
    "blocked_unmatched_friend": {"blocked_unmatched_friend"},
    "blocked_ambiguous_friend": {"blocked_ambiguous_friend"},
    "blocked_receiver_conflict": {"blocked_receiver_conflict"},
    "blocked_unreachable_participant": {"blocked_unreachable_participant"},
    "needs_participants": {"needs_participants"},
    "needs_title": {"needs_title"},
    "needs_time": {"needs_time"},
    "needs_context": {"needs_context"},
    "needs_past_time_confirmation": {"needs_past_time_confirmation"},
    "needs_incomplete_date_clarification": {
        "needs_incomplete_date_clarification"
    },
    "invalid": {"failed"},
    "staged_pending_close": {"no_success_claim"},
}

SOCIAL_SCHEDULING_ACTIVE_STATUSES = {"created_active", "duplicate_active"}


@dataclass(frozen=True, slots=True)
class ValidatedOutput:
    valid: bool
    kind: OutputKind | None
    segments: tuple[str, ...] = ()
    reason_code: str | None = None
    retry_guidance: str | None = None
    domain_claim: Mapping[str, Any] | None = None


class OutputProtocolValidator:
    def __init__(self) -> None:
        self.rewrite_invocations = 0

    def validate_first_answer(
        self, output: Mapping[str, Any] | None
    ) -> ValidatedOutput:
        if not isinstance(output, Mapping):
            return self._invalid()

        if (
            output.get("type") == "invalid_output_protocol"
            and output.get("reason") == "serialized_tool_call_output"
        ):
            return self._invalid(
                "serialized_tool_call_output_requires_native_tool_call"
            )
        if (
            output.get("type") == "invalid_output_protocol"
            and output.get("reason") == "state_change_reply_without_tool_call"
        ):
            return self._invalid("state_change_reply_requires_native_tool_call")

        output_type = output.get("type")
        if output_type == "reply":
            segments = output.get("segments")
            if not isinstance(segments, list) or not 1 <= len(segments) <= 3:
                return self._invalid(
                    "reply_segments_must_contain_1_to_3_non_empty_strings"
                )
            clean_segments: list[str] = []
            for segment in segments:
                if not isinstance(segment, str) or not segment.strip():
                    return self._invalid(
                        "reply_segments_must_contain_1_to_3_non_empty_strings"
                    )
                clean_segments.append(segment)
            domain_claim = output.get("domain_claim")
            if domain_claim is not None and not isinstance(domain_claim, Mapping):
                return self._invalid("domain_claim_must_be_object")
            return ValidatedOutput(
                valid=True,
                kind="reply",
                segments=tuple(clean_segments),
                reason_code="reply_ready",
                domain_claim=domain_claim,
            )

        if output_type == "no_reply":
            if output.get("reason") != "intentional_no_reply":
                return self._invalid()
            return ValidatedOutput(
                valid=True,
                kind="no_reply",
                reason_code="intentional_no_reply",
            )

        return self._invalid()

    def validate_social_scheduling_claim(
        self,
        validated: ValidatedOutput,
        *,
        outcomes: Sequence[Mapping[str, Any]],
        claim_required: bool = False,
        active_shared_reminder_exists: Callable[[str], bool] | None = None,
    ) -> ValidatedOutput:
        if not validated.valid:
            return validated
        claim = validated.domain_claim
        if not outcomes:
            if claim_required:
                return self._invalid("social_scheduling_outcome_missing")
            if (
                isinstance(claim, Mapping)
                and claim.get("domain") == "social_scheduling"
            ):
                return self._invalid("social_scheduling_outcome_missing")
            return validated
        if not isinstance(claim, Mapping) or claim.get("domain") != "social_scheduling":
            return self._invalid("social_scheduling_claim_required")

        outcome_id = claim.get("outcome_id")
        outcome = _find_social_scheduling_outcome(outcomes, outcome_id)
        if outcome is None:
            return self._invalid("social_scheduling_outcome_missing")

        outcome_status = outcome.get("status")
        if claim.get("status") != outcome_status:
            return self._invalid("social_scheduling_claim_status_mismatch")

        allowed_claims = SOCIAL_SCHEDULING_ALLOWED_CLAIMS.get(str(outcome_status), set())
        if claim.get("claim") not in allowed_claims:
            return self._invalid("social_scheduling_claim_not_allowed")

        outcome_blocker = outcome.get("blocker")
        if outcome_blocker is not None and claim.get("blocker") != outcome_blocker:
            return self._invalid("social_scheduling_claim_blocker_mismatch")

        if outcome_status in SOCIAL_SCHEDULING_ACTIVE_STATUSES:
            shared_reminder_id = outcome.get("shared_reminder_id")
            if not isinstance(shared_reminder_id, str) or not shared_reminder_id:
                return self._invalid(
                    "social_scheduling_active_shared_reminder_missing"
                )
            if (
                active_shared_reminder_exists is not None
                and not active_shared_reminder_exists(shared_reminder_id)
            ):
                return self._invalid(
                    "social_scheduling_active_shared_reminder_missing"
                )

        return validated

    def _invalid(self, retry_guidance: str | None = None) -> ValidatedOutput:
        return ValidatedOutput(
            valid=False,
            kind=None,
            reason_code="invalid_output_protocol",
            retry_guidance=retry_guidance,
        )


def _find_social_scheduling_outcome(
    outcomes: Sequence[Mapping[str, Any]],
    outcome_id: Any,
) -> Mapping[str, Any] | None:
    if not isinstance(outcome_id, str) or not outcome_id:
        return None
    for outcome in outcomes:
        if outcome.get("outcome_id") == outcome_id:
            return outcome
    return None
