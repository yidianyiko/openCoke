from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from coke.turn.context import TurnTrigger


class PreLLMGatePort(Protocol):
    def evaluate(self, trigger: TurnTrigger) -> GateDecision: ...


@dataclass(frozen=True, slots=True)
class GateDecision:
    permitted: bool
    trust_facts: dict[str, Any] = field(default_factory=dict)
    denial_reason: str | None = None
    access_facts: dict[str, Any] = field(default_factory=dict)
    activation_guidance_required: bool = False

    @classmethod
    def allowed(
        cls,
        *,
        trust_facts: dict[str, Any] | None = None,
        activation_guidance_required: bool = False,
    ) -> GateDecision:
        return cls(
            permitted=True,
            trust_facts=trust_facts or {},
            activation_guidance_required=activation_guidance_required,
        )

    @classmethod
    def denied(
        cls,
        *,
        denial_reason: str,
        access_facts: dict[str, Any] | None = None,
    ) -> GateDecision:
        return cls(
            permitted=False,
            denial_reason=denial_reason,
            access_facts=access_facts or {},
        )


class PreLLMGateService:
    def __init__(self, gate_port: PreLLMGatePort) -> None:
        self._gate_port = gate_port

    def evaluate(self, trigger: TurnTrigger) -> GateDecision:
        return self._gate_port.evaluate(trigger)
