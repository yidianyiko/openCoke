from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from coke.domains.conversation_runtime.models import ConversationRuntimeError
from coke.turn.runner import (
    WAITING_TEXT,
    DeliveryRequest,
    WaitingDeliveryCircuitBreaker,
    send_waiting_delivery,
)

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

    def latest_context_token_observation(self, conversation_id: str): ...

    def get_disposition(self, turn_id: str): ...


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
        retry_jitter: Callable[[int], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        circuit_breaker: WaitingDeliveryCircuitBreaker | None = None,
    ) -> None:
        self.conversation_runtime = conversation_runtime
        self.outbound_delivery = outbound_delivery
        self.delay_seconds = delay_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._retry_jitter = retry_jitter
        self._sleep = sleep
        self._circuit_breaker = circuit_breaker or WaitingDeliveryCircuitBreaker()

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
            observation = self.conversation_runtime.latest_context_token_observation(
                candidate.conversation_id
            )
            context_token_age_seconds = observation.age_seconds
            if observation.observed_at is not None:
                observed_at = observation.observed_at
                now = self._now()
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=UTC)
                if now.tzinfo is None:
                    now = now.replace(tzinfo=UTC)
                context_token_age_seconds = max(
                    0,
                    int((now - observed_at).total_seconds()),
                )
            outcomes = send_waiting_delivery(
                outbound_delivery=self.outbound_delivery,
                account_id=candidate.account_id,
                conversation_id=candidate.conversation_id,
                turn_id=candidate.turn_id,
                message_id=waiting_message.id,
                context_token=observation.token,
                delivery_source="waiting_timer",
                traceparent=observation.traceparent,
                context_token_source=observation.source,
                context_token_age_seconds=context_token_age_seconds,
                turn_disposition=self.conversation_runtime.get_disposition,
                retry_jitter=self._retry_jitter,
                sleep=self._sleep,
                circuit_breaker=self._circuit_breaker,
                logger=LOGGER,
            )
            outcome = outcomes[-1] if outcomes else None
            delivery_status = str(getattr(outcome, "status", "delivered"))
            error_code = getattr(outcome, "error_code", None)
            if delivery_status == "failed":
                LOGGER.info(
                    "waiting_reply_visibility_failed",
                    extra={
                        "turn_id": candidate.turn_id,
                        "conversation_id": candidate.conversation_id,
                        "delivery_status": delivery_status,
                        "error_code": error_code,
                    },
                )
                return False
            LOGGER.info(
                "waiting_reply_dispatched",
                extra={
                    "turn_id": candidate.turn_id,
                    "conversation_id": candidate.conversation_id,
                    "delivery_status": delivery_status,
                    "error_code": error_code,
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
