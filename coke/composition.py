from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.config import ConfigurationError, Settings
from coke.domains.calendar_import.google import (
    GoogleCalendarClientAdapter,
    GoogleCalendarClientPort,
)
from coke.domains.calendar_import.models import CalendarSourceEvent
from coke.domains.calendar_import.service import (
    CalendarImportService,
    InMemoryCalendarImportRepository,
    PostgresCalendarImportRepository,
)
from coke.domains.channel_reachability.models import ChannelReachabilityError
from coke.domains.channel_reachability.repository import (
    InMemoryChannelReachabilityRepository,
    PostgresChannelReachabilityRepository,
)
from coke.domains.channel_reachability.service import ChannelReachabilityService
from coke.domains.conversation_runtime.models import ConversationRuntimeError
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
    PostgresConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.domains.identity_access.email import NullEmailSender, ResendEmailSender
from coke.domains.identity_access.models import IdentityAccessError
from coke.domains.identity_access.repository import (
    InMemoryIdentityAccessRepository,
    PostgresIdentityAccessRepository,
)
from coke.domains.identity_access.service import IdentityAccessService
from coke.domains.reminder.models import DetectedReminderFields, ReminderBatchItem
from coke.domains.reminder.repository import (
    InMemoryReminderRepository,
    PostgresReminderRepository,
)
from coke.domains.reminder.service import ReminderService
from coke.domains.settings.models import SettingsError, SettingsView
from coke.domains.settings.repository import (
    InMemorySettingsRepository,
    PostgresSettingsRepository,
)
from coke.domains.settings.service import SettingsService
from coke.domains.social_scheduling.availability import BusyInterval
from coke.domains.social_scheduling.models import SocialSchedulingError
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
    PostgresSocialSchedulingRepository,
)
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.infra.postgres import create_engine, create_session_factory
from coke.infra.redis import (
    RedisLockAdapter,
    RedisReplyPubSub,
    RedisWorkStream,
    create_redis_client,
)
from coke.infra.tracing import ensure_traceparent
from coke.llm.agno_interaction_agent import AgnoInteractionAgent
from coke.llm.config import (
    TEXT_PROVIDER_DEEPSEEK,
    SiliconFlowMediaConfig,
    ZAILLMConfig,
)
from coke.llm.media_text import (
    MediaTextResolver,
    SiliconFlowAsrClient,
    SiliconFlowVisionTextClient,
)
from coke.llm.reminder_detector import SiliconFlowReminderDetector
from coke.providers.base import provider_registry
from coke.providers.linq import LinqAdapter
from coke.providers.wechat_ecloud import WeChatECloudAdapter
from coke.providers.wechat_personal import WeChatPersonalAdapter
from coke.providers.whatsapp_evolution import WhatsAppEvolutionAdapter
from coke.turn.agent import (
    AgentRequest,
    AgentResult,
    AgentToolPorts,
    DomainExecutionResult,
    ToolExecutionResult,
)
from coke.turn.focus import FocusResolver, MessageSubject
from coke.turn.inbound.close import CloseCoordinator
from coke.turn.inbound.contracts import TurnPlan
from coke.turn.inbound.express import ExpressAgent
from coke.turn.inbound.handlers.calendar import CalendarImportActionHandler
from coke.turn.inbound.handlers.friend import FriendshipActionHandler
from coke.turn.inbound.handlers.reminder import ReminderActionHandler
from coke.turn.inbound.handlers.settings import SettingsActionHandler
from coke.turn.inbound.handlers.social import SocialSchedulingActionHandler
from coke.turn.inbound.pending import (
    InMemoryPendingClarificationStore,
    PostgresPendingClarificationRepository,
)
from coke.turn.inbound.pipeline import TurnPipeline
from coke.turn.inbound.plan import SiliconFlowPlanner
from coke.turn.locks import ConversationLockManager, RedisLockPort
from coke.turn.memory import MemoryPort
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import DeliveryRequest, OutboundDeliveryPort, TurnRunner


@dataclass(frozen=True, slots=True)
class CokeRepositories:
    identity_access: Any
    channel_reachability: Any
    conversation_runtime: Any
    reminder: Any
    social_scheduling: Any
    calendar_import: Any
    settings: Any | None = None
    pending_clarification: Any | None = None


@dataclass(frozen=True, slots=True)
class CokeToolAdapters:
    reminder_tool: "ReminderToolAdapter"
    social_scheduling_tool: "SocialSchedulingToolAdapter"
    calendar_import_tool: "CalendarImportToolAdapter"
    identity_access_tool: "IdentityAccessToolAdapter"
    settings_tool: "SettingsToolAdapter"


@dataclass(frozen=True, slots=True)
class CokeRuntime:
    repositories: CokeRepositories
    identity_access_service: IdentityAccessService
    channel_reachability_service: ChannelReachabilityService
    conversation_runtime_service: ConversationRuntimeService
    reminder_service: ReminderService
    social_scheduling_service: SocialSchedulingService
    calendar_import_service: CalendarImportService
    settings_service: SettingsService
    adapters: CokeToolAdapters
    tool_ports: AgentToolPorts
    pre_llm_gate: PreLLMGateService
    lock_manager: ConversationLockManager
    turn_runner: TurnRunner
    turn_pipeline: TurnPipeline | None = None
    provider_adapters: Mapping[str, Any] | None = None
    engine: Any | None = None
    session_factory: Any | None = None
    session: Any | None = None
    redis_client: Any | None = None
    work_stream: Any | None = None
    reply_pubsub: Any | None = None
    media_text_resolver: MediaTextResolver | None = None
    interactive_runtime_factory: Callable[[], "CokeRuntime"] | None = None


class EmptyGoogleCalendarClient(GoogleCalendarClientPort):
    def list_events(
        self,
        auth_handle: str,
        visible_start: datetime,
        visible_end: datetime,
    ) -> list[CalendarSourceEvent]:
        return []

    def revoke_authorization(self, auth_handle: str) -> None:
        return None


class FakeInteractionAgent:
    def invoke(self, request: AgentRequest) -> AgentResult:
        return AgentResult.completed(
            {
                "type": "reply",
                "segments": ["COKE_LLM_FAKE synthetic reply"],
            }
        )

    async def ainvoke(self, request: AgentRequest) -> AgentResult:
        return self.invoke(request)

    async def cancel(self, run_id: str) -> bool:
        return True

    def complete_async(self, task_id: str) -> AgentResult:
        return AgentResult.completed(
            {
                "type": "reply",
                "segments": ["COKE_LLM_FAKE synthetic async reply"],
            }
        )


class FakeTurnPlanner:
    def plan(self, request) -> TurnPlan:
        return TurnPlan(actions=(), reply_necessity="reply_needed")


class FakeTurnExpress:
    def render(self, request) -> tuple[str, ...]:
        return ("COKE_LLM_FAKE synthetic turn pipeline reply",)

    async def render_streaming(self, request):
        yield "COKE_LLM_FAKE synthetic turn pipeline reply"


class FakeReminderDetector:
    def extract(self, text: str, captured_timezone: str, now: datetime):
        return DetectedReminderFields(
            content=text or None,
            trigger_time=None,
            recurrence_rule={},
            duration_minutes=None,
            kind=None,
        )


class ChannelReachabilityOutboundDelivery:
    def __init__(
        self,
        channel_reachability: ChannelReachabilityService,
        *,
        conversation_runtime: Any | None = None,
    ) -> None:
        self.channel_reachability = channel_reachability
        self.conversation_runtime = conversation_runtime

    def deliver(self, request: DeliveryRequest):
        try:
            context_token = request.context_token
            context_token_source = request.context_token_source
            context_token_age_seconds = request.context_token_age_seconds
            traceparent = request.traceparent
            if context_token is None and self.conversation_runtime is not None:
                observation_reader = getattr(
                    self.conversation_runtime,
                    "latest_context_token_observation",
                    None,
                )
                if callable(observation_reader):
                    observation = observation_reader(request.conversation_id)
                    context_token = observation.token
                    context_token_source = context_token_source or observation.source
                    context_token_age_seconds = (
                        context_token_age_seconds or observation.age_seconds
                    )
                    traceparent = traceparent or observation.traceparent
                else:
                    context_token = self.conversation_runtime.latest_context_token(
                        request.conversation_id
                    )
            return self.channel_reachability.send_text(
                account_id=request.account_id,
                text=request.visible_text,
                idempotency_key=request.idempotency_key,
                turn_id=request.turn_id,
                message_id=request.message_id,
                context_token=context_token,
                delivery_source=request.delivery_source,
                delivery_intent=request.delivery_intent,
                retry_attempt=request.retry_attempt,
                traceparent=traceparent,
                container=request.container,
                context_token_source=context_token_source,
                context_token_age_seconds=context_token_age_seconds,
            )
        except ChannelReachabilityError:
            raise


class OutputLifecycleDeliveryCallbacks:
    def __init__(
        self,
        *,
        reminder_service: ReminderService,
        social_scheduling_service: SocialSchedulingService,
        conversation_runtime_service: ConversationRuntimeService | None = None,
        identity_access_service: IdentityAccessService | None = None,
    ) -> None:
        self.reminder_service = reminder_service
        self.social_scheduling_service = social_scheduling_service
        self.conversation_runtime_service = conversation_runtime_service
        self.identity_access_service = identity_access_service

    def record_delivery(self, *, trigger, request, outcome) -> None:
        delivered = outcome.status in {"sent", "delivered"}
        undelivered = _is_context_token_window_failure(outcome)
        if trigger.trigger_type == "ReminderFireTurn":
            fire_ids = _string_list(trigger.payload.get("fire_ids"))
            if fire_ids:
                self.reminder_service.record_fire_delivery(
                    fire_ids,
                    delivered=delivered,
                )
            return
        if trigger.trigger_type == "ProactiveFireTurn":
            fire_id = trigger.payload.get("fire_id")
            if isinstance(fire_id, str) and fire_id:
                self.reminder_service.record_proactive_delivery(
                    fire_id,
                    delivered=delivered,
                )
            return
        if trigger.trigger_type == "UndeliveredResendTurn":
            fire_ids = _string_list(trigger.payload.get("fire_ids"))
            if fire_ids:
                self.reminder_service.record_fire_delivery(
                    fire_ids,
                    delivered=delivered,
                )
            notification_fact_ids = _string_list(
                trigger.payload.get("notification_fact_ids")
            )
            for fact_id in notification_fact_ids:
                self.social_scheduling_service.record_notification_delivery(
                    notification_fact_id=fact_id,
                    recipient_account_id=request.account_id,
                    delivery_state=(
                        "delivered"
                        if delivered
                        else "undelivered" if undelivered else "failed"
                    ),
                    error_facts=(
                        {} if delivered else {"type": "recipient_channel_unavailable"}
                    ),
                    turn_id=request.turn_id,
                )
            return
        if trigger.trigger_type == "NotificationTurn":
            fact_id = trigger.payload.get("notification_fact_id")
            if not isinstance(fact_id, str) or not fact_id:
                return
            self.social_scheduling_service.record_notification_delivery(
                notification_fact_id=fact_id,
                recipient_account_id=request.account_id,
                delivery_state=(
                    "delivered"
                    if delivered
                    else "undelivered" if undelivered else "failed"
                ),
                error_facts=(
                    {} if delivered else {"type": "recipient_channel_unavailable"}
                ),
                turn_id=request.turn_id,
            )

    def record_render_failure(self, *, trigger, turn_id: str, reason_code: str) -> None:
        if trigger.trigger_type != "NotificationTurn":
            return
        fact_id = trigger.payload.get("notification_fact_id")
        if not isinstance(fact_id, str) or not fact_id:
            return
        recipient_ids = _string_list(trigger.payload.get("recipient_account_ids"))
        if not recipient_ids:
            recipient_ids = [trigger.account_id]
        for recipient_id in recipient_ids:
            self.social_scheduling_service.record_notification_delivery(
                notification_fact_id=fact_id,
                recipient_account_id=recipient_id,
                delivery_state="failed",
                error_facts={
                    "type": "notification_render_failed",
                    "reason_code": reason_code,
                },
                turn_id=turn_id,
            )

    def record_inbound_reply_completed(
        self,
        *,
        trigger,
        delivered: bool,
        onboarding_guidance_delivered: bool = False,
    ) -> None:
        if (
            delivered
            and onboarding_guidance_delivered
            and self.identity_access_service is not None
            and trigger.trigger_type == "InboundTurn"
        ):
            account_id = getattr(trigger, "account_id", None)
            if isinstance(account_id, str) and account_id:
                self.identity_access_service.mark_first_guidance_sent(account_id)
        if not delivered or self.conversation_runtime_service is None:
            return
        if trigger.trigger_type != "InboundTurn":
            return
        account_id = getattr(trigger, "account_id", None)
        conversation_id = getattr(trigger, "conversation_id", None)
        if not isinstance(account_id, str) or not account_id:
            return
        if not isinstance(conversation_id, str) or not conversation_id:
            return
        raw_event_id = str(trigger.payload.get("causal_inbound_event_id") or "")
        if not raw_event_id:
            return
        fire_ids = _string_list(
            self.reminder_service.undelivered_resend_turn(account_id).fire_ids
        )
        notification_fact_ids = _string_list(
            self.social_scheduling_service.undelivered_notification_resend_turn(
                account_id
            ).notification_fact_ids
        )
        if not fire_ids and not notification_fact_ids:
            return
        trigger_id = f"undelivered_resend:{account_id}:{raw_event_id}"
        payload = {
            "trigger_id": trigger_id,
            "trigger_type": "UndeliveredResendTurn",
            "account_id": account_id,
            "conversation_id": conversation_id,
            "causal_inbound_event_id": raw_event_id,
            "framing": "previously_undelivered",
        }
        if fire_ids:
            payload["fire_ids"] = fire_ids
        if notification_fact_ids:
            payload["notification_fact_ids"] = notification_fact_ids
        try:
            self.conversation_runtime_service.enqueue_render_turn(
                topic="turn.undelivered_resend",
                idempotency_key=trigger_id,
                payload=payload,
                traceparent=_traceparent_from_trigger(trigger),
            )
        except ConversationRuntimeError as error:
            if error.code != "duplicate_outbox_idempotency_key":
                raise


class IdentityReachabilityAdapter:
    def __init__(self, identity_access: IdentityAccessService) -> None:
        self.identity_access = identity_access

    def has_usable_channel(self, account_id: str) -> bool:
        return self.identity_access.repository.has_usable_channel(account_id)


class DeferredFriendLinkCompletionAdapter:
    def __init__(
        self,
        *,
        identity_access: IdentityAccessService,
        social_scheduling: SocialSchedulingService,
    ) -> None:
        self.identity_access = identity_access
        self.social_scheduling = social_scheduling

    def complete_pending_for_account(self, account_id: str) -> None:
        for (
            friend_link_id
        ) in self.identity_access.consume_deferred_friend_link_continuations(
            account_id
        ):
            self.social_scheduling.complete_deferred_friend_link(
                joiner_account_id=account_id,
                friend_link_id=friend_link_id,
            )


class ReminderAvailabilityAdapter:
    def __init__(self, reminder_repository: Any) -> None:
        self.reminder_repository = reminder_repository

    def personal_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
        requester_timezone: str,
    ) -> list[BusyInterval]:
        intervals: list[BusyInterval] = []
        for reminder in self.reminder_repository.list_active_reminders(account_id):
            if reminder.next_fire_at is None or reminder.kind == "proactive":
                continue
            interval_start = _local_wall_clock(
                reminder.next_fire_at, requester_timezone
            )
            interval_end = interval_start + _duration_delta(reminder.duration_minutes)
            if interval_start < end and interval_end > start:
                intervals.append(
                    BusyInterval(
                        account_id=account_id,
                        start=interval_start,
                        end=interval_end,
                        source="personal",
                        detail_id=reminder.id,
                    )
                )
        return intervals


class ReminderLifecycleFocusRepository:
    def __init__(
        self, conversation_runtime_repository: Any, reminder_repository: Any
    ) -> None:
        self.conversation_runtime_repository = conversation_runtime_repository
        self.reminder_repository = reminder_repository

    def last_rendered_subject(self, conversation_id: str) -> MessageSubject | None:
        turn_ids = self.conversation_runtime_repository.latest_turn_ids(
            conversation_id,
            limit=20,
        )
        for event in self.reminder_repository.list_lifecycle_events_for_turn_ids(
            turn_ids,
            limit=20,
        ):
            if event.payload.get("operation") not in {
                "create",
                "update",
                "reschedule",
                "clear_trigger_time",
            }:
                continue
            reminder_id = event.payload.get("reminder_id")
            if not isinstance(reminder_id, str) or not reminder_id:
                continue
            reminder = self.reminder_repository.get_reminder(reminder_id)
            if reminder is None or reminder.lifecycle != "active":
                continue
            return MessageSubject(
                subject_type="reminder",
                object_ids=(reminder.id,),
                ordered=True,
            )
        return None


class IdentityAccessPreLLMGatePort:
    def __init__(
        self,
        identity_access: IdentityAccessService,
        settings_service: SettingsService | None = None,
    ) -> None:
        self.identity_access = identity_access
        self.settings_service = settings_service

    def evaluate(self, trigger) -> GateDecision:
        try:
            access = self.identity_access.check_access_for_inbound(trigger.account_id)
            if not access.allowed:
                return GateDecision.denied(
                    denial_reason=access.denial_reason or "access_denied",
                    access_facts=access.fact or {},
                )
            account = self.identity_access.repository.get_account(trigger.account_id)
            activation = self.identity_access.mark_first_inbound_received(
                trigger.account_id
            )
            settings_view = (
                self.settings_service.view_settings(trigger.account_id)
                if self.settings_service is not None
                else None
            )
        except IdentityAccessError as error:
            return GateDecision.denied(
                denial_reason=error.code,
                access_facts=error.fact or {"type": error.code},
            )
        except SettingsError as error:
            return GateDecision.denied(
                denial_reason=error.code,
                access_facts=error.fact or {"type": error.code},
            )

        trust_facts = {
            "account_id": trigger.account_id,
            "default_timezone": (
                account.default_timezone if account is not None else "UTC"
            ),
            "memory_enabled": True,
        }
        if settings_view is not None:
            trust_facts.update(_settings_view_facts(settings_view))
        return GateDecision.allowed(
            trust_facts=trust_facts,
            activation_guidance_required=activation.first_guidance_sent_at is None,
        )


class ReminderToolAdapter:
    def __init__(self, reminder_service: ReminderService) -> None:
        self.reminder_service = reminder_service

    def execute(self, command: Mapping[str, Any], guard: Any) -> ToolExecutionResult:
        operation = _required_str(command, "operation")
        owner = _required_str(command, "owner_account_id", default_key="account_id")

        if operation in {"list_reminders", "filter_reminders"}:
            display_timezone = str(
                command.get("display_timezone")
                or command.get("captured_timezone")
                or "UTC"
            )
            facts = _reminder_list_facts(
                owner,
                self.reminder_service.filter_reminders(
                    owner_account_id=owner,
                    keyword=_optional_non_empty_str(command.get("keyword")),
                    lifecycle=_reminder_lifecycle_filter(command),
                    kind=_reminder_kind_filter(command),
                    trigger_after=_optional_datetime(command.get("trigger_after")),
                    trigger_before=_optional_datetime(command.get("trigger_before")),
                ),
                display_timezone=display_timezone,
            )
            return ToolExecutionResult(
                ok=True,
                facts=facts,
                domain_result=DomainExecutionResult(
                    domain="reminder",
                    intent="list reminders",
                    action=operation,
                    effect="listed",
                    intent_fulfilled=True,
                    visible_summary=_reminder_list_visible_summary(facts),
                    reply_contract="render_reminder_list",
                    privacy_notes=("Only describe reminders for this account.",),
                ),
            )

        _guard_state_change(guard)
        if operation in {"create", "detect_and_create"}:
            result = self.reminder_service.execute_batch(
                owner_account_id=owner,
                items=[
                    _reminder_batch_item(
                        command,
                        turn_id=_guard_turn_id(guard),
                        item_index=1,
                    )
                ],
                commit_guard=_guard_commit_guard(guard),
            )
            return ToolExecutionResult(
                ok=all(item.state == "succeeded" for item in result.items),
                facts={
                    "owner_account_id": result.owner_account_id,
                    "items": [_item_fact(item) for item in result.items],
                },
                reason_code=_first_reason(result.items),
            )

        if operation == "execute_batch":
            items = command.get("items")
            if not isinstance(items, list):
                return ToolExecutionResult(
                    ok=False,
                    facts={},
                    reason_code="items_required",
                )
            result = self.reminder_service.execute_batch(
                owner_account_id=owner,
                items=[
                    _reminder_batch_item(
                        item,
                        turn_id=_guard_turn_id(guard),
                        item_index=index,
                    )
                    for index, item in enumerate(items, start=1)
                ],
                commit_guard=_guard_commit_guard(guard),
            )
            return ToolExecutionResult(
                ok=all(item.state == "succeeded" for item in result.items),
                facts={
                    "owner_account_id": result.owner_account_id,
                    "items": [_item_fact(item) for item in result.items],
                },
                reason_code=_first_reason(result.items),
            )

        if operation == "schedule_unscheduled":
            result = self.reminder_service.schedule_unscheduled(
                owner_account_id=owner,
                reminder_id=_required_str(command, "reminder_id"),
                trigger_time=_required_datetime(command, "trigger_time"),
                captured_timezone=str(command.get("captured_timezone") or "UTC"),
                commit_guard=_guard_commit_guard(guard),
            )
            return _single_item_tool_result(result)

        if operation == "reschedule_reminder":
            result = self.reminder_service.reschedule_reminder(
                owner_account_id=owner,
                reminder_id=_required_str(command, "reminder_id"),
                trigger_time=_required_datetime(command, "trigger_time"),
                captured_timezone=str(command.get("captured_timezone") or "UTC"),
                commit_guard=_guard_commit_guard(guard),
            )
            return _single_item_tool_result(result)

        if operation == "update_reminder":
            keyword = _optional_non_empty_str(command.get("keyword"))
            if keyword and not command.get("reminder_id"):
                result = self.reminder_service.update_reminder_by_keyword(
                    owner_account_id=owner,
                    keyword=keyword,
                    content=command.get("content"),
                    trigger_time=_optional_datetime(command.get("trigger_time")),
                    captured_timezone=command.get("captured_timezone"),
                    duration_minutes=command.get("duration_minutes"),
                    commit_guard=_guard_commit_guard(guard),
                )
            else:
                result = self.reminder_service.update_reminder(
                    owner_account_id=owner,
                    reminder_id=_required_str(command, "reminder_id"),
                    content=command.get("content"),
                    trigger_time=_optional_datetime(command.get("trigger_time")),
                    captured_timezone=command.get("captured_timezone"),
                    duration_minutes=command.get("duration_minutes"),
                    commit_guard=_guard_commit_guard(guard),
                )
            return _single_item_tool_result(result)

        if operation == "clear_trigger_time":
            result = self.reminder_service.clear_trigger_time(
                owner_account_id=owner,
                reminder_id=_required_str(command, "reminder_id"),
                commit_guard=_guard_commit_guard(guard),
            )
            return _single_item_tool_result(result)

        if operation == "complete_reminder":
            keyword = _optional_non_empty_str(command.get("keyword"))
            if keyword and not command.get("reminder_id"):
                result = self.reminder_service.complete_reminder_by_keyword(
                    owner_account_id=owner,
                    keyword=keyword,
                    commit_guard=_guard_commit_guard(guard),
                )
            else:
                result = self.reminder_service.complete_reminder(
                    owner_account_id=owner,
                    reminder_id=_required_str(command, "reminder_id"),
                    commit_guard=_guard_commit_guard(guard),
                )
            return _single_item_tool_result(result)

        if operation == "delete_reminder":
            keyword = _optional_non_empty_str(command.get("keyword"))
            if keyword and not command.get("reminder_id"):
                result = self.reminder_service.delete_reminder_by_keyword(
                    owner_account_id=owner,
                    keyword=keyword,
                    commit_guard=_guard_commit_guard(guard),
                )
            else:
                result = self.reminder_service.delete_reminder(
                    owner_account_id=owner,
                    reminder_id=_required_str(command, "reminder_id"),
                    commit_guard=_guard_commit_guard(guard),
                )
            return _single_item_tool_result(result)

        return ToolExecutionResult(
            ok=False, facts={}, reason_code="unsupported_reminder_operation"
        )


class SocialSchedulingToolAdapter:
    def __init__(self, social_scheduling_service: SocialSchedulingService) -> None:
        self.social_scheduling_service = social_scheduling_service

    def execute(self, command: Mapping[str, Any], guard: Any) -> ToolExecutionResult:
        operation = _required_str(command, "operation")
        try:
            if operation == "list_friends":
                entries = self.social_scheduling_service.list_friends(
                    _required_str(command, "account_id")
                )
                return ToolExecutionResult(
                    ok=True,
                    facts={"friends": [asdict(entry) for entry in entries]},
                )

            if operation == "query_availability":
                result = self.social_scheduling_service.query_availability(
                    requester_account_id=_required_str(
                        command, "requester_account_id", default_key="account_id"
                    ),
                    friend_account_ids=_list_value(command, "friend_account_ids"),
                    local_start=_required_datetime(command, "local_start"),
                    local_end=_required_datetime(command, "local_end"),
                    requester_timezone=str(command.get("requester_timezone") or "UTC"),
                )
                return ToolExecutionResult(
                    ok=True,
                    facts={"availability": _availability_facts(result)},
                )

            _guard_state_change(guard)
            if operation == "get_friend_link":
                link = self.social_scheduling_service.get_or_create_friend_link(
                    owner_account_id=_required_str(
                        command, "owner_account_id", default_key="account_id"
                    ),
                    commit_guard=_guard_commit_guard(guard),
                )
                return ToolExecutionResult(ok=True, facts=_friend_link_facts(link))

            if operation == "reset_friend_link":
                link = self.social_scheduling_service.reset_friend_link(
                    owner_account_id=_required_str(
                        command, "owner_account_id", default_key="account_id"
                    ),
                    commit_guard=_guard_commit_guard(guard),
                )
                return ToolExecutionResult(ok=True, facts=_friend_link_facts(link))

            if operation == "disable_friend_link":
                link = self.social_scheduling_service.disable_friend_link(
                    owner_account_id=_required_str(
                        command, "owner_account_id", default_key="account_id"
                    ),
                    commit_guard=_guard_commit_guard(guard),
                )
                return ToolExecutionResult(ok=True, facts=_friend_link_facts(link))

            if operation == "create_shared_reminder":
                result = self.social_scheduling_service.create_shared_reminder(
                    creator_account_id=_required_str(
                        command, "creator_account_id", default_key="account_id"
                    ),
                    receiver_account_ids=_list_value(
                        command,
                        "receiver_account_ids",
                        aliases=("participant_account_ids", "participants"),
                    ),
                    title=command.get("title"),
                    local_trigger_at=_optional_datetime(
                        command.get("local_trigger_at")
                    ),
                    captured_timezone=str(command.get("captured_timezone") or "UTC"),
                    duration_minutes=(
                        int(command["duration_minutes"])
                        if command.get("duration_minutes") is not None
                        else None
                    ),
                    commit_guard=_guard_commit_guard(guard),
                )
                facts = _shared_reminder_create_tool_facts(
                    operation,
                    command,
                    result,
                )
                return ToolExecutionResult(
                    ok=result.status in {"created", "duplicate"},
                    facts=facts,
                    reason_code=(
                        None
                        if result.status in {"created", "duplicate"}
                        else result.status
                    ),
                )

            if operation == "detect_and_create_shared_reminder":
                result = (
                    self.social_scheduling_service.detect_and_create_shared_reminder(
                        creator_account_id=_required_str(
                            command, "creator_account_id", default_key="account_id"
                        ),
                        receiver_account_ids=_list_value(
                            command,
                            "receiver_account_ids",
                            aliases=("participant_account_ids", "participants"),
                        ),
                        raw_text=_required_str(command, "raw_text"),
                        title=command.get("title"),
                        captured_timezone=str(
                            command.get("captured_timezone") or "UTC"
                        ),
                        duration_minutes=(
                            int(command["duration_minutes"])
                            if command.get("duration_minutes") is not None
                            else None
                        ),
                        commit_guard=_guard_commit_guard(guard),
                    )
                )
                facts = _shared_reminder_create_tool_facts(
                    operation,
                    command,
                    result,
                )
                return ToolExecutionResult(
                    ok=result.status in {"created", "duplicate"},
                    facts=facts,
                    reason_code=(
                        None
                        if result.status in {"created", "duplicate"}
                        else result.status
                    ),
                )

            if operation == "cancel_shared_reminder":
                result = self.social_scheduling_service.cancel_shared_reminder(
                    account_id=_required_str(command, "account_id"),
                    shared_reminder_id=_required_str(command, "shared_reminder_id"),
                    commit_guard=_guard_commit_guard(guard),
                )
                return ToolExecutionResult(
                    ok=True,
                    facts={
                        "status": result.status,
                        "shared_reminder_id": result.shared_reminder.id,
                    },
                )

            if operation == "update_shared_reminder":
                update_kwargs = {
                    "account_id": _required_str(command, "account_id"),
                    "shared_reminder_id": _required_str(command, "shared_reminder_id"),
                    "local_trigger_at": _optional_datetime(
                        command.get("local_trigger_at") or command.get("trigger_time")
                    ),
                    "captured_timezone": str(command.get("captured_timezone") or "UTC"),
                    "duration_minutes": (
                        int(command["duration_minutes"])
                        if command.get("duration_minutes") is not None
                        else None
                    ),
                    "commit_guard": _guard_commit_guard(guard),
                }
                if "idempotent_replay" in command:
                    update_kwargs["idempotent_replay"] = bool(
                        command.get("idempotent_replay")
                    )
                result = self.social_scheduling_service.update_shared_reminder(
                    **update_kwargs
                )
                facts = _shared_reminder_create_tool_facts(
                    operation,
                    command,
                    result,
                )
                return ToolExecutionResult(
                    ok=result.status == "rescheduled",
                    facts=facts,
                    reason_code=(
                        None if result.status == "rescheduled" else result.status
                    ),
                )

            if operation == "establish_friendship_from_token":
                joiner_account_id = _required_str(
                    command, "joiner_account_id", default_key="account_id"
                )
                if command.get("link_code"):
                    result = (
                        self.social_scheduling_service.establish_friendship_from_code(
                            joiner_account_id=joiner_account_id,
                            link_code=_required_str(command, "link_code"),
                            commit_guard=_guard_commit_guard(guard),
                        )
                    )
                else:
                    result = (
                        self.social_scheduling_service.establish_friendship_from_token(
                            joiner_account_id=joiner_account_id,
                            public_token=_required_str(command, "public_token"),
                            commit_guard=_guard_commit_guard(guard),
                        )
                    )
                return ToolExecutionResult(
                    ok=result.status in {"created", "already_active"},
                    facts={
                        "status": result.status,
                        "friendship_id": (
                            result.friendship.id if result.friendship else None
                        ),
                        "counterpart_account_id": result.counterpart_account_id,
                        "counterpart_display_name": result.counterpart_display_name,
                        "continuation": result.continuation,
                    },
                    reason_code=(
                        None
                        if result.status in {"created", "already_active"}
                        else result.status
                    ),
                )

            if operation == "remove_friend":
                friendship = self.social_scheduling_service.remove_friend(
                    account_id=_required_str(command, "account_id"),
                    friend_account_id=_required_str(command, "friend_account_id"),
                    commit_guard=_guard_commit_guard(guard),
                )
                return ToolExecutionResult(ok=True, facts=asdict(friendship))
        except SocialSchedulingError as error:
            return ToolExecutionResult(
                ok=False,
                facts=error.fact or {},
                reason_code=error.code,
            )
        except ValueError:
            reason_code = "social_scheduling_write_failed"
            return ToolExecutionResult(
                ok=False,
                facts={"type": reason_code},
                reason_code=reason_code,
            )

        return ToolExecutionResult(
            ok=False, facts={}, reason_code="unsupported_social_scheduling_operation"
        )


class CalendarImportToolAdapter:
    def __init__(self, calendar_import_service: CalendarImportService) -> None:
        self.calendar_import_service = calendar_import_service

    def execute(self, command: Mapping[str, Any], guard: Any) -> ToolExecutionResult:
        operation = _required_str(command, "operation")
        _guard_state_change(guard)
        if operation == "import_google_calendar":
            summary = self.calendar_import_service.import_google_calendar(
                account_id=_required_str(command, "account_id"),
                auth_handle=_required_str(command, "auth_handle"),
                provider_account_id=command.get("provider_account_id"),
                visible_start=_required_datetime(command, "visible_start"),
                visible_end=_required_datetime(command, "visible_end"),
                captured_timezone=str(command.get("captured_timezone") or "UTC"),
                auth_artifact_id=command.get("auth_artifact_id"),
            )
            return ToolExecutionResult(
                ok=summary.failed_count == 0,
                facts={
                    "run_id": summary.run_id,
                    "imported_count": summary.imported_count,
                    "skipped_count": summary.skipped_count,
                    "downgraded_count": summary.downgraded_count,
                    "failed_count": summary.failed_count,
                },
                reason_code="calendar_import_failed" if summary.failed_count else None,
            )

        if operation == "stop_authorization":
            state = self.calendar_import_service.stop_authorization(
                account_id=_required_str(command, "account_id"),
                auth_handle=_required_str(command, "auth_handle"),
            )
            return ToolExecutionResult(ok=True, facts=asdict(state))

        if operation == "revoke_authorization":
            state = self.calendar_import_service.revoke_authorization(
                account_id=_required_str(command, "account_id"),
                auth_handle=_required_str(command, "auth_handle"),
            )
            return ToolExecutionResult(ok=True, facts=asdict(state))

        return ToolExecutionResult(
            ok=False, facts={}, reason_code="unsupported_calendar_import_operation"
        )


class IdentityAccessToolAdapter:
    def __init__(self, identity_access_service: IdentityAccessService) -> None:
        self.identity_access_service = identity_access_service

    def execute(self, command: Mapping[str, Any], guard: Any) -> ToolExecutionResult:
        operation = _required_str(command, "operation")
        if operation == "get_access_status":
            access = self.identity_access_service.get_access_status(
                _required_str(command, "account_id")
            )
            return ToolExecutionResult(ok=True, facts=asdict(access))

        _guard_state_change(guard)
        if operation == "issue_login_url":
            result = self.identity_access_service.issue_login_url(
                _required_str(command, "account_id")
            )
            return ToolExecutionResult(
                ok=True,
                facts={"artifact_id": result.artifact.id, "code": result.code},
            )

        if operation == "issue_pairing_code":
            result = self.identity_access_service.issue_pairing_code(
                _required_str(command, "account_id")
            )
            return ToolExecutionResult(
                ok=True,
                facts={"artifact_id": result.artifact.id, "code": result.code},
            )

        if operation == "issue_web_claim_code":
            result = self.identity_access_service.issue_web_claim_code(
                browser_session=_required_str(command, "browser_session"),
                continuation=dict(command.get("continuation") or {}),
            )
            return ToolExecutionResult(
                ok=True,
                facts={"artifact_id": result.artifact.id, "code": result.code},
            )

        return ToolExecutionResult(
            ok=False, facts={}, reason_code="unsupported_identity_access_operation"
        )


class SettingsToolAdapter:
    def __init__(self, settings_service: SettingsService) -> None:
        self.settings_service = settings_service

    def execute(self, command: Mapping[str, Any], guard: Any) -> ToolExecutionResult:
        operation = _required_str(command, "operation")
        account_id = _required_str(
            command, "account_id", default_key="owner_account_id"
        )
        try:
            if operation == "view_settings":
                return ToolExecutionResult(
                    ok=True,
                    facts=_settings_view_facts(
                        self.settings_service.view_settings(account_id)
                    ),
                )

            _guard_state_change(guard)
            if operation == "set_timezone":
                view = self.settings_service.set_timezone(
                    account_id,
                    _required_str(
                        command,
                        "default_timezone",
                        default_key="timezone",
                    ),
                )
                return ToolExecutionResult(ok=True, facts=_settings_view_facts(view))

            if operation == "update_settings":
                view = self.settings_service.update_settings(
                    account_id,
                    **_settings_update_fields(command),
                )
                return ToolExecutionResult(ok=True, facts=_settings_view_facts(view))

            if operation == "update_profile":
                view = self.settings_service.update_profile(
                    account_id,
                    **_profile_update_fields(command),
                )
                return ToolExecutionResult(ok=True, facts=_settings_view_facts(view))

            if operation == "reset_agent_settings":
                view = self.settings_service.reset_agent_settings(account_id)
                return ToolExecutionResult(ok=True, facts=_settings_view_facts(view))
        except SettingsError as error:
            return ToolExecutionResult(
                ok=False,
                facts=error.fact or {"type": error.code},
                reason_code=error.code,
            )
        except ValueError:
            reason_code = "settings_write_failed"
            return ToolExecutionResult(
                ok=False,
                facts={"type": reason_code},
                reason_code=reason_code,
            )

        return ToolExecutionResult(
            ok=False, facts={}, reason_code="unsupported_settings_operation"
        )


def _compose_turn_pipeline(
    *,
    planner: Any,
    express: Any,
    reminder_service: ReminderService,
    social_scheduling_service: SocialSchedulingService,
    calendar_import_service: CalendarImportService,
    settings_service: SettingsService,
    conversation_runtime_service: ConversationRuntimeService,
    pending_store: Any,
    reminder_detector: Any,
    now: Callable[[], datetime],
) -> TurnPipeline:
    return TurnPipeline(
        planner=planner,
        handlers={
            "reminder": ReminderActionHandler(
                reminder_service,
                reminder_detector,
                now=now,
            ),
            "social_scheduling": SocialSchedulingActionHandler(
                social_scheduling_service
            ),
            "friendship": FriendshipActionHandler(social_scheduling_service),
            "settings": SettingsActionHandler(settings_service),
            "calendar_import": CalendarImportActionHandler(calendar_import_service),
        },
        express=express,
        close_coordinator=CloseCoordinator(
            conversation_runtime_service,
            pending_store=pending_store,
        ),
        pending_store=pending_store,
    )


def compose_coke_runtime(
    *,
    interaction_agent: Any,
    redis_client: RedisLockPort,
    outbound_delivery: OutboundDeliveryPort,
    turn_planner: Any | None = None,
    turn_express: Any | None = None,
    reminder_detector: Any | None = None,
    reminder_delivery: Any | None = None,
    memory_port: MemoryPort | None = None,
    google_calendar_client: GoogleCalendarClientPort | None = None,
    provider_adapters: Mapping[str, Any] | None = None,
    repositories: CokeRepositories | None = None,
    now: Callable[[], datetime] | None = None,
    id_factory: Callable[[str], str] | None = None,
    lock_token_factory: Callable[[], str] | None = None,
    lock_ttl_ms: int = 30_000,
    public_base_url: str = "http://localhost:4040",
    resend_api_key: str | None = None,
    email_from: str = "noreply@keep4oforever.com",
    email_from_name: str | None = None,
    email_auth_enabled: bool = True,
    claim_boundary_committer: Callable[[], None] | None = None,
    close_boundary_committer: Callable[[], None] | None = None,
) -> CokeRuntime:
    now = now or (lambda: datetime.now(UTC))
    # Row ids must be valid UUIDs because every domain `id` primary-key column is
    # UUID in the clean schema; a `{prefix}_{timestamp}` string only works for the
    # in-memory dict-key repos and fails the Postgres-backed repositories.
    id_factory = id_factory or (lambda prefix: uuid4().hex)

    if repositories is None:
        identity_repository = InMemoryIdentityAccessRepository(now=now)
        repositories = CokeRepositories(
            identity_access=identity_repository,
            channel_reachability=InMemoryChannelReachabilityRepository(),
            conversation_runtime=InMemoryConversationRuntimeRepository(now=now),
            reminder=InMemoryReminderRepository(),
            social_scheduling=InMemorySocialSchedulingRepository(),
            calendar_import=InMemoryCalendarImportRepository(),
            settings=InMemorySettingsRepository(
                accounts=identity_repository.accounts,
            ),
            pending_clarification=InMemoryPendingClarificationStore(),
        )
    elif repositories.settings is None or repositories.pending_clarification is None:
        repositories = CokeRepositories(
            identity_access=repositories.identity_access,
            channel_reachability=repositories.channel_reachability,
            conversation_runtime=repositories.conversation_runtime,
            reminder=repositories.reminder,
            social_scheduling=repositories.social_scheduling,
            calendar_import=repositories.calendar_import,
            settings=(
                repositories.settings
                or InMemorySettingsRepository(
                    accounts=getattr(repositories.identity_access, "accounts", None),
                )
            ),
            pending_clarification=(
                repositories.pending_clarification
                or InMemoryPendingClarificationStore()
            ),
        )

    email_sender = (
        ResendEmailSender(
            api_key=resend_api_key,
            email_from=email_from,
            email_from_name=email_from_name,
            public_base_url=public_base_url,
        )
        if resend_api_key
        else NullEmailSender()
    )
    identity_access_service = IdentityAccessService(
        repository=repositories.identity_access,
        now=now,
        id_factory=id_factory,
        email_sender=email_sender,
        public_base_url=public_base_url,
        email_auth_enabled=email_auth_enabled,
    )
    channel_reachability_service = ChannelReachabilityService(
        repository=repositories.channel_reachability,
        identity_access=identity_access_service,
        providers=provider_adapters or {},
        now=now,
        id_factory=id_factory,
    )
    conversation_runtime_service = ConversationRuntimeService(
        repository=repositories.conversation_runtime,
        now=now,
        id_factory=id_factory,
    )
    social_scheduling_service = SocialSchedulingService(
        repository=repositories.social_scheduling,
        reachability=IdentityReachabilityAdapter(identity_access_service),
        reminder_availability=ReminderAvailabilityAdapter(repositories.reminder),
        detector=reminder_detector,
        now=now,
        id_factory=id_factory,
        public_base_url=public_base_url,
        display_name_resolver=identity_access_service.get_display_name,
    )
    channel_reachability_service.set_deferred_friend_link_completion(
        DeferredFriendLinkCompletionAdapter(
            identity_access=identity_access_service,
            social_scheduling=social_scheduling_service,
        )
    )
    reminder_service = ReminderService(
        repository=repositories.reminder,
        detector=reminder_detector,
        delivery=reminder_delivery,
        now=now,
        id_factory=id_factory,
        friend_identifiers=(
            social_scheduling_service.friend_identifiers_for_shared_reminder
        ),
    )
    calendar_import_service = CalendarImportService(
        repository=repositories.calendar_import,
        google_client=google_calendar_client or EmptyGoogleCalendarClient(),
        reminder_service=reminder_service,
        access_gate=identity_access_service,
        now=now,
        id_factory=id_factory,
    )
    settings_service = SettingsService(
        repository=repositories.settings,
        proactive_reminder_port=repositories.reminder,
        now=now,
        id_factory=id_factory,
    )

    adapters = CokeToolAdapters(
        reminder_tool=ReminderToolAdapter(reminder_service),
        social_scheduling_tool=SocialSchedulingToolAdapter(social_scheduling_service),
        calendar_import_tool=CalendarImportToolAdapter(calendar_import_service),
        identity_access_tool=IdentityAccessToolAdapter(identity_access_service),
        settings_tool=SettingsToolAdapter(settings_service),
    )
    tool_ports = AgentToolPorts(
        reminder_tool=adapters.reminder_tool,
        social_scheduling_tool=adapters.social_scheduling_tool,
        calendar_import_tool=adapters.calendar_import_tool,
        identity_access_tool=adapters.identity_access_tool,
        settings_tool=adapters.settings_tool,
    )
    pre_llm_gate = PreLLMGateService(
        IdentityAccessPreLLMGatePort(identity_access_service, settings_service)
    )
    lock_manager = ConversationLockManager(
        redis_client=redis_client,
        ttl_ms=lock_ttl_ms,
        token_factory=lock_token_factory,
    )
    turn_planner = turn_planner or FakeTurnPlanner()
    turn_express = turn_express or FakeTurnExpress()
    turn_pipeline = _compose_turn_pipeline(
        planner=turn_planner,
        express=turn_express,
        reminder_service=reminder_service,
        social_scheduling_service=social_scheduling_service,
        calendar_import_service=calendar_import_service,
        settings_service=settings_service,
        conversation_runtime_service=conversation_runtime_service,
        pending_store=repositories.pending_clarification,
        reminder_detector=reminder_detector or FakeReminderDetector(),
        now=now,
    )
    turn_runner = TurnRunner(
        conversation_runtime=conversation_runtime_service,
        lock_manager=lock_manager,
        pre_llm_gate=pre_llm_gate,
        memory_port=memory_port,
        interaction_agent=interaction_agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=outbound_delivery,
        tool_ports=tool_ports,
        reminder_fire_facts=reminder_service,
        focus_resolver=FocusResolver(
            ReminderLifecycleFocusRepository(
                repositories.conversation_runtime,
                repositories.reminder,
            )
        ),
        delivery_lifecycle=OutputLifecycleDeliveryCallbacks(
            reminder_service=reminder_service,
            social_scheduling_service=social_scheduling_service,
            conversation_runtime_service=conversation_runtime_service,
            identity_access_service=identity_access_service,
        ),
        now=now,
        account_timezone=lambda account_id: _account_default_timezone(
            identity_access_service, account_id
        ),
        claim_boundary_committer=claim_boundary_committer,
        close_boundary_committer=close_boundary_committer,
        turn_pipeline=turn_pipeline,
        render_express=turn_express,
    )
    return CokeRuntime(
        repositories=repositories,
        identity_access_service=identity_access_service,
        channel_reachability_service=channel_reachability_service,
        conversation_runtime_service=conversation_runtime_service,
        reminder_service=reminder_service,
        social_scheduling_service=social_scheduling_service,
        calendar_import_service=calendar_import_service,
        settings_service=settings_service,
        adapters=adapters,
        tool_ports=tool_ports,
        pre_llm_gate=pre_llm_gate,
        lock_manager=lock_manager,
        turn_runner=turn_runner,
        turn_pipeline=turn_pipeline,
        provider_adapters=provider_adapters or {},
    )


def build_runtime_from_settings(
    settings: Settings,
    *,
    redis_client: Any | None = None,
    now: Callable[[], datetime] | None = None,
    id_factory: Callable[[str], str] | None = None,
) -> CokeRuntime:
    now = now or (lambda: datetime.now(UTC))
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    session = session_factory()
    redis_client = redis_client or create_redis_client(settings)
    redis_lock = RedisLockAdapter(redis_client)
    work_stream = RedisWorkStream(
        redis_client,
        stream_name=settings.work_stream_name,
        group_name=settings.work_group_name,
    )
    reply_pubsub = RedisReplyPubSub(
        redis_client,
        channel_prefix=settings.reply_channel_prefix,
    )
    provider_adapters = _provider_adapters_from_settings(settings, now=now)
    repositories = _postgres_repositories(session)
    (
        interaction_agent,
        reminder_detector,
        turn_planner,
        turn_express,
        media_text_resolver,
    ) = _llm_from_settings(settings)
    google_calendar_client = GoogleCalendarClientAdapter(
        calendar_id=settings.google_calendar_id,
        now=now,
    )

    def interactive_runtime_factory() -> CokeRuntime:
        child_session = session_factory()
        child_repositories = _postgres_repositories(child_session)
        child_runtime = compose_coke_runtime(
            interaction_agent=interaction_agent,
            redis_client=redis_lock,
            outbound_delivery=_DeferredOutboundDelivery(),
            turn_planner=turn_planner,
            turn_express=turn_express,
            reminder_detector=reminder_detector,
            memory_port=None,
            google_calendar_client=google_calendar_client,
            provider_adapters=provider_adapters,
            repositories=child_repositories,
            now=now,
            id_factory=id_factory,
            lock_ttl_ms=settings.lock_ttl_ms,
            public_base_url=settings.public_base_url,
            resend_api_key=settings.resend_api_key,
            email_from=settings.email_from,
            email_from_name=settings.email_from_name,
            email_auth_enabled=settings.email_auth_enabled,
            claim_boundary_committer=child_session.commit,
            close_boundary_committer=child_session.commit,
        )
        object.__setattr__(
            child_runtime.turn_runner,
            "outbound_delivery",
            ChannelReachabilityOutboundDelivery(
                child_runtime.channel_reachability_service,
                conversation_runtime=child_runtime.conversation_runtime_service,
            ),
        )
        return CokeRuntime(
            repositories=child_runtime.repositories,
            identity_access_service=child_runtime.identity_access_service,
            channel_reachability_service=child_runtime.channel_reachability_service,
            conversation_runtime_service=child_runtime.conversation_runtime_service,
            reminder_service=child_runtime.reminder_service,
            social_scheduling_service=child_runtime.social_scheduling_service,
            calendar_import_service=child_runtime.calendar_import_service,
            settings_service=child_runtime.settings_service,
            adapters=child_runtime.adapters,
            tool_ports=child_runtime.tool_ports,
            pre_llm_gate=child_runtime.pre_llm_gate,
            lock_manager=child_runtime.lock_manager,
            turn_runner=child_runtime.turn_runner,
            turn_pipeline=child_runtime.turn_pipeline,
            provider_adapters=provider_adapters,
            engine=engine,
            session_factory=session_factory,
            session=child_session,
            redis_client=redis_client,
            reply_pubsub=reply_pubsub,
            media_text_resolver=media_text_resolver,
        )

    runtime = compose_coke_runtime(
        interaction_agent=interaction_agent,
        redis_client=redis_lock,
        outbound_delivery=_DeferredOutboundDelivery(),
        turn_planner=turn_planner,
        turn_express=turn_express,
        reminder_detector=reminder_detector,
        memory_port=None,
        google_calendar_client=google_calendar_client,
        provider_adapters=provider_adapters,
        repositories=repositories,
        now=now,
        id_factory=id_factory,
        lock_ttl_ms=settings.lock_ttl_ms,
        public_base_url=settings.public_base_url,
        resend_api_key=settings.resend_api_key,
        email_from=settings.email_from,
        email_from_name=settings.email_from_name,
        email_auth_enabled=settings.email_auth_enabled,
        claim_boundary_committer=session.commit,
        close_boundary_committer=session.commit,
    )
    object.__setattr__(
        runtime.turn_runner,
        "outbound_delivery",
        ChannelReachabilityOutboundDelivery(
            runtime.channel_reachability_service,
            conversation_runtime=runtime.conversation_runtime_service,
        ),
    )
    return CokeRuntime(
        repositories=runtime.repositories,
        identity_access_service=runtime.identity_access_service,
        channel_reachability_service=runtime.channel_reachability_service,
        conversation_runtime_service=runtime.conversation_runtime_service,
        reminder_service=runtime.reminder_service,
        social_scheduling_service=runtime.social_scheduling_service,
        calendar_import_service=runtime.calendar_import_service,
        settings_service=runtime.settings_service,
        adapters=runtime.adapters,
        tool_ports=runtime.tool_ports,
        pre_llm_gate=runtime.pre_llm_gate,
        lock_manager=runtime.lock_manager,
        turn_runner=runtime.turn_runner,
        turn_pipeline=runtime.turn_pipeline,
        provider_adapters=provider_adapters,
        engine=engine,
        session_factory=session_factory,
        session=session,
        redis_client=redis_client,
        work_stream=work_stream,
        reply_pubsub=reply_pubsub,
        media_text_resolver=media_text_resolver,
        interactive_runtime_factory=interactive_runtime_factory,
    )


def _postgres_repositories(session: Any) -> CokeRepositories:
    return CokeRepositories(
        identity_access=PostgresIdentityAccessRepository(session),
        channel_reachability=PostgresChannelReachabilityRepository(session),
        conversation_runtime=PostgresConversationRuntimeRepository(session),
        reminder=PostgresReminderRepository(session),
        social_scheduling=PostgresSocialSchedulingRepository(session),
        calendar_import=PostgresCalendarImportRepository(session),
        settings=PostgresSettingsRepository(session),
        pending_clarification=PostgresPendingClarificationRepository(session),
    )


class _DeferredOutboundDelivery:
    def deliver(self, request: DeliveryRequest):
        raise RuntimeError("outbound delivery was not bound")


def _provider_adapters_from_settings(
    settings: Settings,
    *,
    now: Callable[[], datetime],
) -> Mapping[str, Any]:
    return provider_registry(
        [
            WhatsAppEvolutionAdapter(
                base_url=settings.evolution_base_url,
                api_key=settings.evolution_api_key,
                instance=settings.evolution_instance,
                now=now,
            ),
            WeChatPersonalAdapter(
                endpoint_url=settings.wechat_personal_endpoint_url,
                api_key=settings.wechat_personal_api_key,
                timeout=settings.wechat_personal_send_timeout_s,
                now=now,
            ),
            WeChatECloudAdapter(
                endpoint_url=settings.wechat_ecloud_endpoint_url,
                token=settings.wechat_ecloud_token,
                app_id=settings.wechat_ecloud_app_id,
                now=now,
            ),
            LinqAdapter(
                endpoint_url=settings.linq_endpoint_url,
                api_key=settings.linq_api_key,
                now=now,
            ),
        ]
    )


def _llm_from_settings(settings: Settings):
    if settings.llm_fake:
        return (
            FakeInteractionAgent(),
            FakeReminderDetector(),
            FakeTurnPlanner(),
            FakeTurnExpress(),
            None,
        )
    if not settings.zai_api_key:
        raise ConfigurationError("ZAI_API_KEY is required for LLM composition")
    if (
        TEXT_PROVIDER_DEEPSEEK
        in {
            settings.planner_provider,
            settings.detector_provider,
            settings.express_provider,
        }
        and not settings.deepseek_api_key
    ):
        raise ConfigurationError(
            "DEEPSEEK_API_KEY is required for DeepSeek LLM composition"
        )
    llm_config = ZAILLMConfig(
        api_key=settings.zai_api_key,
        base_url=settings.zai_base_url,
        deepseek_api_key=settings.deepseek_api_key,
        deepseek_base_url=settings.deepseek_base_url,
        interaction_model=settings.interaction_model,
        planner_provider=settings.planner_provider,
        planner_model=settings.planner_model,
        detector_provider=settings.detector_provider,
        detector_model=settings.detector_model,
        express_provider=settings.express_provider,
        express_model=settings.express_model,
        interaction_timeout_s=settings.interaction_timeout_s,
        agno_database_url=settings.agno_database_url,
        agno_create_schema=settings.agno_create_schema,
    )
    media_text_resolver = None
    if settings.asr_model or settings.vision_text_model:
        if not settings.siliconflow_api_key:
            raise ConfigurationError(
                "SiliconFlow_API_KEY is required for media model composition"
            )
        media_config = SiliconFlowMediaConfig(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
            asr_model=settings.asr_model,
            vision_text_model=settings.vision_text_model,
            media_model_timeout_s=settings.media_model_timeout_s,
        )
        media_text_resolver = MediaTextResolver(
            asr_client=(
                SiliconFlowAsrClient(
                    api_key=media_config.api_key,
                    base_url=media_config.base_url,
                    model_id=media_config.asr_model,
                    timeout_s=media_config.media_model_timeout_s,
                )
                if media_config.asr_model
                else None
            ),
            vision_text_client=(
                SiliconFlowVisionTextClient(
                    api_key=media_config.api_key,
                    base_url=media_config.base_url,
                    model_id=media_config.vision_text_model,
                    timeout_s=media_config.media_model_timeout_s,
                )
                if media_config.vision_text_model
                else None
            ),
        )
    return (
        AgnoInteractionAgent.from_config(llm_config),
        SiliconFlowReminderDetector.from_model(llm_config.create_detector_model()),
        SiliconFlowPlanner.from_config(llm_config),
        ExpressAgent.from_config(llm_config),
        media_text_resolver,
    )


def _duration_delta(minutes: int):
    from datetime import timedelta

    return timedelta(minutes=minutes)


def _local_wall_clock(value: datetime, timezone: str) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo(timezone)).replace(tzinfo=None)


def _guard_state_change(guard: Any) -> None:
    guard.guard_state_change()


def _guard_commit_guard(guard: Any):
    return guard.guard_state_change


def _guard_turn_id(guard: Any) -> str | None:
    value = getattr(guard, "turn_id", None)
    return value if isinstance(value, str) else None


def _social_scheduling_account_id_from_command(
    command: Mapping[str, Any],
) -> str | None:
    for key in (
        "account_id",
        "owner_account_id",
        "creator_account_id",
        "joiner_account_id",
    ):
        value = command.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _shared_reminder_create_tool_facts(
    operation: str,
    command: Mapping[str, Any],
    result: Any,
) -> dict[str, Any]:
    shared_reminder = getattr(result, "shared_reminder", None)
    status = str(getattr(result, "status", "invalid"))
    facts = {
        "status": status,
        "shared_reminder_id": (
            getattr(shared_reminder, "id", None) if shared_reminder else None
        ),
        "breakdown": getattr(result, "breakdown", {}) or {},
        "follow_up_facts": getattr(result, "follow_up_facts", {}) or {},
    }
    outcome_status = _social_scheduling_outcome_status(status, command, result)
    facts["social_scheduling_outcome"] = _social_scheduling_outcome_from_command(
        command,
        operation=operation,
        status=outcome_status,
        shared_reminder=shared_reminder,
        blocker=_social_scheduling_blocker(outcome_status),
    )
    return facts


def _social_scheduling_outcome_status(
    service_status: str,
    command: Mapping[str, Any],
    result: Any,
) -> str:
    if service_status == "created":
        return "created_active"
    if service_status == "rescheduled":
        return "rescheduled_active"
    if service_status == "duplicate":
        return "duplicate_active"
    if service_status == "blocked":
        breakdown = getattr(result, "breakdown", {}) or {}
        conflicting = breakdown.get("conflicting_participants")
        if isinstance(conflicting, list) and conflicting:
            return "blocked_receiver_conflict"
        unreachable = breakdown.get("unreachable_participants")
        if isinstance(unreachable, list) and unreachable:
            return "blocked_unreachable_participant"
        return "invalid"
    if service_status == "needs_participants":
        resolution = _friend_resolution_status(command, result)
        if resolution in {"unmatched", "unmatched_friend"}:
            return "blocked_unmatched_friend"
        if resolution in {"ambiguous", "ambiguous_friend"}:
            return "blocked_ambiguous_friend"
        return "needs_participants"
    if service_status in {
        "needs_title",
        "needs_time",
        "needs_duration",
        "needs_past_time_confirmation",
        "needs_incomplete_date_clarification",
    }:
        return service_status
    return "invalid"


def _friend_resolution_status(command: Mapping[str, Any], result: Any) -> str | None:
    context = _optional_context(command.get("context")) or {}
    value = context.get("friend_resolution_status")
    if isinstance(value, str) and value:
        return value
    follow_up_facts = getattr(result, "follow_up_facts", {}) or {}
    if isinstance(follow_up_facts, Mapping):
        value = follow_up_facts.get("reason")
        if isinstance(value, str) and value:
            return value
    return None


def _social_scheduling_blocker(outcome_status: str) -> str | None:
    blockers = {
        "blocked_unmatched_friend": "unmatched_friend",
        "blocked_ambiguous_friend": "ambiguous_friend",
        "blocked_receiver_conflict": "receiver_conflict",
        "blocked_unreachable_participant": "unreachable_participant",
    }
    return blockers.get(outcome_status)


def _social_scheduling_outcome_from_command(
    command: Mapping[str, Any],
    *,
    operation: str,
    status: str,
    shared_reminder: Any | None = None,
    blocker: str | None = None,
) -> dict[str, Any]:
    context = _optional_context(command.get("context")) or {}
    creator_account_id = (
        _social_scheduling_account_id_from_command(command) or "unknown"
    )
    unresolved_reference = _unresolved_friend_reference(command, context)
    reference = (
        unresolved_reference
        or getattr(shared_reminder, "id", None)
        or command.get("title")
        or "none"
    )
    receiver_account_ids = _list_value(
        command,
        "receiver_account_ids",
        aliases=("participant_account_ids", "participants"),
    )
    if not receiver_account_ids and shared_reminder is not None:
        receiver_account_ids = list(
            getattr(shared_reminder, "participant_account_ids", ()) or ()
        )
    shared_reminder_id = (
        getattr(shared_reminder, "id", None) if shared_reminder else None
    )
    return {
        "outcome_id": f"{operation}:{status}:{creator_account_id}:{reference}",
        "operation": operation,
        "status": status,
        "shared_reminder_id": shared_reminder_id,
        "title": _outcome_title(command, shared_reminder),
        "local_trigger_at": _outcome_datetime_value(
            command.get("local_trigger_at"),
            getattr(shared_reminder, "local_trigger_at", None),
        ),
        "captured_timezone": str(
            command.get("captured_timezone")
            or getattr(shared_reminder, "captured_timezone", None)
            or "UTC"
        ),
        "duration_minutes": _outcome_duration_minutes(command, shared_reminder),
        "participant_account_ids": list(receiver_account_ids),
        "blocker": blocker,
        "facts_hash": (
            command.get("facts_hash")
            if isinstance(command.get("facts_hash"), str)
            else None
        ),
    }


def _unresolved_friend_reference(
    command: Mapping[str, Any],
    context: Mapping[str, Any],
) -> str | None:
    for source in (context, command):
        value = source.get("unresolved_reference_text")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _outcome_title(
    command: Mapping[str, Any], shared_reminder: Any | None
) -> str | None:
    title = command.get("title")
    if isinstance(title, str) and title.strip():
        return title
    value = getattr(shared_reminder, "title", None) if shared_reminder else None
    return value if isinstance(value, str) else None


def _outcome_datetime_value(command_value: Any, fallback: Any) -> str | None:
    value = command_value if command_value is not None else fallback
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    return None


def _outcome_duration_minutes(
    command: Mapping[str, Any],
    shared_reminder: Any | None,
) -> int | None:
    value = command.get("duration_minutes")
    if value is None and shared_reminder is not None:
        value = getattr(shared_reminder, "duration_minutes", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_str(
    command: Mapping[str, Any],
    key: str,
    *,
    default_key: str | None = None,
) -> str:
    value = command.get(key)
    if value is None and default_key is not None:
        value = command.get(default_key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key}_required")
    return value


def _required_datetime(command: Mapping[str, Any], key: str) -> datetime:
    value = command.get(key)
    parsed = _optional_datetime(value)
    if parsed is None:
        raise ValueError(f"{key}_required")
    return parsed


def _optional_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("invalid_datetime")


def _optional_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _reminder_lifecycle_filter(command: Mapping[str, Any]) -> str | None:
    value = command.get("lifecycle", command.get("status", "active"))
    if value is None or value == "all":
        return None
    if value in {"active", "completed", "deleted"}:
        return str(value)
    raise ValueError("invalid_reminder_lifecycle")


def _reminder_kind_filter(command: Mapping[str, Any]) -> str | None:
    value = command.get("kind", command.get("reminder_type"))
    if value is None or value == "all":
        return None
    if value in {
        "timed",
        "no_trigger_time",
        "recurring",
        "proactive",
        "shared_projection",
    }:
        return str(value)
    raise ValueError("invalid_reminder_kind")


def _list_value(
    command: Mapping[str, Any],
    key: str,
    *,
    aliases: tuple[str, ...] = (),
) -> list[Any]:
    value = command.get(key)
    for alias in aliases:
        if value is not None:
            break
        value = command.get(alias)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                import json

                parsed = json.loads(stripped)
            except ValueError as exc:
                raise ValueError(f"{key}_invalid") from exc
            if isinstance(parsed, list):
                return parsed
            raise ValueError(f"{key}_invalid")
        return [part.strip() for part in stripped.split(",") if part.strip()]
    raise ValueError(f"{key}_invalid")


def _optional_context(value: Any) -> dict | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return {"text": stripped}
    raise ValueError("context_invalid")


def _reminder_batch_item(
    command: Mapping[str, Any],
    *,
    turn_id: str | None = None,
    item_index: int | None = None,
) -> ReminderBatchItem:
    return ReminderBatchItem(
        operation=_required_str(command, "operation"),
        content=command.get("content"),
        raw_text=command.get("raw_text"),
        reminder_id=command.get("reminder_id"),
        trigger_time=_optional_datetime(command.get("trigger_time")),
        captured_timezone=str(command.get("captured_timezone") or "UTC"),
        recurrence_rule=dict(command.get("recurrence_rule") or {}),
        duration_minutes=command.get("duration_minutes"),
        kind=command.get("kind"),
        entry_point=command.get("entry_point"),
        time_state=command.get("time_state"),
        incomplete_date=bool(command.get("incomplete_date", False)),
        shared_reminder_id=command.get("shared_reminder_id"),
        turn_id=turn_id,
        item_index=item_index,
    )


def _item_fact(item: Any) -> dict[str, Any]:
    fact = {
        "state": item.state,
        "reminder_id": item.reminder_id,
        "reason": item.reason,
        "time_state": item.time_state,
        "fact": item.fact,
    }
    return fact


def _single_item_tool_result(item: Any) -> ToolExecutionResult:
    return ToolExecutionResult(
        ok=item.state == "succeeded",
        facts=_item_fact(item),
        reason_code=item.reason,
    )


def _reminder_list_facts(
    owner_account_id: str, reminders: list[Any], *, display_timezone: str = "UTC"
) -> dict[str, Any]:
    zone_name, zone = _display_zone(display_timezone)
    reminder_facts = [
        _reminder_fact(reminder, zone_name=zone_name, zone=zone)
        for reminder in reminders
    ]
    return {
        "owner_account_id": owner_account_id,
        "display_timezone": zone_name,
        "count": len(reminder_facts),
        "reminders": reminder_facts,
        "display_lines": [
            _reminder_display_line(index, reminder)
            for index, reminder in enumerate(reminder_facts, start=1)
        ],
    }


def _reminder_fact(reminder: Any, *, zone_name: str, zone: ZoneInfo) -> dict[str, Any]:
    return {
        "reminder_id": reminder.id,
        "content": reminder.content,
        "kind": reminder.kind,
        "next_fire_at": _iso_or_none(reminder.next_fire_at),
        "display_timezone": zone_name,
        "display_time_label": _display_time_label(
            reminder.next_fire_at, zone_name, zone
        ),
        "captured_timezone": reminder.captured_timezone,
        "duration_minutes": reminder.duration_minutes,
        "lifecycle": reminder.lifecycle,
        "hidden_from_calendar": reminder.hidden_from_calendar,
        "shared_reminder_id": reminder.shared_reminder_id,
        "created_at": _iso_or_none(reminder.created_at),
        "updated_at": _iso_or_none(reminder.updated_at),
    }


def _iso_or_none(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _display_zone(timezone_name: str) -> tuple[str, ZoneInfo]:
    try:
        return timezone_name, ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return "UTC", ZoneInfo("UTC")


def _display_time_label(value: Any, timezone_name: str, zone: ZoneInfo) -> str | None:
    if not isinstance(value, datetime):
        return None
    return f"{value.astimezone(zone):%Y-%m-%d %H:%M} {timezone_name}"


def _reminder_display_line(index: int, reminder: Mapping[str, Any]) -> str:
    time_label = reminder.get("display_time_label") or "unscheduled"
    return f"{index}. {reminder.get('content', '')} ({time_label})"


def _reminder_list_visible_summary(facts: Mapping[str, Any]) -> str:
    count = facts.get("count", 0)
    lines = [f"Active reminder count: {count}."]
    display_lines = facts.get("display_lines")
    if isinstance(display_lines, list):
        lines.extend(str(line) for line in display_lines)
    return "\n".join(lines)


def _friend_link_facts(link: Any) -> dict[str, Any]:
    return {
        "friend_link_id": link.id,
        "owner_account_id": link.owner_account_id,
        "lifecycle": link.lifecycle,
        "public_token": link.public_token,
        "link_code": link.link_code,
        "public_link_url": link.qr_payload,
        "qr_payload": link.qr_payload,
    }


def _availability_facts(result: Any) -> list[dict[str, Any]]:
    items = result if isinstance(result, list) else [result]
    return [
        {
            "friend_account_id": item.friend_account_id,
            "friend_display_name": item.friend_display_name or item.friend_account_id,
            "windows": [window.to_public_dict() for window in item.windows],
        }
        for item in items
    ]


def _settings_view_facts(view: SettingsView) -> dict[str, Any]:
    settings = view.agent_settings
    profile = view.user_profile
    agent_settings = {
        "assistant_name": settings.assistant_name,
        "user_address_name": settings.user_address_name,
        "persona": settings.persona,
        "background": settings.background,
        "speaking_style": settings.speaking_style,
        "extra_rules": settings.extra_rules,
        "proactive_enabled": settings.proactive_enabled,
        "memory_enabled": settings.memory_enabled,
    }
    user_profile = {
        "real_name": profile.real_name,
        "nickname": profile.nickname,
        "description": profile.description,
        "relationship_description": profile.relationship_description,
    }
    return {
        "account_id": view.account_id,
        "default_timezone": view.default_timezone,
        **agent_settings,
        "agent_settings": agent_settings,
        "user_profile": user_profile,
    }


def _account_default_timezone(
    identity_access_service: IdentityAccessService, account_id: str
) -> str:
    account = identity_access_service.repository.get_account(account_id)
    return account.default_timezone if account is not None else "UTC"


def _settings_update_fields(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "default_timezone",
        "assistant_name",
        "user_address_name",
        "persona",
        "background",
        "speaking_style",
        "extra_rules",
        "proactive_enabled",
        "memory_enabled",
    )
    return {field: command[field] for field in fields if field in command}


def _profile_update_fields(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "real_name",
        "nickname",
        "description",
        "relationship_description",
    )
    return {field: command[field] for field in fields if field in command}


def _first_reason(items: list[Any]) -> str | None:
    for item in items:
        if item.reason is not None:
            return item.reason
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list | tuple):
        return [item for item in value if isinstance(item, str) and item]
    if isinstance(value, str) and value:
        return [value]
    return []


def _traceparent_from_trigger(trigger: Any) -> str:
    raw = None
    payload = getattr(trigger, "payload", None)
    if isinstance(payload, Mapping):
        raw = payload.get("_traceparent") or payload.get("traceparent")
    try:
        return ensure_traceparent(raw if isinstance(raw, str) else None)
    except ValueError:
        return ensure_traceparent(None)


def _is_context_token_window_failure(outcome: Any) -> bool:
    error_code = getattr(outcome, "error_code", None)
    if not isinstance(error_code, str) or not error_code:
        return False
    normalized = error_code.lower()
    return (
        normalized == "context_token_required"
        or "ret_-2" in normalized
        or "invalid_context_token" in normalized
    )
