from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Any, Protocol


class RedisLockPort(Protocol):
    def set(self, name: str, value: str, nx: bool = False, px: int | None = None): ...

    def get(self, name: str): ...

    def pexpire(self, name: str, ttl_ms: int): ...

    def delete(self, name: str): ...


Instrument = Callable[[dict[str, Any]], None]


class ConversationLockManager:
    def __init__(
        self,
        redis_client: RedisLockPort,
        ttl_ms: int,
        token_factory: Callable[[], str] | None = None,
        instrument: Instrument | None = None,
        key_prefix: str = "coke:conversation-lock",
    ) -> None:
        self.redis_client = redis_client
        self.ttl_ms = ttl_ms
        self._token_factory = token_factory or (lambda: token_urlsafe(24))
        self._instrument = instrument or (lambda event: None)
        self.key_prefix = key_prefix

    def acquire(self, conversation_id: str) -> ConversationLock | None:
        token = self._token_factory()
        key = self._key(conversation_id)
        acquired = self.redis_client.set(key, token, nx=True, px=self.ttl_ms)
        if not acquired:
            return None
        return ConversationLock(
            redis_client=self.redis_client,
            conversation_id=conversation_id,
            key=key,
            token=token,
            ttl_ms=self.ttl_ms,
            instrument=self._instrument,
        )

    def _key(self, conversation_id: str) -> str:
        return f"{self.key_prefix}:{conversation_id}"


@dataclass(frozen=True, slots=True)
class ConversationLock:
    redis_client: RedisLockPort
    conversation_id: str
    key: str
    token: str
    ttl_ms: int
    instrument: Instrument

    def heartbeat(self) -> bool:
        if not self._owns_lock():
            self._record_loss()
            return False
        extended = bool(self.redis_client.pexpire(self.key, self.ttl_ms))
        if not extended:
            self._record_loss()
        return extended

    def release(self) -> bool:
        if not self._owns_lock():
            return False
        return bool(self.redis_client.delete(self.key))

    def _owns_lock(self) -> bool:
        return _decode_redis_value(self.redis_client.get(self.key)) == self.token

    def _record_loss(self) -> None:
        self.instrument(
            {
                "event": "lock_loss",
                "conversation_id": self.conversation_id,
                "token": self.token,
            }
        )


def _decode_redis_value(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
