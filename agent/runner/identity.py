from collections.abc import Mapping

from bson import ObjectId


def is_mongo_object_id(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return ObjectId.is_valid(value)


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

    coke_account = metadata.get("coke_account")
    if not isinstance(coke_account, Mapping):
        return None

    account_id = (
        coke_account.get("id")
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
        coke_account.get("display_name")
        or coke_account.get("nickname")
        or coke_account.get("name")
        or account_id
    )
    display_name = str(display_name).strip() or account_id

    return {
        "id": account_id,
        "_id": account_id,
        "nickname": display_name,
        "is_coke_account": True,
    }
