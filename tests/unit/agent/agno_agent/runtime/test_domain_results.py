import pytest

from agent.agno_agent.runtime.domain_results import (
    DomainError,
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
    ReplyFactRequirement,
)


def _reply_contract() -> ReplyContract:
    return ReplyContract(
        intent="confirm_execution",
        required_facts=(
            ReplyFactRequirement(path="operations[0].facts.title"),
            ReplyFactRequirement(path="operations[0].facts.local_time", label="time"),
        ),
        allow_rephrase=True,
    )


def test_domain_execution_result_round_trips_json_dict():
    result = DomainExecutionResult(
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
                    "title": "drink water",
                    "local_date": "2026-05-22",
                    "local_time": "22:06:00",
                    "timezone": "Asia/Tokyo",
                    "rrule": None,
                    "conversation_id": "conv-1",
                },
            ),
        ),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=_reply_contract(),
    )

    payload = result.to_dict()

    assert payload == {
        "domain": "reminder",
        "outcome": "executed",
        "operations": [
            {
                "action": "create",
                "ok": True,
                "effect": "write",
                "entity_type": "reminder",
                "entity_id": "rem-1",
                "facts": {
                    "title": "drink water",
                    "local_date": "2026-05-22",
                    "local_time": "22:06:00",
                    "timezone": "Asia/Tokyo",
                    "rrule": None,
                    "conversation_id": "conv-1",
                },
                "error": None,
            }
        ],
        "missing_fields": [],
        "safety_boundary": None,
        "reply_contract": {
            "intent": "confirm_execution",
            "required_facts": [
                {"path": "operations[0].facts.title", "label": None},
                {"path": "operations[0].facts.local_time", "label": "time"},
            ],
            "allow_rephrase": True,
        },
        "error": None,
    }
    assert DomainExecutionResult.from_dict(payload) == result


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "outcome": "executed",
                "operations": (),
                "missing_fields": (),
                "safety_boundary": None,
                "error": None,
            },
            "executed requires at least one successful operation",
        ),
        (
            {
                "outcome": "needs_clarification",
                "operations": (),
                "missing_fields": (),
                "safety_boundary": None,
                "error": None,
            },
            "needs_clarification requires missing_fields or safety_boundary",
        ),
        (
            {
                "outcome": "rejected",
                "operations": (),
                "missing_fields": (),
                "safety_boundary": None,
                "error": None,
            },
            "rejected requires safety_boundary",
        ),
        (
            {
                "outcome": "failed",
                "operations": (),
                "missing_fields": (),
                "safety_boundary": None,
                "error": None,
            },
            "failed requires error",
        ),
        (
            {
                "outcome": "no_action",
                "operations": (
                    DomainOperationResult(
                        action="none",
                        ok=True,
                        effect="none",
                        entity_type="reminder",
                        entity_id=None,
                        facts={},
                    ),
                ),
                "missing_fields": (),
                "safety_boundary": None,
                "error": None,
            },
            "no_action requires operations == ()",
        ),
    ],
)
def test_domain_execution_result_enforces_outcome_invariants(kwargs, message):
    with pytest.raises(ValueError, match=message):
        DomainExecutionResult(
            domain="reminder",
            reply_contract=ReplyContract(
                intent="direct_answer",
                required_facts=(),
                allow_rephrase=True,
            ),
            **kwargs,
        )


def test_failed_result_allows_structured_error_detail():
    result = DomainExecutionResult(
        domain="scheduling",
        outcome="failed",
        operations=(),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="report_failure",
            required_facts=(),
            allow_rephrase=True,
        ),
        error=DomainError(
            code="no_tool_called",
            message="Scheduling execution agent did not call a tool",
            retryable=True,
            detail={"intent": "create_shared_reminder"},
        ),
    )

    assert result.error is not None
    assert result.error.to_dict() == {
        "code": "no_tool_called",
        "message": "Scheduling execution agent did not call a tool",
        "retryable": True,
        "detail": {"intent": "create_shared_reminder"},
    }
    assert DomainExecutionResult.from_dict(result.to_dict()) == result


def test_from_dict_rejects_invalid_literal_values():
    payload = DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-1",
                facts={"title": "drink water"},
            ),
        ),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=_reply_contract(),
    ).to_dict()

    invalid_payloads = [
        ("domain", {**payload, "domain": "notes"}),
        ("outcome", {**payload, "outcome": "maybe_done"}),
        (
            "effect",
            {
                **payload,
                "operations": [{**payload["operations"][0], "effect": "mutate"}],
            },
        ),
        (
            "intent",
            {
                **payload,
                "reply_contract": {
                    **payload["reply_contract"],
                    "intent": "say_anything",
                },
            },
        ),
    ]

    for field_name, invalid_payload in invalid_payloads:
        with pytest.raises(ValueError, match=f"unsupported {field_name}"):
            DomainExecutionResult.from_dict(invalid_payload)
