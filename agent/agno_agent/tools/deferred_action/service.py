from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.runner import deferred_action_policy as policy
from agent.runner.deferred_action_scheduler import (
    get_deferred_action_scheduler_instance,
)
from dao.deferred_action_dao import DeferredActionDAO


DEFAULT_RETRY_POLICY = {
    "max_attempts_per_occurrence": 3,
    "base_backoff_seconds": 60,
    "max_backoff_seconds": 900,
}


class DeferredActionService:
    def __init__(
        self,
        action_dao: DeferredActionDAO | None = None,
        scheduler: Any | None = None,
        now_provider=None,
    ) -> None:
        self.action_dao = action_dao or DeferredActionDAO()
        self.scheduler = scheduler or get_deferred_action_scheduler_instance()
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def create_visible_reminder(
        self,
        *,
        user_id: str,
        character_id: str,
        conversation_id: str,
        title: str,
        dtstart: datetime,
        timezone: str,
        rrule: str | None = None,
        schedule_kind: str = "floating_local",
        fixed_timezone: bool = False,
        prompt: str | None = None,
        retry_policy: dict | None = None,
    ) -> dict[str, Any]:
        now = self.now_provider()
        action = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "character_id": character_id,
            "kind": "user_reminder",
            "source": "user_explicit",
            "visibility": "visible",
            "lifecycle_state": "active",
            "revision": 0,
            "title": title,
            "payload": {"prompt": prompt or title, "metadata": {}},
            "timezone": timezone,
            "schedule_kind": schedule_kind,
            "fixed_timezone": fixed_timezone,
            "dtstart": dtstart,
            "rrule": rrule,
            "next_run_at": None,
            "last_run_at": None,
            "run_count": 0,
            "max_runs": None,
            "expires_at": None,
            "retry_policy": retry_policy or dict(DEFAULT_RETRY_POLICY),
            "lease": {
                "token": None,
                "leased_at": None,
                "lease_expires_at": None,
            },
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
        action["next_run_at"] = policy.compute_initial_next_run_at(action, now)
        action_id = self.action_dao.create_action(action)
        action["_id"] = action_id
        if self.scheduler is not None:
            self.scheduler.register_action(action)
        return action

    def list_visible_reminders(self, user_id: str) -> list[dict[str, Any]]:
        reminders = self.action_dao.list_visible_actions(user_id)
        return [
            item
            for item in reminders
            if item.get("kind") == "user_reminder" and item.get("visibility") == "visible"
        ]

    def resolve_visible_reminder_by_keyword(
        self, user_id: str, keyword: str
    ) -> dict[str, Any]:
        keyword = (keyword or "").strip()
        if not keyword:
            raise ValueError("keyword is required")

        reminders = self.list_visible_reminders(user_id)
        exact = [
            item for item in reminders if str(item.get("title", "")).strip() == keyword
        ]
        if exact:
            return exact[0]

        fuzzy = [
            item for item in reminders if keyword in str(item.get("title", "")).strip()
        ]
        if fuzzy:
            return fuzzy[0]

        raise ValueError("visible user reminders only")

    def update_visible_reminder(
        self,
        *,
        action_id: str,
        user_id: str,
        title: str | None = None,
        dtstart: datetime | None = None,
        timezone: str | None = None,
        rrule: str | None = None,
        schedule_kind: str | None = None,
        fixed_timezone: bool | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        action = self._require_visible_reminder(action_id, user_id)
        now = self.now_provider()
        updated = {**action}
        updated.setdefault("schedule_kind", "floating_local")
        updated.setdefault("fixed_timezone", False)
        if title is not None:
            updated["title"] = title
        if dtstart is not None:
            updated["dtstart"] = dtstart
        if timezone is not None:
            updated["timezone"] = timezone
        if rrule is not None:
            updated["rrule"] = rrule
        if schedule_kind is not None:
            updated["schedule_kind"] = schedule_kind
        if fixed_timezone is not None:
            updated["fixed_timezone"] = fixed_timezone
        if prompt is not None or title is not None:
            updated["payload"] = {
                **(action.get("payload") or {}),
                "prompt": prompt or title or action.get("payload", {}).get("prompt"),
            }
        updated["next_run_at"] = policy.compute_initial_next_run_at(updated, now)

        updates = {
            "title": updated["title"],
            "payload": updated["payload"],
            "timezone": updated["timezone"],
            "schedule_kind": updated["schedule_kind"],
            "fixed_timezone": updated["fixed_timezone"],
            "dtstart": updated["dtstart"],
            "rrule": updated.get("rrule"),
            "next_run_at": updated["next_run_at"],
        }
        self.action_dao.update_action(
            action_id,
            updates=updates,
            expected_revision=action["revision"],
            now=now,
        )
        updated["revision"] = action["revision"] + 1
        updated["updated_at"] = now
        if self.scheduler is not None:
            self.scheduler.reschedule_action(updated)
        return updated

    def delete_visible_reminder(self, action_id: str, user_id: str) -> dict[str, Any]:
        return self._finish_visible_reminder(action_id, user_id, lifecycle_state="cancelled")

    def complete_visible_reminder(self, action_id: str, user_id: str) -> dict[str, Any]:
        return self._finish_visible_reminder(action_id, user_id, lifecycle_state="completed")

    def create_or_replace_internal_followup(
        self,
        *,
        conversation_id: str,
        user_id: str,
        character_id: str,
        title: str,
        prompt: str,
        dtstart: datetime,
        timezone: str,
        rrule: str | None = None,
        payload_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = self.action_dao.find_active_internal_followup(conversation_id)
        if existing:
            return self._update_internal_followup(
                existing,
                title=title,
                prompt=prompt,
                dtstart=dtstart,
                timezone=timezone,
                rrule=rrule,
                payload_metadata=payload_metadata,
            )
        return self._create_internal_followup(
            conversation_id=conversation_id,
            user_id=user_id,
            character_id=character_id,
            title=title,
            prompt=prompt,
            dtstart=dtstart,
            timezone=timezone,
            rrule=rrule,
            payload_metadata=payload_metadata,
        )

    def clear_internal_followup(self, conversation_id: str) -> dict[str, Any] | None:
        existing = self.action_dao.find_active_internal_followup(conversation_id)
        if not existing:
            return None
        now = self.now_provider()
        self.action_dao.update_action(
            str(existing["_id"]),
            updates={
                "lifecycle_state": "cancelled",
                "next_run_at": None,
            },
            expected_revision=existing["revision"],
            now=now,
        )
        if self.scheduler is not None:
            self.scheduler.remove_action(str(existing["_id"]))
        return {**existing, "lifecycle_state": "cancelled", "next_run_at": None}

    def _finish_visible_reminder(
        self,
        action_id: str,
        user_id: str,
        *,
        lifecycle_state: str,
    ) -> dict[str, Any]:
        action = self._require_visible_reminder(action_id, user_id)
        now = self.now_provider()
        self.action_dao.update_action(
            action_id,
            updates={"lifecycle_state": lifecycle_state, "next_run_at": None},
            expected_revision=action["revision"],
            now=now,
        )
        if self.scheduler is not None:
            self.scheduler.remove_action(action_id)
        return {
            **action,
            "revision": action["revision"] + 1,
            "lifecycle_state": lifecycle_state,
            "next_run_at": None,
            "updated_at": now,
        }

    def _require_visible_reminder(self, action_id: str, user_id: str) -> dict[str, Any]:
        action = self.action_dao.get_action(action_id)
        if (
            not action
            or action.get("user_id") != user_id
            or action.get("kind") != "user_reminder"
            or action.get("visibility") != "visible"
        ):
            raise ValueError("visible user reminders only")
        return action

    def _create_internal_followup(
        self,
        *,
        conversation_id: str,
        user_id: str,
        character_id: str,
        title: str,
        prompt: str,
        dtstart: datetime,
        timezone: str,
        rrule: str | None = None,
        payload_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self.now_provider()
        action = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "character_id": character_id,
            "kind": "proactive_followup",
            "source": "llm_inferred",
            "visibility": "internal",
            "lifecycle_state": "active",
            "revision": 0,
            "title": title,
            "payload": {"prompt": prompt, "metadata": payload_metadata or {}},
            "timezone": timezone,
            "dtstart": dtstart,
            "rrule": rrule,
            "next_run_at": None,
            "last_run_at": None,
            "run_count": 0,
            "max_runs": None,
            "expires_at": None,
            "retry_policy": dict(DEFAULT_RETRY_POLICY),
            "lease": {
                "token": None,
                "leased_at": None,
                "lease_expires_at": None,
            },
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
        action["next_run_at"] = policy.compute_initial_next_run_at(action, now)
        action_id = self.action_dao.create_action(action)
        action["_id"] = action_id
        if self.scheduler is not None:
            self.scheduler.register_action(action)
        return action

    def _update_internal_followup(
        self,
        action: dict[str, Any],
        *,
        title: str,
        prompt: str,
        dtstart: datetime,
        timezone: str,
        rrule: str | None,
        payload_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = self.now_provider()
        updated = {
            **action,
            "title": title,
            "payload": {"prompt": prompt, "metadata": payload_metadata or {}},
            "dtstart": dtstart,
            "timezone": timezone,
            "rrule": rrule,
        }
        updated["next_run_at"] = policy.compute_initial_next_run_at(updated, now)
        self.action_dao.update_action(
            str(action["_id"]),
            updates={
                "title": updated["title"],
                "payload": updated["payload"],
                "dtstart": updated["dtstart"],
                "timezone": updated["timezone"],
                "rrule": updated["rrule"],
                "next_run_at": updated["next_run_at"],
            },
            expected_revision=action["revision"],
            now=now,
        )
        updated["revision"] = action["revision"] + 1
        if self.scheduler is not None:
            self.scheduler.reschedule_action(updated)
        return updated
