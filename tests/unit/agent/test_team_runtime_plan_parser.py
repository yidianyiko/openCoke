def test_parse_response_and_capability_requests():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan(
        "RESPONSE:\n我来处理。\n"
        "REQUEST reminder_intent {}\n"
        "REQUEST url_context {}\n"
        'REQUEST timezone {"action":"direct_set","timezone":"Asia/Tokyo"}\n'
    )

    assert plan.response_text == "我来处理。"
    assert [request.name for request in plan.capability_requests] == [
        "reminder_intent",
        "url_context",
        "timezone",
    ]
    assert plan.capability_requests[2].args == {
        "action": "direct_set",
        "timezone": "Asia/Tokyo",
    }


def test_parse_plain_text_as_response_only():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan("你好，我在。")

    assert plan.response_text == "你好，我在。"
    assert plan.capability_requests == ()


def test_parse_response_marker_without_colon():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan("RESPONSE\n让我确认一下。")

    assert plan.response_text == "让我确认一下。"
    assert plan.capability_requests == ()


def test_parse_inline_response_marker_without_colon():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan("RESPONSE 让我确认一下。")

    assert plan.response_text == "让我确认一下。"
    assert plan.capability_requests == ()


def test_parse_inline_request_after_response_text():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan(
        "RESPONSE:\n"
        "好的，我来帮你设置今天10:50的提醒！"
        "REQUEST reminder_intent {\"action\":\"create\",\"message\":\"出门\"}"
    )

    assert plan.response_text == "好的，我来帮你设置今天10:50的提醒！"
    assert [request.name for request in plan.capability_requests] == [
        "reminder_intent"
    ]
    assert plan.capability_requests[0].args == {
        "action": "create",
        "message": "出门",
    }


def test_parser_rejects_unknown_capability():
    from agent.agno_agent.runtime.plan_parser import parse_team_plan

    plan = parse_team_plan("RESPONSE:\nok\nREQUEST shell {}")

    assert plan.response_text == "ok"
    assert plan.capability_requests == ()
    assert plan.rejected_requests == ("shell",)
