import time

import requests
from pymongo import ReturnDocument


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

    def _claim_pending_message(self, now: int):
        return self.mongo.get_collection("outputmessages").find_one_and_update(
            {
                "platform": "wechat",
                "status": "pending",
                "expect_output_timestamp": {"$lte": now},
                "metadata.route_via": "clawscale",
                "metadata.delivery_mode": "push",
            },
            {"$set": {"status": "dispatching", "dispatching_timestamp": now}},
            return_document=ReturnDocument.AFTER,
        )

    def _finalize_message(self, message_id, status: str, now: int):
        self.mongo.update_one(
            "outputmessages",
            {"_id": message_id, "status": "dispatching"},
            {"$set": {"status": status, "handled_timestamp": now}},
        )

    def dispatch_once(self) -> bool:
        now = int(time.time())
        message = self._claim_pending_message(now)
        if not message:
            return False

        payload = {
            "tenant_id": message["metadata"]["tenant_id"],
            "channel_id": message["metadata"]["channel_id"],
            "end_user_id": message["metadata"]["external_end_user_id"],
            "text": message["message"],
            "idempotency_key": message["metadata"]["push_idempotency_key"],
        }
        try:
            response = self.session.post(
                self.outbound_api_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.outbound_api_key}"},
                timeout=15,
            )
            new_status = "handled" if response.status_code in (200, 409) else "failed"
        except Exception:
            self._finalize_message(message["_id"], "failed", now)
            return False

        self._finalize_message(message["_id"], new_status, now)
        return new_status == "handled"
