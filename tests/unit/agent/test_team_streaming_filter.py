from types import SimpleNamespace

from agent.agno_agent.runtime.streaming import filter_user_visible_team_events


def test_filter_keeps_only_team_run_content_events():
    events = [
        SimpleNamespace(event="TeamRunStarted", content=None),
        SimpleNamespace(event="ToolCallStarted", content="secret tool"),
        SimpleNamespace(event="RunContent", content="member text", agent_id="member-1"),
        SimpleNamespace(event="TeamRunContent", content="hello", agent_id=None),
        SimpleNamespace(event="TeamRunContent", content=" world", agent_id=None),
        SimpleNamespace(event="TeamRunCompleted", content=None),
    ]

    chunks = list(filter_user_visible_team_events(events))

    assert chunks == ["hello", " world"]


def test_filter_ignores_reasoning_and_tool_content():
    events = [
        SimpleNamespace(event="TeamReasoningContentDelta", reasoning_content="hidden"),
        SimpleNamespace(event="ToolCallCompleted", content="tool result"),
        SimpleNamespace(event="RunContent", content="member text"),
        SimpleNamespace(event="TeamRunContent", content="visible"),
    ]

    chunks = list(filter_user_visible_team_events(events))

    assert chunks == ["visible"]


def test_filter_accepts_dict_events():
    events = [
        {"event": "RunContent", "content": "member text"},
        {"event": "TeamRunContent", "content": "dict text"},
    ]

    chunks = list(filter_user_visible_team_events(events))

    assert chunks == ["dict text"]


def test_filter_drops_non_string_and_empty_content():
    events = [
        SimpleNamespace(event="TeamRunContent", content=""),
        SimpleNamespace(event="TeamRunContent", content=None),
        SimpleNamespace(event="TeamRunContent", content=123),
        SimpleNamespace(event="TeamRunContent", content="visible"),
    ]

    chunks = list(filter_user_visible_team_events(events))

    assert chunks == ["visible"]
