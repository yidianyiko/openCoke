from typing import Any


def resolve_default_character_id(
    user_dao,
    *,
    config: dict[str, Any] | None = None,
    alias: str | None = None,
) -> str:
    from conf.config import get_config

    active_config = config or get_config()
    character_alias = alias or active_config.get("default_character_alias", "coke")
    characters = user_dao.find_characters({"name": character_alias})
    if not characters:
        raise RuntimeError(f"character not found for alias: {character_alias}")
    return str(characters[0]["_id"])
