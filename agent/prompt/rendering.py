from copy import deepcopy
from typing import Any

from util.profile_util import resolve_profile_label


def build_prompt_context(context: dict[str, Any] | None) -> dict[str, Any]:
    normalized = deepcopy(context or {})

    user = normalized.setdefault("user", {})
    character = normalized.setdefault("character", {})
    conversation = normalized.setdefault("conversation", {})

    user_label = resolve_profile_label(user, "user")
    character_label = resolve_profile_label(character, "character")
    channel_label = conversation.get("platform") or "business"

    normalized["user_label"] = user_label
    normalized["character_label"] = character_label
    normalized["channel_label"] = channel_label

    user.setdefault("nickname", user_label)
    character.setdefault("nickname", character_label)
    conversation.setdefault("platform", channel_label)

    return normalized


def render_prompt_template(template: str, context: dict[str, Any] | None) -> str:
    return template.format(**build_prompt_context(context))
