from __future__ import annotations

from copy import deepcopy
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SOURCE_PRIORITY = {
    "app_device_timezone": 100,
    "web_region": 90,
    "external_account_timezone": 80,
    "messaging_identity_region": 70,
    "deployment_default": 10,
}


class TimezoneService:
    def _validate_timezone(self, timezone: str) -> str:
        try:
            return ZoneInfo(timezone).key
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"invalid timezone: {timezone}") from exc

    def _base_state(self, timezone: str, source: str, status: str) -> dict[str, Any]:
        return {
            "timezone": self._validate_timezone(timezone),
            "timezone_source": source,
            "timezone_status": status,
            "pending_timezone_change": None,
            "pending_task_draft": None,
        }

    def _normalize_existing_state(self, state: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(state)
        normalized["timezone"] = self._validate_timezone(normalized["timezone"])
        normalized.setdefault("timezone_source", "legacy_preserved")
        normalized.setdefault("timezone_status", "user_confirmed")
        normalized.setdefault("pending_timezone_change", None)
        normalized.setdefault("pending_task_draft", None)
        return {
            "timezone": normalized["timezone"],
            "timezone_source": normalized["timezone_source"],
            "timezone_status": normalized["timezone_status"],
            "pending_timezone_change": normalized["pending_timezone_change"],
            "pending_task_draft": normalized["pending_task_draft"],
        }

    def build_initial_state(
        self,
        *,
        existing_state: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
        fallback_timezone: str,
    ) -> dict[str, Any]:
        if existing_state and existing_state.get("timezone"):
            return self._normalize_existing_state(existing_state)

        ranked_candidates = sorted(
            [
                candidate
                for candidate in candidates
                if candidate.get("timezone")
                and candidate.get("source")
                and self._is_valid_candidate(candidate["timezone"])
            ],
            key=lambda candidate: SOURCE_PRIORITY.get(candidate["source"], 0),
            reverse=True,
        )
        if ranked_candidates:
            selected = ranked_candidates[0]
            return self._base_state(
                selected["timezone"],
                selected["source"],
                "system_inferred",
            )

        return self._base_state(
            fallback_timezone,
            "deployment_default",
            "system_inferred",
        )

    def _is_valid_candidate(self, timezone: str) -> bool:
        try:
            self._validate_timezone(timezone)
        except ValueError:
            return False
        return True

    def apply_user_explicit_change(
        self,
        current_state: dict[str, Any] | None,
        timezone: str,
    ) -> dict[str, Any]:
        canonical_timezone = self._validate_timezone(timezone)
        state = self.build_initial_state(
            existing_state=current_state,
            candidates=[],
            fallback_timezone=canonical_timezone,
        )
        state.update(
            {
                "timezone": canonical_timezone,
                "timezone_source": "user_explicit",
                "timezone_status": "user_confirmed",
                "pending_timezone_change": None,
                "pending_task_draft": None,
            }
        )
        return state
