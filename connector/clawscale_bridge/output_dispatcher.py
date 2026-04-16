import logging
import time

from pymongo import ReturnDocument

from connector.clawscale_bridge.customer_ids import resolve_customer_id
from connector.clawscale_bridge.gateway_outbound_client import GatewayOutboundClient

logger = logging.getLogger(__name__)

STALE_DISPATCHING_TIMEOUT_SECONDS = 300


class ClawScaleOutputDispatcher:
    def __init__(
        self,
        mongo,
        session=None,
        outbound_api_url: str | None = None,
        outbound_api_key: str = "test-outbound-key",
        gateway_client: GatewayOutboundClient | None = None,
        timeout_seconds: int = 15,
    ):
        self.mongo = mongo
        self.gateway_client = gateway_client or GatewayOutboundClient(
            api_url=outbound_api_url,
            api_key=outbound_api_key,
            session=session,
            timeout_seconds=timeout_seconds,
        )

    def _claimable_query(self, now: int):
        return {
            "$and": [
                {
                    "$or": [
                        {"customer_id": {"$exists": True}},
                        {"account_id": {"$exists": True}},
                    ]
                }
            ],
            "expect_output_timestamp": {"$lte": now},
            "metadata.business_conversation_key": {"$exists": True},
            "metadata.delivery_mode": "push",
            "metadata.output_id": {"$exists": True},
            "$or": [
                {"status": "pending"},
                {
                    "status": "dispatching",
                    "$or": [
                        {
                            "dispatching_timestamp": {
                                "$lte": now - STALE_DISPATCHING_TIMEOUT_SECONDS
                            }
                        },
                        {"dispatching_timestamp": {"$exists": False}},
                    ],
                },
            ],
        }

    def _claim_pending_message(self, now: int):
        return self.mongo.get_collection("outputmessages").find_one_and_update(
            self._claimable_query(now),
            {"$set": {"status": "dispatching", "dispatching_timestamp": now}},
            return_document=ReturnDocument.AFTER,
        )

    def _finalize_message(self, message_id, status: str, now: int):
        self.mongo.update_one(
            "outputmessages",
            {"_id": message_id, "status": "dispatching"},
            {"$set": {"status": status, "handled_timestamp": now}},
        )

    def _mark_failed_best_effort(self, message_id, now: int):
        try:
            self._finalize_message(message_id, "failed", now)
        except Exception:
            logger.exception("failed to finalize clawscale output message")

    def _release_message_for_retry(self, message_id):
        try:
            self.mongo.update_one(
                "outputmessages",
                {"_id": message_id, "status": "dispatching"},
                {"$set": {"status": "pending"}, "$unset": {"dispatching_timestamp": ""}},
            )
        except Exception:
            logger.exception("failed to release clawscale output message for retry")

    def _build_gateway_args(self, message):
        metadata = message["metadata"]
        customer_id = resolve_customer_id(
            customer_id=message.get("customer_id"),
            account_id=message.get("account_id"),
        )
        return {
            "output_id": metadata["output_id"],
            "customer_id": customer_id,
            "business_conversation_key": metadata["business_conversation_key"],
            "text": message["message"],
            "message_type": message.get("message_type", "text"),
            "delivery_mode": metadata["delivery_mode"],
            "expect_output_timestamp": message["expect_output_timestamp"],
            "idempotency_key": metadata["idempotency_key"],
            "trace_id": metadata["trace_id"],
            "causal_inbound_event_id": metadata.get("causal_inbound_event_id"),
        }

    def dispatch_once(self) -> bool:
        now = int(time.time())
        message = self._claim_pending_message(now)
        if not message:
            return False

        try:
            payload = self._build_gateway_args(message)
        except Exception:
            logger.exception("clawscale output payload construction failed")
            self._mark_failed_best_effort(message["_id"], now)
            return False

        try:
            response = self.gateway_client.post_output(**payload)
        except Exception:
            logger.exception("clawscale output request failed")
            self._mark_failed_best_effort(message["_id"], now)
            return False

        if response.status_code == 200:
            new_status = "handled"
        elif response.status_code == 409:
            error = None
            try:
                error = response.json().get("error")
            except Exception:
                logger.exception("clawscale output duplicate response parsing failed")

            if error == "duplicate_request":
                new_status = "handled"
            elif error == "idempotency_key_conflict":
                new_status = "failed"
            else:
                self._release_message_for_retry(message["_id"])
                return False
        else:
            new_status = "failed"

        self._finalize_message(message["_id"], new_status, now)
        return new_status == "handled"
