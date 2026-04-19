import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pymongo import MongoClient

from conf.config import CONF
from connector.clawscale_bridge.app import BusinessOnlyBridgeGateway
from connector.clawscale_bridge.message_gateway import CokeMessageGateway
from dao.user_dao import UserDAO

FORBIDDEN_ROUTE_KEYS = (
    "account_status",
    "email_verified",
    "subscription_active",
    "subscription_expires_at",
    "account_access_allowed",
    "account_access_denied_reason",
    "renewal_url",
)

ACCOUNT_ID_COLLECTION_PATHS = (
    ("user_profiles", "account_id"),
    ("coke_settings", "account_id"),
    ("outputmessages", "account_id"),
    ("reminders", "user_id"),
    ("conversations", "talkers.id"),
)


def _mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


def _json_default(value: Any):
    return str(value)


def _is_account_id(value: Any) -> bool:
    if value is None:
        return False
    normalized = str(value).strip()
    return normalized.startswith(("acct_", "ck_"))


def _extract_field_values(value: Any, path_parts: Iterable[str]) -> list[Any]:
    path_parts = list(path_parts)
    if not path_parts:
        if isinstance(value, list):
            return list(value)
        return [value]

    if isinstance(value, list):
        extracted: list[Any] = []
        for item in value:
            extracted.extend(_extract_field_values(item, path_parts))
        return extracted

    if not isinstance(value, dict):
        return []

    head = path_parts[0]
    if head not in value:
        return []

    return _extract_field_values(value[head], path_parts[1:])


def _discover_account_ids(db, max_account_ids: int = 5) -> tuple[list[str], bool]:
    collection_names = set(db.list_collection_names())
    observed_business_docs = False
    account_ids: list[str] = []
    seen = set()
    for collection_name, field_path in ACCOUNT_ID_COLLECTION_PATHS:
        if collection_name not in collection_names:
            continue
        collection = db.get_collection(collection_name)
        projection = {"_id": 0, field_path: 1}
        for document in collection.find({}, projection).limit(50):
            observed_business_docs = True
            for value in _extract_field_values(document, field_path.split(".")):
                if not _is_account_id(value):
                    continue
                normalized = str(value).strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                account_ids.append(normalized)
                if len(account_ids) >= max_account_ids:
                    return account_ids, True
    return account_ids, observed_business_docs


def _check_users_collection(db) -> dict:
    collection_names = set(db.list_collection_names())
    exists = "users" in collection_names
    document_count = 0
    if exists:
        document_count = db.get_collection("users").count_documents({})
    return {
        "exists": exists,
        "document_count": document_count,
    }


def _check_business_account_resolution(
    user_dao: UserDAO,
    account_ids: list[str],
    observed_business_docs: bool,
) -> dict:
    if not account_ids:
        return {
            "account_ids": [],
            "resolved": not observed_business_docs,
        }

    resolved = all(
        isinstance(user_dao.get_user_by_account_id(account_id), dict)
        for account_id in account_ids
    )
    return {
        "account_ids": account_ids,
        "resolved": resolved,
    }


def _check_bridge_payload(bridge_gateway) -> dict:
    response = bridge_gateway.handle_inbound(
        {
            "messages": [{"role": "user", "content": "verify auth retirement"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "channelScope": "personal",
                "clawscaleUserId": "csu_1",
                "businessConversationKey": "bc_verify_1",
                "inboundEventId": "in_evt_verify_1",
                "cokeAccountId": "acct_123",
                "cokeAccountDisplayName": "Alice",
                "accountStatus": "subscription_required",
                "emailVerified": True,
                "subscriptionActive": False,
                "subscriptionExpiresAt": "2026-04-30T00:00:00Z",
                "accountAccessAllowed": True,
                "accountAccessDeniedReason": "subscription_required",
                "renewalUrl": "https://renew.example/checkout",
            },
        }
    )
    if not isinstance(response, dict) or response.get("status") != "ok":
        raise RuntimeError(f"bridge_payload_verification_failed:{response}")

    inputmessages = bridge_gateway.message_gateway.mongo.get_collection("inputmessages")
    update_calls = getattr(inputmessages, "updated", None)
    if not isinstance(update_calls, list) or not update_calls:
        raise RuntimeError("bridge_payload_verification_failed:no_emitted_message")

    emitted = update_calls[0][0][1]["$setOnInsert"]
    customer = emitted["metadata"]["customer"]
    coke_account = emitted["metadata"]["coke_account"]
    forbidden_keys = [
        key
        for key in FORBIDDEN_ROUTE_KEYS
        if key in customer or key in coke_account
    ]
    return {
        "forbidden_keys": forbidden_keys,
        "customer_keys": sorted(customer.keys()),
        "coke_account_keys": sorted(coke_account.keys()),
    }


class _CapturingCollection:
    def __init__(self):
        self.updated: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def create_index(self, *args, **kwargs):
        return None

    def update_one(self, *args, **kwargs):
        self.updated.append((args, kwargs))
        return None


class _CapturingMongo:
    def __init__(self):
        self.inputmessages = _CapturingCollection()

    def get_collection(self, name: str):
        if name != "inputmessages":
            raise KeyError(name)
        return self.inputmessages


def verify_auth_retirement(
    *,
    mongo_client_factory: Callable[..., Any] = MongoClient,
    user_dao_factory: Callable[..., Any] = UserDAO,
    bridge_gateway_factory: Optional[Callable[[], Any]] = None,
    mongo_uri: Optional[str] = None,
    db_name: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    mongo_uri = mongo_uri or _mongo_uri()
    db_name = db_name or CONF["mongodb"]["mongodb_name"]

    client = mongo_client_factory(mongo_uri, serverSelectionTimeoutMS=5000)
    user_dao = user_dao_factory(mongo_uri=mongo_uri, db_name=db_name)
    try:
        client.admin.command("ping")
        db = client[db_name]

        users_collection = _check_users_collection(db)
        observed_business_docs = False
        if account_id is None:
            account_ids, observed_business_docs = _discover_account_ids(db)
        else:
            account_ids = [account_id]
        business_account_resolution = _check_business_account_resolution(
            user_dao,
            account_ids,
            observed_business_docs,
        )

        if bridge_gateway_factory is None:
            bridge_gateway = BusinessOnlyBridgeGateway(
                message_gateway=CokeMessageGateway(
                    mongo=_CapturingMongo(),
                    user_dao=SimpleNamespace(),
                ),
                reply_waiter=SimpleNamespace(
                    wait_for_reply=lambda *args, **kwargs: {"reply": "ok"}
                ),
                target_character_id="char_1",
            )
        else:
            bridge_gateway = bridge_gateway_factory()
        bridge_payload = _check_bridge_payload(bridge_gateway)

        report = {
            "users_collection": users_collection,
            "business_account_resolution": business_account_resolution,
            "bridge_payload": bridge_payload,
        }

        failures = []
        if users_collection["exists"] and users_collection["document_count"] > 0:
            failures.append("users_collection_not_empty")
        if not business_account_resolution["resolved"]:
            failures.append("business_account_not_resolved")
        if bridge_payload["forbidden_keys"]:
            failures.append("bridge_payload_contains_auth_only_keys")
        if failures:
            raise RuntimeError(
                json.dumps({"failures": failures, "report": report}, default=_json_default)
            )
        return report
    finally:
        close = getattr(user_dao, "close", None)
        if callable(close):
            close()
        client.close()


def main() -> int:
    try:
        report = verify_auth_retirement()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
