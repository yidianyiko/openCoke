from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from agent.agno_agent.runtime._immutability import (
    freeze_mapping,
    freeze_sequence,
    freeze_value,
)

DomainName = Literal["reminder", "scheduling"]
DomainOutcome = Literal[
    "executed",
    "needs_clarification",
    "no_action",
    "rejected",
    "failed",
]
DomainEffect = Literal["none", "read", "write"]
ReplyIntent = Literal[
    "confirm_execution",
    "ask_clarification",
    "report_no_target",
    "report_rejection",
    "report_failure",
    "direct_answer",
]


@dataclass(frozen=True)
class DomainError:
    code: str
    message: str
    retryable: bool
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "detail", freeze_mapping(self.detail))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "detail": _jsonable(self.detail),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> DomainError | None:
        if payload is None:
            return None
        return cls(
            code=str(payload.get("code") or ""),
            message=str(payload.get("message") or ""),
            retryable=bool(payload.get("retryable")),
            detail=_mapping(payload.get("detail")),
        )


@dataclass(frozen=True)
class DomainOperationResult:
    action: str
    ok: bool
    effect: DomainEffect
    entity_type: str
    entity_id: str | None
    facts: Mapping[str, Any] = field(default_factory=dict)
    error: DomainError | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", freeze_mapping(self.facts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "ok": self.ok,
            "effect": self.effect,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "facts": _jsonable(self.facts),
            "error": self.error.to_dict() if self.error else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DomainOperationResult:
        return cls(
            action=str(payload.get("action") or ""),
            ok=bool(payload.get("ok")),
            effect=_literal(payload.get("effect"), {"none", "read", "write"}, "effect"),
            entity_type=str(payload.get("entity_type") or ""),
            entity_id=_optional_str(payload.get("entity_id")),
            facts=_mapping(payload.get("facts")),
            error=DomainError.from_dict(_optional_mapping(payload.get("error"))),
        )


@dataclass(frozen=True)
class ReplyFactRequirement:
    path: str
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "label": self.label}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ReplyFactRequirement:
        return cls(
            path=str(payload.get("path") or ""),
            label=_optional_str(payload.get("label")),
        )


@dataclass(frozen=True)
class ReplyContract:
    intent: ReplyIntent
    required_facts: Sequence[ReplyFactRequirement] = field(default_factory=tuple)
    allow_rephrase: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_facts",
            freeze_sequence(self.required_facts),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "required_facts": [item.to_dict() for item in self.required_facts],
            "allow_rephrase": self.allow_rephrase,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ReplyContract:
        return cls(
            intent=_literal(
                payload.get("intent"),
                {
                    "confirm_execution",
                    "ask_clarification",
                    "report_no_target",
                    "report_rejection",
                    "report_failure",
                    "direct_answer",
                },
                "intent",
            ),
            required_facts=tuple(
                ReplyFactRequirement.from_dict(_mapping(item))
                for item in _sequence(payload.get("required_facts"))
            ),
            allow_rephrase=bool(payload.get("allow_rephrase", True)),
        )


@dataclass(frozen=True)
class DomainExecutionResult:
    domain: DomainName
    outcome: DomainOutcome
    operations: Sequence[DomainOperationResult] = field(default_factory=tuple)
    missing_fields: Sequence[str] = field(default_factory=tuple)
    safety_boundary: str | None = None
    reply_contract: ReplyContract = field(
        default_factory=lambda: ReplyContract(
            intent="direct_answer",
            required_facts=(),
            allow_rephrase=True,
        )
    )
    error: DomainError | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", freeze_sequence(self.operations))
        object.__setattr__(
            self,
            "missing_fields",
            freeze_sequence(tuple(str(item) for item in self.missing_fields)),
        )
        object.__setattr__(
            self,
            "reply_contract",
            freeze_value(self.reply_contract),
        )
        violations = self.validate_invariants()
        if violations:
            raise ValueError("; ".join(violations))

    def validate_invariants(self) -> Sequence[str]:
        violations: list[str] = []
        if self.outcome == "executed" and not any(
            operation.ok for operation in self.operations
        ):
            violations.append("executed requires at least one successful operation")
        if (
            self.outcome == "needs_clarification"
            and not self.missing_fields
            and self.safety_boundary is None
        ):
            violations.append(
                "needs_clarification requires missing_fields or safety_boundary"
            )
        if self.outcome == "rejected" and self.safety_boundary is None:
            violations.append("rejected requires safety_boundary")
        if self.outcome == "failed" and self.error is None:
            violations.append("failed requires error")
        if self.outcome == "no_action" and tuple(self.operations) != ():
            violations.append("no_action requires operations == ()")
        return tuple(violations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "outcome": self.outcome,
            "operations": [operation.to_dict() for operation in self.operations],
            "missing_fields": list(self.missing_fields),
            "safety_boundary": self.safety_boundary,
            "reply_contract": self.reply_contract.to_dict(),
            "error": self.error.to_dict() if self.error else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DomainExecutionResult:
        return cls(
            domain=_literal(
                payload.get("domain"),
                {"reminder", "scheduling"},
                "domain",
            ),
            outcome=_literal(
                payload.get("outcome"),
                {
                    "executed",
                    "needs_clarification",
                    "no_action",
                    "rejected",
                    "failed",
                },
                "outcome",
            ),
            operations=tuple(
                DomainOperationResult.from_dict(_mapping(item))
                for item in _sequence(payload.get("operations"))
            ),
            missing_fields=tuple(
                str(item) for item in _sequence(payload.get("missing_fields"))
            ),
            safety_boundary=_optional_str(payload.get("safety_boundary")),
            reply_contract=ReplyContract.from_dict(
                _mapping(payload.get("reply_contract"))
            ),
            error=DomainError.from_dict(_optional_mapping(payload.get("error"))),
        )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _literal(value: Any, allowed: set[str], field_name: str) -> Any:
    text = str(value or "")
    if text in allowed:
        return text
    allowed_values = ", ".join(sorted(allowed))
    raise ValueError(
        f"unsupported {field_name}: {text!r}; expected one of: {allowed_values}"
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
