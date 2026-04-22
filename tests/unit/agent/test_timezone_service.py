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
