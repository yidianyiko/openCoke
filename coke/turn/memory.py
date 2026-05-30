from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MemoryPort(Protocol):
    def recent_context(self, conversation_id: str) -> tuple[str, ...]: ...

    def long_term_context(self, account_id: str) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class MemoryContext:
    short_term: tuple[str, ...]
    long_term: tuple[str, ...]


class NullMemoryPort:
    def recent_context(self, conversation_id: str) -> tuple[str, ...]:
        return ()

    def long_term_context(self, account_id: str) -> tuple[str, ...]:
        return ()


class MemoryManager:
    def __init__(self, port: MemoryPort | None = None) -> None:
        self._port = port or NullMemoryPort()

    def load(
        self,
        *,
        account_id: str,
        conversation_id: str,
        long_term_enabled: bool,
    ) -> MemoryContext:
        short_term = tuple(self._port.recent_context(conversation_id))
        long_term = (
            tuple(self._port.long_term_context(account_id))
            if long_term_enabled
            else ()
        )
        return MemoryContext(short_term=short_term, long_term=long_term)
