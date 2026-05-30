from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class RedisConsumerStreamPort(Protocol):
    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: Mapping[str, str],
        count: int = 1,
        block: int = 1000,
    ): ...

    def xack(self, stream_name: str, group_name: str, message_id: str): ...


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

    def poll_once(self, handler: Callable[[StreamEvent], object]) -> int:
        received = self.redis_stream.xreadgroup(
            self.group_name,
            self.consumer_name,
            {self.stream_name: ">"},
            count=1,
            block=self.block_ms,
        )
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
            event_id=str(fields["event_id"]),
            topic=str(fields["topic"]),
            idempotency_key=str(fields["idempotency_key"]),
            traceparent=str(fields["traceparent"]),
            payload=fields["payload"],
            stream_message_id=message_id,
        )
