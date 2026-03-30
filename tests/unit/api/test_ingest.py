from unittest.mock import MagicMock

import pytest

from api.schema import ChatRequest


def _build_service():
    from api.ingest import GatewayIngestService

    service = GatewayIngestService(
        mongo=MagicMock(),
        user_dao=MagicMock(),
        redis_client=MagicMock(),
        redis_conf=MagicMock(stream_key="coke:input"),
        gateway_config=MagicMock(),
    )
    service.gateway_config.resolve_account.return_value = MagicMock(
        account_id="bot-a",
        character="coke",
        channel="wechat",
        character_platform_id="coke-wechat",
    )
    service.user_dao.find_characters.return_value = [
        {
            "_id": "char-1",
            "name": "coke",
            "platforms": {"wechat": {"id": "coke-wechat"}},
        }
    ]
    service.user_dao.find_users.return_value = [{"_id": "user-1"}]
    return service


def test_ingest_builds_gateway_metadata_for_private_message():
    from api.ingest import GatewayIngestService

    service = _build_service()

    request = ChatRequest(
        message_id="gw-001",
        channel="wechat",
        account_id="bot-a",
        sender={"platform_id": "wx-user-1", "display_name": "Alice"},
        chat_type="private",
        message_type="text",
        content="hello",
        timestamp=1711411200,
        metadata={"source": "gateway"},
        reply_to={
            "id": "reply-1",
            "content": "previous",
            "author_name": "Bob",
        },
    )

    doc = service._build_input_doc(request)

    assert doc["from_user"] == "user-1"
    assert doc["to_user"] == "char-1"
    assert doc["platform"] == "wechat"
    assert doc["chatroom_name"] is None
    assert doc["message"] == "hello"
    assert doc["metadata"]["source"] == "gateway"
    assert doc["metadata"]["reference"] == {
        "id": "reply-1",
        "text": "previous",
        "user": "Bob",
    }
    assert doc["metadata"]["gateway"] == {
        "account_id": "bot-a",
        "message_id": "gw-001",
        "character_platform_id": "coke-wechat",
    }


def test_ingest_detects_duplicate_gateway_message():
    from api.ingest import DuplicateMessageError

    service = _build_service()
    service.mongo.find_one.return_value = {"_id": "existing"}

    request = ChatRequest(
        message_id="gw-dup",
        channel="wechat",
        account_id="bot-a",
        sender={"platform_id": "wx-user-1"},
        chat_type="private",
        message_type="text",
        content="hello",
        timestamp=1711411200,
    )

    with pytest.raises(DuplicateMessageError):
        service._ensure_not_duplicate(request)

    service.mongo.find_one.assert_called_once_with(
        "inputmessages",
        {
            "platform": "wechat",
            "metadata.gateway.account_id": "bot-a",
            "metadata.gateway.message_id": "gw-dup",
        },
    )


def test_ingest_accepts_message_and_publishes_stream_event():
    from api.ingest import IngestResult

    service = _build_service()
    service.mongo.find_one.return_value = None
    service.mongo.insert_one.return_value = "507f1f77bcf86cd799439011"

    request = ChatRequest(
        message_id="gw-001",
        channel="wechat",
        account_id="bot-a",
        sender={"platform_id": "wx-user-1"},
        chat_type="private",
        message_type="text",
        content="hello",
        timestamp=1711411200,
    )

    result = service.accept(request)

    assert result == IngestResult(
        request_message_id="gw-001",
        input_message_id="507f1f77bcf86cd799439011",
    )
    service.redis_client.xadd.assert_called_once_with(
        "coke:input",
        {
            "message_id": "507f1f77bcf86cd799439011",
            "platform": "wechat",
            "ts": "1711411200",
        },
    )


def test_ingest_rejects_character_without_matching_routing_identity():
    service = _build_service()
    service.user_dao.find_characters.return_value = [
        {
            "_id": "char-1",
            "name": "coke",
            "platforms": {"wechat": {"id": "other-wechat-id"}},
        }
    ]

    request = ChatRequest(
        message_id="gw-001",
        channel="wechat",
        account_id="bot-a",
        sender={"platform_id": "wx-user-1"},
        chat_type="private",
        message_type="text",
        content="hello",
        timestamp=1711411200,
    )

    with pytest.raises(LookupError, match="routing identity mismatch"):
        service._build_input_doc(request)
