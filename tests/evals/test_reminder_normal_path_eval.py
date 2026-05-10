from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId

from scripts import user_path_normal_eval as normal_eval

_ORIGINAL_RUN_CLARIFICATION_OUTPUT_JUDGE = normal_eval.run_clarification_output_judge


@pytest.fixture(autouse=True)
def disable_live_reminder_eval_judges(monkeypatch):
    def clarification_judge(_case_input, output_text):
        return any(marker in output_text for marker in ("?", "？", "吗", "呢"))

    monkeypatch.setattr(
        normal_eval, "run_clarification_output_judge", clarification_judge
    )
    monkeypatch.setattr(
        normal_eval, "run_unconfirmed_reminder_judge", lambda text: False
    )


def test_normal_path_user_id_isolates_valid_original_user_by_batch_and_case():
    case = normal_eval.ReminderNormalPathCase(
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
    case = normal_eval.ReminderNormalPathCase(
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
    assert relation["relationship"]["closeness"] >= 50
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


def test_iter_case_batches_preserves_json_order_in_fixed_chunks():
    batches = list(
        normal_eval.iter_case_batches(
            total_count=70, offset=0, limit=None, batch_size=32
        )
    )

    assert batches == [
        normal_eval.CaseBatch(offset=0, limit=32),
        normal_eval.CaseBatch(offset=32, limit=32),
        normal_eval.CaseBatch(offset=64, limit=6),
    ]


def test_iter_case_batches_applies_total_limit_before_chunking():
    batches = list(
        normal_eval.iter_case_batches(
            total_count=70, offset=10, limit=33, batch_size=32
        )
    )

    assert batches == [
        normal_eval.CaseBatch(offset=10, limit=32),
        normal_eval.CaseBatch(offset=42, limit=1),
    ]


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
    assert evidence["pending_workflow_two_turn_eval"]["name"] == (
        "pending-workflow-hourly-checkin-two-turn"
    )


def test_case_input_timestamp_defaults_to_fresh_corpus_wall_clock_for_worker_eligibility(
    monkeypatch,
):
    case = normal_eval.ReminderNormalPathCase(
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
    case = normal_eval.ReminderNormalPathCase(
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


def test_build_result_isolates_outputs_and_reminders_to_current_case():
    case = normal_eval.ReminderNormalPathCase(
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


def test_validate_observations_defaults_unannotated_cases_to_discussion():
    case = normal_eval.ReminderNormalPathCase(
        input="最近要学习llya的一篇文章 明天下班前必须学完",
        expected_intent="reminder",
        matched_keywords=["明天", "下班", "学习"],
        metadata={},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "提醒操作失败：提醒识别超时，未能完成提醒设置"}],
        reminders=[],
    )

    assert "no_reminder_created" not in errors


def test_validate_observations_accepts_delete_crud_without_created_reminder():
    case = normal_eval.ReminderNormalPathCase(
        input="晚上不用叫我",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_operation": "delete",
        },
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "取消提醒失败：没有找到要取消的提醒，请告诉我提醒名称。"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_accepts_allowed_delete_clarification():
    case = normal_eval.ReminderNormalPathCase(
        input="晚上不用叫我",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_operation": "delete",
            "allow_clarification": True,
        },
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "你说的不用叫你是说晚上的什么提醒呀？"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_rejects_create_clarification_for_delete_request():
    case = normal_eval.ReminderNormalPathCase(
        input="今天学习结束，晚安，不要打扰我了",
        expected_intent="reminder",
        matched_keywords=["不要打扰"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_operation": "delete",
            "allow_clarification": True,
        },
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "你把具体时间和事项再发我一遍，我可以继续帮你处理。"}],
        reminders=[],
    )

    assert "user_output_missing_crud_ack" in errors


def test_validate_observations_accepts_cancel_target_clarification():
    case = normal_eval.ReminderNormalPathCase(
        input="晚上不用叫我",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "是指晚上那个“开始学习”的提醒取消掉吗？"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_accepts_what_reminder_clarification():
    case = normal_eval.ReminderNormalPathCase(
        input="晚上不用叫我",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "你说的不用叫你是说晚上的什么提醒呀？"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_accepts_confirmation_style_clarification():
    case = normal_eval.ReminderNormalPathCase(
        input="晚上不用叫我",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_operation": "delete",
            "allow_clarification": True,
        },
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "晚上不用叫你是说今晚的计划有调整吗"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_accepts_explicit_delete_target_question():
    case = normal_eval.ReminderNormalPathCase(
        input="今天学习结束，晚安，不要打扰我了",
        expected_intent="reminder",
        matched_keywords=["不要打扰"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_operation": "delete",
            "allow_clarification": True,
        },
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": "你是想取消今天剩余的所有提醒，还是删除某个具体的提醒？请告诉我具体要取消的提醒。"
            }
        ],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_does_not_require_crud_for_unschedulable_label():
    case = normal_eval.ReminderNormalPathCase(
        input="我这周一和周五是全天兼职，这两天估计要插空学习",
        expected_intent="reminder",
        matched_keywords=["周一", "周五", "学习"],
        metadata={"evaluation_expectation": "discussion"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "你这两天可以先把学习任务拆小一点。"}],
        reminders=[],
    )

    assert "no_reminder_created" not in errors


def test_validate_observations_accepts_planning_detail_question_as_discussion():
    case = normal_eval.ReminderNormalPathCase(
        input="还有就是规划一下，我这今天半天和明天半天我要怎么安排我的时间才能差不多做完",
        expected_intent="reminder",
        matched_keywords=["今天", "明天", "时间"],
        metadata={"evaluation_expectation": "discussion"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": (
                    "我很乐意帮你规划时间，不过我需要先了解一下："
                    "你今天半天和明天半天需要完成什么呢？"
                    "只要你告诉我具体要做的任务或工作内容，我就可以帮你安排时间啦！"
                )
            }
        ],
        reminders=[],
    )

    assert "unexpected_reminder_clarification" not in errors
    assert errors == []


def test_validate_observations_accepts_discussion_with_trailing_reminder_offer():
    case = normal_eval.ReminderNormalPathCase(
        input="我希望可以7点起床早读",
        expected_intent="reminder",
        matched_keywords=["7点", "起床"],
        metadata={"evaluation_expectation": "discussion"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": (
                    "早晨好！这个计划听起来很棒，7点起床早读可以让你的一天更加充实。"
                    "坚持下去一定会很有收获的！\n\n"
                    "如果之后需要提醒或其他帮助，随时告诉我哦。"
                )
            }
        ],
        reminders=[],
    )

    assert "unexpected_reminder_clarification" not in errors
    assert errors == []


def test_validate_observations_does_not_require_crud_for_nickname_request():
    case = normal_eval.ReminderNormalPathCase(
        input="叫我小凡就行了",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "小凡好！"}],
        reminders=[],
    )

    assert "no_reminder_created" not in errors


def test_validate_observations_rejects_reminder_clarification_for_nickname_request():
    case = normal_eval.ReminderNormalPathCase(
        input="叫我小凡就行了",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "提醒设置还没完成。请确认具体提醒时间和提醒内容。"}],
        reminders=[],
    )

    assert "unexpected_reminder_clarification" in errors


def test_validate_observations_rejects_wrong_clarification_focus():
    case = normal_eval.ReminderNormalPathCase(
        input="冥想可以每个小时提醒我做一次冥想吗",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={
            "evaluation_expectation": "clarify",
            "expected_clarification_terms": ["持续", "结束", "截止"],
        },
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "提醒设置还没完成。请确认具体提醒时间和提醒内容。"}],
        reminders=[],
    )

    assert "user_output_wrong_clarification_focus" in errors


def test_validate_observations_does_not_require_crud_for_vague_capability_question():
    case = normal_eval.ReminderNormalPathCase(
        input="你可以循环提醒我吗",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "capability"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "可以，但你要告诉我提醒内容和时间。"}],
        reminders=[],
    )

    assert "no_reminder_created" not in errors


def test_validate_observations_does_not_require_crud_for_frustrated_capability_question():
    case = normal_eval.ReminderNormalPathCase(
        input="怎么这样！那你到底会不会提醒我",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "capability"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "会提醒你，但需要具体时间和内容。"}],
        reminders=[],
    )

    assert "no_reminder_created" not in errors


def test_validate_observations_does_not_require_crud_for_missed_reminder_complaint():
    case = normal_eval.ReminderNormalPathCase(
        input="今天下午怎么不提醒我？",
        expected_intent="reminder",
        matched_keywords=["提醒我", "今天", "下午"],
        metadata={"evaluation_expectation": "query"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "我查到今天下午没有需要新建的提醒。"}],
        reminders=[],
    )

    assert "no_reminder_created" not in errors


def test_validate_observations_does_not_require_crud_for_underspecified_reminder_request():
    case = normal_eval.ReminderNormalPathCase(
        input="你提醒我一下",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "可以，你想让我提醒什么、什么时候提醒？"}],
        reminders=[],
    )

    assert "no_reminder_created" not in errors


def test_validate_observations_does_not_require_crud_for_reminder_time_query():
    case = normal_eval.ReminderNormalPathCase(
        input="那你打算几点提醒我",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"evaluation_expectation": "query"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "我会在明天早上九点提醒你。"}],
        reminders=[],
    )

    assert "no_reminder_created" not in errors


def test_validate_observations_requires_fixture_for_date_only_clarification():
    case = normal_eval.ReminderNormalPathCase(
        input="明天继续提醒我看文章，要看完，然后要写学习笔记。小说明天也继续写！",
        expected_intent="reminder",
        matched_keywords=["提醒我", "明天", "学习"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "可以，明天几点提醒你看文章、写笔记和写小说？"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_rejects_reminder_for_clarification_fixture():
    case = normal_eval.ReminderNormalPathCase(
        input="明天继续提醒我看文章，要看完，然后要写学习笔记。小说明天也继续写！",
        expected_intent="reminder",
        matched_keywords=["提醒我", "明天", "学习"],
        metadata={"evaluation_expectation": "clarify"},
    )
    reminder = {
        "title": "看文章",
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 4, 30, 0, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc),
    }

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：看文章"}],
        reminders=[reminder],
    )

    assert "unexpected_reminder_created" in errors


def test_clarification_output_accepts_cadence_confirmation_question():
    case = normal_eval.ReminderNormalPathCase(
        input="你觉得多久提醒我一下鼓励我学习呢",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "可以先半小时一次，你想每隔多久提醒一次？"}],
        reminders=[],
    )

    assert errors == []


def test_clarification_output_accepts_proposed_cadence_confirmation():
    case = normal_eval.ReminderNormalPathCase(
        input="你觉得多久提醒我一下鼓励我学习呢",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {"message": "半小时一次既能保持节奏又不会太频繁，你觉得这个频率怎么样？"}
        ],
        reminders=[],
    )

    assert errors == []


def test_clarification_output_accepts_cadence_adoption_question():
    case = normal_eval.ReminderNormalPathCase(
        input="那你建议我多久来提醒我呢？",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "我建议先每半小时提醒一次。你想按这个频率吗？"}],
        reminders=[],
    )

    assert errors == []


def test_clarification_output_accepts_frequency_question_wording():
    case = normal_eval.ReminderNormalPathCase(
        input="10点到11点写作，随时提醒我专注",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "想在10:00-11:00之间以什么频率提醒你专注呢？"}],
        reminders=[],
        unconfirmed_reminder_judge=lambda text: False,
    )

    assert errors == []


def test_clarification_output_accepts_when_question_with_injected_judge():
    case = normal_eval.ReminderNormalPathCase(
        input="可以提醒我喝水哦",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"evaluation_expectation": "clarify"},
    )
    calls = []

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": "你想什么时候提醒你喝水？比如每天的某个时间，或者每隔几个小时？"
            }
        ],
        reminders=[],
        clarification_judge=lambda case_input, output_text: calls.append(
            (case_input, output_text)
        )
        or True,
        unconfirmed_reminder_judge=lambda text: False,
    )

    assert errors == []
    assert calls == [
        (
            case.input,
            "你想什么时候提醒你喝水？比如每天的某个时间，或者每隔几个小时？",
        )
    ]


def test_clarification_output_accepts_every_how_long_wording():
    case = normal_eval.ReminderNormalPathCase(
        input="10点到11点写作，随时提醒我专注",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "您希望每隔多长时间提醒一次保持专注呢？"}],
        reminders=[],
        unconfirmed_reminder_judge=lambda text: False,
    )

    assert errors == []


def test_clarification_output_accepts_how_often_remind_wording():
    case = normal_eval.ReminderNormalPathCase(
        input="10点到11点写作，随时提醒我专注",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "具体希望多久提醒一次？比如每15分钟、每30分钟？"}],
        reminders=[],
        unconfirmed_reminder_judge=lambda text: False,
    )

    assert errors == []


def test_clarification_output_accepts_how_often_remind_you_wording():
    case = normal_eval.ReminderNormalPathCase(
        input="10点到11点写作，随时提醒我专注",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "多久提醒你一次保持专注呢？"}],
        reminders=[],
        unconfirmed_reminder_judge=lambda text: False,
    )

    assert errors == []


def test_clarification_output_accepts_llm_judged_frequency_question():
    case = normal_eval.ReminderNormalPathCase(
        input="我10：13-11：00要写个个人陈述，随时提醒我让我专注。11：00点个外卖",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )
    calls = []

    def clarification_judge(case_input, output_text):
        calls.append((case_input, output_text))
        return True

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {"message": "专注提醒的频率是多少呢？另外，11:00点外卖也需要设一个提醒吗？"}
        ],
        reminders=[],
        clarification_judge=clarification_judge,
        unconfirmed_reminder_judge=lambda text: False,
    )

    assert errors == []
    assert calls == [
        (
            case.input,
            "专注提醒的频率是多少呢？另外，11:00点外卖也需要设一个提醒吗？",
        )
    ]


def test_clarification_output_uses_injected_llm_rejection():
    assert (
        normal_eval.output_mentions_clarification(
            [{"message": "我已经安排好了。"}],
            case_input="明天提醒我写作",
            judge=lambda case_input, output_text: False,
        )
        is False
    )


@pytest.mark.parametrize(
    ("case_input", "output_text"),
    [
        ("明天继续提醒我看文章", "明天几点提醒你看文章和写小说呢？"),
        ("可以提醒我喝水哦", "请问要在什么时间提醒你喝水呢？"),
        ("本周六订蛋糕提醒", "我得先确认一下，本周六你打算什么时间去订蛋糕？"),
        (
            "提醒我学习进度如何？",
            "您希望我何时提醒您检查学习进度？例如一个具体的时间或日期。",
        ),
        (
            "随时提醒我让我专注",
            "你说10:13到11:00写个人陈述，想要多频繁提醒你？",
        ),
        (
            "你觉得多久提醒我一下鼓励我学习呢",
            "如果五点二十五开始提醒你怎么样？",
        ),
    ],
)
def test_clarification_output_uses_deterministic_fallback_for_clear_questions(
    case_input, output_text
):
    assert (
        normal_eval.output_mentions_clarification(
            [{"message": output_text}],
            case_input=case_input,
        )
        is True
    )


def test_clarification_output_deterministic_fallback_rejects_setup_claim():
    assert (
        normal_eval.output_mentions_clarification(
            [{"message": "已创建提醒：写作（明天 10:00）"}],
            case_input="明天提醒我写作",
        )
        is False
    )


def test_clarification_output_llm_judge_timeout_returns_false(monkeypatch):
    class SlowJudge:
        def run(self, _prompt):
            import time

            time.sleep(1)

    monkeypatch.setattr(
        normal_eval,
        "CLARIFICATION_OUTPUT_JUDGE_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(normal_eval, "LLM_JUDGE_PROCESS_START_METHOD", "fork")
    monkeypatch.setattr(
        normal_eval,
        "_clarification_output_judge_agent",
        lambda: SlowJudge(),
    )
    monkeypatch.setattr(
        normal_eval,
        "run_clarification_output_judge",
        _ORIGINAL_RUN_CLARIFICATION_OUTPUT_JUDGE,
    )

    assert (
        normal_eval.run_clarification_output_judge("提醒我写作", "几点提醒你？")
        is False
    )


def test_clarification_output_llm_judge_rubric_covers_missing_cadence():
    prompt = normal_eval.build_clarification_output_judge_prompt(
        "10点到11点写作，随时提醒我专注",
        "专注提醒的频率是多少呢？",
    )

    assert "cadence/frequency" in prompt
    assert "proposed option" in prompt
    assert "structured schema" in prompt


def test_clarification_output_rejects_unconfirmed_future_reminder_commitment():
    case = normal_eval.ReminderNormalPathCase(
        input="你觉得多久提醒我一下鼓励我学习呢",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {"message": "我建议每30分钟提醒一次，我准时催你，你觉得这个节奏怎么样？"}
        ],
        reminders=[],
        unconfirmed_reminder_judge=lambda text: True,
    )

    assert "user_output_implies_unconfirmed_reminder" in errors


def test_discussion_output_rejects_unconfirmed_future_reminder_commitment():
    case = normal_eval.ReminderNormalPathCase(
        input="还想继续休息一会",
        expected_intent="reminder",
        matched_keywords=["一会", "休息"],
        metadata={},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "休息到几点？我到时候提醒你起来动一动。"}],
        reminders=[],
        unconfirmed_reminder_judge=lambda text: True,
    )

    assert "user_output_implies_unconfirmed_reminder" in errors


def test_clarification_question_is_not_treated_as_unconfirmed_reminder_commitment():
    case = normal_eval.ReminderNormalPathCase(
        input="晚上10点提醒我",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "晚上十点提醒你是吧，想让我提醒你做什么事？"}],
        reminders=[],
        unconfirmed_reminder_judge=lambda text: True,
    )

    assert errors == []


def test_unconfirmed_reminder_output_judge_uses_injected_llm_decision():
    calls = []

    def judge(text):
        calls.append(text)
        return False

    assert (
        normal_eval.output_implies_unconfirmed_reminder(
            [{"message": "我准时催你，你觉得这个节奏怎么样？"}],
            judge=judge,
        )
        is False
    )
    assert calls == ["我准时催你，你觉得这个节奏怎么样？"]


def test_unconfirmed_reminder_llm_judge_timeout_returns_false(monkeypatch):
    class SlowJudge:
        def run(self, _prompt):
            import time

            time.sleep(1)

    monkeypatch.setattr(
        normal_eval,
        "UNCONFIRMED_REMINDER_JUDGE_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(normal_eval, "LLM_JUDGE_PROCESS_START_METHOD", "fork")
    monkeypatch.setattr(
        normal_eval,
        "_unconfirmed_reminder_judge_agent",
        lambda: SlowJudge(),
    )

    assert normal_eval.run_unconfirmed_reminder_judge("我会提醒你") is False


def test_llm_judge_timeout_process_uses_spawn_by_default(monkeypatch):
    calls = []

    class FakeProcess:
        def start(self):
            pass

        def join(self, _timeout=None):
            pass

        def is_alive(self):
            return False

    class FakeQueue:
        def empty(self):
            return False

        def get(self):
            return ("ok", True)

    class FakeContext:
        def Queue(self):
            return FakeQueue()

        def Process(self, **_kwargs):
            return FakeProcess()

    def fake_get_context(method):
        calls.append(method)
        return FakeContext()

    monkeypatch.setattr(normal_eval, "get_context", fake_get_context)

    assert normal_eval._run_clarification_output_judge_with_timeout("prompt") is True
    assert calls == ["spawn"]


def test_unconfirmed_reminder_llm_judge_rubric_allows_clarification_questions():
    prompt = normal_eval.build_unconfirmed_reminder_judge_prompt(
        "多久提醒你一次？另外，点外卖需要我设置一个提醒吗？"
    )

    assert "whether the user wants a reminder" in prompt
    assert "what frequency to use" in prompt
    assert "declarative claims" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_memory_references():
    prompt = normal_eval.build_unconfirmed_reminder_judge_prompt(
        "你不是亲口说的嘛，今晚7点要出门，我记得清清楚楚的"
    )

    assert "remembers, knows, or recalls" in prompt
    assert "not a claimed reminder action" in prompt


def test_load_cases_applies_normal_path_expectation_fixture():
    cases = normal_eval.load_cases()
    expectations = normal_eval.load_case_expectations(
        normal_eval.DEFAULT_EXPECTATIONS_PATH
    )

    assert len(expectations) <= 149
    for index, expectation in expectations.items():
        for key, value in expectation.items():
            assert cases[index].metadata[key] == value

    classes = {
        expectation.get("evaluation_expectation", "crud")
        for expectation in expectations.values()
    }
    assert {"crud", "query", "clarify", "discussion"}.issubset(classes)


def test_run_all_uses_pruned_expectation_cases_and_preserves_raw_indices():
    cases = normal_eval.load_cases()
    selected = normal_eval.select_expectation_cases(cases)

    assert len(selected) == 149
    assert selected[0].metadata["_case_index"] == 0
    assert selected[-1].metadata["_case_index"] == 444
    assert normal_eval.runtime_case_index(selected[0], fallback_index=0) == 0


def test_pending_workflow_two_turn_eval_manifest_records_open_runtime_evidence():
    manifest = normal_eval.pending_workflow_two_turn_eval_manifest()

    assert manifest["name"] == "pending-workflow-hourly-checkin-two-turn"
    assert manifest["turns"] == [
        "每个整点喊我打卡吧",
        "从现在到晚上七点",
    ]
    assert manifest["guard_modes"] == [
        "high_frequency_guards_enabled",
        "high_frequency_guards_bypassed",
    ]
    assert manifest["transport"] == "business-clawscale"
    assert manifest["evidence_status"] == (
        "open_real_model_business_clawscale_run_required"
    )


def test_validate_observations_still_requires_crud_for_call_me_with_time():
    case = normal_eval.ReminderNormalPathCase(
        input="七点叫我可以么",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={"evaluation_expectation": "crud"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "可以，七点叫你。"}],
        reminders=[],
    )

    assert "no_reminder_created" in errors


def test_case_evaluation_expectation_does_not_use_regex_fallbacks():
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={},
    )

    assert normal_eval.case_evaluation_expectation(case) == "discussion"


def test_reminder_drift_report_tracks_fixture_and_regex_metrics():
    from scripts.reminder_drift_report import build_report

    report = build_report()

    assert report["fixture_overrides"] <= 149
    assert report["workflow_regex_fast_path_markers"] == {
        "looks_like_reminder": False,
        "actionable_patterns": False,
        "explicit_reminder_patterns": False,
    }
    assert {"crud", "query", "clarify", "discussion"}.issubset(
        report["evaluation_expectation_counts"]
    )


def test_validate_observations_allows_clarification_for_implicit_time_task():
    case = normal_eval.ReminderNormalPathCase(
        input="因为我就是6点钟醒了，我还得摸一下，大概6:15开始背书",
        expected_intent="reminder",
        matched_keywords=["点钟", "开始", "背书"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "要我在6:15提醒你开始背书吗？"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_accepts_colloquial_when_clarification():
    case = normal_eval.ReminderNormalPathCase(
        input="到点提醒我，中间转一下我有没有摸鱼",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "好嘞，那你大概啥时候想让我提醒你转一下？"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_accepts_optional_confirmation_for_schedule_statement():
    case = normal_eval.ReminderNormalPathCase(
        input="七点半开始正式学习",
        expected_intent="reminder",
        matched_keywords=["点半", "开始", "学习"],
        metadata={"evaluation_expectation": "discussion"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "需要我帮你设置一个提醒吗？"}],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_allows_min_call_me_reminder():
    case = normal_eval.ReminderNormalPathCase(
        input="15min后喊我！",
        expected_intent="reminder",
        matched_keywords=["喊我", "min"],
        metadata={"evaluation_expectation": "crud"},
    )
    reminder = {
        "title": "提醒",
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 4, 29, 3, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 4, 29, 2, 45, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 4, 29, 2, 45, tzinfo=timezone.utc),
    }

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：提醒（2026-04-29 11:00）"}],
        reminders=[reminder],
    )

    assert "unexpected_reminder_created" not in errors


def test_validate_observations_accepts_created_reminder_and_matching_user_ack():
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"evaluation_expectation": "crud"},
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


def test_expected_created_reminders_strips_modal_reminder_prefix():
    expected = normal_eval.expected_created_reminders("明天早上6:30可以提醒我起床吗")

    assert expected == [
        normal_eval.ExpectedReminderCreate(
            title="起床",
            local_time="06:30:00",
            recurring=False,
        )
    ]


def test_expected_created_reminders_uses_title_after_de_reminder_clause():
    expected = normal_eval.expected_created_reminders("设置一个00:04的提醒，睡觉")

    assert expected == [
        normal_eval.ExpectedReminderCreate(
            title="睡觉",
            local_time="00:04:00",
            recurring=False,
        )
    ]


def test_expected_created_reminders_strips_nominal_reminder_suffix():
    expected = normal_eval.expected_created_reminders("唔 设置一个上午9:20 起床的提醒")

    assert expected == [
        normal_eval.ExpectedReminderCreate(
            title="起床",
            local_time="09:20:00",
            recurring=False,
        )
    ]


def test_expected_created_reminders_handles_time_ranges_without_dash_titles():
    expected = normal_eval.expected_created_reminders(
        "这是我今天的任务 11-11：30 吃饭；11：30-13：30 看法考网课；"
        "13：30-15：30 健身 15：30-16：40 吃饭 16：40-17：20 洗澡 "
        "17：20-19：00 看法考网课和做题 19：00-20：00练腹 请在这些时间点提醒我学习"
    )

    assert expected == [
        normal_eval.ExpectedReminderCreate(
            title="吃饭",
            local_time="11:30:00",
            recurring=False,
        ),
        normal_eval.ExpectedReminderCreate(
            title="看法考网课",
            local_time="13:30:00",
            recurring=False,
        ),
        normal_eval.ExpectedReminderCreate(
            title="健身",
            local_time="15:30:00",
            recurring=False,
        ),
        normal_eval.ExpectedReminderCreate(
            title="吃饭",
            local_time="16:40:00",
            recurring=False,
        ),
        normal_eval.ExpectedReminderCreate(
            title="洗澡",
            local_time="17:20:00",
            recurring=False,
        ),
        normal_eval.ExpectedReminderCreate(
            title="看法考网课和做题",
            local_time="19:00:00",
            recurring=False,
        ),
        normal_eval.ExpectedReminderCreate(
            title="练腹",
            local_time="20:00:00",
            recurring=False,
        ),
    ]


def test_validate_observations_rejects_case3_false_positive_shape():
    case = normal_eval.ReminderNormalPathCase(
        input="哦对还有，今天18:02提醒我喝水，每天18:04提醒我吃饭呢",
        expected_intent="reminder",
        matched_keywords=["提醒", "每天"],
        metadata={"evaluation_expectation": "crud"},
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
        metadata={"evaluation_expectation": "crud"},
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
        outputs=[
            {
                "message": (
                    "已创建提醒：喝水（2026-04-29 18:02）；"
                    "已创建提醒：吃饭（每天 18:04）"
                )
            }
        ],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_normalizes_title_punctuation_and_quotes():
    case = normal_eval.ReminderNormalPathCase(
        input="另外10:40提醒思考一个问题：工作应该去做“非我不可”的事情",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "思考：工作应该去做“非我不可”的事情",
                    "title_variants": ["思考一个问题:工作应该去做“非我不可”的事情"],
                    "local_time": "10:40:00",
                    "recurring": False,
                }
            ],
        },
    )
    reminders = [
        {
            "title": '思考一个问题：工作应该去做"非我不可"的事情',
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 4, 30, 1, 40, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "10:40:00",
                "timezone": "Asia/Shanghai",
                "rrule": None,
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": '已创建提醒：思考一个问题：工作应该去做"非我不可"的事情（2026-04-30 10:40）'
            }
        ],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_tolerates_common_leading_come_verb_in_title():
    case = normal_eval.ReminderNormalPathCase(
        input="20:00提醒我来法考记忆和做题",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={"evaluation_expectation": "crud"},
    )
    reminders = [
        {
            "title": "法考记忆和做题",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 4, 30, 11, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "20:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": None,
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：法考记忆和做题（2026-04-30 20:00）"}],
        reminders=reminders,
    )

    assert errors == []


def test_title_normalizer_keeps_short_lai_nouns_intact():
    assert normal_eval.expected_title_variants(
        normal_eval.ExpectedReminderCreate(
            title="来信",
            local_time="20:00:00",
            recurring=False,
        )
    ) == ["来信"]


def test_validate_observations_allows_light_action_prefix_title_match():
    case = normal_eval.ReminderNormalPathCase(
        input="16：00提醒我开始写论文文献综述（国外研究现状）",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "开始写论文文献综述（国外研究现状）",
                    "local_time": "16:00:00",
                    "recurring": False,
                }
            ],
        },
    )
    reminders = [
        {
            "title": "写论文文献综述（国外研究现状）",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 4, 29, 7, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "16:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": None,
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": "已创建提醒：写论文文献综述（国外研究现状）（2026-04-29 16:00）"
            }
        ],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_tolerates_polite_light_prefix_and_longer_title():
    case = normal_eval.ReminderNormalPathCase(
        input="如果可以的话 你8:40提醒我一下回复刘冲、Eva，约一下袁琳、浩然",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"evaluation_expectation": "crud"},
    )
    reminders = [
        {
            "title": "回复刘冲、Eva，约一下袁琳、浩然",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 4, 29, 23, 40, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "08:40:00",
                "timezone": "Asia/Tokyo",
                "rrule": None,
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": "已创建提醒：回复刘冲、Eva，约一下袁琳、浩然（2026-04-30 08:40）"
            }
        ],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_tolerates_light_connector_in_title():
    case = normal_eval.ReminderNormalPathCase(
        input="下午 1:50 提醒我起床并开始准备论文写作",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"evaluation_expectation": "crud"},
    )
    reminders = [
        {
            "title": "起床准备论文写作",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 4, 30, 4, 50, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "13:50:00",
                "timezone": "Asia/Tokyo",
                "rrule": None,
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：起床准备论文写作（2026-04-30 13:50）"}],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_tolerates_structural_de_omission_in_title():
    case = normal_eval.ReminderNormalPathCase(
        input="明天下午3点左右提醒我看数学的网课",
        expected_intent="reminder",
        matched_keywords=["提醒我"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "看数学的网课",
                    "local_time": "15:00:00",
                    "recurring": False,
                }
            ],
        },
    )
    reminders = [
        {
            "title": "看数学网课",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 11, 6, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "15:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": None,
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：看数学网课（2026-05-11 15:00）"}],
        reminders=reminders,
    )

    assert errors == []


def test_expected_created_reminders_applies_afternoon_marker_to_colon_time():
    expected = normal_eval.expected_created_reminders("下午2:30提醒我起来走一走")

    assert expected == [
        normal_eval.ExpectedReminderCreate(
            title="起来走一走",
            local_time="14:30:00",
            recurring=False,
        )
    ]


def test_validate_observations_uses_fixture_expected_creates_for_daily_schedule():
    case = normal_eval.ReminderNormalPathCase(
        input=(
            "我一般7:15起床，23:00睡觉。早上8:00开始学习，下午13:00开始健身 "
            "下午16:00开始学习。晚上20:00开始学习。我需要你在上述这些时间提醒我"
        ),
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {"title": "起床", "local_time": "07:15:00", "recurring": True},
                {
                    "title": "开始学习",
                    "title_variants": ["早上学习"],
                    "local_time": "08:00:00",
                    "recurring": True,
                },
                {
                    "title": "开始健身",
                    "title_variants": ["健身"],
                    "local_time": "13:00:00",
                    "recurring": True,
                },
                {
                    "title": "开始学习",
                    "title_variants": ["下午学习"],
                    "local_time": "16:00:00",
                    "recurring": True,
                },
                {
                    "title": "开始学习",
                    "title_variants": ["晚上学习"],
                    "local_time": "20:00:00",
                    "recurring": True,
                },
                {"title": "睡觉", "local_time": "23:00:00", "recurring": True},
            ],
        },
    )
    reminders = [
        {
            "title": title,
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": local_time,
                "timezone": "Asia/Shanghai",
                "rrule": "FREQ=DAILY",
            },
        }
        for title, local_time in [
            ("起床", "07:15:00"),
            ("早上学习", "08:00:00"),
            ("健身", "13:00:00"),
            ("下午学习", "16:00:00"),
            ("晚上学习", "20:00:00"),
            ("睡觉", "23:00:00"),
        ]
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": (
                    "已创建提醒：起床（每天 07:15）；已创建提醒：早上学习（每天 08:00）；"
                    "已创建提醒：健身（每天 13:00）；已创建提醒：下午学习（每天 16:00）；"
                    "已创建提醒：晚上学习（每天 20:00）；已创建提醒：睡觉（每天 23:00）"
                )
            }
        ],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_enforces_bounded_recurring_deadline_fixture():
    case = normal_eval.ReminderNormalPathCase(
        input="12月7号前，每天晚上八点提醒我跑步",
        expected_intent="reminder",
        matched_keywords=["提醒", "每天"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "跑步",
                    "local_time": "20:00:00",
                    "recurring": True,
                    "rrule_contains": "UNTIL",
                    "output_terms": ["截止"],
                }
            ],
        },
    )
    reminder = {
        "title": "跑步",
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 5, 11, 11, 0, tzinfo=timezone.utc),
        "schedule": {
            "local_time": "20:00:00",
            "timezone": "Asia/Tokyo",
            "rrule": "FREQ=DAILY",
        },
    }

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：跑步（每天 20:00）"}],
        reminders=[reminder],
    )

    assert "expected_rrule_missing:跑步:UNTIL" in errors
    assert "user_output_missing_expected_term:跑步:截止" in errors


def test_validate_observations_rejects_user_output_recurrence_mismatch():
    case = normal_eval.ReminderNormalPathCase(
        input="哦对还有，今天18:02提醒我喝水，每天18:04提醒我吃饭呢",
        expected_intent="reminder",
        matched_keywords=["提醒", "每天"],
        metadata={"evaluation_expectation": "crud"},
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
        outputs=[
            {
                "message": (
                    "好嘞，我已经帮你设置好了，每天18:02提醒你喝水，"
                    "18:04提醒你吃饭。"
                )
            }
        ],
        reminders=reminders,
    )

    assert "user_output_unexpected_recurring:喝水" in errors
    assert "user_output_missing_recurring:吃饭" in errors


def test_validate_observations_keeps_newline_separated_batch_ack_segments():
    case = normal_eval.ReminderNormalPathCase(
        input="今天17:57提醒我喝水，每天17:58提醒我锻炼",
        expected_intent="reminder",
        matched_keywords=["提醒", "每天"],
        metadata={"evaluation_expectation": "crud"},
    )
    reminders = [
        {
            "title": "喝水",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 7, 8, 57, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "17:57:00",
                "timezone": "Asia/Tokyo",
                "rrule": None,
            },
        },
        {
            "title": "锻炼",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 7, 8, 58, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "17:58:00",
                "timezone": "Asia/Tokyo",
                "rrule": "FREQ=DAILY",
            },
        },
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": (
                    "已创建提醒：喝水（2026-05-07 17:57）\n"
                    "已创建提醒：锻炼（每天 17:58）"
                )
            }
        ],
        reminders=reminders,
    )

    assert "user_output_unexpected_recurring:喝水" not in errors
    assert errors == []


def test_validate_observations_accepts_every_two_weeks_as_recurring_ack():
    case = normal_eval.ReminderNormalPathCase(
        input="每个奇数周周三周四晚上八点，提醒我开例会，直到17周",
        expected_intent="reminder",
        matched_keywords=["提醒", "周三", "周四"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "开例会",
                    "local_time": "20:00:00",
                    "recurring": True,
                    "rrule_contains": ["INTERVAL=2", "WE", "TH"],
                    "output_terms": ["每两周", "周四"],
                }
            ],
        },
    )
    reminders = [
        {
            "title": "开例会",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "20:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=WE,TH",
            },
        },
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": "已创建提醒：开例会（每两周的周三、周四 20:00，截止 2026-06-26 20:00）"
            }
        ],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_rejects_duplicate_reminders():
    case = normal_eval.ReminderNormalPathCase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={"evaluation_expectation": "crud"},
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
