from agent.prompt.character import get_character_prompt, get_character_status
from conf.config import CONF
from dao.user_dao import UserDAO


def build_default_character_payload(character_alias: str) -> dict:
    system_prompt = get_character_prompt(character_alias)
    if not system_prompt:
        raise ValueError(f"unregistered_default_character_alias:{character_alias}")

    status = get_character_status(character_alias) or {
        "place": "workstation",
        "action": "supervising",
    }
    return {
        "is_character": True,
        "name": character_alias,
        "nickname": character_alias,
        "status": "normal",
        "user_info": {
            "description": system_prompt,
            "status": status,
        },
    }


def ensure_default_character_seeded(
    *, user_dao: UserDAO | None = None, character_alias: str | None = None
) -> str:
    alias = character_alias or CONF.get("default_character_alias", "coke")
    dao = user_dao or UserDAO()
    dao.create_indexes()
    return dao.upsert_user(
        {"name": alias, "is_character": True},
        build_default_character_payload(alias),
    )


def main() -> int:
    character_id = ensure_default_character_seeded()
    print(f"seeded_default_character:{character_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
