from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId

from scripts import eval_reminder_normal_path_cases as normal_eval


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


def test_case_input_timestamp_defaults_to_current_time_for_worker_eligibility(
    monkeypatch,
):
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


def test_validate_observations_requires_reminder_for_expected_reminder_intent():
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

    assert "no_reminder_created" in errors


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
        outputs=[{"message": "取消提醒失败：keyword '晚上' matched 0 reminders"}],
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
    )

    assert "user_output_implies_unconfirmed_reminder" in errors


def test_load_cases_applies_normal_path_expectation_fixture():
    cases = normal_eval.load_cases()

    assert cases[73].metadata["evaluation_expectation"] == "clarify"
    assert cases[75].metadata["evaluation_expectation"] == "clarify"
    assert cases[86].metadata["evaluation_expectation"] == "clarify"
    assert cases[88].metadata["evaluation_expectation"] == "clarify"
    assert cases[91].metadata["evaluation_expectation"] == "clarify"
    assert cases[102].metadata["evaluation_expectation"] == "clarify"
    assert cases[107].metadata["evaluation_expectation"] == "discussion"
    assert cases[109].metadata["expected_creates"][0]["local_time"] == "20:10:00"
    assert cases[112].metadata["evaluation_expectation"] == "clarify"
    assert cases[116].metadata["evaluation_expectation"] == "discussion"
    assert cases[117].metadata["evaluation_expectation"] == "clarify"
    assert cases[122].metadata["expected_creates"][0]["recurring"] is False
    assert cases[123].metadata["expected_creates"][0]["local_time"] == "10:40:00"
    assert cases[124].metadata["evaluation_expectation"] == "query"
    assert cases[125].metadata["evaluation_expectation"] == "query"
    assert cases[130].metadata["evaluation_expectation"] == "clarify"
    assert cases[133].metadata["expected_creates"][0]["local_time"] == "19:40:00"
    assert cases[136].metadata["evaluation_expectation"] == "clarify"
    assert cases[139].metadata["evaluation_expectation"] == "query"
    assert cases[145].metadata["evaluation_expectation"] == "discussion"
    assert cases[146].metadata["evaluation_expectation"] == "discussion"
    assert cases[149].metadata["evaluation_expectation"] == "clarify"
    assert cases[150].metadata["evaluation_expectation"] == "clarify"
    assert cases[158].metadata["expected_operation"] == "delete"
    assert cases[158].metadata["allow_clarification"] is True
    assert cases[161].metadata["evaluation_expectation"] == "clarify"
    assert cases[168].metadata["expected_operation"] == "delete"
    assert cases[168].metadata["allow_clarification"] is True


def test_validate_observations_still_requires_crud_for_call_me_with_time():
    case = normal_eval.ReminderNormalPathCase(
        input="七点叫我可以么",
        expected_intent="reminder",
        matched_keywords=["叫我"],
        metadata={},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[{"message": "可以，七点叫你。"}],
        reminders=[],
    )

    assert "no_reminder_created" in errors


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


def test_validate_observations_accepts_time_choice_clarification():
    case = normal_eval.ReminderNormalPathCase(
        input="七点半开始正式学习",
        expected_intent="reminder",
        matched_keywords=["点半", "开始", "学习"],
        metadata={"evaluation_expectation": "clarify"},
    )

    errors = normal_eval.validate_observations(
        case,
        "handled",
        outputs=[
            {"message": "七点半？你是说今天晚上七点半开始学习，还是明天早上七点半呀？"}
        ],
        reminders=[],
    )

    assert errors == []


def test_validate_observations_allows_min_call_me_reminder():
    case = normal_eval.ReminderNormalPathCase(
        input="15min后喊我！",
        expected_intent="reminder",
        matched_keywords=["喊我", "min"],
        metadata={},
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


def test_expected_created_reminders_strips_modal_reminder_prefix():
    expected = normal_eval.expected_created_reminders("明天早上6:30可以提醒我起床吗")

    assert expected == [
        normal_eval.ExpectedReminderCreate(
            title="起床",
            local_time="06:30:00",
            recurring=False,
        )
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
            "expected_creates": [
                {
                    "title": "思考：工作应该去做“非我不可”的事情",
                    "title_variants": ["思考一个问题:工作应该去做“非我不可”的事情"],
                    "local_time": "10:40:00",
                    "recurring": False,
                }
            ]
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
            ]
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


def test_validate_observations_rejects_user_output_recurrence_mismatch():
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
