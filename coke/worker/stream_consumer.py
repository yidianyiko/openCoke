from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class RedisConsumerStreamPort(Protocol):
    def ensure_group(self) -> None: ...

    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: Mapping[str, str],
        count: int = 1,
        block: int = 1000,
    ): ...

    def xack(self, stream_name: str, group_name: str, message_id: str): ...

    def xautoclaim(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int = 1,
    ): ...


@dataclass(frozen=True, slots=True)
class StreamEvent:
    event_id: str
    topic: str
    idempotency_key: str
    traceparent: str
    payload: Mapping[str, Any]
    stream_message_id: str


class StreamConsumer:
    def __init__(
        self,
        redis_stream: RedisConsumerStreamPort,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        ack_callback: Callable[[str], object],
        block_ms: int = 1000,
    ) -> None:
        self.redis_stream = redis_stream
        self.stream_name = stream_name
        self.group_name = group_name
        self.consumer_name = consumer_name
        self.ack_callback = ack_callback
        self.block_ms = block_ms
        self._handled_event_ids: set[str] = set()

    def ensure_group(self) -> None:
        self.redis_stream.ensure_group()

    def poll_once(self, handler: Callable[[StreamEvent], object]) -> int:
        received = self.redis_stream.xreadgroup(
            self.group_name,
            self.consumer_name,
            {self.stream_name: ">"},
            count=1,
            block=self.block_ms,
        )
        return self._handle_received(received, handler)

    def reclaim_pending_once(
        self,
        handler: Callable[[StreamEvent], object],
        min_idle_ms: int,
        start_id: str = "0-0",
        count: int = 1,
    ) -> int:
        claimed = self.redis_stream.xautoclaim(
            self.stream_name,
            self.group_name,
            self.consumer_name,
            min_idle_ms,
            start_id=start_id,
            count=count,
        )
        return self._handle_received(claimed, handler)

    def _handle_received(
        self,
        received: Any,
        handler: Callable[[StreamEvent], object],
    ) -> int:
        handled = 0
        for stream_name, messages in received or []:
            for message_id, fields in messages:
                event = self._event_from_fields(message_id, fields)
                if event.event_id in self._handled_event_ids:
                    self.redis_stream.xack(stream_name, self.group_name, message_id)
                    continue
                handler(event)
                self.ack_callback(event.event_id)
                self.redis_stream.xack(stream_name, self.group_name, message_id)
                self._handled_event_ids.add(event.event_id)
                handled += 1
        return handled

    def _event_from_fields(self, message_id: str, fields: Mapping[str, Any]) -> StreamEvent:
        return StreamEvent(
            event_id=_decode_field(fields["event_id"]),
            topic=_decode_field(fields["topic"]),
            idempotency_key=_decode_field(fields["idempotency_key"]),
            traceparent=_decode_field(fields["traceparent"]),
            payload=_decode_payload(fields["payload"]),
            stream_message_id=_decode_field(message_id),
        )


def _decode_field(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _decode_payload(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    decoded = json.loads(_decode_field(value))
    if not isinstance(decoded, dict):
        raise ValueError("stream payload must decode to a JSON object")
    return decoded
