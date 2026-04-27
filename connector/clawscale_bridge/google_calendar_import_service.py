from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agent.role.bootstrap import ensure_default_character_seeded
from dao.conversation_dao import ConversationDAO
from dao.user_dao import UserDAO
from util.time_util import get_default_timezone


class GoogleCalendarImportService:
    def __init__(
        self,
        *,
        conversation_dao: ConversationDAO | None = None,
        deferred_action_service=None,
        character_id_provider=None,
        user_dao: UserDAO | None = None,
        default_timezone_provider=None,
        now_provider=None,
    ) -> None:
        if deferred_action_service is None:
            from agent.agno_agent.tools.deferred_action.service import (
                DeferredActionService,
            )

            deferred_action_service = DeferredActionService()
        self.conversation_dao = conversation_dao or ConversationDAO()
        self.deferred_action_service = deferred_action_service
        self.character_id_provider = character_id_provider or ensure_default_character_seeded
        self.user_dao = user_dao or UserDAO()
        self.default_timezone_provider = default_timezone_provider or get_default_timezone
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def preflight(self, *, customer_id: str) -> dict[str, str]:
        if not isinstance(customer_id, str) or not customer_id.strip():
            raise ValueError("customer_id_required")

        character_id = self.character_id_provider()
        conversation = self.conversation_dao.find_latest_private_conversation_by_db_user_ids(
            db_user_id1=customer_id,
            db_user_id2=character_id,
        )
        if not conversation:
            raise ValueError("conversation_required")

        return {
            "conversation_id": str(conversation["_id"]),
            "user_id": customer_id,
            "character_id": character_id,
            "timezone": self._resolve_target_timezone(customer_id),
        }

    def import_events(
        self,
        *,
        target: dict[str, str],
        run_id: str,
        provider_account_email: str | None,
        calendar_defaults: dict[str, Any] | None,
        events: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        calendar_defaults = calendar_defaults or {}
        events = events or []

        result = {
            "imported_count": 0,
            "skipped_count": 0,
            "warning_count": 0,
            "warnings": [],
        }
        series_ids = {
            str(event.get("id"))
            for event in events
            if isinstance(event, dict) and event.get("recurrence")
        }
        series_exception_ids = {
            str(event.get("recurringEventId"))
            for event in events
            if isinstance(event, dict)
            and not self._is_tombstone_only_cancellation_artifact(event)
            and event.get("recurringEventId")
            and event.get("originalStartTime")
            and str(event.get("recurringEventId")) in series_ids
        }
        seen_keys: set[tuple[str, str]] = set()

        for event in events:
            if not isinstance(event, dict):
                continue

            if self._is_tombstone_only_cancellation_artifact(event):
                continue

            if event.get("recurringEventId") and event.get("originalStartTime"):
                continue

            event_id = str(event.get("id") or "").strip()
            if not event_id:
                continue

            if event_id in series_exception_ids:
                result["skipped_count"] += 1
                result["warnings"].append(
                    {
                        "event_id": event_id,
                        "reason": "unsupported_recurring_exceptions",
                    }
                )
                result["warning_count"] = len(result["warnings"])
                continue

            source_original_start_time = self._source_original_start_time(event)
            dedupe_key = (event_id, source_original_start_time)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            if self._find_duplicate(
                user_id=target["user_id"],
                source_event_id=event_id,
                source_original_start_time=source_original_start_time,
            ):
                result["skipped_count"] += 1
                result["warnings"].append(
                    {
                        "event_id": event_id,
                        "reason": "duplicate_existing_reminder",
                    }
                )
                result["warning_count"] = len(result["warnings"])
                continue

            dtstart, timezone_name = self._effective_reminder_datetime(
                event=event,
                calendar_defaults=calendar_defaults,
                target_timezone=target["timezone"],
            )
            metadata = {
                "import_provider": "google_calendar",
                "import_run_id": run_id,
                "provider_account_email": provider_account_email,
                "source_event_id": event_id,
                "source_original_start_time": source_original_start_time,
            }
            title = (event.get("summary") or "").strip() or "Google Calendar event"

            if event.get("recurrence"):
                self.deferred_action_service.create_imported_recurring_reminder(
                    user_id=target["user_id"],
                    character_id=target["character_id"],
                    conversation_id=target["conversation_id"],
                    title=title,
                    dtstart=dtstart,
                    timezone=timezone_name,
                    rrule=self._normalize_rrule(event.get("recurrence")),
                    metadata=metadata,
                )
                result["imported_count"] += 1
                continue

            if dtstart >= self.now_provider():
                self.deferred_action_service.create_imported_future_reminder(
                    user_id=target["user_id"],
                    character_id=target["character_id"],
                    conversation_id=target["conversation_id"],
                    title=title,
                    dtstart=dtstart,
                    timezone=timezone_name,
                    metadata=metadata,
                )
            else:
                self.deferred_action_service.create_imported_historical_reminder(
                    user_id=target["user_id"],
                    character_id=target["character_id"],
                    conversation_id=target["conversation_id"],
                    title=title,
                    dtstart=dtstart,
                    timezone=timezone_name,
                    metadata=metadata,
                )
            result["imported_count"] += 1

        return result

    def _resolve_target_timezone(self, customer_id: str) -> str:
        user = self.user_dao.get_user_by_id(customer_id)
        timezone_name = user.get("timezone") if isinstance(user, dict) else None
        if isinstance(timezone_name, str) and timezone_name.strip():
            try:
                ZoneInfo(timezone_name)
                return timezone_name
            except Exception:
                pass
        fallback = self.default_timezone_provider()
        return getattr(fallback, "key", str(fallback))

    def _find_duplicate(
        self,
        *,
        user_id: str,
        source_event_id: str,
        source_original_start_time: str,
    ) -> dict[str, Any] | None:
        action_dao = getattr(self.deferred_action_service, "action_dao", None)
        if action_dao is None or not hasattr(action_dao, "find_imported_reminder_duplicate"):
            return None
        return action_dao.find_imported_reminder_duplicate(
            user_id=user_id,
            import_provider="google_calendar",
            source_event_id=source_event_id,
            source_original_start_time=source_original_start_time,
        )

    def _effective_reminder_datetime(
        self,
        *,
        event: dict[str, Any],
        calendar_defaults: dict[str, Any],
        target_timezone: str,
    ) -> tuple[datetime, str]:
        timezone_name = self._resolve_event_timezone(
            event=event,
            calendar_defaults=calendar_defaults,
            target_timezone=target_timezone,
        )
        event_start = self._parse_event_start(event, timezone_name)
        reminder_minutes = self._effective_reminder_minutes(event, calendar_defaults)
        if reminder_minutes is not None:
            return event_start - timedelta(minutes=reminder_minutes), timezone_name

        start = event.get("start") or {}
        if start.get("date"):
            return event_start.replace(hour=9), timezone_name
        return event_start, timezone_name

    def _resolve_event_timezone(
        self,
        *,
        event: dict[str, Any],
        calendar_defaults: dict[str, Any],
        target_timezone: str,
    ) -> str:
        start = event.get("start") or {}
        end = event.get("end") or {}
        if start.get("date") and not start.get("dateTime"):
            candidates = (
                start.get("timeZone"),
                end.get("timeZone"),
                target_timezone,
                calendar_defaults.get("timezone"),
            )
        else:
            candidates = (
                start.get("timeZone"),
                end.get("timeZone"),
                calendar_defaults.get("timezone"),
                target_timezone,
            )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                try:
                    ZoneInfo(candidate)
                    return candidate
                except Exception:
                    continue
        fallback = self.default_timezone_provider()
        return getattr(fallback, "key", str(fallback))

    def _effective_reminder_minutes(
        self, event: dict[str, Any], calendar_defaults: dict[str, Any]
    ) -> int | None:
        reminders = event.get("reminders") or {}
        if reminders.get("useDefault") is True:
            effective = calendar_defaults.get("default_reminders") or []
        else:
            overrides = reminders.get("overrides")
            if overrides:
                effective = overrides
            else:
                effective = []

        minutes = [
            item.get("minutes")
            for item in effective
            if isinstance(item, dict) and isinstance(item.get("minutes"), int)
        ]
        return min(minutes) if minutes else None

    def _parse_event_start(self, event: dict[str, Any], timezone_name: str) -> datetime:
        start = event.get("start") or {}
        tz = ZoneInfo(timezone_name)
        if start.get("dateTime"):
            return self._parse_datetime(start["dateTime"], timezone_name)
        if start.get("date"):
            return datetime.fromisoformat(start["date"]).replace(tzinfo=tz)
        raise ValueError("event_start_required")

    def _source_original_start_time(self, event: dict[str, Any]) -> str:
        original_start_time = event.get("originalStartTime") or {}
        if isinstance(original_start_time, dict):
            if original_start_time.get("dateTime"):
                return str(original_start_time["dateTime"])
            if original_start_time.get("date"):
                return str(original_start_time["date"])

        start = event.get("start") or {}
        if start.get("dateTime"):
            return str(start["dateTime"])
        if start.get("date"):
            return str(start["date"])
        return ""

    def _normalize_rrule(self, recurrence: Any) -> str:
        if isinstance(recurrence, str):
            values = [recurrence]
        else:
            values = [item for item in (recurrence or []) if isinstance(item, str)]

        for item in values:
            if item.startswith("RRULE:"):
                return item.removeprefix("RRULE:")
        if values:
            return values[0]
        raise ValueError("recurrence_required")

    def _is_tombstone_only_cancellation_artifact(self, event: dict[str, Any]) -> bool:
        if event.get("status") != "cancelled":
            return False
        return not any(
            event.get(field)
            for field in ("summary", "description", "location", "start", "end", "recurrence")
        )

    def _parse_datetime(self, value: str, timezone_name: str) -> datetime:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC)
        return parsed.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(UTC)
