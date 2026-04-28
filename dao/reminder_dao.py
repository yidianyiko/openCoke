# -*- coding: utf-8 -*-
"""MongoDB access for reminders."""

from datetime import datetime
from typing import Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection

from conf.config import CONF


class ReminderDAO:
    COLLECTION = "reminders"

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

    def create_indexes(self) -> None:
        self.collection.create_index(
            [("owner_user_id", 1), ("lifecycle_state", 1), ("created_at", 1)]
        )
        self.collection.create_index([("lifecycle_state", 1), ("next_fire_at", 1)])

    def insert_reminder(self, document: Dict) -> str:
        result = self.collection.insert_one(document)
        return str(result.inserted_id)

    def get_reminder(self, reminder_id: str) -> Optional[Dict]:
        return self.collection.find_one({"_id": ObjectId(reminder_id)})

    def get_reminder_for_owner(
        self, reminder_id: str, owner_user_id: str
    ) -> Optional[Dict]:
        return self.collection.find_one(
            {"_id": ObjectId(reminder_id), "owner_user_id": owner_user_id}
        )

    def list_for_owner(
        self, owner_user_id: str, lifecycle_states: Optional[List[str]] = None
    ) -> List[Dict]:
        selector: Dict = {"owner_user_id": owner_user_id}
        if lifecycle_states is not None:
            selector["lifecycle_state"] = {"$in": lifecycle_states}
        return list(self.collection.find(selector))

    def list_due_active(self) -> List[Dict]:
        return list(
            self.collection.find(
                {"lifecycle_state": "active", "next_fire_at": {"$ne": None}}
            )
        )

    def replace_reminder(
        self, reminder_id: str, owner_user_id: str, updates: Dict
    ) -> bool:
        result = self.collection.update_one(
            {"_id": ObjectId(reminder_id), "owner_user_id": owner_user_id},
            {"$set": updates},
        )
        return result.modified_count > 0

    def atomic_apply_fire_success(
        self, reminder_id: str, expected_next_fire_at: datetime, updates: Dict
    ) -> bool:
        result = self.collection.update_one(
            {
                "_id": ObjectId(reminder_id),
                "next_fire_at": expected_next_fire_at,
                "lifecycle_state": "active",
            },
            {"$set": updates},
        )
        return result.modified_count > 0

    def atomic_apply_fire_failure(
        self, reminder_id: str, expected_next_fire_at: datetime, updates: Dict
    ) -> bool:
        set_fields = dict(updates)
        set_fields["next_fire_at"] = None
        result = self.collection.update_one(
            {
                "_id": ObjectId(reminder_id),
                "next_fire_at": expected_next_fire_at,
                "lifecycle_state": "active",
            },
            {"$set": set_fields},
        )
        return result.modified_count > 0

    def close(self):
        self.client.close()
