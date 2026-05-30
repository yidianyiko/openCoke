from __future__ import annotations

import fakeredis

from coke.infra.redis import RedisLockAdapter
from coke.turn.locks import ConversationLockManager


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttl_ms: dict[str, int] = {}
        self.deleted: list[str] = []

    def set(self, name, value, nx=False, px=None):
        if nx and name in self.values:
            return False
        self.values[name] = value
        if px is not None:
            self.ttl_ms[name] = px
        return True

    def get(self, name):
        return self.values.get(name)

    def pexpire(self, name, ttl_ms):
        if name not in self.values:
            return False
        self.ttl_ms[name] = ttl_ms
        return True

    def delete(self, name):
        self.deleted.append(name)
        existed = name in self.values
        self.values.pop(name, None)
        self.ttl_ms.pop(name, None)
        return 1 if existed else 0

    def acquire_lock(self, name: str, token: str, ttl_ms: int) -> bool:
        return bool(self.set(name, token, nx=True, px=ttl_ms))

    def get_token(self, name: str) -> str | None:
        return self.get(name)

    def extend_if_owned(self, name: str, token: str, ttl_ms: int) -> bool:
        if self.get(name) != token:
            return False
        return bool(self.pexpire(name, ttl_ms))

    def release_if_owned(self, name: str, token: str) -> bool:
        if self.get(name) != token:
            return False
        return bool(self.delete(name))


def test_conversation_lock_uses_set_nx_px_and_returns_none_when_owned():
    redis = FakeRedis()
    manager = ConversationLockManager(
        redis_client=redis,
        ttl_ms=30_000,
        token_factory=lambda: "owner-1",
    )

    lock = manager.acquire("conversation_1")
    second = manager.acquire("conversation_1")

    assert lock is not None
    assert lock.token == "owner-1"
    assert redis.values["coke:conversation-lock:conversation_1"] == "owner-1"
    assert redis.ttl_ms["coke:conversation-lock:conversation_1"] == 30_000
    assert second is None


def test_conversation_lock_heartbeat_extends_only_for_owner_and_records_loss():
    redis = FakeRedis()
    events = []
    manager = ConversationLockManager(
        redis_client=redis,
        ttl_ms=30_000,
        token_factory=lambda: "owner-1",
        instrument=events.append,
    )
    lock = manager.acquire("conversation_1")
    assert lock is not None

    assert lock.heartbeat() is True
    redis.values["coke:conversation-lock:conversation_1"] = "owner-2"

    assert lock.heartbeat() is False
    assert events == [
        {
            "event": "lock_loss",
            "conversation_id": "conversation_1",
            "token": "owner-1",
        }
    ]


def test_conversation_lock_release_deletes_only_when_owner_token_matches():
    redis = FakeRedis()
    events = []
    manager = ConversationLockManager(
        redis_client=redis,
        ttl_ms=30_000,
        token_factory=lambda: "owner-1",
        instrument=events.append,
    )
    lock = manager.acquire("conversation_1")
    assert lock is not None

    redis.values["coke:conversation-lock:conversation_1"] = "owner-2"
    assert lock.release() is False
    assert redis.values["coke:conversation-lock:conversation_1"] == "owner-2"

    redis.values["coke:conversation-lock:conversation_1"] = "owner-1"
    assert lock.release() is True
    assert "coke:conversation-lock:conversation_1" not in redis.values
    assert redis.deleted == ["coke:conversation-lock:conversation_1"]


def test_redis_lock_adapter_uses_real_set_nx_px_and_blocks_contention():
    redis = fakeredis.FakeRedis(decode_responses=True)
    adapter = RedisLockAdapter(redis)
    manager = ConversationLockManager(
        redis_client=adapter,
        ttl_ms=30_000,
        token_factory=lambda: "owner-1",
    )

    lock = manager.acquire("conversation_1")
    second = manager.acquire("conversation_1")

    assert lock is not None
    assert second is None
    assert redis.get("coke:conversation-lock:conversation_1") == "owner-1"
    assert redis.pttl("coke:conversation-lock:conversation_1") > 0


def test_redis_lock_adapter_release_and_heartbeat_require_owner_token():
    redis = fakeredis.FakeRedis(decode_responses=True)
    events = []
    adapter = RedisLockAdapter(redis)
    manager = ConversationLockManager(
        redis_client=adapter,
        ttl_ms=30_000,
        token_factory=lambda: "owner-1",
        instrument=events.append,
    )
    lock = manager.acquire("conversation_1")
    assert lock is not None

    redis.set("coke:conversation-lock:conversation_1", "owner-2", xx=True, px=30_000)

    assert lock.heartbeat() is False
    assert lock.release() is False
    assert redis.get("coke:conversation-lock:conversation_1") == "owner-2"
    assert events == [
        {
            "event": "lock_loss",
            "conversation_id": "conversation_1",
            "token": "owner-1",
        }
    ]
