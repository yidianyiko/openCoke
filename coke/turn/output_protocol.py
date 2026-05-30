from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


OutputKind = Literal["reply", "no_reply"]


@dataclass(frozen=True, slots=True)
class ValidatedOutput:
    valid: bool
    kind: OutputKind | None
    segments: tuple[str, ...] = ()
    reason_code: str | None = None


class OutputProtocolValidator:
    def __init__(self) -> None:
        self.rewrite_invocations = 0

    def validate_first_answer(self, output: Mapping[str, Any] | None) -> ValidatedOutput:
        if not isinstance(output, Mapping):
            return self._invalid()

        output_type = output.get("type")
        if output_type == "reply":
            segments = output.get("segments")
            if not isinstance(segments, list) or not 1 <= len(segments) <= 3:
                return self._invalid()
            clean_segments: list[str] = []
            for segment in segments:
                if not isinstance(segment, str) or not segment.strip():
                    return self._invalid()
                clean_segments.append(segment)
            return ValidatedOutput(
                valid=True,
                kind="reply",
                segments=tuple(clean_segments),
                reason_code="reply_ready",
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

    def _invalid(self) -> ValidatedOutput:
        return ValidatedOutput(
            valid=False,
            kind=None,
            reason_code="invalid_output_protocol",
        )
