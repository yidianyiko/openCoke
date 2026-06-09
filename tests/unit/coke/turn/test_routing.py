from __future__ import annotations

from dataclasses import dataclass

from coke.turn.routing import derive_route


@dataclass(frozen=True, slots=True)
class Decision:
    reply_necessity: str = "reply_needed"
    intent_action: str = "list_reminders"
    ambiguity: str = "clear"
    required_clarification: str = "none"
    list_is_plain: bool = True


def test_plain_clear_list_routes_to_prepared_list():
    assert derive_route(Decision()) == "prepared_list"


def test_plain_list_with_none_ambiguity_routes_to_prepared_list():
    # Production interpreter emits ambiguity="none" (not "clear") for unambiguous
    # plain list queries. Both mean "no blocking ambiguity" and must route.
    assert derive_route(Decision(ambiguity="none")) == "prepared_list"


def test_blocking_ambiguity_does_not_route_to_prepared_list():
    assert derive_route(Decision(ambiguity="ambiguous_reference")) == "full_agent"


def test_filtered_list_routes_to_full_agent():
    assert derive_route(Decision(list_is_plain=False)) == "full_agent"


def test_required_clarification_routes_to_clarification():
    assert (
        derive_route(Decision(required_clarification="ask_trigger_time"))
        == "clarification"
    )


def test_intentional_no_reply_routes_to_no_reply():
    assert derive_route(Decision(reply_necessity="intentional_no_reply")) == "no_reply"


def test_create_reminder_routes_to_full_agent():
    assert derive_route(Decision(intent_action="create_reminder")) == "full_agent"


def test_route_does_not_read_confidence_or_user_text():
    class Probe:
        reply_necessity = "reply_needed"
        intent_action = "list_reminders"
        ambiguity = "clear"
        required_clarification = "none"
        list_is_plain = True

        def __getattr__(self, name: str):
            if name in {"confidence", "text", "user_text", "payload", "raw_text"}:
                raise AssertionError(f"derive_route must not read {name}")
            raise AttributeError(name)

    assert derive_route(Probe()) == "prepared_list"
