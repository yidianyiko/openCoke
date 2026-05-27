from datetime import UTC, datetime, timedelta

from agent.agno_agent.runtime.focus import build_focus_channel, focus_from_product_notification


def _pending_action(**overrides):
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


def test_build_focus_channel_returns_single_pending_focus():
    focus = build_focus_channel(
        [_pending_action()],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none"
    assert focus.current is not None
    assert focus.current.action_id == "req_shared_1"
    assert focus.current.kind == "shared_reminder_request"
    assert tuple(focus.current.allowed_actions) == ("accept", "reject")
    assert focus.current.status == "pending"
    assert focus.current.summary_for_llm
    assert focus.candidates == (focus.current,)


def test_build_focus_channel_marks_multi_pending_as_ambiguous():
    focus = build_focus_channel(
        [
            _pending_action(action_id="req_shared_1"),
            _pending_action(
                action_id="req_friend_1",
                kind="friend_request",
                summary_for_llm="Ada sent you a friend request.",
            ),
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "multi_pending"
    assert focus.current is None
    assert len(focus.candidates) == 2


def test_build_focus_channel_marks_empty_actions_as_none_actionable():
    focus = build_focus_channel(
        [],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none_actionable"
    assert focus.current is None
    assert focus.candidates == ()


def test_build_focus_channel_marks_expired_action_as_none_actionable():
    focus = build_focus_channel(
        [
            _pending_action(
                expires_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
                - timedelta(seconds=1)
            )
        ],
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "none_actionable"
    assert focus.current is None
    assert focus.candidates == ()


def test_focus_from_product_notification_preserves_multi_pending_candidates():
    focus = focus_from_product_notification(
        {
            "ambiguity": "multi_pending",
            "candidates": [
                _pending_action(action_id="srr_1"),
                _pending_action(
                    action_id="srr_2",
                    summary_for_llm="Another shared reminder request.",
                ),
            ],
        },
        current_time=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )

    assert focus.ambiguity == "multi_pending"
    assert focus.current is None
    assert [candidate.action_id for candidate in focus.candidates] == ["srr_1", "srr_2"]
