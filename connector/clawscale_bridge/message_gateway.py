import uuid

from pymongo.errors import DuplicateKeyError

from connector.clawscale_bridge.customer_ids import resolve_customer_id


def _normalized_attachments_from_inbound(inbound: dict) -> list[dict]:
    attachments = inbound.get("attachments")
    if not isinstance(attachments, list):
        return []
    return [attachment for attachment in attachments if isinstance(attachment, dict)]


def _resolve_message_type(attachments: list[dict]) -> str:
    if len(attachments) != 1:
        return "text"

    content_type = attachments[0].get("contentType")
    if not isinstance(content_type, str):
        return "text"

    normalized_content_type = content_type.lower()
    if normalized_content_type.startswith("image/"):
        return "image"
    if normalized_content_type.startswith("audio/"):
        return "voice"
    return "text"


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

        customer_id = resolve_customer_id(
            customer_id=inbound.get("customer_id") or inbound.get("coke_account_id"),
            account_id=account_id,
        )
        customer = {
            "id": customer_id,
            "display_name": inbound.get("coke_account_display_name"),
        }

        attachments = _normalized_attachments_from_inbound(inbound)
        metadata = {
            "source": "clawscale",
            "business_protocol": business_protocol,
            "customer": customer,
            "coke_account": customer,
        }
        if attachments:
            metadata["attachments"] = attachments
            metadata["mediaUrls"] = [
                attachment.get("url")
                for attachment in attachments
                if isinstance(attachment.get("url"), str)
            ]
            if "inbound_text" in inbound:
                metadata["inbound_text"] = inbound.get("inbound_text")

        return {
            "input_timestamp": inbound["timestamp"],
            "handled_timestamp": inbound["timestamp"],
            "status": "pending",
            "from_user": account_id,
            "platform": "business",
            "chatroom_name": None,
            "to_user": character_id,
            "message_type": _resolve_message_type(attachments),
            "message": text,
            "metadata": metadata,
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
