from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from pymongo import MongoClient
from pymongo.collection import Collection

from conf.config import CONF

BASE_AGENT_TYPE = "coke_companion"
COLLECTION_NAME = "agent_instances"
OVERRIDE_FIELDS = (
    "display_name",
    "nickname",
    "user_address_name",
    "persona",
    "background",
    "speaking_style",
    "extra_rules",
    "status",
    "proactive",
    "memory",
)


def _mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


def _now_default() -> datetime:
    return datetime.now(UTC)


def _instance_id() -> str:
    return f"agentinst_{uuid4().hex}"


class AgentInstanceDAO:
    def __init__(
        self,
        *,
        collection: Collection | None = None,
        mongo_uri: str | None = None,
        db_name: str | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = None
        if collection is None:
            self.client = MongoClient(mongo_uri or _mongo_uri(), tz_aware=True)
            db = self.client[db_name or CONF["mongodb"]["mongodb_name"]]
            collection = db.get_collection(COLLECTION_NAME)
        self.collection = collection
        self.now_provider = now_provider or _now_default

    def create_indexes(self) -> None:
        self.collection.create_index(
            [("owner_user_id", 1), ("base_agent_type", 1)],
            unique=True,
            partialFilterExpression={"active": True},
        )

    def get_active_agent_instance(
        self,
        owner_user_id: str,
        *,
        base_agent_type: str = BASE_AGENT_TYPE,
    ) -> Optional[Dict[str, Any]]:
        owner = _require_owner(owner_user_id)
        return self.collection.find_one(
            {
                "owner_user_id": owner,
                "base_agent_type": base_agent_type,
                "active": True,
            }
        )

    def upsert_active_agent_instance(
        self,
        owner_user_id: str,
        overrides: Dict[str, Any],
        *,
        base_character_id: str,
        base_agent_type: str = BASE_AGENT_TYPE,
    ) -> Dict[str, Any]:
        owner = _require_owner(owner_user_id)
        now = self.now_provider()
        sanitized = _sanitize_overrides(overrides)
        selector = {
            "owner_user_id": owner,
            "base_agent_type": base_agent_type,
            "active": True,
        }
        set_fields = {
            **sanitized,
            "owner_user_id": owner,
            "base_agent_type": base_agent_type,
            "base_character_id": _require_string(base_character_id, "base_character_id"),
            "active": True,
            "updated_at": now,
        }
        self.collection.update_one(
            selector,
            {
                "$set": set_fields,
                "$setOnInsert": {
                    "agent_instance_id": _instance_id(),
                    "created_at": now,
                },
            },
            upsert=True,
        )
        result = self.get_active_agent_instance(owner, base_agent_type=base_agent_type)
        if result is None:
            raise RuntimeError("agent_instance_upsert_failed")
        return result

    def reset_active_agent_instance(
        self,
        owner_user_id: str,
        *,
        base_character_id: str,
        base_agent_type: str = BASE_AGENT_TYPE,
    ) -> Dict[str, Any]:
        cleared = {field: None for field in OVERRIDE_FIELDS}
        cleared["status"] = {"place": None, "action": None}
        cleared["proactive"] = {"enabled": None}
        cleared["memory"] = {"enabled": None}
        return self.upsert_active_agent_instance(
            owner_user_id,
            cleared,
            base_character_id=base_character_id,
            base_agent_type=base_agent_type,
        )

    def close(self) -> None:
        if self.client is not None:
            self.client.close()


def _require_owner(value: Any) -> str:
    normalized = _require_string(value, "owner_user_id")
    if not (normalized.startswith("ck_") or normalized.startswith("acct_")):
        raise ValueError("invalid_owner_user_id")
    return normalized


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_required")
    return value.strip()


def _sanitize_overrides(overrides: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(overrides, dict):
        raise ValueError("invalid_body")
    return {field: overrides[field] for field in OVERRIDE_FIELDS if field in overrides}
