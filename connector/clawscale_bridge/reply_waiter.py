import time


class ReplyWaiter:
    def __init__(
        self,
        mongo,
        poll_interval_seconds: float,
        timeout_seconds: int,
        drain_interval_seconds: float | None = None,
    ):
        self.mongo = mongo
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.drain_interval_seconds = (
            drain_interval_seconds
            if drain_interval_seconds is not None
            else poll_interval_seconds
        )

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

    def _find_reply_messages(self, query: dict, first_message: dict) -> list[dict]:
        if not self._can_find_many():
            return [first_message]
        messages = self.mongo.find_many("outputmessages", query)
        if not messages:
            return [first_message]
        return sorted(
            messages,
            key=lambda message: (
                message.get("expect_output_timestamp") or 0,
                str(message.get("_id", "")),
            ),
        )

    def _can_find_many(self) -> bool:
        find_many = getattr(type(self.mongo), "find_many", None)
        return callable(find_many)

    def wait_for_reply_messages(
        self,
        causal_inbound_event_id: str,
        sync_reply_token: str | None = None,
        *,
        consume: bool = True,
    ) -> list[dict]:
        query = self._build_query(
            causal_inbound_event_id,
            sync_reply_token=sync_reply_token,
        )
        deadline = time.time() + self.timeout_seconds
        messages = []
        last_change_at = None
        last_ids = ()

        while time.time() < deadline:
            first_message = self.mongo.find_one("outputmessages", query)
            if first_message:
                current_messages = self._find_reply_messages(query, first_message)
                current_ids = tuple(
                    str(message.get("_id")) for message in current_messages
                )
                if current_ids != last_ids:
                    messages = current_messages
                    last_ids = current_ids
                    last_change_at = time.time()

                if not self._can_find_many():
                    break

                if (
                    messages
                    and last_change_at is not None
                    and time.time() - last_change_at >= self.drain_interval_seconds
                ):
                    break

            time.sleep(self.poll_interval_seconds)

        if not messages:
            raise TimeoutError(
                "Timed out waiting for "
                f"causal_inbound_event_id={causal_inbound_event_id}"
            )

        if consume:
            handled_timestamp = int(time.time())
            for message in messages:
                self.mongo.update_one(
                    "outputmessages",
                    {"_id": message["_id"], "status": "pending"},
                    {
                        "$set": {
                            "status": "handled",
                            "handled_timestamp": handled_timestamp,
                        }
                    },
                )
        return messages

    def wait_for_reply(
        self, causal_inbound_event_id: str, sync_reply_token: str | None = None
    ) -> dict:
        messages = self.wait_for_reply_messages(
            causal_inbound_event_id,
            sync_reply_token=sync_reply_token,
            consume=False,
        )
        message = self._refresh_pending_reply_message(message)
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
        message = messages[0]
        protocol_meta = message.get("metadata", {}).get("business_protocol", {})
        response = {
            "reply": "\n".join(message["message"] for message in messages),
            "output_id": str(message["_id"]),
            "causal_inbound_event_id": protocol_meta.get(
                "causal_inbound_event_id", causal_inbound_event_id
            ),
        }
        if len(messages) > 1:
            response["output_ids"] = [str(message["_id"]) for message in messages]
        business_conversation_key = protocol_meta.get("business_conversation_key")
        if business_conversation_key:
            response["business_conversation_key"] = business_conversation_key
        return response

    def _refresh_pending_reply_message(self, message: dict) -> dict:
        if not isinstance(message, dict):
            return message

        deadline = time.time() + self.poll_interval_seconds
        latest_message = message

        while time.time() < deadline:
            time.sleep(self.poll_interval_seconds)
            refreshed = self.mongo.find_one(
                "outputmessages",
                {"_id": message["_id"], "status": "pending"},
            )
            if not isinstance(refreshed, dict):
                break
            latest_message = refreshed
            message = refreshed

        return latest_message
