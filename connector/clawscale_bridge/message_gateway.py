import uuid


class CokeMessageGateway:
    def __init__(self, mongo, user_dao, target_character_alias: str = "coke"):
        self.mongo = mongo
        self.user_dao = user_dao
        self.target_character_alias = target_character_alias

    def build_input_message(
        self,
        account_id: str,
        character_id: str,
        text: str,
        bridge_request_id: str,
        inbound: dict,
    ):
        return {
            "input_timestamp": inbound["timestamp"],
            "handled_timestamp": inbound["timestamp"],
            "status": "pending",
            "from_user": account_id,
            "platform": "wechat",
            "chatroom_name": None,
            "to_user": character_id,
            "message_type": "text",
            "message": text,
            "metadata": {
                "source": "clawscale",
                "bridge_request_id": bridge_request_id,
                "delivery_mode": "request_response",
                "clawscale": {
                    "tenant_id": inbound["tenant_id"],
                    "channel_id": inbound["channel_id"],
                    "conversation_id": inbound["conversation_id"],
                    "platform": inbound["platform"],
                    "end_user_id": inbound["end_user_id"],
                    "external_id": inbound["external_id"],
                    "external_message_id": inbound["external_message_id"],
                },
            },
        }

    def enqueue(self, account_id: str, character_id: str, text: str, inbound: dict):
        bridge_request_id = f"br_{uuid.uuid4().hex}"
        doc = self.build_input_message(
            account_id=account_id,
            character_id=character_id,
            text=text,
            bridge_request_id=bridge_request_id,
            inbound=inbound,
        )
        self.mongo.insert_one("inputmessages", doc)
        return bridge_request_id
