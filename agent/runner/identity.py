from collections.abc import Mapping
import re

from bson import ObjectId

from agent.timezone_service import TimezoneService
from util.time_util import get_default_timezone


TIMEZONE_STATE_FIELDS = (
    "timezone",
    "timezone_source",
    "timezone_status",
    "pending_timezone_change",
    "pending_task_draft",
)

PHONE_LIKE_RE = re.compile(r"^\+?\d{7,20}$")
PHONE_TIMEZONE_BY_PREFIX = (
    ("886", "Asia/Taipei"),
    ("852", "Asia/Hong_Kong"),
    ("853", "Asia/Macau"),
    ("81", "Asia/Tokyo"),
    ("82", "Asia/Seoul"),
    ("86", "Asia/Shanghai"),
)


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


def _metadata_account_id(entity: Mapping) -> str:
    for key in ("id", "_id", "customer_id", "coke_account_id"):
        value = entity.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return ""


def _restrict_metadata_to_account(account_id: str, entity: Mapping) -> Mapping:
    metadata_account_id = _metadata_account_id(entity)
    if metadata_account_id and metadata_account_id != account_id:
        return {}
    return entity


def _resolve_clawscale_account_id(user_id_str, input_message):
    if not isinstance(input_message, Mapping):
        return None, {}, {}
    if input_message.get("platform") != "business":
        return None, {}, {}

    metadata = input_message.get("metadata")
    if not isinstance(metadata, Mapping):
        return None, {}, {}
    if metadata.get("source") != "clawscale":
        return None, {}, {}

    customer = metadata.get("customer")
    if not isinstance(customer, Mapping):
        customer = {}

    coke_account = metadata.get("coke_account")
    if not isinstance(coke_account, Mapping):
        coke_account = {}

    synthetic_account_id = user_id_str if is_synthetic_coke_account_id(user_id_str) else None
    if synthetic_account_id is not None:
        account_id = synthetic_account_id
        customer = _restrict_metadata_to_account(account_id, customer)
        coke_account = _restrict_metadata_to_account(account_id, coke_account)
    else:
        account_id = (
            customer.get("id")
            or customer.get("_id")
            or customer.get("customer_id")
            or customer.get("coke_account_id")
            or coke_account.get("id")
            or coke_account.get("_id")
            or coke_account.get("coke_account_id")
        )
    if account_id is None:
        return None, customer, coke_account

    account_id = str(account_id).strip()
    if not account_id:
        return None, customer, coke_account

    return account_id, customer, coke_account


def _resolve_clawscale_display_name(account_id, input_message, customer, coke_account):
    metadata = input_message.get("metadata") if isinstance(input_message, Mapping) else {}
    if not isinstance(metadata, Mapping):
        metadata = {}

    display_name = (
        customer.get("display_name")
        or coke_account.get("display_name")
        or metadata.get("sender")
    )
    display_name = str(display_name).strip() if display_name is not None else ""
    if display_name:
        return display_name
    return f"user-{account_id[-6:]}"


def _extract_timezone_candidates(input_message):
    if not isinstance(input_message, Mapping):
        return []

    metadata = input_message.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}

    candidates = []
    seen = set()
    for value in (
        input_message.get("timezone"),
        metadata.get("timezone"),
    ):
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(
            {
                "timezone": normalized,
                "source": "external_account_timezone",
            }
        )

    for value in (
        input_message.get("external_id"),
        input_message.get("externalId"),
        metadata.get("external_id"),
        metadata.get("externalId"),
    ):
        if value is None:
            continue
        mapped_timezone = _map_phone_like_identity_timezone(value)
        if not mapped_timezone or mapped_timezone in seen:
            continue
        seen.add(mapped_timezone)
        candidates.append(
            {
                "timezone": mapped_timezone,
                "source": "messaging_identity_region",
            }
        )
    return candidates


def _map_phone_like_identity_timezone(value):
    normalized = str(value).strip()
    if not normalized:
        return None

    digits = normalized[1:] if normalized.startswith("+") else normalized
    if not PHONE_LIKE_RE.match(normalized):
        return None

    for prefix, timezone in PHONE_TIMEZONE_BY_PREFIX:
        if digits.startswith(prefix):
            return timezone
    return None


def _resolve_timezone_state(account_id, input_message, user_dao, current_user=None):
    timezone_service = TimezoneService()
    fallback_timezone = get_default_timezone().key

    existing_state = None
    should_persist = False
    get_timezone_state = getattr(user_dao, "get_timezone_state", None)
    if callable(get_timezone_state):
        existing_state = get_timezone_state(account_id)

    if not (isinstance(existing_state, Mapping) and existing_state.get("timezone")):
        if isinstance(current_user, Mapping) and current_user.get("timezone"):
            existing_state = {"timezone": current_user.get("timezone")}
            for key in (
                "timezone_source",
                "timezone_status",
                "pending_timezone_change",
                "pending_task_draft",
            ):
                if key in current_user and current_user.get(key) is not None:
                    existing_state[key] = current_user.get(key)
            should_persist = True

    if isinstance(existing_state, Mapping) and existing_state.get("timezone"):
        try:
            state = timezone_service.build_initial_state(
                existing_state=dict(existing_state),
                candidates=[],
                fallback_timezone=fallback_timezone,
            )
            if should_persist:
                update_timezone_state = getattr(user_dao, "update_timezone_state", None)
                if callable(update_timezone_state):
                    update_timezone_state(account_id, state)
            return state
        except ValueError:
            pass

    state = timezone_service.build_initial_state(
        existing_state=None,
        candidates=_extract_timezone_candidates(input_message),
        fallback_timezone=fallback_timezone,
    )

    update_timezone_state = getattr(user_dao, "update_timezone_state", None)
    if callable(update_timezone_state):
        update_timezone_state(account_id, state)

    return state


def _apply_timezone_state(user, timezone_state):
    if not isinstance(user, dict) or not isinstance(timezone_state, Mapping):
        return user

    resolved_user = dict(user)
    for key in TIMEZONE_STATE_FIELDS:
        if key in timezone_state:
            resolved_user[key] = timezone_state[key]
    return resolved_user


def _resolve_business_account_user(account_id, input_message, user_dao, customer, coke_account):
    get_user_by_account_id = getattr(user_dao, "get_user_by_account_id", None)
    if callable(get_user_by_account_id):
        user = get_user_by_account_id(account_id)
        if isinstance(user, dict):
            resolved_user = dict(user)
            resolved_user.setdefault("account_id", account_id)
            resolved_user["id"] = account_id
            resolved_user["_id"] = account_id
            timezone_state = _resolve_timezone_state(
                account_id,
                input_message,
                user_dao,
                current_user=resolved_user,
            )
            return _apply_timezone_state(resolved_user, timezone_state)

    fallback_user = {
        "id": account_id,
        "_id": account_id,
        "nickname": _resolve_clawscale_display_name(
            account_id,
            input_message,
            customer,
            coke_account,
        ),
        "is_coke_account": True,
    }
    timezone_state = _resolve_timezone_state(
        account_id,
        input_message,
        user_dao,
        current_user=fallback_user,
    )
    return _apply_timezone_state(fallback_user, timezone_state)


def resolve_agent_user_context(user_id, input_message, user_dao):
    user_id_str = "" if user_id is None else str(user_id).strip()
    if not user_id_str:
        return None

    account_id, customer, coke_account = _resolve_clawscale_account_id(
        user_id_str,
        input_message,
    )
    if account_id is not None:
        return _resolve_business_account_user(
            account_id,
            input_message,
            user_dao,
            customer,
            coke_account,
        )

    if is_mongo_object_id(user_id_str):
        user = user_dao.get_user_by_id(user_id_str)
        if not isinstance(user, dict):
            return user
        canonical_id = get_agent_entity_id(user) or user_id_str
        resolved_user = dict(user)
        resolved_user.setdefault("id", canonical_id)
        resolved_user.setdefault("_id", canonical_id)
        return resolved_user

    return None
