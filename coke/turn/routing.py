from __future__ import annotations

from typing import Literal

from coke.turn.semantic_interpreter import SemanticDecision

Route = Literal["prepared_list", "clarification", "no_reply", "full_agent"]


def derive_route(decision: SemanticDecision) -> Route:
    if (
        decision.intent_action == "list_reminders"
        and decision.ambiguity in {"clear", "none"}
        and decision.required_clarification == "none"
        and decision.list_is_plain
        and decision.reply_necessity == "reply_needed"
    ):
        return "prepared_list"
    if decision.required_clarification != "none":
        return "clarification"
    if decision.reply_necessity == "intentional_no_reply":
        return "no_reply"
    return "full_agent"
