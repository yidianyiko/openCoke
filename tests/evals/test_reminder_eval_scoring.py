from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.reminder_eval import judges
from scripts.reminder_eval import scoring as normal_eval
from scripts.reminder_eval.dataset import (
    DEFAULT_EXPECTATIONS_PATH,
    ExpectedReminderCreate,
    ReminderNormalPathCase,
)

_ORIGINAL_RUN_CLARIFICATION_OUTPUT_JUDGE = judges.run_clarification_output_judge


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


def test_validate_observations_requires_user_visible_crud_ack():
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
        judges,
        "CLARIFICATION_OUTPUT_JUDGE_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(judges, "LLM_JUDGE_PROCESS_START_METHOD", "fork")
    monkeypatch.setattr(
        judges,
        "_clarification_output_judge_agent",
        lambda: SlowJudge(),
    )
    monkeypatch.setattr(
        judges,
        "run_clarification_output_judge",
        _ORIGINAL_RUN_CLARIFICATION_OUTPUT_JUDGE,
    )

    assert judges.run_clarification_output_judge("提醒我写作", "几点提醒你？") is False


def test_clarification_output_llm_judge_rubric_covers_missing_cadence():
    prompt = judges.build_clarification_output_judge_prompt(
        "10点到11点写作，随时提醒我专注",
        "专注提醒的频率是多少呢？",
    )

    assert "cadence/frequency" in prompt
    assert "proposed option" in prompt
    assert "structured schema" in prompt


def test_clarification_output_llm_judge_rubric_excludes_conditional_future_offers():
    prompt = judges.build_clarification_output_judge_prompt(
        "我以为把你纯当闹钟就行了，没想到还得回复你你才会保持提醒",
        "如果你有特别需要长期提醒的事项，可以随时告诉我。",
    )

    assert "conditional future offers" in prompt
    assert "do not ask for current missing reminder details" in prompt


def test_clarification_output_rejects_unconfirmed_future_reminder_commitment():
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
        judges,
        "UNCONFIRMED_REMINDER_JUDGE_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(judges, "LLM_JUDGE_PROCESS_START_METHOD", "fork")
    monkeypatch.setattr(
        judges,
        "_unconfirmed_reminder_judge_agent",
        lambda: SlowJudge(),
    )

    assert judges.run_unconfirmed_reminder_judge("我会提醒你") is False


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

    monkeypatch.setattr(judges, "get_context", fake_get_context)

    assert judges._run_clarification_output_judge_with_timeout("prompt") is True
    assert calls == ["spawn"]


def test_unconfirmed_reminder_llm_judge_rubric_allows_clarification_questions():
    prompt = judges.build_unconfirmed_reminder_judge_prompt(
        "多久提醒你一次？另外，点外卖需要我设置一个提醒吗？"
    )

    assert "whether the user wants a reminder" in prompt
    assert "what frequency to use" in prompt
    assert "declarative claims" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_conditional_memory_offers():
    prompt = judges.build_unconfirmed_reminder_judge_prompt(
        "如果你需要的话，我可以帮忙记着时间。"
    )

    assert "conditional offer" in prompt
    assert "requires the user's opt-in" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_reminder_capability_offers():
    prompt = judges.build_unconfirmed_reminder_judge_prompt(
        "你把计划内容再发我一遍，我可以继续帮你整理或设置提醒。"
    )

    assert "Capability offers" in prompt
    assert "can help set a reminder" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_memory_references():
    prompt = judges.build_unconfirmed_reminder_judge_prompt(
        "你不是亲口说的嘛，今晚7点要出门，我记得清清楚楚的"
    )

    assert "remembers, knows, or recalls" in prompt
    assert "not a claimed reminder action" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_social_return_acknowledgement():
    prompt = judges.build_unconfirmed_reminder_judge_prompt("下午3点见，一起继续学习")

    assert "Social acknowledgements" in prompt
    assert "see you at" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_user_self_advice():
    prompt = judges.build_unconfirmed_reminder_judge_prompt(
        "十分钟很快就到了，记得起来活动活动再继续干活～"
    )

    assert "Advice that tells the user to remember" in prompt
    assert "get up, rest, or resume an activity" in prompt


def test_unconfirmed_reminder_llm_judge_rubric_allows_future_profile_tracking():
    prompt = judges.build_unconfirmed_reminder_judge_prompt(
        "我会在每次对话中告知您当前的等级和经验值。"
    )

    assert "track, record, remember, or report account/profile" in prompt
    assert "future conversations" in prompt


def test_validate_observations_still_requires_crud_for_call_me_with_time():
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
        ExpectedReminderCreate(
            title="喝水",
            local_time="18:02:00",
            recurring=False,
        ),
        ExpectedReminderCreate(
            title="吃饭",
            local_time="18:04:00",
            recurring=True,
        ),
    ]


def test_expected_created_reminders_strips_modal_reminder_prefix():
    expected = normal_eval.expected_created_reminders("明天早上6:30可以提醒我起床吗")

    assert expected == [
        ExpectedReminderCreate(
            title="起床",
            local_time="06:30:00",
            recurring=False,
        )
    ]


def test_expected_created_reminders_uses_title_after_de_reminder_clause():
    expected = normal_eval.expected_created_reminders("设置一个00:04的提醒，睡觉")

    assert expected == [
        ExpectedReminderCreate(
            title="睡觉",
            local_time="00:04:00",
            recurring=False,
        )
    ]


def test_expected_created_reminders_strips_nominal_reminder_suffix():
    expected = normal_eval.expected_created_reminders("唔 设置一个上午9:20 起床的提醒")

    assert expected == [
        ExpectedReminderCreate(
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
        ExpectedReminderCreate(
            title="吃饭",
            local_time="11:30:00",
            recurring=False,
        ),
        ExpectedReminderCreate(
            title="看法考网课",
            local_time="13:30:00",
            recurring=False,
        ),
        ExpectedReminderCreate(
            title="健身",
            local_time="15:30:00",
            recurring=False,
        ),
        ExpectedReminderCreate(
            title="吃饭",
            local_time="16:40:00",
            recurring=False,
        ),
        ExpectedReminderCreate(
            title="洗澡",
            local_time="17:20:00",
            recurring=False,
        ),
        ExpectedReminderCreate(
            title="看法考网课和做题",
            local_time="19:00:00",
            recurring=False,
        ),
        ExpectedReminderCreate(
            title="练腹",
            local_time="20:00:00",
            recurring=False,
        ),
    ]


def test_validate_observations_rejects_case3_false_positive_shape():
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
        ExpectedReminderCreate(
            title="来信",
            local_time="20:00:00",
            recurring=False,
        )
    ) == ["来信"]


def test_title_matching_accepts_colon_qualified_short_title():
    expected = ExpectedReminderCreate(
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
    expected = ExpectedReminderCreate(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
        ExpectedReminderCreate(
            title="起来走一走",
            local_time="14:30:00",
            recurring=False,
        )
    ]


def test_validate_observations_uses_fixture_expected_creates_for_daily_schedule():
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
    case = ReminderNormalPathCase(
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
