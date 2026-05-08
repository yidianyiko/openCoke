from agent.agno_agent.runtime.agent_runtime import _extract_final_text


class Out:
    def __init__(self, messages, content=""):
        self.messages = messages
        self.content = content


def test_extracts_post_tool_assistant_message_only():
    out = Out(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Let me check..."},
            {"role": "tool_use", "content": "calling tool"},
            {"role": "tool", "content": "tool result"},
            {"role": "assistant", "content": "Here is the info."},
        ],
        content="Let me check...Here is the info.",
    )

    assert _extract_final_text(out) == "Here is the info."


def test_no_tool_call_returns_sole_assistant_text():
    out = Out(messages=[{"role": "assistant", "content": "hi back"}])

    assert _extract_final_text(out) == "hi back"


def test_tool_call_with_empty_final_assistant_returns_empty():
    out = Out(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "tool result"},
            {"role": "assistant", "content": ""},
        ]
    )

    assert _extract_final_text(out) == ""


def test_no_messages_falls_back_to_content():
    out = Out(messages=[], content="legacy text")

    assert _extract_final_text(out) == "legacy text"
