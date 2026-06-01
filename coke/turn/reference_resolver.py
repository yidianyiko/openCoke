from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Reference:
    reference_id: str
    text: str
    target_type: str


@dataclass(frozen=True, slots=True)
class ReferenceResolutionCandidate:
    target_type: str
    target_id: str
    label: str


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    reference_id: str
    target_type: str
    target_id: str
    label: str


@dataclass(frozen=True, slots=True)
class ClarificationRequest:
    reference_id: str
    target_type: str
    reason: str
    candidates: tuple[ReferenceResolutionCandidate, ...]


@dataclass(frozen=True, slots=True)
class ReferenceResolutionResult:
    resolved: tuple[ResolvedReference, ...]
    clarifications: tuple[ClarificationRequest, ...]

    def can_mutate(self, reference_id: str) -> bool:
        return any(item.reference_id == reference_id for item in self.resolved)


class ReferenceLookupPort(Protocol):
    def candidates_for(
        self, reference: Reference
    ) -> list[ReferenceResolutionCandidate]: ...


class ReferenceResolver:
    def __init__(self, lookup: ReferenceLookupPort | None = None) -> None:
        self._lookup = lookup

    def resolve_all(self, references: list[Reference]) -> ReferenceResolutionResult:
        if self._lookup is None:
            return ReferenceResolutionResult(resolved=(), clarifications=())

        resolved: list[ResolvedReference] = []
        clarifications: list[ClarificationRequest] = []
        for reference in references:
            candidates = tuple(self._lookup.candidates_for(reference))
            if len(candidates) == 1:
                candidate = candidates[0]
                resolved.append(
                    ResolvedReference(
                        reference_id=reference.reference_id,
                        target_type=candidate.target_type,
                        target_id=candidate.target_id,
                        label=candidate.label,
                    )
                )
                continue
            clarifications.append(
                ClarificationRequest(
                    reference_id=reference.reference_id,
                    target_type=reference.target_type,
                    reason=(
                        "zero_candidates" if not candidates else "multiple_candidates"
                    ),
                    candidates=candidates,
                )
            )
        return ReferenceResolutionResult(
            resolved=tuple(resolved),
            clarifications=tuple(clarifications),
        )
