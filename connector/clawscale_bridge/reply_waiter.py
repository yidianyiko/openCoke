import time


class ReplyWaiter:
    def __init__(self, mongo, poll_interval_seconds: float, timeout_seconds: int):
        self.mongo = mongo
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds

    def wait_for_reply(self, bridge_request_id: str) -> str:
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            message = self.mongo.find_one(
                "outputmessages",
                {
                    "platform": "wechat",
                    "status": "pending",
                    "message_type": "text",
                    "metadata.source": "clawscale",
                    "metadata.bridge_request_id": bridge_request_id,
                    "metadata.delivery_mode": "request_response",
                },
            )
            if message:
                self.mongo.update_one(
                    "outputmessages",
                    {"_id": message["_id"], "status": "pending"},
                    {"$set": {"status": "handled", "handled_timestamp": int(time.time())}},
                )
                return message["message"]
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError(
            f"Timed out waiting for bridge_request_id={bridge_request_id}"
        )
