import sys

sys.path.append(".")

from util.log_util import get_logger

logger = get_logger(__name__)

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import MongoClient
from pymongo.collection import Collection

from conf.config import CONF

AUDIT_CUSTOMER_ID_COLLECTION_SPECS = (
    {"collection": "outputmessages", "fieldPath": "account_id"},
    {"collection": "reminders", "fieldPath": "user_id"},
    {"collection": "conversations", "fieldPath": "talkers.id"},
)


def _normalize_customer_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_account_id_reference(value: Any) -> Optional[str]:
    normalized = _normalize_customer_id(value)
    if normalized is None:
        return None
    if normalized.startswith(("acct_", "ck_")):
        return normalized
    return None


def _extract_field_values(value: Any, path_parts: Sequence[str]) -> List[Any]:
    if not path_parts:
        if isinstance(value, list):
            return list(value)
        return [value]

    if isinstance(value, list):
        extracted: List[Any] = []
        for item in value:
            extracted.extend(_extract_field_values(item, path_parts))
        return extracted

    if not isinstance(value, dict):
        return []

    head = path_parts[0]
    if head not in value:
        return []

    return _extract_field_values(value[head], path_parts[1:])


def audit_customer_id_parity(
    customer_ids: Iterable[Any],
    mongo_uri: str = "mongodb://"
    + CONF["mongodb"]["mongodb_ip"]
    + ":"
    + CONF["mongodb"]["mongodb_port"]
    + "/",
    db_name: str = CONF["mongodb"]["mongodb_name"],
    collection_specs: Sequence[Dict[str, str]] = AUDIT_CUSTOMER_ID_COLLECTION_SPECS,
    example_limit: int = 20,
    server_selection_timeout_ms: int = 5000,
) -> Dict[str, Any]:
    normalized_customer_ids = {
        normalized
        for normalized in (_normalize_customer_id(value) for value in customer_ids)
        if normalized is not None
    }

    client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
    )
    try:
        client.admin.command("ping")
        db = client[db_name]

        collections_checked: List[str] = []
        examples: List[Dict[str, str]] = []
        drift_count = 0

        for spec in collection_specs:
            collection_name = spec["collection"]
            field_path = spec["fieldPath"]
            collections_checked.append(collection_name)

            collection = db.get_collection(collection_name)
            cursor = collection.find({}, {"_id": 1, field_path: 1})

            for document in cursor:
                for value in _extract_field_values(document, field_path.split(".")):
                    account_id = _normalize_account_id_reference(value)
                    if account_id is None or account_id in normalized_customer_ids:
                        continue

                    drift_count += 1
                    if len(examples) >= example_limit:
                        continue

                    examples.append(
                        {
                            "collection": collection_name,
                            "fieldPath": field_path,
                            "documentId": str(document.get("_id")),
                            "accountId": account_id,
                        }
                    )

        return {
            "collectionsChecked": collections_checked,
            "driftCount": drift_count,
            "examples": examples,
        }
    finally:
        client.close()


def _normalize_account_id(value: Any) -> Optional[str]:
    return _normalize_customer_id(value)


class UserDAO:
    """Business DAO for legacy users, user profiles, settings, and characters."""

    def __init__(
        self,
        mongo_uri: str = "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name: str = CONF["mongodb"]["mongodb_name"],
    ):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection: Collection = self.db.get_collection("users")
        self.profile_collection: Collection = self.db.get_collection("user_profiles")
        self.settings_collection: Collection = self.db.get_collection("coke_settings")
        self.characters_collection: Collection = self.db.get_collection("characters")

    def create_indexes(self):
        self.profile_collection.create_index([("account_id", 1)], unique=True)
        self.settings_collection.create_index([("account_id", 1)], unique=True)
        self.characters_collection.create_index([("name", 1)])

    def _sanitize_character_document(self, user_data: Dict) -> Dict:
        sanitized = {}
        for field in ("_id", "name", "nickname", "platforms", "user_info"):
            if field in user_data:
                sanitized[field] = user_data[field]
        return sanitized

    def _build_business_documents(self, account_id: str, user_data: Dict) -> tuple[Dict, Dict]:
        profile_doc = {"account_id": account_id}
        settings_doc = {"account_id": account_id}

        for field in ("name", "display_name", "platforms", "user_info"):
            if field in user_data:
                profile_doc[field] = user_data[field]

        for field in ("timezone", "access"):
            if field in user_data:
                settings_doc[field] = user_data[field]

        return profile_doc, settings_doc

    def create_user(self, user_data: Dict) -> str:
        character_id = user_data.get("_id")
        if isinstance(character_id, str) and ObjectId.is_valid(character_id):
            user_data = dict(user_data)
            user_data["_id"] = ObjectId(character_id)

        if user_data.get("is_character") is True:
            result = self.characters_collection.insert_one(
                self._sanitize_character_document(user_data)
            )
            return str(result.inserted_id)

        account_id = _normalize_account_id(user_data.get("account_id"))
        if account_id is None:
            raise ValueError("account_id_required")

        profile_doc, settings_doc = self._build_business_documents(account_id, user_data)
        self.profile_collection.replace_one(
            {"account_id": account_id},
            profile_doc,
            upsert=True,
        )
        self.settings_collection.replace_one(
            {"account_id": account_id},
            settings_doc,
            upsert=True,
        )
        return account_id

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        if not user_id:
            return None

        try:
            object_id = ObjectId(user_id)
        except (TypeError, ValueError, InvalidId):
            return None

        user = self.collection.find_one({"_id": object_id})
        if user is not None:
            return user

        return self.characters_collection.find_one({"_id": object_id})

    def get_user_by_phone_number(self, phone_number: str) -> Optional[Dict]:
        return None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        return None

    def update_user(self, user_id: str, update_data: Dict) -> bool:
        try:
            object_id = ObjectId(user_id)
        except (TypeError, ValueError, InvalidId):
            return False

        result = self.collection.update_one({"_id": object_id}, {"$set": update_data})
        return result.modified_count > 0

    def delete_user(self, user_id: str) -> bool:
        try:
            object_id = ObjectId(user_id)
        except (TypeError, ValueError, InvalidId):
            return False

        result = self.collection.delete_one({"_id": object_id})
        return result.deleted_count > 0

    def change_status(self, user_id: str, status: str) -> bool:
        return False

    def find_users(
        self, query: Dict = None, limit: int = 0, skip: int = 0, sort=None
    ) -> List[Dict]:
        if query is None:
            query = {}

        cursor = self.profile_collection.find(query)

        if skip > 0:
            cursor = cursor.skip(skip)

        if limit > 0:
            cursor = cursor.limit(limit)

        if sort:
            cursor = cursor.sort(sort)

        return list(cursor)

    def count_users(self, query: Dict = None) -> int:
        if query is None:
            query = {}

        return self.profile_collection.count_documents(query)

    def find_characters(self, query: Dict = None, limit: int = 0) -> List[Dict]:
        if query is None:
            query = {}

        character_query = dict(query)
        character_query.pop("is_character", None)

        cursor = (
            self.characters_collection.find(character_query).limit(limit)
            if limit > 0
            else self.characters_collection.find(character_query)
        )
        return list(cursor)

    def bulk_update_users(self, query: Dict, update: Dict) -> int:
        result = self.profile_collection.update_many(query, {"$set": update})
        return result.modified_count

    def upsert_user(self, query: Dict, user_data: Dict) -> str:
        is_character = user_data.get("is_character") is True or query.get("is_character") is True
        if is_character:
            character_query = dict(query)
            character_query.pop("is_character", None)
            sanitized = self._sanitize_character_document(user_data)
            result = self.characters_collection.update_one(
                character_query,
                {"$set": sanitized},
                upsert=True,
            )
            if result.upserted_id:
                return str(result.upserted_id)
            user = self.characters_collection.find_one(character_query, {"_id": 1})
            return str(user["_id"]) if user else None

        account_id = _normalize_account_id(
            user_data.get("account_id") or query.get("account_id")
        )
        if account_id is None:
            raise ValueError("account_id_required")

        profile_doc, settings_doc = self._build_business_documents(account_id, user_data)
        self.profile_collection.replace_one(
            {"account_id": account_id},
            profile_doc,
            upsert=True,
        )
        self.settings_collection.replace_one(
            {"account_id": account_id},
            settings_doc,
            upsert=True,
        )
        return account_id

    def _update_settings(self, account_id: str, update_fields: Dict) -> bool:
        normalized_account_id = _normalize_account_id(account_id)
        if normalized_account_id is None:
            return False

        result = self.settings_collection.update_one(
            {"account_id": normalized_account_id},
            {"$set": update_fields},
        )
        return result.modified_count > 0

    def update_access(self, user_id: str, order_no: str, expire_time: datetime) -> bool:
        return self._update_settings(
            user_id,
            {
                "access.order_no": order_no,
                "access.granted_at": datetime.now(),
                "access.expire_time": expire_time,
            },
        )

    def update_timezone(self, user_id: str, timezone: str) -> bool:
        return self._update_settings(user_id, {"timezone": timezone})

    def update_access_stripe(
        self,
        user_id: str,
        stripe_customer_id: str,
        stripe_subscription_id: str,
        expire_time: datetime,
    ) -> bool:
        return self._update_settings(
            user_id,
            {
                "access.stripe_customer_id": stripe_customer_id,
                "access.stripe_subscription_id": stripe_subscription_id,
                "access.expire_time": expire_time,
                "access.granted_at": datetime.now(),
            },
        )

    def update_access_creem(
        self,
        user_id: str,
        creem_customer_id: str,
        creem_subscription_id: str,
        expire_time: datetime,
    ) -> bool:
        return self._update_settings(
            user_id,
            {
                "access.creem_customer_id": creem_customer_id,
                "access.creem_subscription_id": creem_subscription_id,
                "access.expire_time": expire_time,
                "access.granted_at": datetime.now(),
            },
        )

    def revoke_access(self, user_id: str) -> bool:
        return self._update_settings(
            user_id,
            {"access.expire_time": datetime.now()},
        )

    def close(self):
        self.client.close()


if __name__ == "__main__":
    user_model = UserDAO()
    results = user_model.find_users(query={}, limit=10)

    for result in results:
        print(result)

    user_model.close()
