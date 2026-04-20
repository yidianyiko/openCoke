import sys
import types

import pytest


@pytest.mark.asyncio
async def test_get_reminder_context_builds_synthetic_business_user_from_conversation(
    monkeypatch,
):
    stub_agent_handler = types.ModuleType("agent.runner.agent_handler")
    stub_agent_handler.handle_message = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "agent.runner.agent_handler", stub_agent_handler)

    from agent.runner import agent_background_handler as background_handler

    conversation = {
        "_id": "conv_1",
        "platform": "business",
        "talkers": [
            {
                "id": "clawscale:conv_1",
                "nickname": "Shared User",
                "db_user_id": "ck_123",
            },
            {
                "id": "clawscale-character:char_1",
                "nickname": "Coke",
                "db_user_id": "char_1",
            },
        ],
    }
    reminder = {
        "reminder_id": "r1",
        "user_id": "ck_123",
        "character_id": "char_1",
    }
    fake_character = {"_id": "char_1", "name": "Coke", "is_character": True}

    class FakeUserDAO:
        def get_user_by_id(self, user_id):
            if user_id == "char_1":
                return dict(fake_character)
            if user_id == "ck_123":
                return None
            raise AssertionError(f"unexpected get_user_by_id lookup: {user_id}")

    class FakeConversationDAO:
        def get_conversation_by_id(self, conversation_id):
            assert conversation_id == "conv_1"
            return conversation

    monkeypatch.setattr(background_handler, "user_dao", FakeUserDAO())
    monkeypatch.setattr(
        background_handler,
        "conversation_dao",
        FakeConversationDAO(),
    )

    resolved_conversation, user, character = await background_handler._get_reminder_context(
        "conv_1",
        reminder,
    )

    assert resolved_conversation == conversation
    assert user == {
        "id": "ck_123",
        "_id": "ck_123",
        "nickname": "Shared User",
        "is_coke_account": True,
    }
    assert character == fake_character
