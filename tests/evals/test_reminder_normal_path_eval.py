from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId

from scripts import eval_reminder_normal_path_cases as normal_eval


def test_normal_path_user_id_prefers_from_user_over_source_id():
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={
            "source_id": "692c1546a538f0baad5561bb",
            "from_user": "692c14e6a538f0baad5561b6",
        },
    )

    assert normal_eval.normal_path_user_id(case, 2) == "692c14e6a538f0baad5561b6"


def test_normal_path_user_id_has_deterministic_fallback_for_invalid_metadata():
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"source_id": "conv-a", "from_user": "user-a"},
    )

    first = normal_eval.normal_path_user_id(case, 5)
    second = normal_eval.normal_path_user_id(case, 5)

    assert first == second
    assert ObjectId.is_valid(first)


def test_iter_case_batches_preserves_json_order_in_fixed_chunks():
    batches = list(
        normal_eval.iter_case_batches(total_count=70, offset=0, limit=None, batch_size=32)
    )

    assert batches == [
        normal_eval.CaseBatch(offset=0, limit=32),
        normal_eval.CaseBatch(offset=32, limit=32),
        normal_eval.CaseBatch(offset=64, limit=6),
    ]


def test_iter_case_batches_applies_total_limit_before_chunking():
    batches = list(
        normal_eval.iter_case_batches(total_count=70, offset=10, limit=33, batch_size=32)
    )

    assert batches == [
        normal_eval.CaseBatch(offset=10, limit=32),
        normal_eval.CaseBatch(offset=42, limit=1),
    ]


def test_case_input_timestamp_defaults_to_current_time_for_worker_eligibility(monkeypatch):
    case = normal_eval.ReminderNormalPathCase(
        input="今天18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"timestamp": "2025-11-30 17:55:53"},
    )
    monkeypatch.setattr(normal_eval.time, "time", lambda: 1777413600)

    assert (
        normal_eval.case_input_timestamp(
            case,
            timezone_name="Asia/Tokyo",
            use_case_timestamp=False,
        )
        == 1777413600
    )


def test_case_input_timestamp_can_use_corpus_timestamp_when_requested():
    case = normal_eval.ReminderNormalPathCase(
        input="今天18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"timestamp": "2025-11-30 17:55:53"},
    )

    assert normal_eval.case_input_timestamp(
        case,
        timezone_name="Asia/Tokyo",
        use_case_timestamp=True,
    ) == int(datetime(2025, 11, 30, 17, 55, 53, tzinfo=normal_eval.ZoneInfo("Asia/Tokyo")).timestamp())


class RecordingCollection:
    def __init__(self) -> None:
        self.documents = []

    def insert_one(self, document):
        self.documents.append(document)

        class Result:
            inserted_id = ObjectId("692c14aaa538f0baad5561b4")

        return Result()


class RecordingDB:
    def __init__(self) -> None:
        self.inputmessages = RecordingCollection()


def test_submit_cases_can_write_clawscale_request_response_envelope(monkeypatch):
    db = RecordingDB()
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"from_user": "692c14e6a538f0baad5561b6"},
    )
    monkeypatch.setattr(normal_eval.time, "time", lambda: 1777413600)

    normal_eval.submit_cases(
        db,
        [case],
        offset=7,
        character_id="69eeeee7e7ef890c105124bf",
        platform="business",
        batch_id="manual-reminder-test",
        timezone_name="Asia/Tokyo",
        use_case_timestamp=False,
        transport="business-clawscale",
    )

    document = db.inputmessages.documents[0]
    assert document["platform"] == "business"
    assert document["metadata"]["source"] == "clawscale"
    assert document["metadata"]["source_eval"] == "reminder_normal_path_eval"
    assert document["metadata"]["delivery_mode"] == "request_response"
    assert document["metadata"]["business_protocol"] == {
        "delivery_mode": "request_response",
        "gateway_conversation_id": "manual-reminder-test-case-7",
        "business_conversation_key": "manual-reminder-test-case-7",
        "causal_inbound_event_id": "manual-reminder-test-case-7-inbound",
    }


def test_validate_observations_requires_user_visible_crud_ack():
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={},
    )
    reminder = {
        "title": "喝水",
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc),
    }

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "好的"}],
        reminders=[reminder],
    )

    assert "user_output_missing_crud_ack" in errors


def test_validate_observations_accepts_created_reminder_and_matching_user_ack():
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={},
    )
    reminder = {
        "title": "喝水",
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc),
    }

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：喝水"}],
        reminders=[reminder],
    )

    assert errors == []


def test_expected_created_reminders_infers_multi_create_titles_and_recurrence():
    expected = normal_eval.expected_created_reminders(
        "哦对还有，今天18:02提醒我喝水，每天18:04提醒我吃饭呢"
    )

    assert expected == [
        normal_eval.ExpectedReminderCreate(
            title="喝水",
            local_time="18:02:00",
            recurring=False,
        ),
        normal_eval.ExpectedReminderCreate(
            title="吃饭",
            local_time="18:04:00",
            recurring=True,
        ),
    ]


def test_validate_observations_rejects_case3_false_positive_shape():
    case = normal_eval.ReminderNormalPathCase(
        input="哦对还有，今天18:02提醒我喝水，每天18:04提醒我吃饭呢",
        expected_intent="reminder",
        matched_keywords=["提醒", "每天"],
        metadata={},
    )
    reminder = {
        "title": "喝水",
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 4, 29, 9, 2, tzinfo=timezone.utc),
        "schedule": {
            "local_time": "18:02:00",
            "timezone": "Asia/Shanghai",
            "rrule": "FREQ=DAILY",
        },
    }

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "好的，18:02喝水的提醒已经设好了！"}],
        reminders=[reminder],
    )

    assert "expected_reminder_count_mismatch:2>1" in errors
    assert "expected_one_shot_reminder_is_recurring:喝水" in errors
    assert "missing_expected_reminder_title:吃饭" in errors
    assert "user_output_missing_expected_title:吃饭" in errors


def test_validate_observations_accepts_case3_expected_shape():
    case = normal_eval.ReminderNormalPathCase(
        input="哦对还有，今天18:02提醒我喝水，每天18:04提醒我吃饭呢",
        expected_intent="reminder",
        matched_keywords=["提醒", "每天"],
        metadata={},
    )
    reminders = [
        {
            "title": "喝水",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 4, 29, 9, 2, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "18:02:00",
                "timezone": "Asia/Shanghai",
                "rrule": None,
            },
        },
        {
            "title": "吃饭",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 4, 29, 9, 4, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "18:04:00",
                "timezone": "Asia/Shanghai",
                "rrule": "FREQ=DAILY",
            },
        },
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：18:02喝水，18:04每天吃饭"}],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_rejects_duplicate_reminders():
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={},
    )
    reminder = {
        "title": "喝水",
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
        "schedule": {
            "anchor_at": datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
            "local_date": "2026-04-29",
            "local_time": "18:00:00",
            "timezone": "Asia/Shanghai",
            "rrule": None,
        },
    }

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：喝水"}],
        reminders=[dict(reminder), dict(reminder)],
    )

    assert "duplicate_reminder_created" in errors
