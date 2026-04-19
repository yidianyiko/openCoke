import time


class ReplyWaiter:
    def __init__(self, mongo, poll_interval_seconds: float, timeout_seconds: int):
        self.mongo = mongo
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds

    def _build_query(
        self, causal_inbound_event_id: str, sync_reply_token: str | None = None
    ) -> dict:
        query = {
            "status": "pending",
            "message_type": "text",
            "metadata.source": "clawscale",
            "metadata.business_protocol.delivery_mode": "request_response",
            "metadata.business_protocol.causal_inbound_event_id": causal_inbound_event_id,
        }
        if sync_reply_token:
            query["metadata.business_protocol.sync_reply_token"] = sync_reply_token
        return query

    def wait_for_reply_message(
        self,
        causal_inbound_event_id: str,
        sync_reply_token: str | None = None,
        *,
        consume: bool = True,
    ) -> dict:
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            message = self.mongo.find_one(
                "outputmessages",
                self._build_query(
                    causal_inbound_event_id,
                    sync_reply_token=sync_reply_token,
                ),
            )
            if message:
                if consume:
                    self.mongo.update_one(
                        "outputmessages",
                        {"_id": message["_id"], "status": "pending"},
                        {
                            "$set": {
                                "status": "handled",
                                "handled_timestamp": int(time.time()),
                            }
                        },
                    )
                return message
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError(
            "Timed out waiting for "
            f"causal_inbound_event_id={causal_inbound_event_id}"
        )

    def wait_for_reply(
        self, causal_inbound_event_id: str, sync_reply_token: str | None = None
    ) -> dict:
        message = self.wait_for_reply_message(
            causal_inbound_event_id,
            sync_reply_token=sync_reply_token,
            consume=True,
        )
        protocol_meta = message.get("metadata", {}).get("business_protocol", {})
        response = {
            "reply": message["message"],
            "output_id": str(message["_id"]),
            "causal_inbound_event_id": protocol_meta.get(
                "causal_inbound_event_id", causal_inbound_event_id
            ),
        }
        business_conversation_key = protocol_meta.get("business_conversation_key")
        if business_conversation_key:
            response["business_conversation_key"] = business_conversation_key
        return response
