from __future__ import annotations

from types import SimpleNamespace

from coke.turn.context import ToolProfile, TurnMode, TurnTrigger
from coke.turn.semantic_interpreter import SemanticDecision
from coke.turn.streaming import is_streaming_eligible


def _trigger(
    *,
    trigger_type: str = "InboundTurn",
    mode: TurnMode = TurnMode.INTERACTIVE,
) -> TurnTrigger:
    return TurnTrigger(
        trigger_id="trigger_1",
        trigger_type=trigger_type,
        mode=mode,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={"text": "hello"},
    )


def _decision(
    *,
    intent_family: str = "chit_chat",
    intent_action: str = "chit_chat",
    ambiguity: str = "clear",
) -> SemanticDecision:
    return SemanticDecision(
        reply_necessity="reply_needed",
        intent_family=intent_family,  # type: ignore[arg-type]
        intent_action=intent_action,  # type: ignore[arg-type]
        ambiguity=ambiguity,  # type: ignore[arg-type]
        required_clarification="none",
    )


def _plain_profile() -> ToolProfile:
    return ToolProfile.interactive(SimpleNamespace())


def test_chit_chat_with_none_ambiguity_is_streaming_eligible():
    # Production interpreter emits ambiguity="none" for clean chit-chat turns.
    assert is_streaming_eligible(
        _trigger(), _decision(ambiguity="none"), _plain_profile()
    )


def test_blocking_ambiguity_is_not_streaming_eligible():
    assert not is_streaming_eligible(
        _trigger(), _decision(ambiguity="ambiguous_reference"), _plain_profile()
    )


def test_plain_full_agent_chit_chat_is_streaming_eligible():
    assert is_streaming_eligible(
        _trigger(),
        _decision(),
        _plain_profile(),
    )


def test_reminder_create_is_not_streaming_eligible():
    assert not is_streaming_eligible(
        _trigger(),
        _decision(intent_family="reminder_op", intent_action="create_reminder"),
        _plain_profile(),
    )


def test_reminder_fire_trigger_is_not_streaming_eligible():
    assert not is_streaming_eligible(
        _trigger(trigger_type="ReminderFireTurn", mode=TurnMode.RENDER),
        _decision(),
        _plain_profile(),
    )


def test_notification_render_turn_is_not_streaming_eligible():
    assert not is_streaming_eligible(
        _trigger(trigger_type="NotificationTurn", mode=TurnMode.RENDER),
        _decision(),
        ToolProfile.render(),
    )


def test_social_scheduling_intent_is_not_streaming_eligible():
    assert not is_streaming_eligible(
        _trigger(),
        _decision(
            intent_family="scheduling",
            intent_action="create_shared_reminder",
        ),
        _plain_profile(),
    )
