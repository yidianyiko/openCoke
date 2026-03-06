# -*- coding: utf-8 -*-
"""
Onboarding Prompt - New user onboarding prompt

Injected only on the user's first conversation with the character, controlled by the is_new_user flag.

Usage:
    from agent.prompt.onboarding_prompt import get_onboarding_context

    onboarding_context = get_onboarding_context(context.get("is_new_user", False))
"""

# Onboarding flow prompt (extracted from prepare_character.py)
ONBOARDING_PROMPT = """
<onboarding_and_first_dialogue>
        This is your first conversation with the user. You must execute the following onboarding flow. Your reply must be concise and sent as multiple short messages (no more than three):

        1. First, greet warmly and introduce yourself. Example: "Hii, hey there! I'm Coke, your supervisor. What should I call you? Is there something you've been wanting to get done lately?"

        2. Briefly tell the user how to use:
        a) Goal reminders
        b) Daily reminders
        c) In-progress supervision

        Note: Keep messages in the short style expected on the platform — split questions and explanations into a few short messages (no more than three), rather than sending one long paragraph.
</onboarding_and_first_dialogue>
"""


def get_onboarding_context(is_new_user: bool) -> str:
    """
    Get onboarding context prompt.

    Args:
        is_new_user: Whether this is a new user (first conversation)

    Returns:
        Onboarding prompt if new user, otherwise empty string
    """
    if is_new_user:
        return ONBOARDING_PROMPT
    return ""
