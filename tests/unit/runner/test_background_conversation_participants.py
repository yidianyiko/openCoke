import sys
import types


def test_resolve_conversation_participants_prefers_db_user_ids(monkeypatch):
    stub_agent_handler = types.ModuleType("agent.runner.agent_handler")
    stub_agent_handler.handle_message = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "agent.runner.agent_handler", stub_agent_handler)

    from agent.runner import agent_background_handler as background_handler

    fake_user = {"_id": "user_1", "name": "Alice"}
    fake_character = {"_id": "char_1", "name": "Coke", "is_character": True}
    lookups = []

    class FakeUserDAO:
        def get_user_by_id(self, user_id):
            lookups.append(("get_user_by_id", user_id))
            if user_id == "user_1":
                return fake_user
            if user_id == "char_1":
                return fake_character
            return None

        def find_users(self, *args, **kwargs):
            raise AssertionError("find_users should not be used for talkers with db_user_id")

    monkeypatch.setattr(background_handler, "user_dao", FakeUserDAO())

    user, character = background_handler._resolve_conversation_participants(
        {
            "platform": "business",
            "talkers": [
                {"id": "clawscale:conv_1", "nickname": "Alice", "db_user_id": "user_1"},
                {
                    "id": "clawscale-character:char_1",
                    "nickname": "Coke",
                    "db_user_id": "char_1",
                },
            ],
        }
    )

    assert user == fake_user
    assert character == fake_character
    assert lookups == [("get_user_by_id", "user_1"), ("get_user_by_id", "char_1")]
