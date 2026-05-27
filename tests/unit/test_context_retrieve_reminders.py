from datetime import UTC, datetime, timedelta
import importlib

from agent.reminder.models import AgentOutputTarget, Reminder, ReminderSchedule


def _empty_request() -> dict:
    return {
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


def _reminder(
    *,
    title: str,
    next_fire_at: datetime | None,
    lifecycle_state: str = "active",
) -> Reminder:
    anchor_at = next_fire_at or datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
    return Reminder(
        id=f"rem-{title}",
        owner_user_id="user-1",
        title=title,
        schedule=ReminderSchedule(
            anchor_at=anchor_at,
            local_date=anchor_at.date(),
            local_time=anchor_at.time(),
            timezone="UTC",
            rrule=None,
        ),
        agent_output_target=AgentOutputTarget(
            conversation_id="conv-1",
            character_id="char-1",
            route_key=None,
        ),
        created_by_system="agent",
        origin="user",
        visibility="visible",
        fire_mode="notify",
        prompt=None,
        metadata={},
        lifecycle_state=lifecycle_state,
        next_fire_at=next_fire_at,
        last_fired_at=None,
        last_event_ack_at=None,
        last_error=None,
        created_at=anchor_at,
        updated_at=anchor_at,
        completed_at=None,
        cancelled_at=None,
        failed_at=None,
    )


def test_context_retrieve_uses_runtime_contract_for_confirmed_reminders(monkeypatch):
    module = importlib.import_module("agent.agno_agent.capabilities.context_retrieve")

    now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)

    class FakeReminderRuntime:
        def __init__(self) -> None:
            self.calls = []

        def list_visible_reminders(self, *, owner_user_id, query):
            self.calls.append((owner_user_id, query))
            return [
                _reminder(title="喝水", next_fire_at=now + timedelta(hours=1)),
                _reminder(title="过期提醒", next_fire_at=now - timedelta(hours=1)),
                _reminder(
                    title="已完成提醒",
                    lifecycle_state="completed",
                    next_fire_at=now + timedelta(hours=2),
                ),
            ]

    runtime = FakeReminderRuntime()
    monkeypatch.setattr(module, "MongoDBBase", lambda: object())
    monkeypatch.setattr(module, "_search_embeddings", lambda **kwargs: "")
    monkeypatch.setattr(module, "_search_chat_history", lambda **kwargs: "")
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

    result = module.ContextRetrieveDomainContract(reminder_runtime=runtime).retrieve(
        _empty_request()
    )

    assert result["confirmed_reminders"] == "喝水 · 一小时后"
    assert result["confirmed_reminders_status"] == "available"
    assert result["confirmed_reminders_error"] is None
    assert runtime.calls[0][0] == "user-1"
    assert runtime.calls[0][1].lifecycle_states == ["active"]


def test_context_retrieve_marks_reminders_unavailable_on_runtime_failure(monkeypatch):
    module = importlib.import_module("agent.agno_agent.capabilities.context_retrieve")

    class FailingReminderRuntime:
        def list_visible_reminders(self, *, owner_user_id, query):
            raise RuntimeError("reminder backend unavailable")

    monkeypatch.setattr(module, "MongoDBBase", lambda: object())
    monkeypatch.setattr(module, "_search_embeddings", lambda **kwargs: "")
    monkeypatch.setattr(module, "_search_chat_history", lambda **kwargs: "")

    result = module.ContextRetrieveDomainContract(
        reminder_runtime=FailingReminderRuntime()
    ).retrieve(_empty_request())

    assert result["confirmed_reminders"] == ""
    assert result["confirmed_reminders_status"] == "unavailable"
    assert result["confirmed_reminders_error"] == {
        "type": "RuntimeError",
        "message": "reminder backend unavailable",
    }
