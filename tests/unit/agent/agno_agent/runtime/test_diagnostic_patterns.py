from agent.agno_agent.runtime.diagnostic_patterns import (
    check_prohibited_claims,
    check_required_facts,
    check_required_questions,
)
from agent.agno_agent.runtime.domain_results import (
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
    ReplyFactRequirement,
)


def _executed_result() -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-1",
                facts={
                    "title": "喝水",
                    "local_date": "2026-05-22",
                    "local_time": "22:06:00",
                    "timezone": "Asia/Tokyo",
                },
            ),
        ),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="confirm_execution",
            required_facts=(
                ReplyFactRequirement(path="operations[0].facts.title"),
                ReplyFactRequirement(
                    path="operations[0].facts.local_time", label="time"
                ),
            ),
            required_questions=(),
            prohibited_claims=("not_created",),
            allow_rephrase=True,
        ),
    )


def test_check_required_facts_accepts_literal_and_time_variant():
    result = _executed_result()

    assert check_required_facts(result, "已创建提醒：喝水（22:06）") == []


def test_check_required_facts_reports_missing_fact_path():
    result = _executed_result()

    assert check_required_facts(result, "已创建提醒。") == [
        "missing required fact operations[0].facts.title",
        "missing required fact operations[0].facts.local_time",
    ]


def test_check_required_questions_resolves_label_to_patterns():
    contract = ReplyContract(
        intent="ask_clarification",
        required_facts=(),
        required_questions=("end_time",),
        prohibited_claims=(),
        allow_rephrase=True,
    )

    assert check_required_questions(contract, "这个提醒要持续到什么时候结束？") == []
    assert check_required_questions(contract, "请补充信息。") == [
        "missing required question end_time"
    ]


def test_check_prohibited_claims_resolves_label_not_literal_string():
    contract = ReplyContract(
        intent="ask_clarification",
        required_facts=(),
        required_questions=("end_time",),
        prohibited_claims=("reminder_created",),
        allow_rephrase=True,
    )

    assert check_prohibited_claims(contract, "reminder_created") == []
    assert check_prohibited_claims(contract, "已创建提醒：喝水") == [
        "prohibited claim reminder_created"
    ]
