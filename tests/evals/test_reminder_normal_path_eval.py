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


def test_validate_observations_accepts_behavior_discussion_with_future_reminder_offer():
    case = normal_eval.ReminderNormalPathCase(
        input="我以为把你纯当闹钟就行了，没想到还得回复你你才会保持提醒",
        expected_intent="reminder",
        matched_keywords=["闹钟", "提醒"],
        metadata={"evaluation_expectation": "discussion"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": (
                    "啊，原来你是这么想的呀。其实提醒功能确实需要一点互动来保持活跃，"
                    "不然可能会被系统自动清理掉。"
                    "如果你有特别需要长期提醒的事项，可以随时告诉我。"
                )
            }
        ],
        reminders=[],
        clarification_judge=lambda _case_input, _output_text: False,
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
        clarification_judge=lambda _case_input, _output_text: True,
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


def test_clarification_output_llm_judge_rubric_excludes_conditional_future_offers():
    prompt = normal_eval.build_clarification_output_judge_prompt(
        "我以为把你纯当闹钟就行了，没想到还得回复你你才会保持提醒",
        "如果你有特别需要长期提醒的事项，可以随时告诉我。",
    )

    assert "conditional future offers" in prompt
    assert "do not ask for current missing reminder details" in prompt


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


def test_unconfirmed_reminder_llm_judge_rubric_allows_conditional_memory_offers():
    prompt = normal_eval.build_unconfirmed_reminder_judge_prompt(
        "如果你需要的话，我可以帮忙记着时间。"
    )

    assert "conditional offer" in prompt
    assert "requires the user's opt-in" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_reminder_capability_offers():
    prompt = normal_eval.build_unconfirmed_reminder_judge_prompt(
        "你把计划内容再发我一遍，我可以继续帮你整理或设置提醒。"
    )

    assert "Capability offers" in prompt
    assert "can help set a reminder" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_memory_references():
    prompt = normal_eval.build_unconfirmed_reminder_judge_prompt(
        "你不是亲口说的嘛，今晚7点要出门，我记得清清楚楚的"
    )

    assert "remembers, knows, or recalls" in prompt
    assert "not a claimed reminder action" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_social_return_acknowledgement():
    prompt = normal_eval.build_unconfirmed_reminder_judge_prompt(
        "下午3点见，一起继续学习"
    )

    assert "Social acknowledgements" in prompt
    assert "see you at" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_user_self_advice():
    prompt = normal_eval.build_unconfirmed_reminder_judge_prompt(
        "十分钟很快就到了，记得起来活动活动再继续干活～"
    )

    assert "Advice that tells the user to remember" in prompt
    assert "get up, rest, or resume an activity" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_future_profile_tracking():
    prompt = normal_eval.build_unconfirmed_reminder_judge_prompt(
        "我会在每次对话中告知您当前的等级和经验值。"
    )

    assert "track, record, remember, or report account/profile" in prompt
    assert "future conversations" in prompt


def test_load_cases_applies_normal_path_expectation_fixture():
    cases = normal_eval.load_cases()
    expectations = normal_eval.load_case_expectations(
        normal_eval.DEFAULT_EXPECTATIONS_PATH
    )

    assert len(expectations) <= 380
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
    expectations = normal_eval.load_case_expectations(
        normal_eval.DEFAULT_EXPECTATIONS_PATH
    )
    selected = normal_eval.select_expectation_cases(cases)

    assert len(selected) == len(expectations)
    assert selected[0].metadata["_case_index"] == 0
    assert selected[-1].metadata["_case_index"] == max(expectations)
    assert normal_eval.runtime_case_index(selected[0], fallback_index=0) == 0


def test_case_432_explicit_wakeup_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[432]

    assert case.input == "1 点 50 提醒我起床"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "起床",
            "local_time": "13:50:00",
            "recurring": False,
        }
    ]


def test_case_434_two_explicit_reminder_clauses_are_crud_create():
    cases = normal_eval.load_cases()
    case = cases[434]

    assert case.input == "希望你早上6:00叫我，晚上23:30复盘"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "叫我",
            "local_time": "06:00:00",
            "recurring": False,
        },
        {
            "title": "复盘",
            "local_time": "23:30:00",
            "recurring": False,
        },
    ]


def test_case_435_gamma_clock_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[435]

    assert case.input == "晚上十点再提醒我一下gamma这个"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "gamma",
            "local_time": "22:00:00",
            "recurring": False,
        }
    ]


def test_case_438_relative_delay_writing_break_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[438]

    assert case.input == "开始下午的写作，25分钟后提醒我站起来走动，喝水"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "站起来走动，喝水",
            "recurring": False,
        }
    ]


def test_case_439_relative_delay_activity_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[439]

    assert case.input == "半个小时后提醒我活动一下吧"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "活动一下",
            "recurring": False,
        }
    ]


def test_case_440_five_minute_return_to_writing_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[440]

    assert case.input == "好的五分钟之后提醒我回来继续写作"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "回来继续写作",
            "recurring": False,
        }
    ]


def test_case_441_relative_delay_stand_rest_drink_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[441]

    assert case.input == "25分钟之后提醒我站起来休息喝水"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "站起来休息喝水",
            "recurring": False,
        }
    ]


def test_case_442_five_minute_continue_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[442]

    assert case.input == "五分钟之后提醒我继续"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "继续",
            "recurring": False,
        }
    ]


def test_case_443_relative_delay_rest_drink_continue_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[443]

    assert case.input == "25分钟之后提醒我休息喝水，继续"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "休息喝水，继续",
            "recurring": False,
        }
    ]


def test_case_445_date_only_driver_time_change_reminder_clarifies_time():
    cases = normal_eval.load_cases()
    case = cases[445]

    assert case.input == "你明天提醒我，需要和今天的包车司机师傅们沟通，修改时间提前"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "几点",
        "时间",
        "什么时候",
    ]


def test_case_605_add_annual_summary_to_plan_requires_time_clarification():
    cases = normal_eval.load_cases()
    case = cases[605]

    assert case.input == "我下周三之前要完成年度总结的写作，这也请帮我加入计划"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "时间",
        "几点",
        "多少",
    ]


def test_case_607_eight_thirty_to_nine_study_time_clarification():
    cases = normal_eval.load_cases()
    case = cases[607]

    assert (
        case.input
        == "早上八点半到九点之间可以提醒我学习了，我大约七点多起床吃早餐"
    )
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "几点",
        "时间",
        "几点提醒",
    ]


def test_case_614_task_schedule_clarifies_content_and_task_names():
    cases = normal_eval.load_cases()
    case = cases[614]

    assert (
        case.input
        == "请按照计划中的时间，在每个任务开始和结束时提醒我"
    )
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "任务名称",
        "时间",
        "具体",
    ]


def test_case_616_memorable_reminder_requires_content_and_time():
    cases = normal_eval.load_cases()
    case = cases[616]

    assert case.input == "记得提醒我"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "什么内容",
        "什么时候",
        "具体时间",
    ]


def test_case_621_supervision_with_date_clarifies_time():
    cases = normal_eval.load_cases()
    case = cases[621]

    assert case.input == "好的 请监督我学习 你知道今天是什么日期嘛"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "时间",
        "什么时候",
        "具体时间",
    ]


def test_case_624_drug_reminder_still_clarifies_complete_input():
    cases = normal_eval.load_cases()
    case = cases[624]

    assert case.input == "7点钟提醒我吃膝盖的药"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "提醒内容",
        "具体",
        "具体时间",
        "何时",
    ]


def test_case_631_ten_minute_work_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[631]

    assert case.input == "10分钟后提醒我继续工作"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "继续工作",
            "recurring": False,
        }
    ]


def test_case_632_hourly_game_break_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[632]

    assert case.input == "一个小时后提醒我玩5分钟游戏"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "玩5分钟游戏",
            "recurring": False,
        }
    ]



def test_case_633_physics_class_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[633]

    assert case.input == "7:30提醒我上物理课"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "上物理课",
            "recurring": False,
        }
    ]


def test_case_636_weekday_signout_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[636]

    assert case.input == "对了每个工作日的十点可以提醒我签退吗"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "签退",
            "recurring": True,
        }
    ]


def test_case_637_short_walk_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[637]

    assert case.input == "5分钟后提醒我散步一分钟"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "散步一分钟",
            "recurring": False,
        }
    ]


def test_case_640_hang_clothes_integration_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[640]

    assert case.input == "一个小时之后提醒我晾内裤"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "晾内裤",
            "recurring": False,
        }
    ]


def test_case_641_game_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[641]

    assert case.input == "一个小时后提醒我玩游戏"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "玩游戏",
            "recurring": False,
        }
    ]


def test_case_642_climb_stairs_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[642]

    assert case.input == "20分钟之后提醒我爬楼"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "爬楼",
            "recurring": False,
        }
    ]


def test_case_643_midway_walk_reminder_requires_time():
    cases = normal_eval.load_cases()
    case = cases[643]

    assert case.input == "记得提醒我中途站起来走走"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "时间",
        "具体时间",
        "何时",
        "什么时候",
    ]


def test_case_644_half_hour_stairs_climb_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[644]

    assert case.input == "半个小时之后提醒我爬楼"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "爬楼",
            "recurring": False,
        }
    ]


def test_case_645_half_hour_dry_clothes_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[645]

    assert case.input == "50分钟之后提醒我晾衣服"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "晾衣服",
            "recurring": False,
        }
    ]


def test_case_646_ten_pm_ointment_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[646]

    assert case.input == "晚上10点提醒我涂药膏"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "涂药膏",
            "recurring": False,
        }
    ]


def test_case_647_nine_thirty_scraping_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[647]

    assert case.input == "晚上9:30提醒我刮痧"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "刮痧",
            "recurring": False,
        }
    ]


def test_case_650_hourly_politics_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[650]

    assert case.input == "一个小时后提醒我背政治大题"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "背政治大题",
            "recurring": False,
        }
    ]


@pytest.mark.parametrize(
    ("case_index", "input_contains", "expected_creates"),
    [
        (651, "中午十二点十分提醒我背四级单词", [{"title": "背四级单词"}]),
        (652, "然后下午一点提醒我背民法", [{"title": "背民法"}]),
        (653, "晚上六点提醒我上英语网课", [{"title": "上英语网课"}]),
        (
            656,
            "上午十一点开始叫我学习",
            [
                {"title": "叫我学习", "recurring": True},
                {"title": "问我是否完成每天的任务", "recurring": True},
            ],
        ),
        (658, "10分钟之后提醒我找厕纸", [{"title": "找厕纸"}]),
        (659, "40分钟之后提醒我去洗衣服", [{"title": "去洗衣服"}]),
        (661, "我只需要你提醒我十点半睡觉", [{"title": "睡觉"}]),
        (663, "30分钟之后提醒我找厕纸", [{"title": "找厕纸"}]),
        (665, "半个小时之后提醒我洗鼻子", [{"title": "洗鼻子"}]),
        (666, "5分钟后提醒我敷面膜", [{"title": "敷面膜"}]),
        (668, "14分钟后提醒我洗面膜", [{"title": "洗面膜"}]),
        (672, "10分钟后提醒我晾内裤", [{"title": "晾内裤"}]),
        (675, "明天六点半提醒我准备出门", [{"title": "准备出门"}]),
        (676, "20分钟后提醒我换内裤", [{"title": "换内裤"}]),
        (685, "20分钟后提醒我刷牙", [{"title": "刷牙"}]),
        (695, "周日下午五点半提醒我出门，去漕河泾", [{"title": "出门，去漕河泾", "recurring": True}]),
        (696, "明天下午一点提醒我出门吃饭", [{"title": "出门吃饭"}]),
        (702, "十二点半提醒我睡觉吧", [{"title": "睡觉"}]),
        (704, "我周一到周五下午18:00到家，可以提醒我先运动10-30分钟", [{"title": "先运动10-30分钟", "recurring": True}]),
        (707, "明天九点提醒我学习", [{"title": "学习"}]),
        (717, "药已经吃过啦", [{"title": "吃药"}, {"title": "吃药"}]),
        (
            720,
            "抽查任意2个信号词的解题技巧",
            [
                {"title": "抽查任意2个信号词的解题技巧"},
                {"title": "提交午间打卡反馈"},
                {"title": "提交晚间学习反馈"},
                {"title": "提交复盘清单"},
            ],
        ),
        (727, "每天晚上八点你可以提醒我该去学习了", [{"title": "该去学习了", "recurring": True}]),
        (728, "11点半提醒我去一食堂吃饭", [{"title": "去一食堂吃饭"}]),
    ],
)
def test_case_6xx_7xx_crud_fixture_is_loaded(
    case_index, input_contains, expected_creates
):
    cases = normal_eval.load_cases()
    case = cases[case_index]

    assert input_contains in case.input
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == expected_creates


@pytest.mark.parametrize(
    ("case_index", "input_contains", "expected_clarification_terms"),
    [
        (655, "如果我没回来你要喊我", ["什么时候", "多久", "回来"]),
        (657, "中途还是要提醒我喝水", ["喝水", "多久", "时间"]),
        (660, "不需要提醒我", ["提醒名称", "取消", "要取消"]),
        (670, "明天记得喊我学习", ["几点", "时间", "几点提醒"]),
        (678, "7:00喊我", ["做什么", "提醒", "具体内容"]),
        (680, "记得提醒我", ["具体内容", "提醒你"]),
        (683, "容易看短剧的时间段前提醒我一堆任务没做", ["具体时间", "什么时候", "多久"]),
        (689, "每天提醒我吃药啊，最近我老忘吃药", ["吃药", "每天", "几点"]),
        (691, "今天所有任务都取消，睡觉", ["提醒名称", "取消"]),
        (699, "还有你忘了要提醒我长期任务了", ["长期任务", "具体内容", "什么时间"]),
        (706, "明天八点叫我", ["做什么", "几点", "具体"]),
        (709, "你八点没叫我", ["提醒名称", "做什么", "取消"]),
        (710, "改成九点半提醒我学习吧", ["提醒时间", "提醒内容", "具体"]),
        (711, "因为今天是周末，全天都要提醒我不要看短剧喔", ["频率", "间隔", "具体时间"]),
        (712, "中间怕自己偷懒，偷偷看短剧，忘掉了自己今天要做的事", ["具体时间", "时间点", "监督"]),
        (724, "汇报时间一般是晚上，大概晚上十一点多的样子", ["几点", "提醒", "频率"]),
        (725, "设置晚上十一点半提醒吧", ["做什么", "内容"]),
    ],
)
def test_case_6xx_7xx_clarification_fixture_is_loaded(
    case_index, input_contains, expected_clarification_terms
):
    cases = normal_eval.load_cases()
    case = cases[case_index]

    assert input_contains in case.input
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == expected_clarification_terms


def test_case_446_relative_delay_activity_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[446]

    assert case.input == "正在画～20分钟后提醒我活动一下吧"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "活动一下吧",
            "recurring": False,
        }
    ]


def test_case_447_five_minute_write_paper_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[447]

    assert case.input == "5分钟后提醒我开始写论文"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "开始写论文",
            "recurring": False,
        }
    ]


def test_case_448_relative_delay_water_rest_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[448]

    assert case.input == "okk，25分钟之后，提醒我起来喝水休息"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "起来喝水休息",
            "recurring": False,
        }
    ]


def test_case_449_daily_planning_and_summary_reminders_are_crud_batch():
    cases = normal_eval.load_cases()
    case = cases[449]

    assert "每天早上7点询问我当天的规划" in case.input
    assert "每天晚上23.00告诉我" in case.input
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "询问当天规划",
            "title_variants": ["当天规划", "询问我当天的规划", "询问当天的规划"],
            "local_time": "07:00:00",
            "recurring": True,
            "rrule_contains": ["FREQ=DAILY"],
        },
        {
            "title": "告诉今天完成了哪些任务",
            "title_variants": [
                "今日完成任务总结",
                "告诉我今天完成了哪些任务",
                "我今天完成了哪些任务",
            ],
            "local_time": "23:00:00",
            "recurring": True,
            "rrule_contains": ["FREQ=DAILY"],
        },
    ]


def test_case_450_five_minute_wakeup_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[450]

    assert case.input == "五分钟提醒我起床"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "起床",
            "recurring": False,
        }
    ]


def test_case_452_schedule_list_creates_all_time_blocks():
    cases = normal_eval.load_cases()
    case = cases[452]

    assert "09:00提醒吃药喝温水" in case.input
    assert "22:00提醒护肤，泡脚" in case.input
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {"title": "吃药喝温水", "local_time": "09:00:00", "recurring": False},
        {"title": "化妆", "local_time": "09:10:00", "recurring": False},
        {"title": "国画创作", "local_time": "10:00:00", "recurring": False},
        {"title": "占星学习", "local_time": "13:30:00", "recurring": False},
        {"title": "小说创作", "local_time": "15:00:00", "recurring": False},
        {"title": "AI三件套创作视频", "local_time": "20:00:00", "recurring": False},
        {"title": "护肤，泡脚", "local_time": "22:00:00", "recurring": False},
    ]


def test_case_453_drops_date_only_reminder_task_and_keeps_21_clock():
    cases = normal_eval.load_cases()
    case = cases[453]

    assert case.input == "明天除了提醒任务之后，到晚上9:00要收起我全天学习的作业哦"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "收起全天学习的作业",
            "local_date": "2026-05-12",
            "local_time": "21:00:00",
            "recurring": False,
        }
    ]


def test_case_458_cancel_wakeup_without_existing_match_allows_clarification():
    cases = normal_eval.load_cases()
    case = cases[458]

    assert case.input == "不要6:00叫我起床"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_operation"] == "delete"
    assert case.metadata["allow_clarification"] is True


def test_case_459_bare_call_wakeup_clock_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[459]

    assert case.input == "9:00叫我起床"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "叫我起床",
            "title_variants": ["起床"],
            "local_time": "09:00:00",
            "recurring": False,
        }
    ]


def test_case_460_tomorrow_morning_start_writing_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[460]

    assert case.input == "我搞完了，明天早上9点提醒我开始写作"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "开始写作",
            "local_date": "2026-05-12",
            "local_time": "09:00:00",
            "recurring": False,
        }
    ]


def test_case_461_clock_without_reminder_content_clarifies_content():
    cases = normal_eval.load_cases()
    case = cases[461]

    assert case.input == "那你1:00提醒我一下"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "提醒内容",
        "提醒什么",
        "具体",
    ]


def test_case_464_physics_checkin_clock_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[464]

    assert case.input == "记得2:00问问我物理题做的怎么样"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "问问物理题做的怎么样",
            "local_date": "2026-05-12",
            "local_time": "02:00:00",
            "recurring": False,
        }
    ]


def test_case_465_sleep_nudge_clock_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[465]

    assert case.input == "不管我2:00搞的怎么样了都催我睡觉"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "催我睡觉",
            "title_variants": ["睡觉"],
            "local_date": "2026-05-12",
            "local_time": "02:00:00",
            "recurring": False,
        }
    ]


def test_case_467_tomorrow_wakeup_clock_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[467]

    assert case.input == "明天6:30喊我起床"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "喊我起床",
            "title_variants": ["起床"],
            "local_date": "2026-05-13",
            "local_time": "06:30:00",
            "recurring": False,
        }
    ]


def test_case_468_bare_wakeup_clock_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[468]

    assert case.input == "6:30喊我起床"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "喊我起床",
            "title_variants": ["起床"],
            "local_date": "2026-05-12",
            "local_time": "06:30:00",
            "recurring": False,
        }
    ]


def test_case_469_relative_breakfast_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[469]

    assert case.input == "5分钟后提醒我去吃早饭"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "去吃早饭",
            "recurring": False,
        }
    ]


def test_case_471_approximate_eleven_writing_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[471]

    assert case.input == "11 点左右提醒我开始写作"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "开始写作",
            "local_date": "2026-05-12",
            "local_time": "11:00:00",
            "recurring": False,
        }
    ]


def test_case_473_referential_start_time_clarifies_content():
    cases = normal_eval.load_cases()
    case = cases[473]

    assert case.input == "对的，从9:10开始提醒我吧"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "提醒内容",
        "提醒什么",
        "具体",
    ]


def test_case_474_chinese_painting_clock_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[474]

    assert case.input == "10:00开始提醒我国画创作"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "国画创作",
            "local_date": "2026-05-12",
            "local_time": "10:00:00",
            "recurring": False,
        }
    ]


def test_case_476_relative_feishu_reply_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[476]

    assert case.input == "过一小时提醒我回复飞书的消息"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "回复飞书的消息",
            "recurring": False,
        }
    ]


def test_case_479_thesis_writing_pomodoro_rest_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[479]

    assert case.input == "开始一个论文的写作番茄，25分钟之后提醒我休息"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "论文写作休息",
            "title_variants": ["休息"],
            "recurring": False,
        }
    ]


def test_case_480_afternoon_departure_clock_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[480]

    assert case.input == "下午1:40提醒我出门"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "出门",
            "local_date": "2026-05-12",
            "local_time": "13:40:00",
            "recurring": False,
        }
    ]


def test_case_481_missing_timetable_clarifies_schedule():
    cases = normal_eval.load_cases()
    case = cases[481]

    assert case.input == "你只需要根据我发的时间表提醒我什么时间学习就好了"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "时间表",
        "几点",
        "学习",
    ]


def test_case_482_bare_clock_meet_junior_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[482]

    assert case.input == "3:30提醒我见学弟"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "见学弟",
            "local_date": "2026-05-13",
            "local_time": "03:30:00",
            "recurring": False,
        }
    ]


def test_case_484_clock_without_content_clarifies_content():
    cases = normal_eval.load_cases()
    case = cases[484]

    assert case.input == "4点需要你提醒"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "提醒内容",
        "提醒什么",
        "具体",
    ]


def test_case_485_pomodoro_rest_water_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[485]

    assert case.input == "开始新的番茄，25分钟之后提醒我休息喝水"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "休息喝水",
            "recurring": False,
        }
    ]


def test_case_486_missed_three_oclock_reminder_is_query():
    cases = normal_eval.load_cases()
    case = cases[486]

    assert case.input == "你为啥3点没来提醒我？"
    assert normal_eval.case_evaluation_expectation(case) == "query"


def test_case_562_missed_ten_oclock_reminder_query():
    cases = normal_eval.load_cases()
    case = cases[562]

    assert case.input == "今天怎么没有叫我起床？"
    assert normal_eval.case_evaluation_expectation(case) == "query"


def test_case_563_missed_noon_reminder_query():
    cases = normal_eval.load_cases()
    case = cases[563]

    assert case.input == "今天怎么没有叫我起来吃药喝温水？"
    assert normal_eval.case_evaluation_expectation(case) == "query"


def test_case_692_exam_plan_discussion():
    cases = normal_eval.load_cases()
    case = cases[692]

    assert (
        case.input
        == "明天我上班时间想要看到你对我的整个考研的一个规划 比如哪个月完成哪些部分"
    )
    assert normal_eval.case_evaluation_expectation(case) == "discussion"


def test_case_693_week_plan_discussion():
    cases = normal_eval.load_cases()
    case = cases[693]

    assert (
        case.input
        == "现在就想要一个一周的计划 然后我对它进行微调 明天上班时间需要你完成一个一个月的计划"
    )
    assert normal_eval.case_evaluation_expectation(case) == "discussion"


def test_case_487_pomodoro_get_up_water_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[487]

    assert case.input == "开始25分钟的番茄，25分钟之后提醒我起来喝水"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "起来喝水",
            "recurring": False,
        }
    ]


def test_case_488_relative_rest_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[488]

    assert case.input == "25分钟之后提醒我休息"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "休息",
            "recurring": False,
        }
    ]


def test_case_490_time_correction_without_target_allows_clarification():
    cases = normal_eval.load_cases()
    case = cases[490]

    assert case.input == "你更正一下时间，你这边的时间和我相差27分钟3点钟，你都是3:27才提醒我"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_operation"] == "update"
    assert case.metadata["allow_clarification"] is True


def test_case_492_preceding_paper_task_relative_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[492]

    assert case.input == "我现在准备开始写论文了，25分钟之后提醒我"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "写论文",
            "recurring": False,
        }
    ]


def test_case_494_relative_continue_writing_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[494]

    assert case.input == "5分钟之后提醒我继续写作"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "继续写作",
            "recurring": False,
        }
    ]


def test_case_495_relative_delay_without_content_clarifies_content():
    cases = normal_eval.load_cases()
    case = cases[495]

    assert case.input == "好的好的，25分钟提醒我哦，谢谢你！你真好~"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "提醒内容",
        "提醒什么",
        "具体",
    ]


def test_case_496_relative_return_continue_writing_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[496]

    assert case.input == "好的，5分钟之后提醒我回来继续写作"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "回来继续写作",
            "recurring": False,
        }
    ]


def test_case_497_tomorrow_clock_without_content_clarifies_content():
    cases = normal_eval.load_cases()
    case = cases[497]

    assert case.input == "明天上午10点提醒我吧"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "提醒内容",
        "提醒什么",
        "具体",
    ]


def test_case_498_clock_without_content_clarifies_content():
    cases = normal_eval.load_cases()
    case = cases[498]

    assert case.input == "6点再提醒吧"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == [
        "提醒内容",
        "提醒什么",
        "具体",
    ]


def test_case_499_relative_get_up_rest_water_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[499]

    assert case.input == "25分钟之后，提醒我起来休息、喝水"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "起来休息、喝水",
            "title_variants": ["起来休息喝水"],
            "recurring": False,
        }
    ]


def test_case_501_evening_reminder_content_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[501]

    assert case.input == "晚上7点 提醒我收拾衣服 挂起来。"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "收拾衣服挂起来",
            "recurring": False,
        }
    ]


def test_case_502_evening_half_hour_reminder_is_crud_create():
    cases = normal_eval.load_cases()
    case = cases[502]

    assert case.input == "晚上7点半提醒我继续写论文"
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == [
        {
            "title": "继续写论文",
            "recurring": False,
        }
    ]


def test_case_503_clockless_content_only_reminder_clarifies_time():
    cases = normal_eval.load_cases()
    case = cases[503]

    assert case.input == "提醒我整理书籍，并且打印部分内容"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"
    assert case.metadata["expected_clarification_terms"] == ["时间", "几点", "什么时候"]


@pytest.mark.parametrize(
    "case_index,expected_input,expected_creates",
    [
        (505, "7:30提醒我开会呢", [{"title": "开会"}]),
        (
            508,
            "今晚23点提醒我睡觉",
            [{"title": "睡觉"}],
        ),
        (
            509,
            "明天7点半提醒我起床",
            [{"title": "起床"}],
        ),
        (
            510,
            "09:00提醒吃药喝温水\n09:10提醒化妆\n10:00-12:00提醒国画创作\n13:30-14:30提醒占星学习\n15:00-18:30提醒小说创作\n20:00-21:00 AI三件套创作视频\n22:00提醒护肤，泡脚",
            [
                {"title": "吃药喝温水"},
                {"title": "化妆"},
                {"title": "国画创作"},
                {"title": "占星学习"},
                {"title": "小说创作"},
                {"title": "AI三件套创作视频"},
                {"title": "护肤，泡脚"},
            ],
        ),
        (
            511,
            "09:00提醒吃药喝温水\n09:10提醒化妆\n10:00-12:00提醒书法创作\n13:30-14:30提醒占星学习\n15:00-18:30提醒小说创作\n20:00-21:00 AI三件套创作视频\n22:00提醒护肤，泡脚",
            [
                {"title": "吃药喝温水"},
                {"title": "化妆"},
                {"title": "书法创作"},
                {"title": "占星学习"},
                {"title": "小说创作"},
                {"title": "AI三件套创作视频"},
                {"title": "护肤，泡脚"},
            ],
        ),
        (513, "周六上午十点提醒我找一下jianfeng", [{"title": "找一下jianfeng"}]),
        (514, "明天上午十点半提醒我出门健身", [{"title": "出门健身"}]),
        (521, "12点提醒我吃饭", [{"title": "吃饭"}]),
        (522, "下午四点提醒我resume", [{"title": "resume"}]),
        (524, "  明天上午十点半提醒我出门健身", [{"title": "出门健身"}]),
        (541, "监督我十点半睡觉觉", [{"title": "睡觉觉"}]),
        (
            548,
            "背单词：每天早上10点的时候提醒我一次，然后晚上8点的时候提醒我一次\n\n跟练视频/靠墙站/天鹅飞：一日三餐，每次饭点的时候提醒我（我试试看，能不能看到，吃完饭就去做）",
            [
                {"title": "跟练视频/靠墙站/天鹅飞"},
                {"title": "跟练视频/靠墙站/天鹅飞"},
                {"title": "跟练视频/靠墙站/天鹅飞"},
            ],
        ),
        (553, "或者你七点叫我起来", [{"title": "叫我起来"}]),
        (554, "晚上十一点的时候，提醒我该睡觉了[破涕为笑]", [{"title": "该睡觉了"}]),
        (564, "晚一点提醒我下周找豆包手机和智谱开源项目的负责人吧", [{"title": "找豆包手机和智谱开源项目的负责人"}]),
        (
            565,
            "每天提醒以下计划。\n09:00提醒吃药喝温水\n09:10提醒化妆\n10:00-12:00提醒书法创作\n13:30-14:30提醒占星学习\n15:00-18:30提醒小说创作\n20:00-21:00 AI三件套创作视频\n22:00提醒护肤，泡脚",
            [
                {"title": "吃药喝温水"},
                {"title": "化妆"},
                {"title": "书法创作"},
                {"title": "占星学习"},
                {"title": "小说创作"},
                {"title": "AI三件套创作视频"},
                {"title": "护肤，泡脚"},
            ],
        ),
        (567, "10 点钟提醒我开始写论文", [{"title": "开始写论文"}]),
        (568, "你好 希望你晚上监督我00:00准时睡觉 ", [{"title": "准时睡觉"}]),
        (
            577,
            "英语视频在11：45的时候来催一下我就好。\n《最好不好》干音在下午5点前要录好。模块任务就好\n今天做完普通话",
            [{"title": "催一下英语视频"}],
        ),
        (574, "明天6点半起床，7点开始学习直到8点结束  学习一个小时", [{"title": "起床"}]),
        (
            578,
            "英语视频在11：45的时候来催一下我就好。\n《最好不好》干音在下午5点前要录好。\n今天做完普通话模块任务就好",
            [{"title": "催一下英语视频"}],
        ),
        (
            608,
            "晚上的复盘我打算专攻政治理论部分，你提醒我复习政治理论就行了",
            [{"title": "复习政治理论"}],
        ),
        (583, "5分钟之后提醒我继续写作", [{"title": "继续写作"}]),
        (584, "好的，25分钟之后提醒我休息", [{"title": "休息"}]),
        (585, "明天上午十点，提醒我找yiming", [{"title": "找yiming"}]),
        (586, "下午1点50分提醒我起床", [{"title": "起床"}]),
        (587, "下午两点提醒我开始写论文", [{"title": "开始写论文"}]),
        (613, "一个小时后提醒我做第三项", [{"title": "做第三项"}]),
        (615, "明天早上6：30提醒我准备出门", [{"title": "准备出门"}]),
        (618, "半小时后提醒我洗衣服", [{"title": "洗衣服"}]),
        (619, "计划提醒放到下午1 点，复盘放到晚上9点", [{"title": "计划"}, {"title": "复盘"}]),
        (622, "2小时后提醒我给花换水", [{"title": "给花换水"}]),
        (623, "1小时后提醒我洗内裤", [{"title": "洗内裤"}]),
        (624, "7点钟提醒我吃膝盖的药", [{"title": "吃膝盖的药"}]),
        (627, "从明天开始每天早上7点提醒我起床\n中午13点抽查让我放下手机\n晚上19点抽查让我放下手机\n晚上23点抽查让我放下手机", [{"title": "起床", "recurring": True}, {"title": "抽查让我放下手机", "recurring": True}, {"title": "抽查让我放下手机", "recurring": True}, {"title": "抽查让我放下手机", "recurring": True}]),
        (629, "8.30提醒我去角质", [{"title": "去角质"}]),
        (631, "10分钟后提醒我继续工作", [{"title": "继续工作"}]),
        (632, "一个小时后提醒我玩5分钟游戏", [{"title": "玩5分钟游戏"}]),
        (633, "7:30提醒我上物理课", [{"title": "上物理课"}]),
        (634, "对了每个工作日的十点可以提醒我签退吗", [{"title": "签退", "recurring": True}]),
        (637, "5分钟后提醒我散步一分钟", [{"title": "散步一分钟"}]),
        (640, "一个小时之后提醒我晾内裤", [{"title": "晾内裤"}]),
        (641, "一个小时后提醒我玩游戏", [{"title": "玩游戏"}]),
        (642, "20分钟之后提醒我爬楼", [{"title": "爬楼"}]),
        (646, "晚上10点提醒我涂药膏", [{"title": "涂药膏"}]),
        (647, "晚上9:30提醒我刮痧", [{"title": "刮痧"}]),
        (644, "半个小时之后提醒我爬楼", [{"title": "爬楼"}]),
        (645, "50分钟之后提醒我晾衣服", [{"title": "晾衣服"}]),
        (651, "中午十二点十分提醒我背四级单词", [{"title": "背四级单词"}]),
        (652, "然后下午一点提醒我背民法", [{"title": "背民法"}]),
        (653, "晚上六点提醒我上英语网课", [{"title": "上英语网课"}]),
        (658, "10分钟之后提醒我找厕纸", [{"title": "找厕纸"}]),
        (659, "40分钟之后提醒我去洗衣服", [{"title": "去洗衣服"}]),
        (661, "我只需要你提醒我十点半睡觉", [{"title": "睡觉"}]),
        (663, "30分钟之后提醒我找厕纸", [{"title": "找厕纸"}]),
        (665, "半个小时之后提醒我洗鼻子", [{"title": "洗鼻子"}]),
        (666, "5分钟后提醒我敷面膜", [{"title": "敷面膜"}]),
        (668, "14分钟后提醒我洗面膜", [{"title": "洗面膜"}]),
        (672, "10分钟后提醒我晾内裤", [{"title": "晾内裤"}]),
        (675, "明天六点半提醒我准备出门", [{"title": "准备出门"}]),
        (676, "20分钟后提醒我换内裤", [{"title": "换内裤"}]),
        (678, "7:00喊我", [{"title": "叫我"}]),
        (679, "明天早上六点十分起床", [{"title": "起床"}]),
        (685, "20分钟后提醒我刷牙", [{"title": "刷牙"}]),
        (689, "每天提醒我吃药啊，最近我老忘吃药。", [{"title": "吃药"}]),
        (695, "周日下午五点半提醒我出门，去漕河泾", [{"title": "出门，去漕河泾"}]),
        (696, "明天下午一点提醒我出门吃饭", [{"title": "出门吃饭"}]),
        (702, "十二点半提醒我睡觉吧", [{"title": "睡觉"}]),
        (704, "我周一到周五下午18:00到家，可以提醒我先运动10-30分钟，最近身体机能有些差。【周一要开例会，也可能晚一些到家】", [{"title": "先运动10-30分钟"}]),
        (707, "明天九点提醒我学习", [{"title": "学习"}]),
        (717, "药已经吃过啦，中午和晚上你再提醒一下哈", [{"title": "吃药"}, {"title": "吃药"}]),
        (727, "行，那我上班了。对了每天晚上八点你可以提醒我该去学习了", [{"title": "该去学习了"}]),
        (728, "11点半提醒我去一食堂吃饭", [{"title": "去一食堂吃饭"}]),
        (733, "我今天需要备课，然后出去兼职上课，请你11:10提醒我备课", [{"title": "备课"}]),
        (750, "20分钟之后提醒我坐下", [{"title": "坐下"}]),
        (752, "10分钟之后提醒我散步", [{"title": "散步"}]),
        (751, "20分钟之后提醒我坐下", [{"title": "坐下"}]),
        (753, "一个小时之后提醒我吃中药", [{"title": "吃中药"}]),
        (755, "一点半提醒我去考场", [{"title": "去考场"}]),
        (757, "提醒我下午一点去考场", [{"title": "去考场"}]),
        (760, "记得下午提醒我占星课", [{"title": "占星课"}]),
        (762, "一点提醒我学习", [{"title": "学习"}]),
        (772, "半个小时之后提醒我再爬一下楼", [{"title": "再爬一下楼"}]),
        (773, "40分钟后提醒我二洗衣服", [{"title": "二洗衣服"}]),
        (774, "10分钟后提醒我贴膏药", [{"title": "贴膏药"}]),
        (776, "15分钟后提醒我冥想5分钟", [{"title": "冥想5分钟"}]),
        (779, "晚上10：00提醒我洗脚", [{"title": "洗脚"}]),
        (781, "晚上10：01提醒我洗PG", [{"title": "洗PG"}]),
        (784, "还少了一个任务，10：00提醒我洗脚", [{"title": "洗脚"}]),
        (787, "好滴好滴 两点的时候提醒我出门", [{"title": "出门"}]),
        (789, "40分钟之后提醒我晾衣服", [{"title": "晾衣服"}]),
        (793, "晚上10:30提醒我刮痧", [{"title": "刮痧"}]),
        (795, "三个小时之后提醒我吃饭", [{"title": "吃饭"}]),
        (800, "一小时后提醒我散步", [{"title": "散步"}]),
        (1000, "每天22∶12提醒我洗澡", [{"title": "洗澡", "local_time": "22:12:00", "recurring": True, "rrule_contains": ["FREQ=DAILY"]}]),
        (1001, "每个星期一到星期五的晚上22∶12提醒我洗澡", [{"title": "洗澡", "local_time": "22:12:00", "recurring": True, "rrule_contains": ["FREQ=WEEKLY", "MO", "TU", "WE", "TH", "FR"]}]),
        (1003, "7点的时候提醒我去看老师给的资料", [{"title": "去看老师给的资料", "local_time": "19:00:00", "recurring": False}]),
        (1006, "19点30分，我要开始背诵毛概，请提醒我", [{"title": "背诵毛概", "title_variants": ["开始背诵毛概"], "local_time": "19:30:00", "recurring": False}]),
        (1008, "10分钟后提醒我坐下", [{"title": "坐下", "recurring": False}]),
        (1009, "30分钟后提醒我爬楼", [{"title": "爬楼", "recurring": False}]),
        (1010, "今晚1∶40分提醒我收东西并且早点睡觉", [{"title": "收东西并且早点睡觉", "local_time": "01:40:00", "recurring": False}]),
        (1012, "半个小时之后提醒我爬楼", [{"title": "爬楼", "recurring": False}]),
        (1013, "40分钟后提醒我刷牙洗脸洗脚洗屁股", [{"title": "刷牙洗脸洗脚洗屁股", "recurring": False}]),
        (1027, "准备休息了，明天满课，请提醒我明天早上9:30考医学细胞生物学实验，晚上19:00要考无机化学", [{"title": "考医学细胞生物学实验", "local_time": "09:30:00", "recurring": False}, {"title": "考无机化学", "local_time": "19:00:00", "recurring": False}]),
    ],
)
def test_case_index_fixtures_marked_crud_create(
    case_index: int, expected_input: str, expected_creates: list[dict[str, object]]
):
    cases = normal_eval.load_cases()
    case = cases[case_index]
    assert case.input == expected_input
    assert normal_eval.case_evaluation_expectation(case) == "crud"
    assert case.metadata["expected_creates"] == expected_creates


@pytest.mark.parametrize(
    "case_index,expected_input",
    [
        (506, "估计半小时后完成，第二节完成，提醒我打包垃圾"),
        (512, "内容明天还要再看看 你可以提醒我复习"),
        (515, "你好coke，这是我明天的计划，请监督我并帮助我复盘改善，多多鼓励我哟"),
        (517, "还是按照我昨天发你那个计划来，每天准时提醒我就好了"),
        (523, "每个半小时提醒我喝水 "),
        (526, "我要是一玩手机就会给你发信息，然后你需要提醒我去学习，让我放下手机"),
        (529, "请提醒我做这些"),
        (531, "二点提醒我吧"),
        (532, "你定时间吧"),
        (533, "现在画三个小时，每小时整点提醒我活动一下"),
        (535, "需要，需要提醒我学习"),
        (536, "提醒我准备开题报告"),
        (537, "请你只在20:00点提醒我就好，其余的消息不必发"),
        (
            549,
            "背单词：每天早上10点的时候提醒我一次，然后晚上8点的时候提醒我一次\n\n跟练视频/靠墙站/天鹅飞：中午12点半的时候、下午五点半，晚上九点提醒我",
        ),
        (566, "青工委的推文 审核好了 下午4点正式推送 你提醒我一下"),
        (581, "你要记得提醒人家哦"),
        (582, "总之你要记得提醒人家哦，每分钟一次，现在开始"),
        (588, "好的 我吃完饭继续，完成这个任务后奖励自己玩一局狼人杀。记得提醒我"),
        (590, "下午按时提醒"),
        (591, "你该提醒我学习占星了呀"),
        (592, "你会记得提醒我每天指定第二天的计划吗"),
        (593, "每晚11:30提醒我"),
        (598, "长期任务不要白天提醒，每天晚上提醒我做计划的时候给我提醒"),
        (
            604,
            "状态一般，心态有点丧。监督学习和写作\n活跃时间是上午八点到晚上十一点\n复盘时间晚上十点",
        ),
        (605, "我下周三之前要完成年度总结的写作，这也请帮我加入计划"),
        (607, "早上八点半到九点之间可以提醒我学习了，我大约七点多起床吃早餐"),
        (608, "晚上的复盘我打算专攻政治理论部分，你提醒我复习政治理论就行了"),
        (643, "记得提醒我中途站起来走走"),
        (616, "记得提醒我"),
        (617, "记得提醒我"),
        (680, "记得提醒我"),
        (691, "今天所有任务都取消，睡觉"),
        (621, "好的 请监督我学习 你知道今天是什么日期嘛"),
        (625, "这几天你都不提醒我学习"),
        (636, "对了每个工作日的十点可以提醒我签退吗"),
        (650, "一个小时后提醒我背政治大题"),
        (655, "如果我没回来你要喊我"),
        (656, "嗯嗯，上午十一点开始叫我学习，然后晚上10点问我是否完成每天的任务"),
        (657, "中途还是要提醒我喝水"),
        (662, "十点半之后来给我发消息看看我是否睡觉啦"),
        (669, "习惯（每天）：6:20起床、6:30洗漱、6:45吃早餐、7:00练习英语口语（练25分钟）、7:30开始早读（45分钟）、8:30开始上网课（我明天开始每天把我一天要学的计划发给你）、11:00我要煮饭、11:50我要做饭、13:00我要眯半个小时、13:30起来我要开始上网课、17:00我要出去散步、17:40我要煮饭、煮完饭后我再上一节课，后面我吃完晚饭散步回来大概20:00，我要开始背书、23:30睡觉"),
        (670, "明天记得喊我学习"),
        (699, "还有你忘了要提醒我长期任务了"),
        (700, "我想复习期末考，不需要监督，就我想学的时候告诉你我想在几点学，提醒我学然后时不时抽查什么的就行，要是有奖励和惩罚就更好了"),
        (709, "你八点没叫我"),
        (706, "明天八点叫我"),
        (710, "改成九点半提醒我学习吧"),
        (711, "因为今天是周末，全天都要提醒我不要看短剧喔"),
        (712, "中间怕自己偷懒，偷偷看短剧，忘掉了自己今天要做的事，所以让你来多次来监督。提醒我一下，看我有没有做到。"),
        (715, "你一定要记得多来监督提醒我今天有这些事情要做哈。我怕自己看短剧摸鱼偷懒。"),
        (719, "今天下午提醒我复习专业课捏"),
        (725, "设置晚上十一点半提醒吧"),
        (724, "汇报时间一般是晚上，大概晚上十一点多的样子，当然你也可以提醒我来汇报进度。如果我是凌晨给你汇报的，那都算在前一天里，我有时候会学到凌晨"),
        (734, "1:30开始，我会在1:05出门，请你1:00提醒我出门"),
        (736, "考试时间大概是28.29.30号记得提醒我今天看书"),
        (737, "记得提醒我什么时候该休息什么时候要学习"),
        (739, "记得提醒我什么时候该休息什么时候要学习"),
        (754, "提醒我两点之前背完12篇问诊"),
        (743, "60分钟后提醒我爬楼"),
        (744, "那在每天晚上9点问我明日的计划吧"),
        (745, "记得提醒我"),
        (748, "你上午没有提醒我哦"),
        (749, "你要合理分配时间并提醒我"),
        (761, "记得提醒我"),
        (764, "你可以在13:20提醒我"),
        (768, "你现在 监督我起床 然后下去吃饭 下午的目标是打开电脑，修改场景插画，下单冰箱贴和方卡，完成周三海报"),
        (769, "你早上会叫我起床吗"),
        (768, "你现在 监督我起床 然后下去吃饭 下午的目标是打开电脑，修改场景插画，下单冰箱贴和方卡，完成周三海报"),
        (785, "期间半小时提醒我一次"),
        (790, "好的，准时提醒我"),
        (720, "时段\t科目\t具体任务\t限时要求\t督学检查要点\t\n9:00-9:30\t职测\t1. 默写言语理解四大类信号词：   - 转折：但是、然而、其实、事实上   - 因果：因此、所以、故而、正因如此   - 对策：必须、需要、应当、亟待   - 并列：同时、此外、一方面…另一方面…2. 复述对应易错点：转折前是干扰项、并列要全面概括\t30min\t抽查任意2个信号词的解题技巧，要求脱口而出\t\n9:30-10:15\t职测\t刷言语理解整套题（选词填空20题+中心理解30题+语句表达10题），总题量60题要求：用“？”标记不确定题目，不核对答案，严格限时\t45min\t检查是否完成60题，不确定题是否标注，有无超时\t\n10:15-10:30\t-\t休息15min，远眺放松，禁止看手机、翻资料\t15min\t强制休息，避免疲劳刷题影响正确率\t\n10:30-11:30\t职测\t错题初筛，逐题标注3类具体错误类型（禁止写“不会做”）：1. 信号词遗漏（如漏看“因此”）2. 选项辨析错误（如搭配不当/片面表述）3. 语句表达逻辑混乱（如语序/衔接不当）\t60min\t检查错误类型标注是否精准，是否每道错题都对应技巧漏洞\t\n12:30\t-\t提交午间打卡反馈\t5min\t反馈示例：“言语刷题用时42min，正确率78%，集中错并列文段片面选项” \t\n14:20-16:20\t综应\t观看概念分析题专项课程（2课时），按模块记录笔记：1. 关键词定位技巧：高频词定位法、首尾句定位法、关联词定位法（附课程示例）2. 要素提取类型：内涵类、特征类、措施类（区分不同类型的答题侧重点）3. 规范表述要求：分点用“一是/二是”、关键词前置、每点不超过15字\t120min\t检查笔记是否分模块记录，是否附课程典型例子，逻辑是否清晰\t\n16:20-17:20\t综应\t整理概念分析题型框架手账（1张A4纸），内容包含：左侧：技巧清单（定位+提取+表述）右侧：课程示例（1道简单例题的完整答题步骤）\t60min\t检查手账是否简洁实用，能否直接作为后续做题的参考模板\t\n19:00-20:00\t职测\t补练触发条件与任务：→ 若言语正确率＜75%：加练并列文段专项题20道，必须套用“全面概括”技巧→ 若正确率≥75%：复盘上午错题，补充速记卡中并列题型的易错点\t60min\t补练题需标注技巧应用痕迹，禁止凭语感做题\t\n20:00\t-\t提交晚间反馈\t5min\t如实反馈综应课程学习和笔记整理情况，是否有未理解的知识点\t\n20:00-21:00\t职测\t1. 整理言语错题规律，重点补充并列题型的易错点（如“片面表述”“无中生有”）2. 更新言语理解速记卡，新增并列题型的解题口诀\t60min\t检查速记卡是否更新完善，口诀是否简洁好记\t\n21:00-22:00\t综应\t1. 背诵概念分析关键词定位口诀：“高频词优先找，首尾句跑不了，关联词是信号，要素提炼准又巧”2. 默写概念分析答题框架（定位→提取→表述），确保无遗漏\t60min\t检查是否能熟练背诵口诀、完整默写框架\t\n21:30\t-\t提交复盘清单\t5min\t提交示例：“职测易错点：并列词‘此外’后内容易忽略；综应干货技巧：概念分析先划材料高频词”"),
    ],
)
def test_case_index_fixtures_marked_reminder_clarification(
    case_index: int, expected_input: str
):
    cases = normal_eval.load_cases()
    case = cases[case_index]
    if case_index == 720:
        assert case.input.startswith(
            "时段\t科目\t具体任务\t限时要求\t督学检查要点"
        )
        assert "21:30\t-\t提交复盘清单\t5min" in case.input
    else:
        assert case.input == expected_input
    assert normal_eval.case_evaluation_expectation(case) == "clarify"


def test_case_731_fixtures_marked_reminder_clarification_input():
    case = normal_eval.load_cases()[731]
    assert case.input == "而且中间我还会上班，可能会穿插一些工作上的事情需要你监督提醒我"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"


def test_case_732_fixtures_marked_reminder_clarification_input():
    case = normal_eval.load_cases()[732]
    assert case.input == "我明年考研哦，从今天开始倒数365天，你要监督我每天学习哦"
    assert normal_eval.case_evaluation_expectation(case) == "clarify"


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

    assert report["fixture_overrides"] <= 380
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


def test_validate_observations_allows_minute_precision_for_expected_local_time():
    case = normal_eval.ReminderNormalPathCase(
        input="过5分钟叫我",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {"title": "叫我", "local_time": "08:45:00", "recurring": False}
            ],
        },
    )
    reminder = {
        "title": "叫我",
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 5, 10, 23, 45, 17, tzinfo=timezone.utc),
        "schedule": {
            "local_time": "08:45:17",
            "timezone": "Asia/Tokyo",
            "rrule": None,
        },
    }

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：叫我（2026-05-11 08:45）"}],
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


def test_validate_observations_rejects_unexpected_extra_fixture_create():
    case = normal_eval.ReminderNormalPathCase(
        input="15点-16点起床，开始帮我每小时打卡，打卡持续到20点",
        expected_intent="reminder",
        matched_keywords=["打卡"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "打卡",
                    "local_time": "15:00:00",
                    "recurring": True,
                    "rrule_contains": ["FREQ=HOURLY", "UNTIL"],
                }
            ],
        },
    )
    reminders = [
        {
            "title": "打卡",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 11, 6, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "15:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": "FREQ=HOURLY;UNTIL=20260511T110000Z",
            },
        },
        {
            "title": "起床",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 11, 6, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "15:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": "FREQ=HOURLY;UNTIL=20260511T110000Z",
            },
        },
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": (
                    "已创建提醒：打卡（2026-05-11 15:00，"
                    "循环规则 FREQ=HOURLY;UNTIL=20260511T110000Z）\n"
                    "已创建提醒：起床（2026-05-11 15:00，"
                    "循环规则 FREQ=HOURLY;UNTIL=20260511T110000Z）"
                )
            }
        ],
        reminders=reminders,
    )

    assert "unexpected_reminder_count_mismatch:2>1" in errors


def test_validate_observations_accepts_recurring_output_when_title_contains_comma():
    case = normal_eval.ReminderNormalPathCase(
        input="从明天早上7点到晚上11点，每小时提醒一次及时完成任务，及时打卡",
        expected_intent="reminder",
        matched_keywords=["每小时", "提醒"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "及时完成任务，及时打卡",
                    "local_time": "07:00:00",
                    "recurring": True,
                    "rrule_contains": ["FREQ=HOURLY", "UNTIL"],
                }
            ],
        },
    )
    reminders = [
        {
            "title": "及时完成任务，及时打卡",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 11, 22, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "07:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": "FREQ=HOURLY;UNTIL=20260512T140000Z",
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": (
                    "已创建提醒：及时完成任务，及时打卡（2026-05-12 07:00，"
                    "循环规则 FREQ=HOURLY;UNTIL=20260512T140000Z）"
                )
            }
        ],
        reminders=reminders,
    )

    assert errors == []


def test_validate_observations_rejects_expected_create_date_mismatch():
    case = normal_eval.ReminderNormalPathCase(
        input="22号早上9点提醒我给医院打电话预约手术",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "给医院打电话预约手术",
                    "local_date": "2026-05-22",
                    "local_time": "09:00:00",
                    "recurring": False,
                }
            ],
        },
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：给医院打电话预约手术（2026-05-12 09:00）"}],
        reminders=[
            {
                "title": "给医院打电话预约手术",
                "lifecycle_state": "active",
                "next_fire_at": datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc),
                "schedule": {
                    "local_date": "2026-05-12",
                    "local_time": "09:00:00",
                    "timezone": "Asia/Tokyo",
                    "rrule": None,
                },
            }
        ],
    )

    assert "expected_reminder_date_mismatch:给医院打电话预约手术" in errors


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


def test_title_matching_accepts_colon_qualified_short_title():
    expected = normal_eval.ExpectedReminderCreate(
        title="番茄钟",
        local_time="11:46:00",
        recurring=False,
    )

    assert normal_eval.find_matching_reminder(
        expected,
        [
            {
                "title": "番茄钟：论文写作",
                "schedule": {"local_time": "11:46:00"},
            }
        ],
    )


def test_output_title_matching_reuses_created_title_variant_semantics():
    expected = normal_eval.ExpectedReminderCreate(
        title="约面试",
        title_variants=("去面试对方（约对方）",),
        local_time="11:00:00",
        recurring=False,
    )

    assert normal_eval.output_mentions_expected_title(
        "已创建提醒：约对方（2026-05-11 11:00）",
        expected,
    )


def test_validate_observations_tolerates_trailing_light_action_particle():
    case = normal_eval.ReminderNormalPathCase(
        input="5点叫我一下",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {
                    "title": "叫我一下",
                    "local_time": "05:00:00",
                    "recurring": False,
                }
            ],
        },
    )
    reminders = [
        {
            "title": "叫我",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 10, 20, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "05:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": None,
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "已创建提醒：叫我（2026-05-11 05:00）"}],
        reminders=reminders,
    )

    assert errors == []


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


def test_validate_observations_accepts_rrule_text_as_recurring_ack():
    case = normal_eval.ReminderNormalPathCase(
        input="开始帮我每小时打卡持续到20点",
        expected_intent="reminder",
        matched_keywords=["每小时", "打卡"],
        metadata={
            "evaluation_expectation": "crud",
            "expected_creates": [
                {"title": "打卡", "local_time": "15:00:00", "recurring": True}
            ],
        },
    )
    reminders = [
        {
            "title": "打卡",
            "lifecycle_state": "active",
            "next_fire_at": datetime(2026, 5, 11, 6, 0, tzinfo=timezone.utc),
            "schedule": {
                "local_time": "15:00:00",
                "timezone": "Asia/Tokyo",
                "rrule": "FREQ=HOURLY;UNTIL=20260511T110000Z",
            },
        }
    ]

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {
                "message": "已创建提醒：打卡（2026-05-11 15:00，循环规则 FREQ=HOURLY;UNTIL=20260511T110000Z）"
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
