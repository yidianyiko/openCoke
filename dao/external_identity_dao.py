from pymongo import MongoClient


class ExternalIdentityDAO:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db.get_collection("external_identities")

    def create_indexes(self) -> None:
        self.collection.create_index(
            [
                ("source", 1),
                ("tenant_id", 1),
                ("channel_id", 1),
                ("platform", 1),
                ("external_end_user_id", 1),
            ],
            unique=True,
        )
        self.collection.create_index(
            [("account_id", 1), ("tenant_id", 1), ("is_primary_push_target", 1)]
        )
        self.collection.create_index([("status", 1)])

    def find_active_identity(
        self,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
    ):
        return self.collection.find_one(
            {
                "source": source,
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "platform": platform,
                "external_end_user_id": external_end_user_id,
                "status": "active",
            }
        )

    def find_primary_push_target(self, account_id: str, source: str):
        return self.collection.find_one(
            {
                "account_id": account_id,
                "source": source,
                "status": "active",
                "is_primary_push_target": True,
            }
        )
