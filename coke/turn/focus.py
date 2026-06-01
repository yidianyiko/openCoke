from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MessageSubject:
    subject_type: str
    object_ids: tuple[str, ...]
    ordered: bool = False


class MessageSubjectRepository(Protocol):
    def last_rendered_subject(self, conversation_id: str) -> MessageSubject | None: ...


class FocusResolver:
    def __init__(self, repository: MessageSubjectRepository | None = None) -> None:
        self._repository = repository

    def resolve(self, conversation_id: str) -> MessageSubject | None:
        if self._repository is None:
            return None
        return self._repository.last_rendered_subject(conversation_id)
