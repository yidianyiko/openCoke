from agent.prompt.character import get_character_prompt, get_character_status
from agent.role.bootstrap import (
    build_default_character_payload,
    ensure_bootstrap_indexes,
    ensure_default_character_seeded,
)


class FakeUserDAO:
    def __init__(self):
        self.characters = {}
        self.next_id = 1

    def create_indexes(self):
        return None

    def upsert_user(self, query, user_data):
        key = query["name"]
        existing = self.characters.get(key)
        if existing is None:
            existing = {"_id": f"char_{self.next_id}"}
            self.next_id += 1
        existing.update(user_data)
        self.characters[key] = existing
        return existing["_id"]

    def find_characters(self, query=None, limit=0):
        query = query or {}
        name = query.get("name")
        if name is None or name not in self.characters:
            return []
        results = [self.characters[name]]
        if limit > 0:
            return results[:limit]
        return results


def test_build_default_character_payload_uses_prompt_registry():
    payload = build_default_character_payload("kap")

    assert payload["is_character"] is True
    assert payload["name"] == "kap"
    assert payload["nickname"] == "kap"
    assert payload["status"] == "normal"
    assert payload["user_info"]["description"] == get_character_prompt("kap")
    assert payload["user_info"]["status"] == get_character_status("kap")


def test_coke_system_prompt_includes_poke_inspired_texting_rules():
    prompt = get_character_prompt("kap")

    assert "warm but never sycophantic" in prompt
    assert "subtle wit" in prompt
    assert "match the user's message length" in prompt
    assert (
        "Never expose workflows, tools, model routing, logs, or internal agents"
        in prompt
    )
    assert "Only promise a future reminder" in prompt
    assert "must refuse" not in prompt
    assert "work-related tasks" not in prompt


def test_ensure_default_character_seeded_is_idempotent():
    user_dao = FakeUserDAO()

    first_id = ensure_default_character_seeded(user_dao=user_dao, character_alias="kap")
    second_id = ensure_default_character_seeded(user_dao=user_dao, character_alias="kap")

    assert first_id == second_id
    stored = user_dao.find_characters({"name": "kap"}, limit=1)[0]
    assert stored["_id"] == first_id
    assert stored["user_info"]["description"] == get_character_prompt("kap")
