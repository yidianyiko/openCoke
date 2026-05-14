from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from agent.agno_agent.adapters import (
    DeferredActionFireResult,
    map_agent_result_to_deferred_status,
)
from agent.agno_agent.runtime.result import AgentRunResult, with_output_references
from agent.runner import deferred_action_policy as policy
from agent.runner.context import context_prepare
from agent.runner.identity import is_synthetic_coke_account_id
from agent.util.message_util import send_message_via_context
from dao.conversation_dao import ConversationDAO
from dao.lock import MongoDBLockManager
from dao.user_dao import UserDAO


def _load_handle_message() -> Callable[..., Any]:
    from agent.runner.agent_handler import handle_message

    return handle_message


def _normalize_mongo_datetime(value: datetime) -> datetime:
    normalized = value.astimezone(UTC)
    return normalized.replace(microsecond=(normalized.microsecond // 1000) * 1000)


class DeferredActionExecutor:
    def __init__(
        self,
        action_dao: Any,
        occurrence_dao: Any,
        scheduler: Any,
        lock_manager: Any | None = None,
        conversation_dao: Any | None = None,
        user_dao: Any | None = None,
        handle_message_fn: Callable[..., Any] | None = None,
        runtime_fire_handler: Callable[..., Any] | None = None,
        output_writer: Callable[..., Any] | None = None,
        context_builder: Callable[..., dict] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        conversation_lock_timeout: int = 120,
        action_lease_timeout: int = 180,
    ) -> None:
        self.action_dao = action_dao
        self.occurrence_dao = occurrence_dao
        self.scheduler = scheduler
        self.lock_manager = lock_manager or MongoDBLockManager()
        self.conversation_dao = conversation_dao or ConversationDAO()
        self.user_dao = user_dao or UserDAO()
        self.runtime_fire_handler = runtime_fire_handler
        self.handle_message_fn = handle_message_fn
        if self.handle_message_fn is None and self.runtime_fire_handler is None:
            self.handle_message_fn = _load_handle_message()
        self.output_writer = output_writer or send_message_via_context
        self.context_builder = context_builder or context_prepare
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.conversation_lock_timeout = conversation_lock_timeout
        self.action_lease_timeout = action_lease_timeout

    async def execute_due_action(
        self,
        action_id: str,
        scheduled_for: datetime,
        revision: int,
    ) -> str:
        action = self.action_dao.get_action(action_id)
        if not action:
            return "missing"
        if (
            action.get("lifecycle_state") != "active"
            or action.get("revision") != revision
            or action.get("next_run_at") != scheduled_for
        ):
            return "stale"

        lock_id = await self.lock_manager.acquire_lock_async(
            "conversation",
            action["conversation_id"],
            timeout=self.conversation_lock_timeout,
            max_wait=1,
        )
        if not lock_id:
            return "lock_unavailable"

        lease_token = str(uuid.uuid4())
        started_at = _normalize_mongo_datetime(self.now_provider())
        lease_until = started_at + timedelta(seconds=self.action_lease_timeout)
        claimed = self.action_dao.claim_action_lease(
            action_id=action_id,
            revision=revision,
            scheduled_for=scheduled_for,
            token=lease_token,
            leased_at=started_at,
            lease_until=lease_until,
        )
        if not claimed:
            await self._release_conversation_lock(action["conversation_id"], lock_id)
            return "stale"

        trigger_key = self._build_trigger_key(action_id, scheduled_for)

        occurrence: dict[str, Any] = {}
        try:
            occurrence = self.occurrence_dao.claim_or_get_occurrence(
                action_id=action_id,
                trigger_key=trigger_key,
                scheduled_for=scheduled_for,
                started_at=started_at,
            )
            if occurrence.get("status") == "failed":
                self.occurrence_dao.increment_attempt_count(trigger_key, started_at)
                occurrence["attempt_count"] = occurrence.get("attempt_count", 1) + 1
            elif occurrence.get("status") == "claimed" and occurrence.get(
                "last_started_at"
            ) != started_at:
                self.action_dao.release_action_lease(action_id, lease_token)
                return "duplicate"
            elif occurrence.get("status") in {"succeeded", "skipped"}:
                self.action_dao.release_action_lease(action_id, lease_token)
                return "duplicate"

            context = self._build_context(action)
            input_message = self._build_input_message(action)
            metadata = {
                "action_id": action_id,
                "kind": action["kind"],
                "scheduled_for": scheduled_for.isoformat(),
                "title": action.get("title"),
                "prompt": (action.get("payload") or {}).get("prompt"),
                "proactive_times": (action.get("payload") or {})
                .get("metadata", {})
                .get("proactive_times", 0),
            }
            if self.runtime_fire_handler is not None:
                context["message_source"] = "deferred_action"
                runtime_fire_result = await self._execute_typed_runtime_fire(
                    action=action,
                    action_id=action_id,
                    scheduled_for=scheduled_for,
                    revision=revision,
                    context=context,
                    input_message=input_message,
                    metadata=metadata,
                )
                return await self._apply_runtime_fire_result(
                    runtime_fire_result=runtime_fire_result,
                    action=action,
                    action_id=action_id,
                    revision=revision,
                    scheduled_for=scheduled_for,
                    trigger_key=trigger_key,
                    lease_token=lease_token,
                    occurrence=occurrence,
                )

            handle_message_fn = self.handle_message_fn or _load_handle_message()
            _, _, _, is_content_blocked = await handle_message_fn(
                context=context,
                input_message_str=input_message,
                message_source="deferred_action",
                metadata=metadata,
                check_new_message=False,
                worker_tag="[DEFERRED_ACTION]",
                lock_id=lock_id,
                conversation_id=action["conversation_id"],
            )
            if is_content_blocked:
                raise RuntimeError("content blocked")

            finished_at = _normalize_mongo_datetime(self.now_provider())
            self.occurrence_dao.mark_occurrence_succeeded(trigger_key, finished_at)
            self._handle_success(
                action=action,
                action_id=action_id,
                revision=revision,
                scheduled_for=scheduled_for,
                finished_at=finished_at,
            )
            return "succeeded"
        except Exception as exc:
            finished_at = _normalize_mongo_datetime(self.now_provider())
            attempt_count = int((occurrence or {}).get("attempt_count", 1))
            self.occurrence_dao.mark_occurrence_failed(
                trigger_key,
                str(exc),
                finished_at,
            )
            self._handle_failure(
                action=action,
                action_id=action_id,
                revision=revision,
                scheduled_for=scheduled_for,
                finished_at=finished_at,
                attempt_count=attempt_count,
                error=str(exc),
            )
            return "failed"
        finally:
            await self._release_conversation_lock(action["conversation_id"], lock_id)

    async def _execute_typed_runtime_fire(
        self,
        *,
        action: dict[str, Any],
        action_id: str,
        scheduled_for: datetime,
        revision: int,
        context: dict,
        input_message: str,
        metadata: dict[str, Any],
    ) -> DeferredActionFireResult:
        from agent.agno_agent.runtime.inputs import AgentInput, DeferredActionPayload

        payload = action.get("payload") or {}
        agent_input = AgentInput(
            input_type="deferred_action.fire",
            conversation_id=action["conversation_id"],
            text=input_message,
            payload=DeferredActionPayload(
                action_id=action_id,
                kind=action["kind"],
                scheduled_for=scheduled_for,
                revision=revision,
                prompt=str(payload.get("prompt") or action.get("title") or ""),
                metadata=metadata,
            ),
            occurred_at=scheduled_for,
            metadata=metadata,
        )
        runtime_result = self.runtime_fire_handler(
            agent_input=agent_input,
            context=context,
            message_source="deferred_action",
            metadata=metadata,
        )
        if inspect.isawaitable(runtime_result):
            runtime_result = await runtime_result
        if isinstance(runtime_result, DeferredActionFireResult):
            return runtime_result
        if not isinstance(runtime_result, AgentRunResult):
            return DeferredActionFireResult(
                status="failed",
                retryable=True,
                error_code="invalid_runtime_result",
                error_message="runtime fire handler returned invalid result",
            )

        output_references = []
        for visible_message in runtime_result.visible_messages:
            output = self.output_writer(
                context,
                message=visible_message.content,
                message_type=visible_message.message_type,
                metadata={
                    "deferred_action_id": action_id,
                    "scheduled_for": scheduled_for.isoformat(),
                    **dict(visible_message.metadata),
                },
            )
            if inspect.isawaitable(output):
                output = await output
            output_reference = self._output_reference(output)
            if output_reference:
                output_references.append(output_reference)

        if (
            runtime_result.output_disposition.status == "ok"
            and not output_references
            and not runtime_result.output_disposition.output_references
        ):
            return DeferredActionFireResult(status="no_output", retryable=True)

        updated_result = with_output_references(
            runtime_result,
            tuple(runtime_result.output_disposition.output_references)
            + tuple(output_references),
        )
        return map_agent_result_to_deferred_status(updated_result)

    async def _apply_runtime_fire_result(
        self,
        *,
        runtime_fire_result: DeferredActionFireResult,
        action: dict[str, Any],
        action_id: str,
        revision: int,
        scheduled_for: datetime,
        trigger_key: str,
        lease_token: str,
        occurrence: dict[str, Any],
    ) -> str:
        finished_at = _normalize_mongo_datetime(self.now_provider())
        attempt_count = int(occurrence.get("attempt_count", 1))

        if runtime_fire_result.status == "succeeded":
            if not runtime_fire_result.output_references:
                runtime_fire_result = DeferredActionFireResult(
                    status="no_output",
                    retryable=True,
                )
            else:
                self.occurrence_dao.mark_occurrence_succeeded(
                    trigger_key, finished_at
                )
                self._handle_success(
                    action=action,
                    action_id=action_id,
                    revision=revision,
                    scheduled_for=scheduled_for,
                    finished_at=finished_at,
                )
                return "succeeded"

        if runtime_fire_result.status == "failed":
            error = (
                runtime_fire_result.error_message
                or runtime_fire_result.error_code
                or "runtime fire failed"
            )
            self.occurrence_dao.mark_occurrence_failed(
                trigger_key,
                error,
                finished_at,
            )
            self._handle_failure(
                action=action,
                action_id=action_id,
                revision=revision,
                scheduled_for=scheduled_for,
                finished_at=finished_at,
                attempt_count=attempt_count,
                error=error,
            )
            return "failed"

        if runtime_fire_result.status == "no_output":
            error = "runtime produced no output"
            self.occurrence_dao.mark_occurrence_failed(
                trigger_key,
                error,
                finished_at,
            )
            self._handle_failure(
                action=action,
                action_id=action_id,
                revision=revision,
                scheduled_for=scheduled_for,
                finished_at=finished_at,
                attempt_count=attempt_count,
                error=error,
            )
            return "no_output"

        if runtime_fire_result.status in {"rollback", "skipped"}:
            release = getattr(self.action_dao, "release_action_lease", None)
            if callable(release):
                release(action_id, lease_token)
            return runtime_fire_result.status

        return "failed"

    def _output_reference(self, output: Any) -> str | None:
        if isinstance(output, dict):
            value = output.get("_id") or output.get("id")
            return str(value) if value is not None else None
        value = getattr(output, "id", None)
        return str(value) if value is not None else None

    def _handle_success(
        self,
        *,
        action: dict[str, Any],
        action_id: str,
        revision: int,
        scheduled_for: datetime,
        finished_at: datetime,
    ) -> None:
        next_run_at = policy.compute_next_run_after_success(
            action,
            scheduled_for=scheduled_for,
            now=finished_at,
        )
        updates = {
            "last_run_at": finished_at,
            "run_count": action.get("run_count", 0) + 1,
            "last_error": None,
            "lease.token": None,
            "lease.leased_at": None,
            "lease.lease_expires_at": None,
        }
        if next_run_at is None:
            updates["lifecycle_state"] = "completed"
            updates["next_run_at"] = None
            self.action_dao.update_action(
                action_id,
                updates=updates,
                expected_revision=revision,
                now=finished_at,
            )
            self.scheduler.remove_action(action_id)
            return

        updates["next_run_at"] = next_run_at
        self.action_dao.update_action(
            action_id,
            updates=updates,
            expected_revision=revision,
            now=finished_at,
        )
        self.scheduler.reschedule_action(
            {
                **action,
                "revision": revision + 1,
                "run_count": updates["run_count"],
                "last_run_at": finished_at,
                "last_error": None,
                "next_run_at": next_run_at,
            }
        )

    def _handle_failure(
        self,
        *,
        action: dict[str, Any],
        action_id: str,
        revision: int,
        scheduled_for: datetime,
        finished_at: datetime,
        attempt_count: int,
        error: str,
    ) -> None:
        updates = {
            "last_error": error,
            "lease.token": None,
            "lease.leased_at": None,
            "lease.lease_expires_at": None,
        }
        if policy.should_terminally_fail_occurrence(action, attempt_count):
            updates["lifecycle_state"] = "failed"
            updates["next_run_at"] = None
            self.action_dao.update_action(
                action_id,
                updates=updates,
                expected_revision=revision,
                now=finished_at,
            )
            self.scheduler.remove_action(action_id)
            return

        retry_at = policy.compute_retry_at(action, attempt_count, finished_at)
        updates["next_run_at"] = retry_at
        self.action_dao.update_action(
            action_id,
            updates=updates,
            expected_revision=revision,
            now=finished_at,
        )
        self.scheduler.reschedule_action(
            {
                **action,
                "revision": revision + 1,
                "next_run_at": retry_at,
                "last_error": error,
            }
        )

    def _build_context(self, action: dict[str, Any]) -> dict:
        conversation = self.conversation_dao.get_conversation_by_id(action["conversation_id"])
        user = self.user_dao.get_user_by_id(action["user_id"])
        if user is None:
            user = self._recover_synthetic_business_user(
                action["user_id"],
                conversation,
            )
        character = self.user_dao.get_user_by_id(action["character_id"])
        return self.context_builder(user, character, conversation)

    def _recover_synthetic_business_user(
        self,
        user_id: str,
        conversation: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not is_synthetic_coke_account_id(user_id):
            return None

        talkers = (conversation or {}).get("talkers") or []
        for talker in talkers:
            db_user_id = str(talker.get("db_user_id") or "").strip()
            if db_user_id != user_id:
                continue
            nickname = str(talker.get("nickname") or "").strip()
            if not nickname:
                nickname = f"user-{user_id[-6:]}"
            return {
                "id": user_id,
                "_id": user_id,
                "nickname": nickname,
                "is_coke_account": True,
            }
        return None

    def _build_input_message(self, action: dict[str, Any]) -> str:
        prompt = (action.get("payload") or {}).get("prompt") or action.get("title") or ""
        return f"[系统提醒触发] {prompt}"

    def _build_trigger_key(self, action_id: str, scheduled_for: datetime) -> str:
        return f"action:{action_id}:{scheduled_for.isoformat()}"

    async def _release_conversation_lock(self, conversation_id: str, lock_id: str) -> None:
        release = getattr(self.lock_manager, "release_lock_safe_async", None)
        if callable(release):
            await release("conversation", conversation_id, lock_id)
            return
        self.lock_manager.release_lock("conversation", conversation_id, lock_id)
