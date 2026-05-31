from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from coke.config import ConfigurationError, Settings
from coke.domains.calendar_import.google import GoogleCalendarClientPort
from coke.domains.calendar_import.google import GoogleCalendarClientAdapter
from coke.domains.calendar_import.models import CalendarSourceEvent
from coke.domains.calendar_import.service import (
    CalendarImportService,
    InMemoryCalendarImportRepository,
    PostgresCalendarImportRepository,
)
from coke.domains.channel_reachability.repository import (
    InMemoryChannelReachabilityRepository,
    PostgresChannelReachabilityRepository,
)
from coke.domains.channel_reachability.models import ChannelReachabilityError
from coke.domains.channel_reachability.service import ChannelReachabilityService
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
    PostgresConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
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
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
    PostgresSocialSchedulingRepository,
)
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.domains.social_scheduling.models import SocialSchedulingError
from coke.infra.postgres import create_engine, create_session_factory
from coke.infra.redis import (
    RedisLockAdapter,
    RedisReplyPubSub,
    RedisWorkStream,
    create_redis_client,
)
from coke.llm.agno_interaction_agent import AgnoInteractionAgent
from coke.llm.config import SiliconFlowLLMConfig
from coke.llm.reminder_detector import SiliconFlowReminderDetector
from coke.llm.semantic_interpreter import SiliconFlowSemanticInterpreter
from coke.providers.base import provider_registry
from coke.providers.linq import LinqAdapter
from coke.providers.wechat_ecloud import WeChatECloudAdapter
from coke.providers.wechat_personal import WeChatPersonalAdapter
from coke.providers.whatsapp_evolution import WhatsAppEvolutionAdapter
from coke.turn.agent import AgentToolPorts, DomainExecutionResult, ToolExecutionResult
from coke.turn.agent import AgentRequest, AgentResult
from coke.turn.focus import FocusResolver, MessageSubject
from coke.turn.locks import ConversationLockManager, RedisLockPort
from coke.turn.memory import MemoryPort
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import DeliveryRequest, OutboundDeliveryPort, TurnRunner
from coke.turn.semantic_interpreter import SemanticDecision
from coke.turn.semantic_interpreter import SemanticInterpreter


@dataclass(frozen=True, slots=True)
class CokeRepositories:
    identity_access: Any
    channel_reachability: Any
    conversation_runtime: Any
    reminder: Any
    social_scheduling: Any
    calendar_import: Any
    settings: Any | None = None


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
    provider_adapters: Mapping[str, Any] | None = None
    engine: Any | None = None
    session_factory: Any | None = None
    session: Any | None = None
    redis_client: Any | None = None
    work_stream: Any | None = None
    reply_pubsub: Any | None = None


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


class FakeSemanticInterpreter:
    def interpret(self, request) -> SemanticDecision:
        return SemanticDecision(
            reply_necessity="reply_needed",
            intent_family="chit_chat",
            language_hint=None,
        )


class FakeInteractionAgent:
    def invoke(self, request: AgentRequest) -> AgentResult:
        return AgentResult.completed(
            {
                "type": "reply",
                "segments": ["COKE_LLM_FAKE synthetic reply"],
            }
        )

    def complete_async(self, task_id: str) -> AgentResult:
        return AgentResult.completed(
            {
                "type": "reply",
                "segments": ["COKE_LLM_FAKE synthetic async reply"],
            }
        )


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
            if context_token is None and self.conversation_runtime is not None:
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
            )
        except ChannelReachabilityError:
            raise


class OutputLifecycleDeliveryCallbacks:
    def __init__(
        self,
        *,
        reminder_service: ReminderService,
        social_scheduling_service: SocialSchedulingService,
    ) -> None:
        self.reminder_service = reminder_service
        self.social_scheduling_service = social_scheduling_service

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

        if operation == "list_reminders":
            facts = _reminder_list_facts(
                owner,
                self.reminder_service.repository.list_active_reminders(owner),
            )
            return ToolExecutionResult(
                ok=True,
                facts=facts,
                domain_result=DomainExecutionResult(
                    domain="reminder",
                    intent="list reminders",
                    action="list_reminders",
                    effect="listed",
                    intent_fulfilled=True,
                    visible_summary=json.dumps(facts, ensure_ascii=False),
                    reply_contract="render_fact",
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
            result = self.reminder_service.complete_reminder(
                owner_account_id=owner,
                reminder_id=_required_str(command, "reminder_id"),
                commit_guard=_guard_commit_guard(guard),
            )
            return _single_item_tool_result(result)

        if operation == "delete_reminder":
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
                    duration_minutes=int(command.get("duration_minutes") or 15),
                    context=_optional_context(command.get("context")),
                    commit_guard=_guard_commit_guard(guard),
                )
                return ToolExecutionResult(
                    ok=result.status in {"created", "duplicate"},
                    facts={
                        "status": result.status,
                        "shared_reminder_id": (
                            result.shared_reminder.id
                            if result.shared_reminder
                            else None
                        ),
                        "breakdown": result.breakdown,
                        "follow_up_facts": result.follow_up_facts,
                    },
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
                        context=_optional_context(command.get("context")),
                        commit_guard=_guard_commit_guard(guard),
                    )
                )
                return ToolExecutionResult(
                    ok=result.status in {"created", "duplicate"},
                    facts={
                        "status": result.status,
                        "shared_reminder_id": (
                            result.shared_reminder.id
                            if result.shared_reminder
                            else None
                        ),
                        "breakdown": result.breakdown,
                        "follow_up_facts": result.follow_up_facts,
                    },
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


def compose_coke_runtime(
    *,
    semantic_interpreter: SemanticInterpreter,
    interaction_agent: Any,
    redis_client: RedisLockPort,
    outbound_delivery: OutboundDeliveryPort,
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
        )
    elif repositories.settings is None:
        repositories = CokeRepositories(
            identity_access=repositories.identity_access,
            channel_reachability=repositories.channel_reachability,
            conversation_runtime=repositories.conversation_runtime,
            reminder=repositories.reminder,
            social_scheduling=repositories.social_scheduling,
            calendar_import=repositories.calendar_import,
            settings=InMemorySettingsRepository(
                accounts=getattr(repositories.identity_access, "accounts", None),
            ),
        )

    identity_access_service = IdentityAccessService(
        repository=repositories.identity_access,
        now=now,
        id_factory=id_factory,
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
    turn_runner = TurnRunner(
        conversation_runtime=conversation_runtime_service,
        lock_manager=lock_manager,
        pre_llm_gate=pre_llm_gate,
        semantic_interpreter=semantic_interpreter,
        memory_port=memory_port,
        interaction_agent=interaction_agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=outbound_delivery,
        tool_ports=tool_ports,
        focus_resolver=FocusResolver(
            ReminderLifecycleFocusRepository(
                repositories.conversation_runtime,
                repositories.reminder,
            )
        ),
        delivery_lifecycle=OutputLifecycleDeliveryCallbacks(
            reminder_service=reminder_service,
            social_scheduling_service=social_scheduling_service,
        ),
        now=now,
        account_timezone=lambda account_id: _account_default_timezone(
            identity_access_service, account_id
        ),
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
    repositories = CokeRepositories(
        identity_access=PostgresIdentityAccessRepository(session),
        channel_reachability=PostgresChannelReachabilityRepository(session),
        conversation_runtime=PostgresConversationRuntimeRepository(session),
        reminder=PostgresReminderRepository(session),
        social_scheduling=PostgresSocialSchedulingRepository(session),
        calendar_import=PostgresCalendarImportRepository(session),
        settings=PostgresSettingsRepository(session),
    )
    semantic_interpreter, interaction_agent, reminder_detector = _llm_from_settings(
        settings
    )
    google_calendar_client = GoogleCalendarClientAdapter(
        calendar_id=settings.google_calendar_id,
        now=now,
    )
    runtime = compose_coke_runtime(
        semantic_interpreter=semantic_interpreter,
        interaction_agent=interaction_agent,
        redis_client=redis_lock,
        outbound_delivery=_DeferredOutboundDelivery(),
        reminder_detector=reminder_detector,
        memory_port=None,
        google_calendar_client=google_calendar_client,
        provider_adapters=provider_adapters,
        repositories=repositories,
        now=now,
        id_factory=id_factory,
        lock_ttl_ms=settings.lock_ttl_ms,
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
        provider_adapters=provider_adapters,
        engine=engine,
        session_factory=session_factory,
        session=session,
        redis_client=redis_client,
        work_stream=work_stream,
        reply_pubsub=reply_pubsub,
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
        return FakeSemanticInterpreter(), FakeInteractionAgent(), FakeReminderDetector()
    if not settings.siliconflow_api_key:
        raise ConfigurationError("SiliconFlow_API_KEY is required for LLM composition")
    llm_config = SiliconFlowLLMConfig(
        api_key=settings.siliconflow_api_key,
        base_url=settings.siliconflow_base_url,
        interaction_model=settings.interaction_model,
        interpreter_model=settings.interpreter_model,
        detector_model=settings.detector_model,
        agno_database_url=settings.agno_database_url,
        agno_create_schema=settings.agno_create_schema,
    )
    return (
        SiliconFlowSemanticInterpreter.from_model(
            llm_config.create_interpreter_model()
        ),
        AgnoInteractionAgent.from_config(llm_config),
        SiliconFlowReminderDetector.from_model(llm_config.create_detector_model()),
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


def _reminder_list_facts(owner_account_id: str, reminders: list[Any]) -> dict[str, Any]:
    reminder_facts = [_reminder_fact(reminder) for reminder in reminders]
    return {
        "owner_account_id": owner_account_id,
        "count": len(reminder_facts),
        "reminders": reminder_facts,
    }


def _reminder_fact(reminder: Any) -> dict[str, Any]:
    return {
        "reminder_id": reminder.id,
        "content": reminder.content,
        "kind": reminder.kind,
        "next_fire_at": _iso_or_none(reminder.next_fire_at),
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
