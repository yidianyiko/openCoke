from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import logging
from typing import Protocol

from coke.domains.conversation_runtime.models import ConversationRuntimeError
from coke.turn.runner import DeliveryRequest, WAITING_TEXT

LOGGER = logging.getLogger(__name__)


class WaitingCandidateRepositoryPort(Protocol):
    def waiting_reply_candidates(self, *, cutoff: datetime, limit: int = 25): ...


class WaitingConversationRuntimePort(Protocol):
    repository: WaitingCandidateRepositoryPort

    def mark_pending_async_reply(
        self,
        turn_id: str,
        reason_code: str = "waiting_timer_elapsed",
    ): ...

    def record_outbound_message(
        self,
        turn_id: str,
        text: str,
        *,
        segment_index: int,
        payload: dict,
    ): ...

    def latest_context_token(self, conversation_id: str) -> str | None: ...


class WaitingOutboundDeliveryPort(Protocol):
    def deliver(self, request: DeliveryRequest): ...


class WaitingReplyDispatcher:
    def __init__(
        self,
        *,
        conversation_runtime: WaitingConversationRuntimePort,
        outbound_delivery: WaitingOutboundDeliveryPort,
        delay_seconds: int = 20,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.conversation_runtime = conversation_runtime
        self.outbound_delivery = outbound_delivery
        self.delay_seconds = delay_seconds
        self._now = now or (lambda: datetime.now(UTC))

    def dispatch_due(self, *, limit: int = 25) -> int:
        cutoff = self._now() - timedelta(seconds=self.delay_seconds)
        candidates = self.conversation_runtime.repository.waiting_reply_candidates(
            cutoff=cutoff,
            limit=limit,
        )
        dispatched = 0
        for candidate in candidates:
            if self._dispatch_one(candidate):
                dispatched += 1
        return dispatched

    def _dispatch_one(self, candidate) -> bool:
        try:
            self.conversation_runtime.mark_pending_async_reply(
                turn_id=candidate.turn_id,
                reason_code="waiting_timer_elapsed",
            )
            waiting_message = self.conversation_runtime.record_outbound_message(
                candidate.turn_id,
                WAITING_TEXT,
                segment_index=0,
                payload={"message_type": "waiting"},
            )
            self.outbound_delivery.deliver(
                DeliveryRequest(
                    account_id=candidate.account_id,
                    conversation_id=candidate.conversation_id,
                    turn_id=candidate.turn_id,
                    message_type="waiting",
                    visible_text=WAITING_TEXT,
                    idempotency_key=f"{candidate.trigger_id}:waiting",
                    message_id=waiting_message.id,
                    segments=(WAITING_TEXT,),
                    context_token=self.conversation_runtime.latest_context_token(
                        candidate.conversation_id
                    ),
                )
            )
            LOGGER.info(
                "waiting_reply_dispatched",
                extra={
                    "turn_id": candidate.turn_id,
                    "conversation_id": candidate.conversation_id,
                },
            )
            return True
        except ConversationRuntimeError as error:
            LOGGER.info(
                "waiting_reply_skipped",
                extra={
                    "turn_id": candidate.turn_id,
                    "conversation_id": candidate.conversation_id,
                    "reason_code": error.code,
                },
            )
            return False
        except Exception:
            LOGGER.exception(
                "waiting_reply_delivery_failed",
                extra={
                    "turn_id": candidate.turn_id,
                    "conversation_id": candidate.conversation_id,
                },
            )
            return False
