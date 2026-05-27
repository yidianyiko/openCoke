from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE


def test_chat_response_prompt_grounds_future_reminder_language():
    assert "successful reminder tool result" in INSTRUCTIONS_CHAT_RESPONSE
    assert "system reminder trigger" in INSTRUCTIONS_CHAT_RESPONSE
    assert "offer, question, or present-moment encouragement" in INSTRUCTIONS_CHAT_RESPONSE


def test_chat_response_prompt_keeps_current_message_language():
    assert "user's current message language" in INSTRUCTIONS_CHAT_RESPONSE


def test_chat_response_prompt_does_not_turn_rest_plans_into_reminder_promises():
    assert "rest, timer, break, or countdown plan" in INSTRUCTIONS_CHAT_RESPONSE
    assert "ask whether the user wants one" in INSTRUCTIONS_CHAT_RESPONSE


def test_chat_response_prompt_forbids_claims_without_actual_reminder_write():
    assert "upstream reminder decision is `clarify` or `discussion`" in INSTRUCTIONS_CHAT_RESPONSE
    assert "actual reminder tool result is present" in INSTRUCTIONS_CHAT_RESPONSE


def test_chat_response_prompt_surfaces_deadline_for_until_rrules():
    assert "UNTIL clause or `deadline_at`" in INSTRUCTIONS_CHAT_RESPONSE
    assert "surface the deadline" in INSTRUCTIONS_CHAT_RESPONSE


def test_chat_response_prompt_treats_name_preferences_as_name_preferences():
    assert "name or address preference" in INSTRUCTIONS_CHAT_RESPONSE
    assert "Do not ask about reminder setup" in INSTRUCTIONS_CHAT_RESPONSE
