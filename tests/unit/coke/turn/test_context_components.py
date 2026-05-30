from __future__ import annotations

from coke.turn.focus import FocusResolver, MessageSubject
from coke.turn.memory import MemoryManager
from coke.turn.reference_resolver import (
    Reference,
    ReferenceResolutionCandidate,
    ReferenceResolver,
)


class FakeSubjectRepository:
    def __init__(self) -> None:
        self.subject = MessageSubject(
            subject_type="reminder_fire",
            object_ids=("fire_1", "fire_2"),
            ordered=True,
        )

    def last_rendered_subject(self, conversation_id: str):
        return self.subject


class FakeReferenceLookup:
    def __init__(self) -> None:
        self.responses = {
            "clear": [ReferenceResolutionCandidate("friend", "friend_1", "Ana")],
            "ambiguous": [
                ReferenceResolutionCandidate("friend", "friend_2", "Sam A"),
                ReferenceResolutionCandidate("friend", "friend_3", "Sam B"),
            ],
        }

    def candidates_for(self, reference: Reference):
        return self.responses.get(reference.text, [])


class FakeMemoryPort:
    def __init__(self) -> None:
        self.short_term_reads = 0
        self.long_term_reads = 0

    def recent_context(self, conversation_id: str):
        self.short_term_reads += 1
        return ("recent",)

    def long_term_context(self, account_id: str):
        self.long_term_reads += 1
        return ("long",)


def test_focus_resolves_single_or_ordered_subject_from_last_rendered_message():
    resolver = FocusResolver(FakeSubjectRepository())

    subject = resolver.resolve("conversation_1")

    assert subject.subject_type == "reminder_fire"
    assert subject.object_ids == ("fire_1", "fire_2")
    assert subject.ordered is True


def test_reference_resolver_clarifies_per_reference_without_blocking_clear_items():
    resolver = ReferenceResolver(FakeReferenceLookup())

    result = resolver.resolve_all(
        [
            Reference(reference_id="ref_1", text="clear", target_type="friend"),
            Reference(reference_id="ref_2", text="ambiguous", target_type="friend"),
            Reference(reference_id="ref_3", text="missing", target_type="friend"),
        ]
    )

    assert [item.reference_id for item in result.resolved] == ["ref_1"]
    assert result.resolved[0].target_id == "friend_1"
    assert [item.reference_id for item in result.clarifications] == ["ref_2", "ref_3"]
    assert result.can_mutate("ref_1") is True
    assert result.can_mutate("ref_2") is False


def test_memory_manager_always_loads_short_term_and_gates_long_term_by_switch():
    port = FakeMemoryPort()
    manager = MemoryManager(port)

    off = manager.load(
        account_id="account_1",
        conversation_id="conversation_1",
        long_term_enabled=False,
    )
    on = manager.load(
        account_id="account_1",
        conversation_id="conversation_1",
        long_term_enabled=True,
    )

    assert off.short_term == ("recent",)
    assert off.long_term == ()
    assert on.short_term == ("recent",)
    assert on.long_term == ("long",)
    assert port.short_term_reads == 2
    assert port.long_term_reads == 1
