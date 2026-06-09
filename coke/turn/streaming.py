from __future__ import annotations

from coke.turn.context import ToolProfile, TurnTrigger
from coke.turn.semantic_interpreter import SemanticDecision

_CONVERSATIONAL_INTENT_FAMILIES = frozenset({"chit_chat"})
_CONVERSATIONAL_INTENT_ACTIONS = frozenset({"chit_chat", "none"})


def is_streaming_eligible(
    trigger: TurnTrigger,
    semantic_decision: SemanticDecision,
    tool_profile: ToolProfile,
) -> bool:
    if trigger.trigger_type != "InboundTurn":
        return False
    if trigger.mode != "interactive":
        return False
    if tool_profile.constrained:
        return False
    if semantic_decision.reply_necessity != "reply_needed":
        return False
    if semantic_decision.ambiguity != "clear":
        return False
    if semantic_decision.required_clarification != "none":
        return False
    if semantic_decision.intent_family not in _CONVERSATIONAL_INTENT_FAMILIES:
        return False
    if semantic_decision.intent_action not in _CONVERSATIONAL_INTENT_ACTIONS:
        return False
    return True
