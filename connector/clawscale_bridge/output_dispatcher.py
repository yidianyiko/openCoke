import time

import requests


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

    def dispatch_once(self) -> bool:
        now = int(time.time())
        message = self.mongo.find_one(
            "outputmessages",
            {
                "platform": "wechat",
                "status": "pending",
                "expect_output_timestamp": {"$lte": now},
                "metadata.route_via": "clawscale",
                "metadata.delivery_mode": "push",
            },
        )
        if not message:
            return False

        payload = {
            "tenant_id": message["metadata"]["tenant_id"],
            "channel_id": message["metadata"]["channel_id"],
            "end_user_id": message["metadata"]["external_end_user_id"],
            "text": message["message"],
            "idempotency_key": message["metadata"]["push_idempotency_key"],
        }
        response = self.session.post(
            self.outbound_api_url,
            json=payload,
            headers={"Authorization": f"Bearer {self.outbound_api_key}"},
            timeout=15,
        )
        new_status = "handled" if response.status_code in (200, 409) else "failed"
        self.mongo.update_one(
            "outputmessages",
            {"_id": message["_id"]},
            {"$set": {"status": new_status, "handled_timestamp": now}},
        )
        return new_status == "handled"
