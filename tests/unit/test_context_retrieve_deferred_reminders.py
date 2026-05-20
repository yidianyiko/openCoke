from datetime import UTC, datetime, timedelta
import importlib


def test_context_retrieve_uses_reminders_for_confirmed_reminders(monkeypatch):
    module = importlib.import_module("agent.agno_agent.capabilities.context_retrieve")
    reminder_dao_module = importlib.import_module("dao.reminder_dao")

    now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)

    class FakeReminderDAO:
        def list_for_owner(self, *, owner_user_id, lifecycle_states):
            assert owner_user_id == "user-1"
            assert lifecycle_states == ["active"]
            return [
                {
                    "title": "喝水",
                    "lifecycle_state": "active",
                    "next_fire_at": now + timedelta(hours=1),
                },
                {
                    "title": "过期提醒",
                    "lifecycle_state": "active",
                    "next_fire_at": now - timedelta(hours=1),
                },
                {
                    "title": "已完成提醒",
                    "lifecycle_state": "completed",
                    "next_fire_at": now + timedelta(hours=2),
                },
            ]

        def close(self):
            pass

    monkeypatch.setattr(module, "MongoDBBase", lambda: object())
    monkeypatch.setattr(module, "_search_embeddings", lambda **kwargs: "")
    monkeypatch.setattr(module, "_search_chat_history", lambda **kwargs: "")
    monkeypatch.setattr(reminder_dao_module, "ReminderDAO", lambda: FakeReminderDAO())
    monkeypatch.setattr(
        module,
        "format_time_friendly",
        lambda ts: "一小时后"
        if ts == int((now + timedelta(hours=1)).timestamp())
        else "",
    )
    monkeypatch.setattr(
        module,
        "datetime",
        type("FakeDateTime", (), {"now": staticmethod(lambda tz=None: now)}),
    )

    result = module.ContextRetrieveDomainContract().retrieve(
        {
            "character_setting_query": "",
            "character_setting_keywords": "",
            "user_profile_query": "",
            "user_profile_keywords": "",
            "character_knowledge_query": "",
            "character_knowledge_keywords": "",
            "chat_history_query": "",
            "chat_history_keywords": "",
            "character_id": "char-1",
            "user_id": "user-1",
        }
    )

    assert result["confirmed_reminders"] == "喝水 · 一小时后"
