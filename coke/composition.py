from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from coke.domains.calendar_import.google import GoogleCalendarClientPort
from coke.domains.calendar_import.models import CalendarSourceEvent
from coke.domains.calendar_import.service import (
    CalendarImportService,
    InMemoryCalendarImportRepository,
)
from coke.domains.channel_reachability.repository import (
    InMemoryChannelReachabilityRepository,
)
from coke.domains.channel_reachability.service import ChannelReachabilityService
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.domains.identity_access.models import IdentityAccessError
from coke.domains.identity_access.repository import InMemoryIdentityAccessRepository
from coke.domains.identity_access.service import IdentityAccessService
from coke.domains.reminder.models import ReminderBatchItem
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.domains.social_scheduling.availability import BusyInterval
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
)
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.turn.agent import AgentToolPorts, ToolExecutionResult
from coke.turn.locks import ConversationLockManager, RedisLockPort
from coke.turn.memory import MemoryPort
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import OutboundDeliveryPort, TurnRunner
from coke.turn.semantic_interpreter import SemanticInterpreter


@dataclass(frozen=True, slots=True)
class CokeRepositories:
    identity_access: Any
    channel_reachability: Any
    conversation_runtime: Any
    reminder: Any
    social_scheduling: Any
    calendar_import: Any


@dataclass(frozen=True, slots=True)
class CokeToolAdapters:
    reminder_tool: "ReminderToolAdapter"
    social_scheduling_tool: "SocialSchedulingToolAdapter"
    calendar_import_tool: "CalendarImportToolAdapter"
    identity_access_tool: "IdentityAccessToolAdapter"


@dataclass(frozen=True, slots=True)
class CokeRuntime:
    repositories: CokeRepositories
    identity_access_service: IdentityAccessService
    channel_reachability_service: ChannelReachabilityService
    conversation_runtime_service: ConversationRuntimeService
    reminder_service: ReminderService
    social_scheduling_service: SocialSchedulingService
    calendar_import_service: CalendarImportService
    adapters: CokeToolAdapters
    tool_ports: AgentToolPorts
    pre_llm_gate: PreLLMGateService
    lock_manager: ConversationLockManager
    turn_runner: TurnRunner


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


class IdentityReachabilityAdapter:
    def __init__(self, identity_access: IdentityAccessService) -> None:
        self.identity_access = identity_access

    def has_usable_channel(self, account_id: str) -> bool:
        return self.identity_access.repository.has_usable_channel(account_id)


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
            interval_start = reminder.next_fire_at
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


class IdentityAccessPreLLMGatePort:
    def __init__(self, identity_access: IdentityAccessService) -> None:
        self.identity_access = identity_access

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
        except IdentityAccessError as error:
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
        return GateDecision.allowed(
            trust_facts=trust_facts,
            activation_guidance_required=activation.first_guidance_sent_at is None,
        )


class ReminderToolAdapter:
    def __init__(self, reminder_service: ReminderService) -> None:
        self.reminder_service = reminder_service

    def execute(self, command: Mapping[str, Any], guard: Any) -> ToolExecutionResult:
        _guard_state_change(guard)
        operation = _required_str(command, "operation")
        owner = _required_str(command, "owner_account_id", default_key="account_id")

        if operation in {"create", "detect_and_create"}:
            result = self.reminder_service.execute_batch(
                owner_account_id=owner,
                items=[_reminder_batch_item(command)],
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
                items=[_reminder_batch_item(item) for item in items],
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
            )
            return _single_item_tool_result(result)

        if operation == "clear_trigger_time":
            result = self.reminder_service.clear_trigger_time(
                owner_account_id=owner,
                reminder_id=_required_str(command, "reminder_id"),
            )
            return _single_item_tool_result(result)

        if operation == "complete_reminder":
            result = self.reminder_service.complete_reminder(
                owner_account_id=owner,
                reminder_id=_required_str(command, "reminder_id"),
            )
            return _single_item_tool_result(result)

        if operation == "delete_reminder":
            result = self.reminder_service.delete_reminder(
                owner_account_id=owner,
                reminder_id=_required_str(command, "reminder_id"),
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
        if operation == "list_friends":
            entries = self.social_scheduling_service.list_friends(
                _required_str(command, "account_id")
            )
            return ToolExecutionResult(
                ok=True,
                facts={"friends": [asdict(entry) for entry in entries]},
            )

        _guard_state_change(guard)
        if operation == "create_shared_reminder":
            result = self.social_scheduling_service.create_shared_reminder(
                creator_account_id=_required_str(
                    command, "creator_account_id", default_key="account_id"
                ),
                receiver_account_ids=list(command.get("receiver_account_ids") or ()),
                title=command.get("title"),
                local_trigger_at=_optional_datetime(command.get("local_trigger_at")),
                captured_timezone=str(command.get("captured_timezone") or "UTC"),
                duration_minutes=int(command.get("duration_minutes") or 15),
                context=dict(command.get("context") or {}),
            )
            return ToolExecutionResult(
                ok=result.status in {"created", "duplicate"},
                facts={
                    "status": result.status,
                    "shared_reminder_id": (
                        result.shared_reminder.id if result.shared_reminder else None
                    ),
                    "breakdown": result.breakdown,
                    "follow_up_facts": result.follow_up_facts,
                },
                reason_code=(
                    None if result.status in {"created", "duplicate"} else result.status
                ),
            )

        if operation == "cancel_shared_reminder":
            result = self.social_scheduling_service.cancel_shared_reminder(
                account_id=_required_str(command, "account_id"),
                shared_reminder_id=_required_str(command, "shared_reminder_id"),
            )
            return ToolExecutionResult(
                ok=True,
                facts={
                    "status": result.status,
                    "shared_reminder_id": result.shared_reminder.id,
                },
            )

        if operation == "establish_friendship_from_token":
            result = self.social_scheduling_service.establish_friendship_from_token(
                joiner_account_id=_required_str(
                    command, "joiner_account_id", default_key="account_id"
                ),
                public_token=_required_str(command, "public_token"),
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
            )
            return ToolExecutionResult(ok=True, facts=asdict(friendship))

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


def compose_coke_runtime(
    *,
    semantic_interpreter: SemanticInterpreter,
    interaction_agent: Any,
    redis_client: RedisLockPort,
    outbound_delivery: OutboundDeliveryPort,
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
    id_factory = id_factory or (
        lambda prefix: f"{prefix}_{datetime.now(UTC).timestamp()}"
    )

    repositories = repositories or CokeRepositories(
        identity_access=InMemoryIdentityAccessRepository(now=now),
        channel_reachability=InMemoryChannelReachabilityRepository(),
        conversation_runtime=InMemoryConversationRuntimeRepository(now=now),
        reminder=InMemoryReminderRepository(),
        social_scheduling=InMemorySocialSchedulingRepository(),
        calendar_import=InMemoryCalendarImportRepository(),
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
    reminder_service = ReminderService(
        repository=repositories.reminder,
        now=now,
        id_factory=id_factory,
    )
    social_scheduling_service = SocialSchedulingService(
        repository=repositories.social_scheduling,
        reachability=IdentityReachabilityAdapter(identity_access_service),
        reminder_availability=ReminderAvailabilityAdapter(repositories.reminder),
        now=now,
        id_factory=id_factory,
    )
    calendar_import_service = CalendarImportService(
        repository=repositories.calendar_import,
        google_client=google_calendar_client or EmptyGoogleCalendarClient(),
        reminder_service=reminder_service,
        now=now,
        id_factory=id_factory,
    )

    adapters = CokeToolAdapters(
        reminder_tool=ReminderToolAdapter(reminder_service),
        social_scheduling_tool=SocialSchedulingToolAdapter(social_scheduling_service),
        calendar_import_tool=CalendarImportToolAdapter(calendar_import_service),
        identity_access_tool=IdentityAccessToolAdapter(identity_access_service),
    )
    tool_ports = AgentToolPorts(
        reminder_tool=adapters.reminder_tool,
        social_scheduling_tool=adapters.social_scheduling_tool,
        calendar_import_tool=adapters.calendar_import_tool,
        identity_access_tool=adapters.identity_access_tool,
    )
    pre_llm_gate = PreLLMGateService(
        IdentityAccessPreLLMGatePort(identity_access_service)
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
    )
    return CokeRuntime(
        repositories=repositories,
        identity_access_service=identity_access_service,
        channel_reachability_service=channel_reachability_service,
        conversation_runtime_service=conversation_runtime_service,
        reminder_service=reminder_service,
        social_scheduling_service=social_scheduling_service,
        calendar_import_service=calendar_import_service,
        adapters=adapters,
        tool_ports=tool_ports,
        pre_llm_gate=pre_llm_gate,
        lock_manager=lock_manager,
        turn_runner=turn_runner,
    )


def _duration_delta(minutes: int):
    from datetime import timedelta

    return timedelta(minutes=minutes)


def _guard_state_change(guard: Any) -> None:
    guard.guard_state_change()


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


def _reminder_batch_item(command: Mapping[str, Any]) -> ReminderBatchItem:
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


def _first_reason(items: list[Any]) -> str | None:
    for item in items:
        if item.reason is not None:
            return item.reason
    return None
