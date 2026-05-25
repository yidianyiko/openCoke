from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId

from scripts.reminder_eval import runner as normal_eval
from scripts.reminder_eval.dataset import ReminderNormalPathCase


def test_normal_path_user_id_isolates_valid_original_user_by_batch_and_case():
    case = ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={
            "source_id": "692c1546a538f0baad5561bb",
            "from_user": "692c14e6a538f0baad5561b6",
        },
    )

    first = normal_eval.normal_path_user_id(case, 2, batch_id="batch-a")
    second = normal_eval.normal_path_user_id(case, 2, batch_id="batch-a")
    other_batch = normal_eval.normal_path_user_id(case, 2, batch_id="batch-b")

    assert first == second
    assert first != "692c14e6a538f0baad5561b6"
    assert other_batch != first
    assert ObjectId.is_valid(first)


def test_normal_path_user_id_has_deterministic_fallback_for_invalid_metadata():
    case = ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"source_id": "conv-a", "from_user": "user-a"},
    )

    first = normal_eval.normal_path_user_id(case, 5, batch_id="batch-a")
    second = normal_eval.normal_path_user_id(case, 5, batch_id="batch-a")

    assert first == second
    assert ObjectId.is_valid(first)


def test_normal_path_relation_seed_marks_eval_user_as_existing_contact():
    relation = normal_eval.normal_path_relation_seed(
        user_id="user-1",
        character_id="char-1",
        case_index=161,
    )

    assert relation["uid"] == "user-1"
    assert relation["cid"] == "char-1"
    assert relation["user_info"]["hobbyname"] == "reminder-e2e-user-161"
    assert relation["character_info"]["status"] == "空闲"
    assert relation["relationship"]["status"] == "空闲"
    assert "already-known" in relation["relationship"]["description"]


def test_normal_path_user_seed_sets_eval_timezone():
    user = normal_eval.normal_path_user_seed(
        user_id="user-1",
        case_index=162,
        timezone_name="Asia/Tokyo",
    )

    assert user["timezone"] == "Asia/Tokyo"
    assert user["effective_timezone"] == "Asia/Tokyo"
    assert user["user_info"]["status"]["place"] == "test"


def test_default_evidence_path_sanitizes_run_id():
    assert normal_eval.default_evidence_path(run_id="batch/id:1").as_posix() == (
        "artifacts/evidence/reminder-normal/batch-id-1.json"
    )


def test_main_writes_default_evidence_and_uses_serial_batches(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    class FakeClient:
        admin = SimpleNamespace(command=lambda _command: None)

        def __getitem__(self, _name):
            return object()

    captured = {}

    def fake_run_batch(**kwargs):
        captured["serial"] = kwargs["serial"]
        return {
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "batch_id": kwargs["batch_id"],
            "platform": kwargs["platform"],
            "character_id": "char-1",
            "user_ids": [],
            "serial": kwargs["serial"],
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "pass_rate": 0,
                "by_error": {},
                "failures": [],
            },
            "results": [],
        }

    monkeypatch.setattr(
        normal_eval,
        "_parse_args",
        lambda: SimpleNamespace(
            cases=normal_eval.DEFAULT_CASES_PATH,
            offset=0,
            limit=1,
            run_all=False,
            batch_size=32,
            continue_on_failure=False,
            parallel_submit=False,
            timeout_seconds=180,
            timezone="Asia/Tokyo",
            use_case_timestamps=False,
            platform=None,
            transport="business-clawscale",
            batch_id="unit evidence",
            character_alias=None,
            output=None,
        ),
    )
    monkeypatch.setattr(normal_eval, "load_cases", lambda _path: [])
    monkeypatch.setattr(normal_eval, "mongo_client", lambda: FakeClient())
    monkeypatch.setattr(
        normal_eval, "run_batch", lambda *args, **kwargs: fake_run_batch(**kwargs)
    )

    assert normal_eval.main() == 0
    assert captured["serial"] is True
    evidence_path = tmp_path / "artifacts/evidence/reminder-normal/unit-evidence.json"
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert (
        evidence["history_two_turn_eval"]["name"] == "history-hourly-checkin-two-turn"
    )
    assert evidence["trace"]["enabled"] is True
    assert evidence["trace"]["schema_version"] == "agent_turn_trace.v1"
    assert evidence["trace"]["path"] == (
        "artifacts/evidence/agent-turn-traces/reminder-normal/unit-evidence.jsonl"
    )
    assert evidence["trace"]["record_count"] == 0


def test_case_input_timestamp_defaults_to_fresh_corpus_wall_clock_for_worker_eligibility(
    monkeypatch,
):
    case = ReminderNormalPathCase(
        input="今天18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"timestamp": "2025-11-30 17:55:53"},
    )
    monkeypatch.setattr(normal_eval.time, "time", lambda: 1777413600)

    assert normal_eval.case_input_timestamp(
        case,
        timezone_name="Asia/Tokyo",
        use_case_timestamp=False,
    ) == int(
        datetime(
            2026, 4, 29, 17, 55, 53, tzinfo=normal_eval.ZoneInfo("Asia/Tokyo")
        ).timestamp()
    )


def test_case_input_timestamp_rolls_passed_wall_clock_to_next_day(monkeypatch):
    case = ReminderNormalPathCase(
        input="你还需要在15：30提醒我吃饭；16：40提醒我洗澡",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"timestamp": "2025-11-30 09:50:19"},
    )
    monkeypatch.setattr(
        normal_eval.time,
        "time",
        lambda: int(
            datetime(
                2026, 4, 29, 18, 59, 13, tzinfo=normal_eval.ZoneInfo("Asia/Tokyo")
            ).timestamp()
        ),
    )

    assert normal_eval.case_input_timestamp(
        case,
        timezone_name="Asia/Tokyo",
        use_case_timestamp=False,
    ) == int(
        datetime(
            2026, 4, 30, 9, 50, 19, tzinfo=normal_eval.ZoneInfo("Asia/Tokyo")
        ).timestamp()
    )


def test_case_input_timestamp_can_use_corpus_timestamp_when_requested():
    case = ReminderNormalPathCase(
        input="今天18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"timestamp": "2025-11-30 17:55:53"},
    )

    assert normal_eval.case_input_timestamp(
        case,
        timezone_name="Asia/Tokyo",
        use_case_timestamp=True,
    ) == int(
        datetime(
            2025, 11, 30, 17, 55, 53, tzinfo=normal_eval.ZoneInfo("Asia/Tokyo")
        ).timestamp()
    )


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


class QueryResult(list):
    def sort(self, key, direction=None):
        if isinstance(key, list):
            sort_key, direction = key[0]
        else:
            sort_key = key
        return QueryResult(
            sorted(
                self,
                key=lambda document: dotted_get(document, sort_key),
                reverse=direction == -1,
            )
        )


class QueryCollection:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    def find(self, query):
        self.queries.append(query)
        return QueryResult(
            [
                document
                for document in self.documents
                if document_matches_query(document, query)
            ]
        )


class QueryDB:
    def __init__(self, *, outputs, reminders, conversations=None):
        self.outputmessages = QueryCollection(outputs)
        self.reminders = QueryCollection(reminders)
        self.conversations = QueryCollection(conversations or [])


def dotted_get(document, path):
    return dotted_get_parts(document, path.split("."))


def dotted_get_parts(document, parts):
    if not parts:
        return document
    current = document
    part = parts[0]
    if isinstance(current, list):
        values = []
        for item in current:
            value = dotted_get_parts(item, parts)
            if isinstance(value, list):
                values.extend(value)
            elif value is not None:
                values.append(value)
        return values
    if not isinstance(current, dict):
        return None
    return dotted_get_parts(current.get(part), parts[1:])


def document_matches_query(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(document_matches_query(document, option) for option in expected):
                return False
            continue
        actual = dotted_get(document, key)
        if isinstance(expected, dict):
            if "$gte" in expected and not (
                actual is not None and actual >= expected["$gte"]
            ):
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$all" in expected:
                actual_values = actual if isinstance(actual, list) else [actual]
                if not all(item in actual_values for item in expected["$all"]):
                    return False
            continue
        if actual != expected:
            return False
    return True


def test_submit_cases_can_write_clawscale_request_response_envelope(monkeypatch):
    db = RecordingDB()
    case = ReminderNormalPathCase(
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


def test_build_result_isolates_outputs_and_reminders_to_current_case():
    case = ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"from_user": "692c14e6a538f0baad5561b6"},
    )
    submitted_wall_at = datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc)
    db = QueryDB(
        outputs=[
            {
                "platform": "business",
                "from_user": "char-1",
                "to_user": "user-1",
                "expect_output_timestamp": 1777449600,
                "message": "已创建提醒：错误的上一例",
                "metadata": {"batch_id": "batch-a", "case_index": 11},
            },
            {
                "platform": "business",
                "from_user": "char-1",
                "to_user": "user-1",
                "expect_output_timestamp": 1777449601,
                "message": "已创建提醒：喝水",
                "metadata": {"batch_id": "batch-a", "case_index": 12},
            },
        ],
        reminders=[
            {
                "owner_user_id": "user-1",
                "title": "错误的上一例",
                "lifecycle_state": "active",
                "next_fire_at": submitted_wall_at,
                "created_at": submitted_wall_at,
                "updated_at": submitted_wall_at,
                "agent_output_target": {"conversation_id": "conv-11"},
            },
            {
                "owner_user_id": "user-1",
                "title": "喝水",
                "lifecycle_state": "active",
                "next_fire_at": submitted_wall_at,
                "created_at": submitted_wall_at,
                "updated_at": submitted_wall_at,
                "agent_output_target": {"conversation_id": "692c14aaa538f0baad556112"},
            },
        ],
        conversations=[
            {
                "_id": ObjectId("692c14aaa538f0baad556112"),
                "platform": "business",
                "chatroom_name": None,
                "talkers": [
                    {"id": "clawscale:batch-a-case-12"},
                    {"id": "clawscale-character:char-1"},
                ],
            }
        ],
    )

    result = normal_eval.build_result(
        db,
        case_index=12,
        item={
            "case": case,
            "user_id": "user-1",
            "input_message_id": "692c14aaa538f0baad5561b4",
            "submitted_at": 1777449600,
            "submitted_wall_at": submitted_wall_at,
            "batch_id": "batch-a",
            "conversation_key": "batch-a-case-12",
        },
        input_status="handled",
        character_id="char-1",
        platform="business",
        elapsed_seconds=1.5,
    )

    assert [output["message"] for output in result.outputs] == ["已创建提醒：喝水"]
    assert [reminder["title"] for reminder in result.reminders] == ["喝水"]
    assert db.outputmessages.queries[0]["metadata.batch_id"] == "batch-a"
    assert db.outputmessages.queries[0]["metadata.case_index"] == 12
    assert db.reminders.queries[0]["agent_output_target.conversation_id"] == {
        "$in": ["692c14aaa538f0baad556112"]
    }
