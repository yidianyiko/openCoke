from __future__ import annotations

from typing import Any, Mapping

import pytest

from coke.turn.v2.contracts import TurnPlan
from coke.turn.v2.param_schema import param_key_schema_payload
from coke.turn.v2.plan import (
    PlannerOutputError,
    PlanRequest,
    SiliconFlowPlanner,
)


class StubJSONClient:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self,
        *,
        system: str,
        user: dict,
        schema_name: str,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema_name": schema_name,
            }
        )
        return self.payload


def test_planner_maps_json_actions_to_turn_plan() -> None:
    client = StubJSONClient(
        {
            "actions": [
                {
                    "domain": "reminder",
                    "operation": "delete",
                    "params": {"match": "gym"},
                }
            ],
            "reply_necessity": "reply_needed",
        }
    )

    plan = SiliconFlowPlanner(client).plan(_request("delete my gym reminder"))

    assert isinstance(plan, TurnPlan)
    assert len(plan.actions) == 1
    assert plan.actions[0].domain == "reminder"
    assert plan.actions[0].operation == "delete"
    assert plan.actions[0].params["match"] == "gym"
    assert plan.reply_necessity == "reply_needed"
    assert client.calls[0]["schema_name"] == "turn_plan"


def test_empty_actions_represent_converse_or_greeting() -> None:
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "reply_needed",
        }
    )

    plan = SiliconFlowPlanner(client).plan(_request("hi"))

    assert plan.actions == ()
    assert plan.reply_necessity == "reply_needed"


def test_intentional_no_reply_is_parsed() -> None:
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "intentional_no_reply",
        }
    )

    plan = SiliconFlowPlanner(client).plan(_request("ok"))

    assert plan.reply_necessity == "intentional_no_reply"


def test_planner_rejects_unknown_domain_or_operation() -> None:
    planner = SiliconFlowPlanner(
        StubJSONClient(
            {
                "actions": [
                    {
                        "domain": "reminder",
                        "operation": "invent_id_lookup",
                        "params": {},
                    }
                ],
                "reply_necessity": "reply_needed",
            }
        )
    )

    with pytest.raises(PlannerOutputError, match="invalid action.operation"):
        planner.plan(_request("delete something"))


def test_planner_rejects_confidence_fields() -> None:
    planner = SiliconFlowPlanner(
        StubJSONClient(
            {
                "actions": [],
                "reply_necessity": "reply_needed",
                "confidence": 0.9,
            }
        )
    )

    with pytest.raises(PlannerOutputError, match="confidence"):
        planner.plan(_request("list reminders"))


def test_prompt_and_payload_expose_allowed_shape_without_precise_extraction() -> None:
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "reply_needed",
        }
    )

    SiliconFlowPlanner(client).plan(_request("提醒我明天9点跑步"))

    call = client.calls[0]
    assert "keyword/natural" in call["system"]
    assert "never IDs" in call["system"]
    assert "never precise extracted times" in call["system"]
    assert "use exactly these param keys" in call["system"]
    assert "do not invent key names" in call["system"]
    assert "confidence" in call["system"]
    assert call["user"]["allowed_domains"] == sorted(call["user"]["allowed_actions"])
    assert "reminder" in call["user"]["allowed_actions"]
    assert "create" in call["user"]["allowed_actions"]["reminder"]
    assert call["user"]["param_key_schema"] == param_key_schema_payload()
    assert call["user"]["param_key_schema"]["reminder"]["create"] == {
        "required": ["content", "time_phrase"],
        "optional": [
            "owner_account_id",
            "account_id",
            "captured_timezone",
            "display_timezone",
            "duration_minutes",
            "kind",
            "raw_text",
            "text",
        ],
    }


def _request(text: str) -> PlanRequest:
    return PlanRequest(
        account_id="acct-1",
        conversation_id="conv-1",
        payload={"text": text},
        trusted_facts={"timezone": "Asia/Tokyo"},
        focus_subject=None,
    )
