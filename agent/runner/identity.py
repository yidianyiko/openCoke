from collections.abc import Mapping

from bson import ObjectId


def is_mongo_object_id(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return ObjectId.is_valid(value)


def is_synthetic_coke_account_id(value: str) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    return normalized.startswith(("acct_", "ck_"))


def get_agent_entity_id(entity: dict | None) -> str:
    if not isinstance(entity, Mapping):
        return ""

    entity_id = entity.get("id")
    if entity_id is not None:
        entity_id = str(entity_id).strip()
        if entity_id:
            return entity_id

    entity_id = entity.get("_id")
    if entity_id is not None:
        entity_id = str(entity_id).strip()
        if entity_id:
            return entity_id

    return ""


def resolve_agent_user_context(user_id, input_message, user_dao):
    user_id_str = "" if user_id is None else str(user_id).strip()
    if not user_id_str:
        return None

    if is_mongo_object_id(user_id_str):
        user = user_dao.get_user_by_id(user_id_str)
        if not isinstance(user, dict):
            return user
        canonical_id = get_agent_entity_id(user) or user_id_str
        resolved_user = dict(user)
        resolved_user.setdefault("id", canonical_id)
        resolved_user.setdefault("_id", canonical_id)
        return resolved_user

    if not isinstance(input_message, Mapping):
        return None
    if input_message.get("platform") != "business":
        return None

    metadata = input_message.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    if metadata.get("source") != "clawscale":
        return None

    customer = metadata.get("customer")
    if not isinstance(customer, Mapping):
        customer = {}

    coke_account = metadata.get("coke_account")
    if not isinstance(coke_account, Mapping):
        coke_account = {}

    account_id = (
        customer.get("id")
        or customer.get("_id")
        or customer.get("customer_id")
        or customer.get("coke_account_id")
        or coke_account.get("id")
        or coke_account.get("_id")
        or coke_account.get("coke_account_id")
        or user_id_str
    )
    if account_id is None:
        return None
    account_id = str(account_id).strip()
    if not account_id:
        return None

    display_name = (
        customer.get("display_name")
        or coke_account.get("display_name")
        or metadata.get("sender")
    )
    display_name = str(display_name).strip() if display_name is not None else ""
    if not display_name:
        display_name = f"user-{account_id[-6:]}"

    return {
        "id": account_id,
        "_id": account_id,
        "nickname": display_name,
        "is_coke_account": True,
    }
