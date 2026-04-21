from datetime import UTC, datetime, timedelta

import pytest

from agent.runner import deferred_action_policy as policy


def build_action(**overrides):
    action = {
        "_id": "action-1",
        "kind": "user_reminder",
        "dtstart": datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        "rrule": None,
        "run_count": 0,
        "max_runs": None,
        "expires_at": None,
        "retry_policy": {
            "max_attempts_per_occurrence": 3,
            "base_backoff_seconds": 60,
            "max_backoff_seconds": 900,
        },
    }
    action.update(overrides)
    return action


class TestDeferredActionPolicy:
    def test_compute_initial_next_run_at_for_future_one_shot(self):
        action = build_action()
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)

        result = policy.compute_initial_next_run_at(action, now)

        assert result == action["dtstart"]

    def test_compute_initial_next_run_at_for_overdue_one_shot_coalesces_to_now(self):
        action = build_action(dtstart=datetime(2026, 4, 21, 7, 0, tzinfo=UTC))
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)

        result = policy.compute_initial_next_run_at(action, now)

        assert result == now

    def test_parse_rrule_returns_recurrence_set(self):
        dtstart = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)

        rule = policy.parse_rrule(dtstart, "FREQ=DAILY;COUNT=3")

        assert rule.after(datetime(2026, 4, 21, 9, 0, tzinfo=UTC)) == datetime(
            2026, 4, 22, 9, 0, tzinfo=UTC
        )

    def test_compute_initial_next_run_at_for_overdue_recurring_runs_immediately_once(self):
        action = build_action(
            dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
            rrule="FREQ=HOURLY",
        )
        now = datetime(2026, 4, 21, 11, 30, tzinfo=UTC)

        result = policy.compute_initial_next_run_at(action, now)

        assert result == now

    def test_compute_next_run_after_success_advances_recurring_action(self):
        action = build_action(
            dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
            rrule="FREQ=DAILY",
        )
        scheduled_for = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        now = datetime(2026, 4, 21, 9, 0, 5, tzinfo=UTC)

        result = policy.compute_next_run_after_success(action, scheduled_for, now)

        assert result == datetime(2026, 4, 22, 9, 0, tzinfo=UTC)

    def test_compute_next_run_after_success_coalesces_overdue_recurring_to_next_after_now(self):
        action = build_action(
            dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
            rrule="FREQ=HOURLY",
        )
        scheduled_for = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        now = datetime(2026, 4, 21, 11, 30, tzinfo=UTC)

        result = policy.compute_next_run_after_success(action, scheduled_for, now)

        assert result == datetime(2026, 4, 21, 12, 0, tzinfo=UTC)

    def test_compute_next_run_after_success_returns_none_when_max_runs_reached(self):
        action = build_action(
            rrule="FREQ=DAILY",
            run_count=2,
            max_runs=3,
        )
        scheduled_for = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)
        now = datetime(2026, 4, 23, 9, 0, tzinfo=UTC)

        result = policy.compute_next_run_after_success(action, scheduled_for, now)

        assert result is None

    def test_compute_next_run_after_success_returns_none_when_next_occurrence_expires(self):
        action = build_action(
            rrule="FREQ=DAILY",
            expires_at=datetime(2026, 4, 21, 18, 0, tzinfo=UTC),
        )
        scheduled_for = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
        now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)

        result = policy.compute_next_run_after_success(action, scheduled_for, now)

        assert result is None

    def test_compute_retry_at_uses_capped_exponential_backoff(self):
        action = build_action()
        now = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)

        first = policy.compute_retry_at(action, attempt_count=1, now=now)
        second = policy.compute_retry_at(action, attempt_count=2, now=now)
        capped = policy.compute_retry_at(
            build_action(
                retry_policy={
                    "max_attempts_per_occurrence": 8,
                    "base_backoff_seconds": 120,
                    "max_backoff_seconds": 300,
                }
            ),
            attempt_count=4,
            now=now,
        )

        assert first == now + timedelta(seconds=60)
        assert second == now + timedelta(seconds=120)
        assert capped == now + timedelta(seconds=300)

    @pytest.mark.parametrize(
        ("attempt_count", "expected"),
        [
            (1, False),
            (2, False),
            (3, True),
            (4, True),
        ],
    )
    def test_should_terminally_fail_occurrence(self, attempt_count, expected):
        action = build_action()

        assert policy.should_terminally_fail_occurrence(action, attempt_count) is expected

    def test_policy_rejects_naive_datetimes(self):
        action = build_action(dtstart=datetime(2026, 4, 21, 9, 0))
        now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)

        with pytest.raises(ValueError, match="timezone-aware"):
            policy.compute_initial_next_run_at(action, now)
