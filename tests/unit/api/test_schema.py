import pytest
from pydantic import ValidationError

from api.schema import ChatAcceptedResponse, ChatRequest, ErrorResponse


def test_chat_request_defaults_optional_fields():
    request = ChatRequest(
        message_id="msg-1",
        channel="wechat",
        account_id="acct-1",
        sender={"platform_id": "user-1"},
        chat_type="private",
        message_type="text",
        content="hello",
        timestamp=1710000000,
    )

    assert request.media_url is None
    assert request.reply_to is None
    assert request.group_id is None
    assert request.metadata == {}
    assert request.sender.platform_id == "user-1"
    assert request.sender.display_name is None


def test_chat_request_accepts_reply_to_contract():
    request = ChatRequest(
        message_id="msg-3",
        channel="wechat",
        account_id="acct-1",
        sender={"platform_id": "user-1"},
        chat_type="private",
        message_type="reference",
        content="reply",
        reply_to={"id": "reply-1"},
        timestamp=1710000002,
    )

    assert request.reply_to is not None
    assert request.reply_to.id == "reply-1"
    assert request.reply_to.content is None
    assert request.reply_to.author_name is None


def test_chat_request_rejects_group_chat_without_group_id():
    with pytest.raises(ValidationError):
        ChatRequest(
            message_id="msg-2",
            channel="wechat",
            account_id="acct-1",
            sender={"platform_id": "user-1"},
            chat_type="group",
            message_type="text",
            content="hello group",
            timestamp=1710000001,
        )


def test_chat_accepted_response_contract():
    response = ChatAcceptedResponse(
        status="accepted",
        request_message_id="req-1",
        input_message_id="in-1",
    )

    assert response.status == "accepted"
    assert response.request_message_id == "req-1"
    assert response.input_message_id == "in-1"
    assert set(ChatAcceptedResponse.model_fields) == {
        "status",
        "request_message_id",
        "input_message_id",
    }


def test_chat_accepted_response_rejects_other_status_values():
    with pytest.raises(ValidationError):
        ChatAcceptedResponse(
            status="pending",
            request_message_id="req-1",
            input_message_id="in-1",
        )


def test_error_response_contract():
    response = ErrorResponse(error="unauthorized")

    assert response.error == "unauthorized"
    assert response.detail is None
    assert response.message_id is None
    assert response.account_id is None
    assert set(ErrorResponse.model_fields) == {
        "error",
        "detail",
        "message_id",
        "account_id",
    }
