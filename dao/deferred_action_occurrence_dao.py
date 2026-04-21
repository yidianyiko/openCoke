# -*- coding: utf-8 -*-
"""MongoDB access for deferred action occurrences."""

from datetime import datetime
from typing import Dict

from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection

from conf.config import CONF


class DeferredActionOccurrenceDAO:
    COLLECTION = "deferred_action_occurrences"

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
        self.collection.create_index("trigger_key", unique=True)
        self.collection.create_index([("action_id", 1), ("scheduled_for", 1)])

    def claim_or_get_occurrence(
        self,
        action_id: str,
        trigger_key: str,
        scheduled_for: datetime,
        started_at: datetime,
    ) -> Dict:
        return self.collection.find_one_and_update(
            {"trigger_key": trigger_key},
            {
                "$setOnInsert": {
                    "action_id": action_id,
                    "scheduled_for": scheduled_for,
                    "trigger_key": trigger_key,
                    "status": "claimed",
                    "attempt_count": 1,
                    "last_started_at": started_at,
                    "last_finished_at": None,
                    "last_error": None,
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    def increment_attempt_count(self, trigger_key: str, started_at: datetime) -> None:
        self.collection.update_one(
            {"trigger_key": trigger_key},
            {
                "$inc": {"attempt_count": 1},
                "$set": {"status": "claimed", "last_started_at": started_at},
            },
        )

    def mark_occurrence_succeeded(self, trigger_key: str, finished_at: datetime) -> None:
        self.collection.update_one(
            {"trigger_key": trigger_key},
            {
                "$set": {
                    "status": "succeeded",
                    "last_finished_at": finished_at,
                    "last_error": None,
                }
            },
        )

    def mark_occurrence_failed(
        self,
        trigger_key: str,
        error: str,
        finished_at: datetime,
    ) -> None:
        self.collection.update_one(
            {"trigger_key": trigger_key},
            {
                "$set": {
                    "status": "failed",
                    "last_finished_at": finished_at,
                    "last_error": error,
                }
            },
        )

    def close(self):
        self.client.close()
