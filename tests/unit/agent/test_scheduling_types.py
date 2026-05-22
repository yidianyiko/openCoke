from agent.agno_agent.runtime.scheduling_types import (
    SchedulingBookableWindowPreview,
    SchedulingBookableWindowPreviewItem,
    SchedulingBookableWindowRule,
    _compact_scheduling_args,
)


def test_compact_scheduling_args_strips_none_and_empty_string():
    result = _compact_scheduling_args({"a": None, "b": "", "c": "val", "d": "x"})

    assert result == {"c": "val", "d": "x"}


def test_compact_scheduling_args_serializes_pydantic_preview():
    preview = SchedulingBookableWindowPreview(previewId="bwp_1", windows=[])

    result = _compact_scheduling_args({"preview": preview, "reason": None})

    assert result == {"preview": {"previewId": "bwp_1", "windows": []}}


def test_compact_scheduling_args_passes_through_primitives():
    result = _compact_scheduling_args(
        {"target_account_id": "abc", "timezone": "UTC"}
    )

    assert result == {"target_account_id": "abc", "timezone": "UTC"}


def test_scheduling_bookable_window_preview_round_trips():
    preview = SchedulingBookableWindowPreview(
        previewId="bwp_test",
        windows=[
            SchedulingBookableWindowPreviewItem(
                fingerprint="fp_1",
                rule=SchedulingBookableWindowRule(
                    type="weekly",
                    days_of_week=[1, 3],
                    time_start="09:00",
                    time_end="10:00",
                    timezone="Asia/Shanghai",
                ),
            )
        ],
    )

    dumped = preview.model_dump()

    assert dumped["previewId"] == "bwp_test"
    assert dumped["windows"][0]["fingerprint"] == "fp_1"
    assert dumped["windows"][0]["rule"]["type"] == "weekly"
    assert dumped["windows"][0]["rule"]["days_of_week"] == [1, 3]
    assert dumped["windows"][0]["rule"]["time_start"] == "09:00"
    assert dumped["windows"][0]["rule"]["time_end"] == "10:00"
    assert dumped["windows"][0]["rule"]["timezone"] == "Asia/Shanghai"
