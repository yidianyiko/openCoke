from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict

from dao.agent_instance_dao import BASE_AGENT_TYPE, OVERRIDE_FIELDS, AgentInstanceDAO

CHARACTER_NAME_BY_BASE_AGENT_TYPE = {BASE_AGENT_TYPE: "qiaoyun"}
TEXT_LIMITS = {
    "display_name": (1, 20),
    "nickname": (1, 20),
    "user_address_name": (1, 10),
    "persona": (0, 2000),
    "background": (0, 4000),
    "speaking_style": (0, 1000),
    "extra_rules": (0, 1000),
}


class AgentInstanceService:
    def __init__(self, *, dao=None, character_provider=None) -> None:
        self.dao = dao or AgentInstanceDAO()
        self.character_provider = character_provider or _default_character_provider
        self.dao.create_indexes()

    def get_agent_instance(self, *, customer_id: str) -> Dict[str, Any]:
        owner = _require_customer_id(customer_id)
        character = self._base_character()
        instance = self.dao.get_active_agent_instance(
            owner,
            base_agent_type=BASE_AGENT_TYPE,
        )
        return self._response(owner, character, instance)

    def update_agent_instance(
        self, *, customer_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        owner = _require_customer_id(customer_id)
        character = self._base_character()
        overrides = _validate_update_body(body)
        instance = self.dao.upsert_active_agent_instance(
            owner,
            overrides,
            base_character_id=str(character["_id"]),
            base_agent_type=BASE_AGENT_TYPE,
        )
        if isinstance(instance, dict):
            instance = {**instance, **overrides}
        return self._response(owner, character, instance)

    def reset_agent_instance(self, *, customer_id: str) -> Dict[str, Any]:
        owner = _require_customer_id(customer_id)
        character = self._base_character()
        instance = self.dao.reset_active_agent_instance(
            owner,
            base_character_id=str(character["_id"]),
            base_agent_type=BASE_AGENT_TYPE,
        )
        return self._response(owner, character, instance)

    def _base_character(self) -> Dict[str, Any]:
        character = self.character_provider(
            CHARACTER_NAME_BY_BASE_AGENT_TYPE[BASE_AGENT_TYPE]
        )
        if not isinstance(character, dict) or not character.get("_id"):
            raise ValueError("base_character_not_found")
        return character

    def _response(
        self,
        owner: str,
        character: Dict[str, Any],
        instance: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        serialized = _serialize_instance(owner, character, instance)
        return {
            "agent_instance": serialized,
            "effective_profile": _effective_profile(character, serialized),
        }


def _default_character_provider(character_name: str) -> Dict[str, Any] | None:
    from dao.user_dao import UserDAO

    dao = UserDAO()
    try:
        characters = dao.find_characters({"name": character_name}, limit=1)
        return characters[0] if characters else None
    finally:
        dao.close()


def _require_customer_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid_customer_id")
    customer_id = value.strip()
    if not (customer_id.startswith("ck_") or customer_id.startswith("acct_")):
        raise ValueError("invalid_customer_id")
    return customer_id


def _validate_update_body(body: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(body, dict):
        raise ValueError("invalid_body")
    unknown = set(body) - set(OVERRIDE_FIELDS)
    if unknown:
        raise ValueError("invalid_body")

    normalized = {}
    for field in (
        "display_name",
        "nickname",
        "user_address_name",
        "persona",
        "background",
        "speaking_style",
        "extra_rules",
    ):
        if field in body:
            normalized[field] = _optional_text(body[field], field)
    if "status" in body:
        normalized["status"] = _status(body["status"])
    if "proactive" in body:
        normalized["proactive"] = _boolean_object(body["proactive"])
    if "memory" in body:
        normalized["memory"] = _boolean_object(body["memory"])
    return normalized


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_body")
    text = value.strip()
    minimum, maximum = TEXT_LIMITS[field]
    if len(text) < minimum or len(text) > maximum:
        raise ValueError("invalid_body")
    return text


def _status(value: Any) -> Dict[str, str | None]:
    if value is None:
        return {"place": None, "action": None}
    if not isinstance(value, dict):
        raise ValueError("invalid_body")
    return {
        "place": _bounded_nested_text(value.get("place"), 20),
        "action": _bounded_nested_text(value.get("action"), 20),
    }


def _bounded_nested_text(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_body")
    text = value.strip()
    if len(text) > maximum:
        raise ValueError("invalid_body")
    return text or None


def _boolean_object(value: Any) -> Dict[str, bool | None]:
    if value is None:
        return {"enabled": None}
    if not isinstance(value, dict) or set(value) - {"enabled"}:
        raise ValueError("invalid_body")
    enabled = value.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise ValueError("invalid_body")
    return {"enabled": enabled}


def _serialize_instance(
    owner: str,
    character: Dict[str, Any],
    instance: Dict[str, Any] | None,
) -> Dict[str, Any]:
    base = {
        "agent_instance_id": None,
        "owner_user_id": owner,
        "base_agent_type": BASE_AGENT_TYPE,
        "base_character_id": str(character["_id"]),
        "active": True,
        "display_name": None,
        "nickname": None,
        "user_address_name": None,
        "persona": None,
        "background": None,
        "speaking_style": None,
        "extra_rules": None,
        "status": {"place": None, "action": None},
        "proactive": {"enabled": None},
        "memory": {"enabled": None},
        "created_at": None,
        "updated_at": None,
    }
    if instance:
        for key in base:
            if key in instance:
                base[key] = _json_value(instance[key])
    return base


def _effective_profile(
    character: Dict[str, Any], instance: Dict[str, Any]
) -> Dict[str, Any]:
    user_info = (
        character.get("user_info")
        if isinstance(character.get("user_info"), dict)
        else {}
    )
    base_status = (
        user_info.get("status") if isinstance(user_info.get("status"), dict) else {}
    )
    display_name = (
        instance.get("display_name")
        or character.get("nickname")
        or character.get("name")
        or "Coke"
    )
    nickname = instance.get("nickname") or display_name
    status = instance.get("status") if isinstance(instance.get("status"), dict) else {}
    proactive = (
        instance.get("proactive") if isinstance(instance.get("proactive"), dict) else {}
    )
    memory = instance.get("memory") if isinstance(instance.get("memory"), dict) else {}
    return {
        "display_name": display_name,
        "nickname": nickname,
        "user_address_name": instance.get("user_address_name"),
        "persona": instance.get("persona"),
        "background": instance.get("background"),
        "speaking_style": instance.get("speaking_style"),
        "extra_rules": instance.get("extra_rules"),
        "status": {
            "place": status.get("place") or base_status.get("place") or "未知",
            "action": status.get("action") or base_status.get("action") or "未知",
        },
        "proactive": {
            "enabled": (
                proactive.get("enabled")
                if proactive.get("enabled") is not None
                else True
            )
        },
        "memory": {
            "enabled": (
                memory.get("enabled") if memory.get("enabled") is not None else True
            )
        },
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value
