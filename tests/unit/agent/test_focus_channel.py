from datetime import UTC, datetime, timedelta

from agent.agno_agent.runtime.focus import (
    build_focus_channel,
    focus_from_product_notification,
    focus_to_session_state,
)


def _retired_pending_action(**overrides):
    action = {
        "action_id": "req_shared_1",
        "kind": "shared_reminder_request",
        "allowed_actions": ("accept", "reject"),
        "status": "pending",
        "expires_at": datetime(2026, 5, 26, 12, 30, tzinfo=UTC),
        "summary_for_llm": "Eva invited you to join yoga at 12:30.",
    }
    action.update(overrides)
    return action


def test_build_focus_channel_ignores_retired_pending_invitation_actions():
    focus = build_focus_channel(
        [
            _retired_pending_action(),
            _retired_pending_action(
                action_id="req_friend_1",
                kind="friend_request",
                summary_for_llm="Legacy friendship action.",
            ),
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none_actionable"
    assert focus.current is None
    assert focus.candidates == ()


def test_build_focus_channel_marks_empty_actions_as_none_actionable():
    focus = build_focus_channel(
        [],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none_actionable"
    assert focus.current is None
    assert focus.candidates == ()


def test_active_focus_action_does_not_require_or_emit_allowed_actions():
    focus = build_focus_channel(
        [
            {
                "action_id": "candidate_1",
                "kind": "future_product_candidate",
                "status": "pending",
                "summary_for_llm": "A future product candidate.",
            }
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none"
    assert focus.current is not None
    assert "allowed_actions" not in focus.current.model_dump(mode="json")
    assert "allowed_actions" not in focus_to_session_state(focus)["current"]


def test_multiple_active_focus_actions_use_neutral_multi_candidate_name():
    focus = build_focus_channel(
        [
            {
                "action_id": "candidate_1",
                "kind": "future_product_candidate",
                "status": "pending",
                "summary_for_llm": "First product candidate.",
            },
            {
                "action_id": "candidate_2",
                "kind": "future_product_candidate",
                "status": "pending",
                "summary_for_llm": "Second product candidate.",
            },
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "multi_candidate"
    assert focus.current is None
    assert len(focus.candidates) == 2


def test_build_focus_channel_marks_expired_action_as_none_actionable():
    focus = build_focus_channel(
        [
            _retired_pending_action(
                kind="legacy_action",
                expires_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
                - timedelta(seconds=1),
            )
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none_actionable"
    assert focus.current is None
    assert focus.candidates == ()


def test_direct_friendship_notification_is_informational_not_focus_action():
    focus = focus_from_product_notification(
        {
            "kind": "direct_friendship_created",
            "resource_type": "friendship",
            "friendship_id": "fs_1",
            "status": "active",
            "summary": "Ming added you as a friend.",
        },
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none_actionable"
    assert focus.current is None
    assert focus.candidates == ()


def test_shared_reminder_notification_is_informational_not_focus_action():
    focus = focus_from_product_notification(
        {
            "kind": "shared_reminder_created",
            "resource_type": "shared_reminder",
            "shared_reminder_id": "sr_1",
            "status": "active",
            "summary": "Eva created a shared reminder.",
        },
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none_actionable"
    assert focus.current is None
    assert focus.candidates == ()
