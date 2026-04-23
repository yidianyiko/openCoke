from agent.timezone_service import TimezoneService


def test_build_initial_inferred_state_prefers_higher_priority_source():
    service = TimezoneService()

    result = service.build_initial_state(
        existing_state=None,
        candidates=[
            {"timezone": "Asia/Shanghai", "source": "messaging_identity_region"},
            {"timezone": "Europe/London", "source": "web_region"},
        ],
        fallback_timezone="Asia/Shanghai",
    )

    assert result["timezone"] == "Europe/London"
    assert result["timezone_status"] == "system_inferred"
    assert result["timezone_source"] == "web_region"


def test_build_initial_state_ignores_invalid_timezone_candidates():
    service = TimezoneService()

    result = service.build_initial_state(
        existing_state=None,
        candidates=[
            {"timezone": "Not/AZone", "source": "web_region"},
            {"timezone": "Asia/Shanghai", "source": "messaging_identity_region"},
        ],
        fallback_timezone="Asia/Tokyo",
    )

    assert result["timezone"] == "Asia/Shanghai"
    assert result["timezone_status"] == "system_inferred"
    assert result["timezone_source"] == "messaging_identity_region"


def test_build_initial_state_normalizes_existing_legacy_state():
    service = TimezoneService()

    result = service.build_initial_state(
        existing_state={"timezone": "Asia/Tokyo"},
        candidates=[],
        fallback_timezone="Asia/Shanghai",
    )

    assert result == {
        "timezone": "Asia/Tokyo",
        "timezone_source": "legacy_preserved",
        "timezone_status": "user_confirmed",
        "pending_timezone_change": None,
        "pending_task_draft": None,
    }


def test_apply_user_explicit_change_clears_pending_state():
    service = TimezoneService()
    current = {
        "timezone": "Asia/Shanghai",
        "timezone_source": "messaging_identity_region",
        "timezone_status": "system_inferred",
        "pending_timezone_change": {"timezone": "Europe/London"},
        "pending_task_draft": {"kind": "visible_reminder"},
    }

    result = service.apply_user_explicit_change(current, "Asia/Tokyo")

    assert result["timezone"] == "Asia/Tokyo"
    assert result["timezone_status"] == "user_confirmed"
    assert result["timezone_source"] == "user_explicit"
    assert result["pending_timezone_change"] is None
    assert result["pending_task_draft"] is None


def test_apply_user_explicit_change_rejects_invalid_timezone():
    service = TimezoneService()

    try:
        service.apply_user_explicit_change(None, "Not/AZone")
    except ValueError as exc:
        assert "Not/AZone" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid timezone")
