from pymongo import MongoClient


class BindingTicketDAO:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db.get_collection("binding_tickets")

    def create_indexes(self) -> None:
        self.collection.create_index([("ticket_id", 1)], unique=True)
        self.collection.create_index(
            [
                ("source", 1),
                ("tenant_id", 1),
                ("channel_id", 1),
                ("platform", 1),
                ("external_end_user_id", 1),
                ("status", 1),
            ]
        )

    def find_reusable_ticket(
        self,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        now_ts: int,
    ):
        return self.collection.find_one(
            {
                "source": source,
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "platform": platform,
                "external_end_user_id": external_end_user_id,
                "status": "pending",
                "expires_at": {"$gt": now_ts},
            },
            sort=[("created_at", -1)],
        )

    def count_recent_tickets(
        self,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        since_ts: int,
    ) -> int:
        return self.collection.count_documents(
            {
                "source": source,
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "platform": platform,
                "external_end_user_id": external_end_user_id,
                "created_at": {"$gte": since_ts},
            }
        )

    def create_ticket(
        self,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        bind_base_url: str,
        now_ts: int,
    ):
        ticket_id = f"bt_{now_ts}_{external_end_user_id}"
        doc = {
            "ticket_id": ticket_id,
            "source": source,
            "tenant_id": tenant_id,
            "channel_id": channel_id,
            "platform": platform,
            "external_end_user_id": external_end_user_id,
            "status": "pending",
            "created_at": now_ts,
            "expires_at": now_ts + 900,
            "bind_url": f"{bind_base_url}/bind/{ticket_id}",
        }
        self.collection.insert_one(doc)
        return doc
