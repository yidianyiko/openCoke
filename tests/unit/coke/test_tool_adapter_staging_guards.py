from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from coke.composition import SocialSchedulingToolAdapter


class StageMethodGuard:
    def __init__(self) -> None:
        self.staged: list[dict[str, Any]] = []
        self.state_change_calls = 0

    def guard_state_change(self) -> None:
        self.state_change_calls += 1

    def stage_command(self, **kwargs):
        self.staged.append(kwargs)
        raise AssertionError("stage_command must not be called")


class FakeSocialSchedulingService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_shared_reminder(self, **kwargs):
        kwargs.pop("commit_guard", None)
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="created",
            shared_reminder=SimpleNamespace(id="shared_1"),
            breakdown={},
            follow_up_facts={},
        )


def test_adapter_executes_real_write_even_when_guard_exposes_stage_command():
    service = FakeSocialSchedulingService()
    guard = StageMethodGuard()
    adapter = SocialSchedulingToolAdapter(service)

    result = adapter.execute(
        {
            "operation": "create_shared_reminder",
            "creator_account_id": "creator_1",
            "receiver_account_ids": ["friend_1"],
            "title": "Dinner",
            "local_trigger_at": "2026-06-01T19:00:00",
            "captured_timezone": "UTC",
        },
        guard,
    )

    assert result.ok is True
    assert result.facts["status"] == "created"
    assert all(
        "staged" not in key for key in result.facts["social_scheduling_outcome"]
    )
    assert service.calls == [
        {
            "creator_account_id": "creator_1",
            "receiver_account_ids": ["friend_1"],
            "title": "Dinner",
            "local_trigger_at": datetime(2026, 6, 1, 19, 0),
            "captured_timezone": "UTC",
            "duration_minutes": None,
        }
    ]
    assert guard.state_change_calls == 1
    assert guard.staged == []
