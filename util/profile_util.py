from collections.abc import Mapping


def resolve_profile_label(entity: Mapping | None, fallback: str) -> str:
    if not isinstance(entity, Mapping):
        return fallback

    for key in ("display_name", "nickname", "name", "email"):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return fallback
