# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from agent.agno_agent.runtime.pending_workflow import ACTIVE_WORKFLOW_STATUSES
from conf.config import CONF


class PendingWorkflowDAO:
    COLLECTION = "pending_workflows"

    def __init__(
        self,
        mongo_uri: str = "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name: str = CONF["mongodb"]["mongodb_name"],
    ) -> None:
        self.client = MongoClient(mongo_uri, tz_aware=True)
        self.db = self.client[db_name]
        self.collection: Collection = self.db.get_collection(self.COLLECTION)

    def create_indexes(self) -> None:
        self.collection.create_index(
            [("owner_user_id", 1), ("conversation_id", 1)],
            unique=True,
            partialFilterExpression={"status": {"$in": list(ACTIVE_WORKFLOW_STATUSES)}},
        )
        self.collection.create_index([("expires_at", 1)], expireAfterSeconds=0)
        self.collection.create_index([("status", 1), ("updated_at", 1)])

    def load_active_for_conversation(
        self, owner_user_id: str, conversation_id: str, now: datetime | None = None
    ) -> dict[str, Any] | None:
        selector = {
            "owner_user_id": owner_user_id,
            "conversation_id": conversation_id,
            "status": {"$in": list(ACTIVE_WORKFLOW_STATUSES)},
        }
        if now is not None:
            selector["expires_at"] = {"$gt": now}
        return self.collection.find_one(selector, sort=[("updated_at", -1)])

    def upsert_new_active_workflow(
        self, document: dict[str, Any], now: datetime | None = None
    ) -> bool:
        write_doc = dict(document)
        write_doc["revision"] = 0
        if now is not None:
            self.collection.update_many(
                {
                    "owner_user_id": write_doc["owner_user_id"],
                    "conversation_id": write_doc["conversation_id"],
                    "status": {"$in": list(ACTIVE_WORKFLOW_STATUSES)},
                    "expires_at": {"$lte": now},
                },
                {
                    "$set": {
                        "status": "expired",
                        "document.status": "expired",
                        "updated_at": now,
                    }
                },
            )
        try:
            self.collection.insert_one(write_doc)
        except DuplicateKeyError:
            return False
        return True

    def cas_update_workflow(
        self,
        workflow_id: str,
        owner_user_id: str,
        conversation_id: str,
        expected_revision: int,
        document: dict[str, Any],
    ) -> bool:
        write_doc = dict(document)
        write_doc["revision"] = expected_revision + 1
        write_doc["updated_at"] = (
            write_doc.get("updated_at") or datetime.now().astimezone()
        )
        result = self.collection.update_one(
            {
                "id": workflow_id,
                "owner_user_id": owner_user_id,
                "conversation_id": conversation_id,
                "revision": expected_revision,
            },
            {"$set": write_doc},
        )
        return result.matched_count > 0

    def mark_terminal_workflow_from_executing(
        self,
        workflow_id: str,
        owner_user_id: str,
        conversation_id: str,
        document: dict[str, Any],
    ) -> bool:
        result = self.collection.update_one(
            {
                "id": workflow_id,
                "owner_user_id": owner_user_id,
                "conversation_id": conversation_id,
                "status": "executing",
            },
            {"$set": dict(document)},
        )
        return result.matched_count > 0

    def close(self) -> None:
        self.client.close()
