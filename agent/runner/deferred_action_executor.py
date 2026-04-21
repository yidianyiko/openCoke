from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from agent.runner import deferred_action_policy as policy
from agent.runner.context import context_prepare
from dao.conversation_dao import ConversationDAO
from dao.lock import MongoDBLockManager
from dao.user_dao import UserDAO


def _load_handle_message() -> Callable[..., Any]:
    from agent.runner.agent_handler import handle_message

    return handle_message


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
        self.handle_message_fn = handle_message_fn or _load_handle_message()
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
        started_at = self.now_provider()
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
            _, _, _, is_content_blocked = await self.handle_message_fn(
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

            finished_at = self.now_provider()
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
            finished_at = self.now_provider()
            attempt_count = int(occurrence.get("attempt_count", 1))
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
        character = self.user_dao.get_user_by_id(action["character_id"])
        return self.context_builder(user, character, conversation)

    def _build_input_message(self, action: dict[str, Any]) -> str:
        prompt = (action.get("payload") or {}).get("prompt") or action.get("title") or ""
        if action.get("kind") == "proactive_followup":
            return f"[系统延迟跟进触发] {prompt}"
        return f"[系统提醒触发] {prompt}"

    def _build_trigger_key(self, action_id: str, scheduled_for: datetime) -> str:
        return f"action:{action_id}:{scheduled_for.isoformat()}"

    async def _release_conversation_lock(self, conversation_id: str, lock_id: str) -> None:
        release = getattr(self.lock_manager, "release_lock_safe_async", None)
        if callable(release):
            await release("conversation", conversation_id, lock_id)
            return
        self.lock_manager.release_lock("conversation", conversation_id, lock_id)
