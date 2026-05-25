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


def test_coke_system_prompt_defines_health_companion_role():
    prompt = get_character_prompt("kap")

    assert "你是用户在微信中的健康搭子" in prompt
    assert "我是 Coke，你的健康搭子" in prompt
    # Coke does NOT directly book offline coaching / classes — explicit
    # disclaimer required so the model does not hallucinate appointments.
    assert "没有" in prompt and "预约" in prompt
    assert "绝不能说你已经约好" in prompt or "绝不说" in prompt
    assert "运动康复" in prompt
    assert "减肥" in prompt
    assert "健身" in prompt
    assert "任务开始前10分钟" in prompt
    assert "只有当提醒工具确认成功后" in prompt
    assert "必须拒绝" in prompt
    assert "coding" in prompt


def test_ensure_default_character_seeded_is_idempotent():
    user_dao = FakeUserDAO()

    first_id = ensure_default_character_seeded(user_dao=user_dao, character_alias="kap")
    second_id = ensure_default_character_seeded(user_dao=user_dao, character_alias="kap")

    assert first_id == second_id
    stored = user_dao.find_characters({"name": "kap"}, limit=1)[0]
    assert stored["_id"] == first_id
    assert stored["user_info"]["description"] == get_character_prompt("kap")
