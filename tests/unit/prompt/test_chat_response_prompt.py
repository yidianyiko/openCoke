from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE


def test_chat_response_prompt_grounds_future_reminder_language():
    assert "successful reminder tool result" in INSTRUCTIONS_CHAT_RESPONSE
    assert "system reminder trigger" in INSTRUCTIONS_CHAT_RESPONSE
    assert "offer, question, or present-moment encouragement" in INSTRUCTIONS_CHAT_RESPONSE


def test_chat_response_prompt_keeps_current_message_language():
    assert "user's current message language" in INSTRUCTIONS_CHAT_RESPONSE
