from __future__ import annotations

from typing import Any, Mapping

import pytest

from coke.turn.inbound.contracts import TurnPlan
from coke.turn.inbound.param_schema import param_key_schema_payload
from coke.turn.inbound.plan import (
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
    assert "batch_create items follow the same rule" in call["system"]
    assert "omit trigger_time and duration_minutes from natural-language batch items" in (
        call["system"]
    )
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


def test_prompt_requires_iana_timezone_for_settings_timezone_text() -> None:
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "reply_needed",
        }
    )

    SiliconFlowPlanner(client).plan(_request("把我的时区改成东京"))

    system = client.calls[0]["system"]
    assert "settings.set_timezone" in system
    assert "timezone_text MUST be a valid IANA timezone identifier" in system
    assert 'e.g. "Asia/Tokyo", "America/New_York"' in system
    assert "never a bare city name" in system


def test_prompt_keeps_vague_mutation_requests_as_the_requested_action() -> None:
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "reply_needed",
        }
    )

    SiliconFlowPlanner(client).plan(_request("删掉提醒"))

    system = client.calls[0]["system"]
    assert "delete/remove/cancel/complete request is ALWAYS that action" in system
    assert "never substitute a list" in system
    assert "needs_choice/needs_input" in system


def test_prompt_treats_shared_time_only_reschedule_as_update_without_duration() -> None:
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "reply_needed",
        }
    )

    SiliconFlowPlanner(client).plan(
        _request("把我和 lizihao 的 openCoke 改到明天下午4点")
    )

    system = client.calls[0]["system"]
    assert "When the user only changes an existing shared reminder time" in system
    assert "use social_scheduling.update_shared_reminder" in system
    assert "include the new time as time_phrase" in system
    assert "do not ask for duration" in system


def test_prompt_routes_friend_schedule_questions_to_availability_not_shared_list() -> (
    None
):
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "reply_needed",
        }
    )

    SiliconFlowPlanner(client).plan(_request("oliver今天有什么安排"))

    system = client.calls[0]["system"]
    assert "friend's schedule/availability/agenda" in system
    assert "social_scheduling.availability_query" in system
    assert "date_phrase" in system
    assert "list_shared is only for the user's own shared reminders" in system
    assert "我和oliver的共享提醒" in system


def test_prompt_requires_explicit_period_words_to_stay_in_time_phrase() -> None:
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "reply_needed",
        }
    )

    SiliconFlowPlanner(client).plan(_request("不对 是晚上六点"))

    system = client.calls[0]["system"]
    assert "explicit period-of-day words" in system
    assert "keep the period word attached to the time_phrase" in system
    assert "晚上/下午/上午/早上/中午" in system


def test_prompt_treats_contextual_date_correction_as_converse_not_new_schedule() -> (
    None
):
    client = StubJSONClient(
        {
            "actions": [],
            "reply_necessity": "reply_needed",
        }
    )
    history = (
        {
            "role": "user",
            "content": "为什么oliver今天会有开会的日程呢",
            "seq": 21,
        },
        {"role": "assistant", "content": "之前帮他约的，改到晚上6点。"},
    )
    focus_subject = {
        "subject_type": "shared_reminder",
        "object_ids": ["shared-1"],
        "ordered": True,
    }

    plan = SiliconFlowPlanner(client).plan(
        _request(
            "不是明天吗？",
            conversation_history=history,
            focus_subject=focus_subject,
        )
    )

    assert plan.actions == ()
    assert plan.reply_necessity == "reply_needed"
    call = client.calls[0]
    system = call["system"]
    assert "short contradiction/correction" in system
    assert "不是明天吗" in system
    assert "use empty actions with reply_needed" in system
    assert "focus_subject is the typed subject" in system
    assert call["user"]["conversation_history"] == [dict(item) for item in history]
    assert call["user"]["focus_subject"] == focus_subject


def _request(
    text: str,
    *,
    conversation_history: tuple[Mapping[str, Any], ...] = (),
    focus_subject: Any | None = None,
) -> PlanRequest:
    return PlanRequest(
        account_id="acct-1",
        conversation_id="conv-1",
        payload={"text": text},
        trusted_facts={"timezone": "Asia/Tokyo"},
        conversation_history=conversation_history,
        focus_subject=focus_subject,
    )


def test_planner_prompt_forbids_generic_reminder_match_keyword():
    from coke.turn.inbound.plan import TURN_PLANNER_SYSTEM_PROMPT

    assert "never the generic word" in TURN_PLANNER_SYSTEM_PROMPT
    assert "OMIT `match`" in TURN_PLANNER_SYSTEM_PROMPT
