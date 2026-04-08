import logging
import time

import requests
from pymongo import ReturnDocument

logger = logging.getLogger(__name__)

STALE_DISPATCHING_TIMEOUT_SECONDS = 300


class ClawScaleOutputDispatcher:
    def __init__(
        self,
        mongo,
        session,
        outbound_api_url: str,
        outbound_api_key: str = "test-outbound-key",
    ):
        self.mongo = mongo
        self.session = session or requests.Session()
        self.outbound_api_url = outbound_api_url
        self.outbound_api_key = outbound_api_key

    def _claimable_query(self, now: int):
        return {
            "platform": "wechat",
            "expect_output_timestamp": {"$lte": now},
            "metadata.route_via": "clawscale",
            "metadata.delivery_mode": "push",
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

    def _build_payload(self, message):
        metadata = message["metadata"]
        return {
            "tenant_id": metadata["tenant_id"],
            "channel_id": metadata["channel_id"],
            "external_end_user_id": metadata["external_end_user_id"],
            "text": message["message"],
            "idempotency_key": metadata["push_idempotency_key"],
        }

    def dispatch_once(self) -> bool:
        now = int(time.time())
        message = self._claim_pending_message(now)
        if not message:
            return False

        try:
            payload = self._build_payload(message)
        except Exception:
            logger.exception("clawscale output payload construction failed")
            self._mark_failed_best_effort(message["_id"], now)
            return False

        try:
            response = self.session.post(
                self.outbound_api_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.outbound_api_key}"},
                timeout=15,
            )
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
