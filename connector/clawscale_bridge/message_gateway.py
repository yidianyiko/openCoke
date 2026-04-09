import uuid

from pymongo.errors import DuplicateKeyError


class CokeMessageGateway:
    def __init__(self, mongo, user_dao, target_character_alias: str = "coke"):
        self.mongo = mongo
        self.user_dao = user_dao
        self.target_character_alias = target_character_alias
        self._causal_index_ensured = False

    def _ensure_causal_inbound_event_unique_index(self):
        if self._causal_index_ensured:
            return
        collection = self.mongo.get_collection("inputmessages")
        collection.create_index(
            [
                ("metadata.source", 1),
                ("metadata.business_protocol.causal_inbound_event_id", 1),
            ],
            unique=True,
            partialFilterExpression={
                "metadata.source": "clawscale",
                "metadata.business_protocol.causal_inbound_event_id": {
                    "$exists": True
                },
            },
            name="uniq_clawscale_causal_inbound_event_id",
        )
        self._causal_index_ensured = True

    def build_input_message(
        self,
        account_id: str,
        character_id: str,
        text: str,
        causal_inbound_event_id: str,
        inbound: dict,
    ):
        business_protocol = {
            "delivery_mode": "request_response",
            "causal_inbound_event_id": causal_inbound_event_id,
        }
        sync_reply_token = inbound.get("sync_reply_token")
        if sync_reply_token:
            business_protocol["sync_reply_token"] = sync_reply_token
        business_conversation_key = inbound.get("business_conversation_key")
        if business_conversation_key:
            business_protocol["business_conversation_key"] = business_conversation_key
        gateway_conversation_id = inbound.get("gateway_conversation_id")
        if gateway_conversation_id:
            business_protocol["gateway_conversation_id"] = gateway_conversation_id

        return {
            "input_timestamp": inbound["timestamp"],
            "handled_timestamp": inbound["timestamp"],
            "status": "pending",
            "from_user": account_id,
            "platform": "business",
            "chatroom_name": None,
            "to_user": character_id,
            "message_type": "text",
            "message": text,
            "metadata": {
                "source": "clawscale",
                "business_protocol": business_protocol,
            },
        }

    def enqueue(self, account_id: str, character_id: str, text: str, inbound: dict):
        self._ensure_causal_inbound_event_unique_index()
        causal_inbound_event_id = inbound.get("inbound_event_id")
        if not isinstance(causal_inbound_event_id, str) or not causal_inbound_event_id:
            causal_inbound_event_id = inbound.get("causal_inbound_event_id")
        if not isinstance(causal_inbound_event_id, str) or not causal_inbound_event_id:
            causal_inbound_event_id = f"in_evt_{uuid.uuid4().hex}"
        doc = self.build_input_message(
            account_id=account_id,
            character_id=character_id,
            text=text,
            causal_inbound_event_id=causal_inbound_event_id,
            inbound=inbound,
        )
        filter_query = {
            "metadata.source": "clawscale",
            "metadata.business_protocol.causal_inbound_event_id": causal_inbound_event_id,
        }
        try:
            self.mongo.get_collection("inputmessages").update_one(
                filter_query,
                {"$setOnInsert": doc},
                upsert=True,
            )
        except DuplicateKeyError:
            return causal_inbound_event_id
        return causal_inbound_event_id
