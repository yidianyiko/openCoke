from typing import Any

from pymongo import MongoClient


_UNSET = object()


class ClawscalePushRouteDAO:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db.get_collection("clawscale_push_routes")

    def create_indexes(self) -> None:
        self.collection.create_index(
            [
                ("source", 1),
                ("account_id", 1),
                ("platform", 1),
                ("conversation_id", 1),
            ],
            unique=True,
        )
        self.collection.create_index(
            [
                ("source", 1),
                ("account_id", 1),
                ("platform", 1),
                ("conversation_id", 1),
                ("status", 1),
                ("last_seen_at", 1),
            ]
        )

    def upsert_route(
        self,
        *,
        account_id: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        conversation_id: str | None,
        now_ts: int,
        clawscale_user_id: Any = _UNSET,
    ) -> Any:
        route_filter = {
            "source": "clawscale",
            "account_id": account_id,
            "platform": platform,
            "conversation_id": conversation_id,
        }
        route_update = {
            "$set": {
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "external_end_user_id": external_end_user_id,
                "status": "active",
                "last_seen_at": now_ts,
                "updated_at": now_ts,
            },
            "$setOnInsert": {
                "source": "clawscale",
                "account_id": account_id,
                "platform": platform,
                "conversation_id": conversation_id,
                "created_at": now_ts,
            },
        }
        if clawscale_user_id is None:
            route_update["$unset"] = {"clawscale_user_id": ""}
        elif clawscale_user_id is not _UNSET:
            route_update["$set"]["clawscale_user_id"] = clawscale_user_id
        return self.collection.update_one(route_filter, route_update, upsert=True)

    def find_route_for_conversation(
        self, *, account_id: str, conversation_id: str, platform: str
    ):
        return self.collection.find_one(
            {
                "source": "clawscale",
                "account_id": account_id,
                "platform": platform,
                "conversation_id": conversation_id,
                "status": "active",
            },
            sort=[("last_seen_at", -1), ("updated_at", -1)],
        )

    def find_latest_route_for_account(self, *, account_id: str, platform: str):
        return self.collection.find_one(
            {
                "source": "clawscale",
                "account_id": account_id,
                "platform": platform,
                "status": "active",
            },
            sort=[("last_seen_at", -1), ("updated_at", -1)],
        )
