from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any, Callable

from agent.reminder.models import ReminderFiredEvent, ReminderFireResult
from agent.runner.context import context_prepare
from agent.util.message_util import send_message_via_context
from dao.conversation_dao import ConversationDAO
from dao.lock import MongoDBLockManager
from dao.user_dao import UserDAO


class ReminderFireEventHandler:
    def __init__(
        self,
        conversation_dao: Any | None = None,
        user_dao: Any | None = None,
        lock_manager: Any | None = None,
        output_writer: Callable[..., Any] | None = None,
        context_builder: Callable[..., dict] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        conversation_lock_timeout: int = 120,
    ) -> None:
        self.conversation_dao = conversation_dao or ConversationDAO()
        self.user_dao = user_dao or UserDAO()
        self.lock_manager = lock_manager or MongoDBLockManager()
        self.output_writer = output_writer or send_message_via_context
        self.context_builder = context_builder or context_prepare
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.conversation_lock_timeout = conversation_lock_timeout

    async def handle(self, event: ReminderFiredEvent) -> ReminderFireResult:
        conversation_id = event.agent_output_target.conversation_id
        conversation = self.conversation_dao.get_conversation_by_id(conversation_id)
        if not conversation:
            return self._failure(
                event, "ConversationNotFound", "reminder conversation not found"
            )

        if not self._conversation_includes_owner(conversation, event.owner_user_id):
            return self._failure(
                event, "OwnerMismatch", "reminder owner is not in conversation"
            )

        owner = self.user_dao.get_user_by_id(event.owner_user_id)
        if not owner:
            return self._failure(
                event, "OwnerNotFound", "reminder owner user not found"
            )

        character = self.user_dao.get_user_by_id(event.agent_output_target.character_id)
        if not character:
            return self._failure(
                event, "CharacterNotFound", "reminder character not found"
            )

        lock_id = await self._acquire_conversation_lock(conversation_id)
        if not lock_id:
            return self._failure(
                event, "LockUnavailable", "conversation lock unavailable"
            )

        try:
            context = self.context_builder(owner, character, conversation)
            if isinstance(context, dict):
                context.setdefault("message_source", "deferred_action")
            output = self.output_writer(
                context,
                f"提醒：{event.title}",
                message_type="text",
                metadata={
                    "event_type": event.event_type,
                    "event_id": event.event_id,
                    "fire_id": event.fire_id,
                    "reminder_id": event.reminder_id,
                    "scheduled_for": event.scheduled_for.isoformat(),
                    "fire_at": event.fire_at.isoformat(),
                },
            )
            if inspect.isawaitable(output):
                output = await output
            failed_result = self._failed_output_result(event, output)
            if failed_result is not None:
                return failed_result
            return ReminderFireResult(
                ok=True,
                fire_id=event.fire_id,
                output_reference=self._output_reference(output),
                error_code=None,
                error_message=None,
            )
        except Exception as exc:
            return self._failure(event, "OutputFailed", str(exc))
        finally:
            await self._release_conversation_lock(conversation_id, lock_id)

    def _conversation_includes_owner(
        self, conversation: dict[str, Any], owner_user_id: str
    ) -> bool:
        owner_user_id = str(owner_user_id)
        if str(conversation.get("owner_user_id") or "") == owner_user_id:
            return True
        participant_ids = (
            conversation.get("participant_ids")
            or conversation.get("participants")
            or []
        )
        if owner_user_id in {str(value) for value in participant_ids}:
            return True
        for talker in conversation.get("talkers") or []:
            if str(talker.get("db_user_id") or "") == owner_user_id:
                return True
            if str(talker.get("id") or "") == owner_user_id:
                return True
        return False

    async def _acquire_conversation_lock(self, conversation_id: str) -> str | None:
        acquire = getattr(self.lock_manager, "acquire_lock_async", None)
        if callable(acquire):
            return await acquire(
                "conversation",
                conversation_id,
                timeout=self.conversation_lock_timeout,
                max_wait=1,
            )
        return self.lock_manager.acquire_lock(
            "conversation",
            conversation_id,
            timeout=self.conversation_lock_timeout,
            max_wait=1,
        )

    async def _release_conversation_lock(
        self, conversation_id: str, lock_id: str
    ) -> None:
        release = getattr(self.lock_manager, "release_lock_safe_async", None)
        if callable(release):
            await release("conversation", conversation_id, lock_id)
            return
        release_sync = getattr(self.lock_manager, "release_lock_safe", None)
        if callable(release_sync):
            release_sync("conversation", conversation_id, lock_id)
            return
        self.lock_manager.release_lock("conversation", conversation_id, lock_id)

    def _output_reference(self, output: Any) -> str | None:
        if isinstance(output, dict):
            value = output.get("_id") or output.get("id")
            return str(value) if value is not None else None
        value = getattr(output, "id", None)
        return str(value) if value is not None else None

    def _failed_output_result(
        self,
        event: ReminderFiredEvent,
        output: Any,
    ) -> ReminderFireResult | None:
        if output is None:
            return self._failure(
                event,
                "OutputUnavailable",
                "output writer did not return an output message",
            )
        if not isinstance(output, dict) or output.get("status") != "failed":
            return None
        error_message = (
            output.get("last_error")
            or output.get("failure_reason")
            or (output.get("metadata") or {}).get("failure_reason")
            or "output writer returned failed status"
        )
        return ReminderFireResult(
            ok=False,
            fire_id=event.fire_id,
            output_reference=self._output_reference(output),
            error_code="OutputFailed",
            error_message=error_message,
        )

    def _failure(
        self,
        event: ReminderFiredEvent,
        error_code: str,
        error_message: str,
    ) -> ReminderFireResult:
        return ReminderFireResult(
            ok=False,
            fire_id=event.fire_id,
            output_reference=None,
            error_code=error_code,
            error_message=error_message,
        )
