import json
from pathlib import Path

from agent.prompt.character import get_character_prompt
from agent.prompt.character.coke_prompt import COKE_SYSTEM_PROMPT


def test_config_uses_coke_as_default_character_alias():
    config_path = Path("conf/config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["default_character_alias"] == "coke"


def test_config_has_coke_ecloud_wid_mapping():
    config_path = Path("conf/config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert "coke" in config["ecloud"]["wId"]


def test_character_prompt_registry_uses_coke_name():
    assert get_character_prompt("coke") == COKE_SYSTEM_PROMPT


def test_prepare_character_builds_coke_character():
    from agent.role.prepare_character import build_characters

    characters = build_characters()

    assert characters[0]["name"] == "coke"
    assert characters[0]["platforms"]["wechat"]["nickname"].strip() == "coke"


def test_agent_runner_uses_openclaw_runtime():
    source = Path("agent/runner/agent_runner.py").read_text(encoding="utf-8")

    assert "OpenClawClient" in source
    assert "run_http_server" in source


def test_start_script_defaults_to_coke_character():
    source = Path("start.sh").read_text(encoding="utf-8")

    assert 'CHARACTER="coke"' in source
    assert "默认: coke" in source


def test_character_resolver_uses_default_alias():
    from util.character_resolver import resolve_default_character_id

    class StubUserDAO:
        def find_characters(self, query):
            assert query == {"name": "coke"}
            return [{"_id": "char-123"}]

    config = {"default_character_alias": "coke"}

    assert resolve_default_character_id(StubUserDAO(), config=config) == "char-123"


def test_terminal_chat_uses_character_resolver():
    source = Path("connector/terminal/terminal_chat.py").read_text(encoding="utf-8")

    assert "resolve_default_character_id" in source
    assert 'CHARACTER_ID = resolve_default_character_id(' in source


def test_e2e_conftest_uses_character_resolver():
    source = Path("tests/e2e/conftest.py").read_text(encoding="utf-8")

    assert "resolve_default_character_id" in source


def test_e2e_conftest_uses_full_test_state_cleanup():
    source = Path("tests/e2e/conftest.py").read_text(encoding="utf-8")

    assert "clear_test_state" in source


def test_agent_runner_has_main_guard():
    source = Path("agent/runner/agent_runner.py").read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":' in source


def test_agent_runner_reads_disable_background_agents_env():
    source = Path("agent/runner/agent_runner.py").read_text(encoding="utf-8")

    assert 'DISABLE_BACKGROUND_AGENTS' in source


def test_terminal_test_client_can_clear_full_test_state():
    from connector.terminal.terminal_test_client import TerminalTestClient

    class StubMongo:
        def __init__(self):
            self.update_calls = []
            self.delete_calls = []
            self.insert_calls = []

        def update_many(self, collection_name, query, update):
            self.update_calls.append((collection_name, query, update))
            return 1

        def delete_many(self, collection_name, query):
            self.delete_calls.append((collection_name, query))
            return 1

        def insert_one(self, collection_name, document):
            self.insert_calls.append((collection_name, document))
            return "rel-1"

    class StubUserDAO:
        def get_user_by_id(self, user_id):
            if user_id == "user-123":
                return {"_id": "user-123", "name": "Test User"}
            if user_id == "char-456":
                return {"_id": "char-456", "name": "coke"}
            return None

        def close(self):
            return None

    client = object.__new__(TerminalTestClient)
    client.user_id = "user-123"
    client.character_id = "char-456"
    client.platform = "wechat"
    client.mongo = StubMongo()
    client.user_dao = StubUserDAO()

    client.clear_test_state()

    assert ("reminders", {"user_id": "user-123"}) in client.mongo.delete_calls
    assert (
        "embeddings",
        {"metadata.uid": "user-123"},
    ) in client.mongo.delete_calls
    assert any(
        collection == "conversations"
        and "conversation_info.chat_history.from_user" in query["$or"][0]
        for collection, query in client.mongo.delete_calls
    )
    assert any(collection == "relations" for collection, _ in client.mongo.insert_calls)


def test_e2e_case_files_do_not_hardcode_character_id():
    e2e_case_files = [
        Path("tests/e2e/llm_chat_cases.json"),
        Path("tests/e2e/llm_reminder_cases.json"),
        Path("tests/e2e/reminder_e2e_cases.json"),
    ]

    for path in e2e_case_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "character_id" not in data, f"{path} still hardcodes character_id"
