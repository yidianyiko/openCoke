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


def _discover_account_id(db) -> tuple[Optional[str], bool]:
    collection_names = set(db.list_collection_names())
    observed_business_docs = False
    for collection_name, field_path in ACCOUNT_ID_COLLECTION_PATHS:
        if collection_name not in collection_names:
            continue
        collection = db.get_collection(collection_name)
        projection = {"_id": 0, field_path: 1}
        for document in collection.find({}, projection).limit(50):
            observed_business_docs = True
            for value in _extract_field_values(document, field_path.split(".")):
                if _is_account_id(value):
                    return str(value).strip(), True
    return None, observed_business_docs


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
    account_id: Optional[str],
    observed_business_docs: bool,
) -> dict:
    if not account_id:
        return {
            "account_id": None,
            "resolved": not observed_business_docs,
        }

    resolved = isinstance(user_dao.get_user_by_account_id(account_id), dict)
    return {
        "account_id": account_id,
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
                "accountAccessAllowed": False,
                "accountAccessDeniedReason": "subscription_required",
                "renewalUrl": "https://renew.example/checkout",
            },
        }
    )
    if not isinstance(response, dict) or response.get("status") != "ok":
        raise RuntimeError(f"bridge_payload_verification_failed:{response}")

    captured_calls = getattr(bridge_gateway.message_gateway, "calls", None)
    if not isinstance(captured_calls, list) or not captured_calls:
        raise RuntimeError("bridge_payload_verification_failed:no_enqueue_call")

    inbound = captured_calls[0]["inbound"]
    payload_keys = sorted(inbound.keys())
    forbidden_keys = [key for key in FORBIDDEN_ROUTE_KEYS if key in inbound]
    return {
        "forbidden_keys": forbidden_keys,
        "payload_keys": payload_keys,
    }


class _CapturingMessageGateway:
    def __init__(self):
        self.calls: list[dict] = []

    def enqueue(self, **kwargs):
        self.calls.append(kwargs)
        return "in_evt_verify_1"


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
            account_id, observed_business_docs = _discover_account_id(db)
        business_account_resolution = _check_business_account_resolution(
            user_dao,
            account_id,
            observed_business_docs,
        )

        if bridge_gateway_factory is None:
            message_gateway = _CapturingMessageGateway()
            bridge_gateway = BusinessOnlyBridgeGateway(
                message_gateway=message_gateway,
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
