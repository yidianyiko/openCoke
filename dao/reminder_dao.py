# -*- coding: utf-8 -*-
"""MongoDB access for reminders."""

from datetime import date, datetime
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
        self.collection.create_index(
            [
                ("owner_user_id", 1),
                ("lifecycle_state", 1),
                ("schedule.local_date", 1),
                ("schedule.local_time", 1),
            ]
        )
        self.collection.create_index([("lifecycle_state", 1), ("next_fire_at", 1)])
        self.collection.create_index(
            [
                ("owner_user_id", 1),
                ("agent_output_target.conversation_id", 1),
            ],
            unique=True,
            partialFilterExpression={
                "visibility": "internal",
                "fire_mode": "followup",
                "lifecycle_state": "active",
            },
        )

    def insert_reminder(self, document: Dict) -> str:
        result = self.collection.insert_one(document)
        return str(result.inserted_id)

    def get_reminder(self, reminder_id: str) -> Optional[Dict]:
        return self.collection.find_one({"_id": ObjectId(reminder_id)})

    def get_reminder_for_owner(
        self, reminder_id: str, owner_user_id: str
    ) -> Optional[Dict]:
        return self.collection.find_one(
            {
                "_id": ObjectId(reminder_id),
                "owner_user_id": owner_user_id,
                "visibility": "visible",
            }
        )

    def list_for_owner(
        self, owner_user_id: str, lifecycle_states: Optional[List[str]] = None
    ) -> List[Dict]:
        selector: Dict = {"owner_user_id": owner_user_id, "visibility": "visible"}
        if lifecycle_states is not None:
            selector["lifecycle_state"] = {"$in": lifecycle_states}
        return list(self.collection.find(selector))

    def list_for_owner_in_local_date_range(
        self,
        owner_user_id: str,
        *,
        from_date: date,
        to_date: date,
        lifecycle_states: List[str],
    ) -> List[Dict]:
        selector: Dict = {
            "owner_user_id": owner_user_id,
            "visibility": "visible",
            "lifecycle_state": {"$in": lifecycle_states},
            "schedule.local_date": {
                "$gte": from_date.isoformat(),
                "$lte": to_date.isoformat(),
            },
        }
        return list(
            self.collection.find(selector).sort(
                [("schedule.local_date", 1), ("schedule.local_time", 1)]
            )
        )

    def list_visible_recurrence_sources_for_owner(
        self,
        owner_user_id: str,
        *,
        to_date: date,
        lifecycle_states: List[str],
    ) -> List[Dict]:
        selector: Dict = {
            "owner_user_id": owner_user_id,
            "visibility": "visible",
            "lifecycle_state": {"$in": lifecycle_states},
            "schedule.rrule": {"$exists": True, "$ne": None},
            "schedule.local_date": {"$lte": to_date.isoformat()},
        }
        return list(
            self.collection.find(selector).sort(
                [("schedule.local_date", 1), ("schedule.local_time", 1)]
            )
        )

    def list_visible_occupied_sources_for_owner(
        self,
        owner_user_id: str,
        *,
        range_end_at: datetime,
        lifecycle_states: List[str],
    ) -> List[Dict]:
        selector: Dict = {
            "owner_user_id": owner_user_id,
            "visibility": "visible",
            "lifecycle_state": {"$in": lifecycle_states},
            "schedule.duration_minutes": {"$exists": True, "$ne": None},
            "schedule.anchor_at": {"$lt": range_end_at},
        }
        return list(
            self.collection.find(selector).sort(
                [("schedule.anchor_at", 1), ("schedule.local_time", 1)]
            )
        )

    def list_due_active(self) -> List[Dict]:
        return list(
            self.collection.find(
                {
                    "lifecycle_state": "active",
                    "next_fire_at": {"$ne": None, "$exists": True},
                }
            ).sort("next_fire_at", 1)
        )

    def find_active_internal_followup(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
    ) -> Optional[Dict]:
        return self.collection.find_one(
            {
                "owner_user_id": owner_user_id,
                "agent_output_target.conversation_id": conversation_id,
                "visibility": "internal",
                "fire_mode": "followup",
                "lifecycle_state": "active",
            }
        )

    def find_imported_duplicate(
        self,
        *,
        owner_user_id: str,
        import_provider: str,
        source_event_id: str,
        source_original_start_time: str,
    ) -> Optional[Dict]:
        return self.collection.find_one(
            {
                "owner_user_id": owner_user_id,
                "metadata.import_provider": import_provider,
                "metadata.source_event_id": source_event_id,
                "metadata.source_original_start_time": source_original_start_time,
            }
        )

    def find_visible_by_metadata_key(
        self, *, owner_user_id: str, key: str, value: str
    ) -> Optional[Dict]:
        return self.collection.find_one(
            {
                "owner_user_id": owner_user_id,
                "visibility": "visible",
                f"metadata.{key}": value,
            }
        )

    def replace_reminder(
        self,
        reminder_id: str,
        owner_user_id: str,
        updates: Dict,
        lifecycle_state: Optional[str] = None,
        visibility: str = "visible",
    ) -> bool:
        selector: Dict = {
            "_id": ObjectId(reminder_id),
            "owner_user_id": owner_user_id,
            "visibility": visibility,
        }
        if lifecycle_state is not None:
            selector["lifecycle_state"] = lifecycle_state
        result = self.collection.update_one(
            selector,
            {"$set": updates},
        )
        return result.matched_count > 0

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
        return result.matched_count > 0

    def atomic_apply_fire_failure(
        self, reminder_id: str, expected_next_fire_at: datetime, updates: Dict
    ) -> bool:
        set_fields = dict(updates)
        set_fields["lifecycle_state"] = "failed"
        set_fields["next_fire_at"] = None
        result = self.collection.update_one(
            {
                "_id": ObjectId(reminder_id),
                "next_fire_at": expected_next_fire_at,
                "lifecycle_state": "active",
            },
            {"$set": set_fields},
        )
        return result.matched_count > 0

    def close(self):
        self.client.close()
