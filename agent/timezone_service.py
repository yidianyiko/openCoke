from __future__ import annotations

from copy import deepcopy
from typing import Any


SOURCE_PRIORITY = {
    "app_device_timezone": 100,
    "web_region": 90,
    "external_account_timezone": 80,
    "messaging_identity_region": 70,
    "deployment_default": 10,
}


class TimezoneService:
    def _base_state(self, timezone: str, source: str, status: str) -> dict[str, Any]:
        return {
            "timezone": timezone,
            "timezone_source": source,
            "timezone_status": status,
            "pending_timezone_change": None,
            "pending_task_draft": None,
        }

    def build_initial_state(
        self,
        *,
        existing_state: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
        fallback_timezone: str,
    ) -> dict[str, Any]:
        if existing_state and existing_state.get("timezone"):
            merged = deepcopy(existing_state)
            merged.setdefault("pending_timezone_change", None)
            merged.setdefault("pending_task_draft", None)
            return merged

        ranked_candidates = sorted(
            [
                candidate
                for candidate in candidates
                if candidate.get("timezone") and candidate.get("source")
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

    def apply_user_explicit_change(
        self,
        current_state: dict[str, Any] | None,
        timezone: str,
    ) -> dict[str, Any]:
        state = self.build_initial_state(
            existing_state=current_state,
            candidates=[],
            fallback_timezone=timezone,
        )
        state.update(
            {
                "timezone": timezone,
                "timezone_source": "user_explicit",
                "timezone_status": "user_confirmed",
                "pending_timezone_change": None,
                "pending_task_draft": None,
            }
        )
        return state
