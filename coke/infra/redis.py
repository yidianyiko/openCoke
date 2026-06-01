from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

import redis as redis_lib
from redis.exceptions import RedisError, ResponseError

from coke.config import Settings


def create_redis_client(settings: Settings) -> Any:
    return redis_lib.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )


class RedisLockAdapter:
    _EXTEND_IF_OWNED_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("PEXPIRE", KEYS[1], ARGV[2])
    end
    return 0
    """
    _RELEASE_IF_OWNED_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    end
    return 0
    """

    def __init__(self, redis_client: Any) -> None:
        self.redis_client = redis_client

    def acquire_lock(self, name: str, token: str, ttl_ms: int) -> bool:
        return bool(self.redis_client.set(name, token, nx=True, px=ttl_ms))

    def get_token(self, name: str) -> str | None:
        return _decode_redis_value(self.redis_client.get(name))

    def extend_if_owned(self, name: str, token: str, ttl_ms: int) -> bool:
        try:
            result = self.redis_client.eval(
                self._EXTEND_IF_OWNED_SCRIPT,
                1,
                name,
                token,
                str(ttl_ms),
            )
            return bool(result)
        except RedisError:
            if self.get_token(name) != token:
                return False
            return bool(self.redis_client.pexpire(name, ttl_ms))

    def release_if_owned(self, name: str, token: str) -> bool:
        try:
            result = self.redis_client.eval(
                self._RELEASE_IF_OWNED_SCRIPT,
                1,
                name,
                token,
            )
            return bool(result)
        except RedisError:
            if self.get_token(name) != token:
                return False
            return bool(self.redis_client.delete(name))


def _decode_redis_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


class RedisWorkStream:
    def __init__(
        self,
        redis_client: Any,
        stream_name: str = "coke.work",
        group_name: str = "workers",
        dedup_prefix: str = "coke:stream-dedup",
    ) -> None:
        self.redis_client = redis_client
        self.stream_name = stream_name
        self.group_name = group_name
        self.dedup_prefix = dedup_prefix

    def ensure_group(self) -> None:
        try:
            self.redis_client.xgroup_create(
                self.stream_name,
                self.group_name,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def publish_event(
        self,
        *,
        event_id: str,
        topic: str,
        idempotency_key: str,
        traceparent: str,
        payload: Mapping[str, Any],
    ) -> str:
        dedup_key = self._dedup_key(event_id)
        existing = self.redis_client.get(dedup_key)
        if existing:
            return str(existing)
        reserved = self.redis_client.set(dedup_key, "pending", nx=True)
        if not reserved:
            return str(self.redis_client.get(dedup_key) or "")
        try:
            message_id = self.redis_client.xadd(
                self.stream_name,
                {
                    "event_id": event_id,
                    "topic": topic,
                    "idempotency_key": idempotency_key,
                    "traceparent": traceparent,
                    "payload": _encode_json(payload),
                },
            )
        except Exception:
            self.redis_client.delete(dedup_key)
            raise
        message_id = str(message_id)
        self.redis_client.set(dedup_key, message_id, xx=True)
        self.redis_client.set(self._message_event_key(message_id), event_id)
        return message_id

    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: Mapping[str, str],
        count: int = 1,
        block: int = 1000,
    ):
        return self.redis_client.xreadgroup(
            groupname,
            consumername,
            streams,
            count=count,
            block=block,
        )

    def xack(self, stream_name: str, group_name: str, message_id: str):
        acked = self.redis_client.xack(stream_name, group_name, message_id)
        if acked:
            event_id = self.redis_client.get(self._message_event_key(message_id))
            if event_id:
                self.redis_client.delete(self._dedup_key(str(event_id)))
            self.redis_client.delete(self._message_event_key(message_id))
        return acked

    def xautoclaim(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int = 1,
    ):
        claimed = self.redis_client.xautoclaim(
            stream_name,
            group_name,
            consumer_name,
            min_idle_time,
            start_id=start_id,
            count=count,
        )
        if (
            isinstance(claimed, (tuple, list))
            and len(claimed) >= 2
            and isinstance(claimed[1], list)
        ):
            messages = claimed[1]
        elif isinstance(claimed, tuple):
            if len(claimed) >= 2:
                messages = claimed[1]
            else:
                messages = []
        else:
            messages = claimed
        return [(stream_name, messages or [])]

    def _dedup_key(self, event_id: str) -> str:
        return f"{self.dedup_prefix}:{self.stream_name}:{event_id}"

    def _message_event_key(self, message_id: str) -> str:
        return f"{self.dedup_prefix}:{self.stream_name}:message:{message_id}"


class RedisReplyPubSub:
    def __init__(self, redis_client: Any, channel_prefix: str = "coke:reply") -> None:
        self.redis_client = redis_client
        self.channel_prefix = channel_prefix

    def channel_for(self, causal_inbound_event_id: str) -> str:
        return f"{self.channel_prefix}:{causal_inbound_event_id}"

    def subscribe(self, causal_inbound_event_id: str):
        pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(self.channel_for(causal_inbound_event_id))
        return pubsub

    def publish_reply(
        self,
        causal_inbound_event_id: str,
        payload: Mapping[str, Any],
    ) -> int:
        return int(
            self.redis_client.publish(
                self.channel_for(causal_inbound_event_id),
                _encode_json(payload),
            )
        )

    def get_reply(
        self, subscription: Any, timeout_s: float = 30.0
    ) -> Mapping[str, Any] | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            message = subscription.get_message(timeout=0.05)
            if not message or message.get("type") != "message":
                continue
            data = _decode_redis_value(message.get("data"))
            if data is None:
                return None
            decoded = json.loads(data)
            if not isinstance(decoded, dict):
                raise ValueError("reply pub/sub payload must decode to a JSON object")
            return decoded
        return None


def _encode_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
