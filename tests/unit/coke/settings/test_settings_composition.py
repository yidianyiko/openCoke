from __future__ import annotations

from datetime import UTC, datetime

from coke.composition import compose_coke_runtime
from coke.domains.identity_access.email import NullEmailSender, ResendEmailSender
from coke.turn.agent import AgentResult
from coke.turn.context import TurnMode, TurnTrigger

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


class FakeInteractionAgent:
    def invoke(self, request):
        return AgentResult.completed({"type": "reply", "segments": ["ok"]})

    def complete_async(self, task_id):
        return AgentResult.completed({"type": "reply", "segments": ["ok"]})


class FakeOutboundDelivery:
    def deliver(self, request):
        return None


def test_composition_exposes_settings_tool_and_pre_llm_trusted_settings_facts():
    runtime = compose_coke_runtime(
        interaction_agent=FakeInteractionAgent(),
        redis_client=object(),
        outbound_delivery=FakeOutboundDelivery(),
        now=lambda: NOW,
        id_factory=_id_factory(),
    )
    resolution = runtime.identity_access_service.resolve_or_create_channel_identity(
        "whatsapp_evolution",
        "sender",
    )
    account_id = resolution.account.id

    runtime.adapters.settings_tool.execute(
        {
            "operation": "update_settings",
            "account_id": account_id,
            "default_timezone": "Asia/Tokyo",
            "assistant_name": "Mina",
            "user_address_name": "Yuki",
            "speaking_style": "concise",
            "memory_enabled": False,
        },
        _Guard(),
    )

    decision = runtime.pre_llm_gate.evaluate(
        TurnTrigger(
            trigger_id="trigger_1",
            trigger_type="InboundTurn",
            mode=TurnMode.INTERACTIVE,
            conversation_id="conversation_1",
            account_id=account_id,
            payload={"text": "remind me tomorrow at 9"},
        )
    )

    assert runtime.tool_ports.settings_tool is runtime.adapters.settings_tool
    assert decision.permitted is True
    assert decision.trust_facts["default_timezone"] == "Asia/Tokyo"
    assert decision.trust_facts["assistant_name"] == "Mina"
    assert decision.trust_facts["user_address_name"] == "Yuki"
    assert decision.trust_facts["speaking_style"] == "concise"
    assert decision.trust_facts["memory_enabled"] is False


def test_composition_threads_public_base_url_to_social_scheduling():
    runtime = compose_coke_runtime(
        interaction_agent=FakeInteractionAgent(),
        redis_client=object(),
        outbound_delivery=FakeOutboundDelivery(),
        now=lambda: NOW,
        id_factory=_id_factory(),
        public_base_url="https://web.example.com/",
    )

    assert (
        runtime.social_scheduling_service._public_base_url == "https://web.example.com"
    )


def test_composition_exposes_active_turn_pipeline():
    runtime = compose_coke_runtime(
        interaction_agent=FakeInteractionAgent(),
        redis_client=object(),
        outbound_delivery=FakeOutboundDelivery(),
        now=lambda: NOW,
        id_factory=_id_factory(),
    )

    assert runtime.turn_pipeline is not None
    assert runtime.turn_runner.turn_pipeline is runtime.turn_pipeline
    assert runtime.turn_runner.render_express is runtime.turn_pipeline._express


def test_composition_uses_null_email_sender_without_resend_key():
    runtime = compose_coke_runtime(
        interaction_agent=FakeInteractionAgent(),
        redis_client=object(),
        outbound_delivery=FakeOutboundDelivery(),
        now=lambda: NOW,
        id_factory=_id_factory(),
    )

    assert isinstance(runtime.identity_access_service._email_sender, NullEmailSender)


def test_composition_builds_resend_email_sender_from_settings_values():
    runtime = compose_coke_runtime(
        interaction_agent=FakeInteractionAgent(),
        redis_client=object(),
        outbound_delivery=FakeOutboundDelivery(),
        now=lambda: NOW,
        id_factory=_id_factory(),
        public_base_url="https://web.example.com/",
        resend_api_key="resend-key",
        email_from="support@example.com",
        email_from_name="Coke Support",
    )

    sender = runtime.identity_access_service._email_sender
    assert isinstance(sender, ResendEmailSender)
    assert sender._api_key == "resend-key"
    assert sender._email_from == "support@example.com"
    assert sender._email_from_name == "Coke Support"
    assert sender._public_base_url == "https://web.example.com"


class _Guard:
    def guard_state_change(self) -> None:
        return None


def _id_factory():
    counters: dict[str, int] = {}

    def factory(prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}_{counters[prefix]}"

    return factory
