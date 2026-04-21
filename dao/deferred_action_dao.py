# -*- coding: utf-8 -*-
"""MongoDB access for deferred actions."""

from datetime import datetime
from typing import Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection

from conf.config import CONF


class DeferredActionDAO:
    COLLECTION = "deferred_actions"

    def __init__(
        self,
        mongo_uri: str = "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name: str = CONF["mongodb"]["mongodb_name"],
    ):
        self.client = MongoClient(mongo_uri, tz_aware=True)
        self.db = self.client[db_name]
        self.collection: Collection = self.db.get_collection(self.COLLECTION)

    def create_indexes(self):
        self.collection.create_index([("lifecycle_state", 1), ("next_run_at", 1)])
        self.collection.create_index(
            [("conversation_id", 1), ("kind", 1), ("lifecycle_state", 1)]
        )
        self.collection.create_index(
            [("user_id", 1), ("visibility", 1), ("lifecycle_state", 1), ("next_run_at", 1)]
        )
        self.collection.create_index(
            [("conversation_id", 1), ("kind", 1), ("lifecycle_state", 1)],
            unique=True,
            partialFilterExpression={
                "kind": "proactive_followup",
                "lifecycle_state": "active",
            },
        )

    def create_action(self, document: Dict) -> str:
        result = self.collection.insert_one(document)
        return str(result.inserted_id)

    def get_action(self, action_id: str) -> Optional[Dict]:
        return self.collection.find_one({"_id": ObjectId(action_id)})

    def update_action(
        self,
        action_id: str,
        updates: Dict,
        expected_revision: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        selector: Dict = {"_id": ObjectId(action_id)}
        if expected_revision is not None:
            selector["revision"] = expected_revision

        set_fields = dict(updates)
        set_fields["updated_at"] = now or datetime.utcnow()
        result = self.collection.update_one(
            selector,
            {"$set": set_fields, "$inc": {"revision": 1}},
        )
        return result.modified_count > 0

    def claim_action_lease(
        self,
        action_id: str,
        revision: int,
        scheduled_for: datetime,
        token: str,
        leased_at: datetime,
        lease_until: datetime,
    ) -> bool:
        result = self.collection.update_one(
            {
                "_id": ObjectId(action_id),
                "lifecycle_state": "active",
                "revision": revision,
                "next_run_at": scheduled_for,
                "lease.token": None,
            },
            {
                "$set": {
                    "lease.token": token,
                    "lease.leased_at": leased_at,
                    "lease.lease_expires_at": lease_until,
                }
            },
        )
        return result.modified_count > 0

    def release_action_lease(self, action_id: str, token: str) -> bool:
        result = self.collection.update_one(
            {"_id": ObjectId(action_id), "lease.token": token},
            {
                "$set": {
                    "lease.token": None,
                    "lease.leased_at": None,
                    "lease.lease_expires_at": None,
                }
            },
        )
        return result.modified_count > 0

    def list_active_actions(self) -> List[Dict]:
        return list(self.collection.find({"lifecycle_state": "active"}).sort("next_run_at", 1))

    def list_visible_actions(self, user_id: str) -> List[Dict]:
        return list(
            self.collection.find(
                {
                    "user_id": user_id,
                    "kind": "user_reminder",
                    "visibility": "visible",
                    "lifecycle_state": {"$in": ["active", "completed", "cancelled"]},
                }
            ).sort("next_run_at", 1)
        )

    def find_active_internal_followup(self, conversation_id: str) -> Optional[Dict]:
        return self.collection.find_one(
            {
                "conversation_id": conversation_id,
                "kind": "proactive_followup",
                "visibility": "internal",
                "lifecycle_state": "active",
            }
        )

    def reconcile_expired_leases(self, now: datetime) -> int:
        result = self.collection.update_many(
            {
                "lifecycle_state": "active",
                "lease.token": {"$ne": None},
                "lease.lease_expires_at": {"$lt": now},
            },
            {
                "$set": {
                    "lease.token": None,
                    "lease.leased_at": None,
                    "lease.lease_expires_at": None,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count

    def close(self):
        self.client.close()
