from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from coke.config import Settings
from coke.domains.calendar_import.google import GoogleCalendarClientPort
from coke.domains.reminder.models import ReminderBatchItem
from coke.turn.agent import AgentResult
from coke.turn.context import TurnMode, TurnTrigger
from coke.turn.semantic_interpreter import SemanticDecision

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class FakeRedis:
    """In-memory RedisLockPort for composition integration tests.

    Lock internals are covered by the RR2 lock suite against fakeredis; here we
    only need a conforming port so the Turn pipeline can take/release the lock.
    """

    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}

    def acquire_lock(self, name, token, ttl_ms):
        if name in self.tokens:
            return False
        self.tokens[name] = token
        return True

    def get_token(self, name):
        return self.tokens.get(name)

    def extend_if_owned(self, name, token, ttl_ms):
        return self.tokens.get(name) == token

    def release_if_owned(self, name, token):
        if self.tokens.get(name) == token:
            del self.tokens[name]
            return True
        return False


class FakeSemanticInterpreter:
    def __init__(self) -> None:
        self.next_decision = SemanticDecision(
            reply_necessity="reply_needed",
            intent_family="reminder_op",
            language_hint="en",
        )
        self.calls = 0

    def interpret(self, request):
        self.calls += 1
        return self.next_decision


class FakeMemory:
    def recent_context(self, conversation_id: str):
        return ()

    def long_term_context(self, account_id: str):
        return ()


class RecordingOutbound:
    def __init__(self) -> None:
        self.requests = []
        self.outcomes = []

    def deliver(self, request):
        self.requests.append(request)
        if self.outcomes:
            return self.outcomes.pop(0)
        return SimpleNamespace(status="delivered", error_code=None)


class FakeGoogleCalendarClient(GoogleCalendarClientPort):
    def list_events(self, auth_handle, visible_start, visible_end):
        return []

    def revoke_authorization(self, auth_handle: str) -> None:
        return None


class ScriptedAgent:
    def __init__(self) -> None:
        self.invocations = 0
        self.requests = []
        self.before_tool = None
        self.execute_reminder_tool = False
        self.output = {"type": "reply", "segments": ["created it"]}

    def invoke(self, request):
        self.invocations += 1
        self.requests.append(request)
        if self.before_tool is not None:
            self.before_tool()
        if self.execute_reminder_tool:
            request.tool_profile.reminder_tool.execute(
                {
                    "operation": "create",
                    "account_id": request.account_id,
                    "content": "pay rent",
                    "trigger_time": (NOW + timedelta(hours=1)).isoformat(),
                    "captured_timezone": "UTC",
                    "duration_minutes": 15,
                },
                request.freshness_guard,
            )
        return AgentResult.completed(self.output)

    def complete_async(self, task_id: str):
        return AgentResult.completed(self.output)


@pytest.fixture
def composed():
    from coke.composition import compose_coke_runtime

    semantic = FakeSemanticInterpreter()
    agent = ScriptedAgent()
    outbound = RecordingOutbound()
    runtime = compose_coke_runtime(
        semantic_interpreter=semantic,
        interaction_agent=agent,
        redis_client=FakeRedis(),
        outbound_delivery=outbound,
        memory_port=FakeMemory(),
        google_calendar_client=FakeGoogleCalendarClient(),
        now=lambda: NOW,
        id_factory=lambda prefix: f"{prefix}_{len(prefix)}_{runtime_counter.next()}",
        lock_token_factory=lambda: "lock-owner",
    )
    identity = runtime.identity_access_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="sender-1",
    )
    runtime.identity_access_service.observe_usable_channel(identity.account.id)
    return runtime, semantic, agent, outbound, identity


class runtime_counter:
    value = 0

    @classmethod
    def next(cls) -> int:
        cls.value += 1
        return cls.value


def _record_inbound(runtime, identity, event_id: str, text: str):
    return runtime.conversation_runtime_service.record_inbound(
        account_id=identity.account.id,
        channel_identity_id=identity.channel_identity.id,
        causal_inbound_event_id=event_id,
        text=text,
        payload={"text": text, "provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )


def _trigger(inbound, identity, event_id: str, text: str) -> TurnTrigger:
    return TurnTrigger(
        trigger_id=f"inbound:{event_id}",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=inbound.conversation.id,
        account_id=identity.account.id,
        channel_identity_id=identity.channel_identity.id,
        payload={"text": text},
    )


def test_inbound_reminder_create_runs_real_domains_and_records_replied(composed):
    runtime, _semantic, agent, outbound, identity = composed
    inbound = _record_inbound(runtime, identity, "provider-message-1", "remind me")
    agent.execute_reminder_tool = True

    result = runtime.turn_runner.run_inbound_turn(
        _trigger(inbound, identity, "provider-message-1", "remind me")
    )

    reminders = runtime.repositories.reminder.list_active_reminders(identity.account.id)
    assert result.disposition == "replied"
    assert result.reason_code == "reply_ready"
    assert [reminder.content for reminder in reminders] == ["pay rent"]
    assert outbound.requests[-1].visible_text == "created it"


def test_inbound_reminder_count_uses_tool_result_for_visible_reply(composed):
    runtime, semantic, _agent, outbound, identity = composed
    runtime.reminder_service.execute_batch(
        owner_account_id=identity.account.id,
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
                duration_minutes=15,
            ),
            ReminderBatchItem(
                operation="create",
                content="buy milk",
                captured_timezone="UTC",
                duration_minutes=15,
            ),
        ],
    )
    semantic.next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="reminder_op",
        intent_action="list_reminders",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )

    class ReminderCountAgent:
        def __init__(self) -> None:
            self.tool_result = None

        def invoke(self, request):
            self.tool_result = request.tool_profile.reminder_tool.execute(
                {
                    "operation": "list_reminders",
                    "account_id": request.account_id,
                    "captured_timezone": "Asia/Shanghai",
                },
                request.freshness_guard,
            )
            count = self.tool_result.facts["count"]
            lines = "\n".join(self.tool_result.facts["display_lines"])
            return AgentResult.completed(
                {
                    "type": "reply",
                    "segments": [f"你现在一共有 {count} 个提醒：\n{lines}"],
                }
            )

        def complete_async(self, task_id: str):
            raise AssertionError("reminder count should complete synchronously")

    agent = ReminderCountAgent()
    runtime.turn_runner.interaction_agent = agent
    inbound = _record_inbound(
        runtime,
        identity,
        "provider-message-count",
        "现在我一共有几个提醒？",
    )

    result = runtime.turn_runner.run_inbound_turn(
        _trigger(
            inbound,
            identity,
            "provider-message-count",
            "现在我一共有几个提醒？",
        )
    )

    assert result.disposition == "replied"
    assert agent.tool_result.ok is True
    assert agent.tool_result.facts["count"] == 2
    assert outbound.requests[-1].visible_text == (
        "你现在一共有 2 个提醒：\n"
        "1. pay rent (2026-05-30 21:00 Asia/Shanghai)\n"
        "2. buy milk (unscheduled)"
    )


def test_followup_reminder_edit_receives_recent_created_reminder_focus(composed):
    runtime, _semantic, agent, outbound, identity = composed
    create_inbound = _record_inbound(
        runtime, identity, "provider-message-focus-1", "remind me"
    )
    agent.execute_reminder_tool = True

    runtime.turn_runner.run_inbound_turn(
        _trigger(create_inbound, identity, "provider-message-focus-1", "remind me")
    )

    reminder = runtime.repositories.reminder.list_active_reminders(identity.account.id)[
        0
    ]

    class FocusUpdateAgent:
        def __init__(self) -> None:
            self.requests = []
            self.tool_result = None

        def invoke(self, request):
            self.requests.append(request)
            focus = request.context.focus_subject
            assert focus is not None
            assert focus.subject_type == "reminder"
            assert focus.object_ids == (reminder.id,)
            self.tool_result = request.tool_profile.reminder_tool.execute(
                {
                    "operation": "update_reminder",
                    "owner_account_id": request.account_id,
                    "reminder_id": focus.object_ids[0],
                    "duration_minutes": 60,
                },
                request.freshness_guard,
            )
            return AgentResult.completed(
                {"type": "reply", "segments": ["updated duration"]}
            )

        def complete_async(self, task_id: str):
            raise AssertionError("focus update should not be async")

    update_agent = FocusUpdateAgent()
    runtime.turn_runner.interaction_agent = update_agent
    update_inbound = _record_inbound(
        runtime, identity, "provider-message-focus-2", "change it to 60 minutes"
    )

    result = runtime.turn_runner.run_inbound_turn(
        _trigger(
            update_inbound,
            identity,
            "provider-message-focus-2",
            "change it to 60 minutes",
        )
    )

    assert result.disposition == "replied"
    assert update_agent.tool_result.ok is True
    assert (
        runtime.repositories.reminder.get_reminder(reminder.id).duration_minutes == 60
    )
    assert outbound.requests[-1].visible_text == "updated duration"


def test_semantic_intentional_no_reply_reaches_agent_and_creates_no_reminder(
    composed,
):
    runtime, semantic, agent, outbound, identity = composed
    inbound = _record_inbound(runtime, identity, "provider-message-2", "thanks")
    semantic.next_decision = SemanticDecision(
        reply_necessity="intentional_no_reply",
        intent_family="chit_chat",
        language_hint="en",
    )
    agent.output = {"type": "no_reply", "reason": "intentional_no_reply"}

    result = runtime.turn_runner.run_inbound_turn(
        _trigger(inbound, identity, "provider-message-2", "thanks")
    )

    assert result.disposition == "no_reply"
    assert result.reason_code == "intentional_no_reply"
    assert agent.invocations == 1
    assert outbound.requests == []
    assert (
        runtime.repositories.reminder.list_active_reminders(identity.account.id) == []
    )


def test_superseded_inbound_blocks_state_commit_and_records_superseded(composed):
    runtime, _semantic, agent, outbound, identity = composed
    inbound = _record_inbound(runtime, identity, "provider-message-3", "remind me")
    agent.execute_reminder_tool = True

    def supersede() -> None:
        _record_inbound(runtime, identity, "provider-message-4", "actually never mind")

    agent.before_tool = supersede

    result = runtime.turn_runner.run_inbound_turn(
        _trigger(inbound, identity, "provider-message-3", "remind me")
    )

    assert result.disposition == "superseded"
    assert result.reason_code == "newer_inbound_seq"
    assert (
        runtime.repositories.reminder.list_active_reminders(identity.account.id) == []
    )
    assert outbound.requests == []


def test_reminder_fire_render_turn_produces_prose_without_business_mutation(composed):
    runtime, _semantic, agent, outbound, identity = composed
    inbound = _record_inbound(runtime, identity, "provider-message-5", "seed")
    create = runtime.reminder_service.execute_batch(
        owner_account_id=identity.account.id,
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=NOW + timedelta(hours=2),
                captured_timezone="UTC",
            )
        ],
    )
    reminder_id = create.items[0].reminder_id
    fire = runtime.reminder_service.claim_due_fire(
        reminder_id=reminder_id,
        due_at=NOW + timedelta(hours=2),
    )
    reminder_count_before = len(
        runtime.repositories.reminder.list_active_reminders(identity.account.id)
    )
    agent.output = {"type": "reply", "segments": ["rent is due"]}

    result = runtime.turn_runner.run_render_turn(
        TurnTrigger(
            trigger_id=f"reminder_fire:{identity.account.id}:{fire.due_at.isoformat()}",
            trigger_type="ReminderFireTurn",
            mode=TurnMode.RENDER,
            conversation_id=inbound.conversation.id,
            account_id=identity.account.id,
            payload={"fire_ids": [fire.id]},
        )
    )

    assert result.disposition == "replied"
    assert result.visible_text == "rent is due"
    assert outbound.requests[-1].visible_text == "rent is due"
    assert agent.requests[-1].tool_profile.intent_tools_enabled is False
    assert agent.requests[-1].tool_profile.reminder_tool is None
    assert (
        len(runtime.repositories.reminder.list_active_reminders(identity.account.id))
        == reminder_count_before
    )


def test_reminder_fire_render_failure_marks_fire_undelivered(composed):
    runtime, _semantic, agent, outbound, identity = composed
    inbound = _record_inbound(runtime, identity, "provider-message-6", "seed")
    create = runtime.reminder_service.execute_batch(
        owner_account_id=identity.account.id,
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=NOW + timedelta(hours=2),
                captured_timezone="UTC",
            )
        ],
    )
    fire = runtime.reminder_service.claim_due_fire(
        reminder_id=create.items[0].reminder_id,
        due_at=NOW + timedelta(hours=2),
    )
    agent.output = {"type": "reply", "segments": ["rent is due"]}
    outbound.outcomes = [SimpleNamespace(status="failed", error_code="provider_failed")]

    result = runtime.turn_runner.run_render_turn(
        TurnTrigger(
            trigger_id=f"reminder_fire:{identity.account.id}:{fire.due_at.isoformat()}",
            trigger_type="ReminderFireTurn",
            mode=TurnMode.RENDER,
            conversation_id=inbound.conversation.id,
            account_id=identity.account.id,
            payload={"fire_ids": [fire.id]},
        )
    )

    assert result.disposition == "replied"
    assert (
        runtime.repositories.reminder.get_fire(fire.id).delivery_result == "undelivered"
    )


def test_notification_render_writes_per_recipient_delivery_state(composed):
    runtime, _semantic, agent, outbound, identity = composed
    inbound = _record_inbound(runtime, identity, "provider-message-7", "seed")
    friend_identity = (
        runtime.identity_access_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="sender-2",
        )
    )
    runtime.identity_access_service.observe_usable_channel(friend_identity.account.id)
    link = runtime.social_scheduling_service.get_or_create_friend_link(
        identity.account.id
    )
    runtime.social_scheduling_service.establish_friendship_from_token(
        friend_identity.account.id,
        link.public_token,
    )
    fact = runtime.repositories.social_scheduling.list_notification_facts()[0]
    agent.output = {"type": "reply", "segments": ["friendship created"]}
    outbound.outcomes = [
        SimpleNamespace(status="delivered", error_code=None),
        SimpleNamespace(status="failed", error_code="provider_failed"),
    ]

    result = runtime.turn_runner.run_render_turn(
        TurnTrigger(
            trigger_id=f"notification:{fact.id}",
            trigger_type="NotificationTurn",
            mode=TurnMode.RENDER,
            conversation_id=inbound.conversation.id,
            account_id=identity.account.id,
            payload={
                "notification_fact_id": fact.id,
                "recipient_account_ids": [
                    identity.account.id,
                    friend_identity.account.id,
                ],
                "facts": fact.facts,
            },
        )
    )

    recipients = {
        recipient.recipient_account_id: recipient
        for recipient in runtime.repositories.social_scheduling.list_notification_recipients(
            fact.id
        )
    }
    assert result.disposition == "replied"
    assert recipients[identity.account.id].delivery_state == "delivered"
    assert recipients[friend_identity.account.id].delivery_state == "failed"
    assert {request.account_id for request in outbound.requests[-2:]} == {
        identity.account.id,
        friend_identity.account.id,
    }


def test_notification_render_retries_no_reply_and_delivers_recipients(composed):
    runtime, _semantic, _agent, outbound, identity = composed
    inbound = _record_inbound(runtime, identity, "provider-message-8", "seed")
    friend_identity = (
        runtime.identity_access_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="sender-3",
        )
    )
    runtime.identity_access_service.observe_usable_channel(friend_identity.account.id)
    link = runtime.social_scheduling_service.get_or_create_friend_link(
        identity.account.id
    )
    runtime.social_scheduling_service.establish_friendship_from_token(
        friend_identity.account.id,
        link.public_token,
    )
    fact = runtime.repositories.social_scheduling.list_notification_facts()[0]

    class RetryNotificationAgent:
        def __init__(self) -> None:
            self.requests = []

        def invoke(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                return AgentResult.completed(
                    {"type": "no_reply", "reason": "intentional_no_reply"}
                )
            return AgentResult.completed(
                {"type": "reply", "segments": ["friendship created"]}
            )

        def complete_async(self, task_id: str):
            raise AssertionError("notification render should not be async")

    retry_agent = RetryNotificationAgent()
    runtime.turn_runner.interaction_agent = retry_agent

    result = runtime.turn_runner.run_render_turn(
        TurnTrigger(
            trigger_id=f"notification:{fact.id}",
            trigger_type="NotificationTurn",
            mode=TurnMode.RENDER,
            conversation_id=inbound.conversation.id,
            account_id=identity.account.id,
            payload={
                "notification_fact_id": fact.id,
                "recipient_account_ids": [
                    identity.account.id,
                    friend_identity.account.id,
                ],
                "facts": fact.facts,
            },
        )
    )

    recipients = {
        recipient.recipient_account_id: recipient
        for recipient in runtime.repositories.social_scheduling.list_notification_recipients(
            fact.id
        )
    }
    assert result.disposition == "replied"
    assert len(retry_agent.requests) == 2
    assert (
        retry_agent.requests[1].trusted_facts["protocol_retry"]["reason_code"]
        == "notification_requires_visible_reply"
    )
    assert recipients[identity.account.id].delivery_state == "delivered"
    assert recipients[friend_identity.account.id].delivery_state == "delivered"
    assert {request.account_id for request in outbound.requests[-2:]} == {
        identity.account.id,
        friend_identity.account.id,
    }


def test_notification_render_persistent_no_reply_fails_recipient_state(composed):
    runtime, _semantic, _agent, outbound, identity = composed
    inbound = _record_inbound(runtime, identity, "provider-message-9", "seed")
    friend_identity = (
        runtime.identity_access_service.resolve_or_create_channel_identity(
            provider_type="whatsapp_evolution",
            provider_subject="sender-4",
        )
    )
    runtime.identity_access_service.observe_usable_channel(friend_identity.account.id)
    link = runtime.social_scheduling_service.get_or_create_friend_link(
        identity.account.id
    )
    runtime.social_scheduling_service.establish_friendship_from_token(
        friend_identity.account.id,
        link.public_token,
    )
    fact = runtime.repositories.social_scheduling.list_notification_facts()[0]

    class NoReplyNotificationAgent:
        def __init__(self) -> None:
            self.requests = []

        def invoke(self, request):
            self.requests.append(request)
            return AgentResult.completed(
                {"type": "no_reply", "reason": "intentional_no_reply"}
            )

        def complete_async(self, task_id: str):
            raise AssertionError("notification render should not be async")

    no_reply_agent = NoReplyNotificationAgent()
    runtime.turn_runner.interaction_agent = no_reply_agent

    result = runtime.turn_runner.run_render_turn(
        TurnTrigger(
            trigger_id=f"notification:{fact.id}",
            trigger_type="NotificationTurn",
            mode=TurnMode.RENDER,
            conversation_id=inbound.conversation.id,
            account_id=identity.account.id,
            payload={
                "notification_fact_id": fact.id,
                "recipient_account_ids": [identity.account.id],
                "facts": fact.facts,
            },
        )
    )

    recipient = runtime.repositories.social_scheduling.get_notification_recipient(
        fact.id, identity.account.id
    )
    assert result.disposition == "failed"
    assert result.reason_code == "notification_requires_visible_reply"
    assert len(no_reply_agent.requests) == 2
    assert recipient.delivery_state == "failed"
    assert recipient.turn_id == result.turn_id
    assert recipient.error_facts == {
        "type": "notification_render_failed",
        "reason_code": "notification_requires_visible_reply",
    }
    assert outbound.requests == []


def test_create_app_accepts_composed_runtime(composed):
    from coke.app import create_app

    runtime, _semantic, _agent, _outbound, _identity = composed
    settings = Settings(
        database_url="postgresql+psycopg://coke:pass@localhost:5432/coke",
        redis_url="redis://localhost:6379/0",
        app_env="test",
    )

    app = create_app(settings, composed_runtime=runtime)

    assert app.config["COKE_RUNTIME"] is runtime
    assert app.test_client().get("/healthz").get_json() == {"ok": True}
