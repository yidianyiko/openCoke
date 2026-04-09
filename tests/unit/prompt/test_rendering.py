from agent.prompt.chat_contextprompt import get_message_source_context
from agent.prompt.rendering import build_prompt_context, render_prompt_template


def test_render_prompt_template_uses_generic_labels_without_platform_profiles():
    rendered = render_prompt_template(
        "hello {character_label} and {user_label}",
        {
            "user": {"display_name": "Alice"},
            "character": {"name": "Coke"},
            "conversation": {"platform": "business"},
        },
    )

    assert rendered == "hello Coke and Alice"


def test_build_prompt_context_populates_generic_labels_and_channel():
    context = build_prompt_context(
        {
            "user": {"email": "alice@example.com"},
            "character": {"nickname": "Qiaoyun"},
            "conversation": {"platform": "business"},
        }
    )

    assert context["user_label"] == "alice@example.com"
    assert context["character_label"] == "Qiaoyun"
    assert context["channel_label"] == "business"
    assert context["user"]["nickname"] == "alice@example.com"
    assert context["character"]["nickname"] == "Qiaoyun"


def test_message_source_context_uses_generic_user_label():
    rendered = get_message_source_context(
        "user",
        {
            "user": {"display_name": "Alice"},
            "conversation": {"platform": "business"},
        },
    )

    assert "Alice" in rendered
    assert "{user_label}" not in rendered
