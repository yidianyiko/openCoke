from unittest.mock import ANY, AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_delivery_marks_journal_handled_after_send():
    from api.delivery import DeliveryService

    mongo = MagicMock()
    mongo.update_one.return_value = 1
    openclaw_client = AsyncMock()
    service = DeliveryService(mongo=mongo, openclaw_client=openclaw_client)

    outputmessage = {
        "_id": "out-1",
        "platform": "wechat",
        "chatroom_name": None,
        "expect_output_timestamp": 0,
        "message_type": "text",
        "message": "hello",
        "metadata": {
            "gateway": {
                "account_id": "bot-a",
                "to_platform_id": "wx-user-1",
            }
        },
    }

    await service.deliver(outputmessage)

    openclaw_client.send.assert_awaited_once_with(
        account_id="bot-a",
        channel="wechat",
        idempotency_key="out-1",
        to="wx-user-1",
        group_id=None,
        message="hello",
        media_url=None,
    )
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out-1"},
        {"$set": {"status": "handled", "handled_timestamp": ANY}},
    )


@pytest.mark.asyncio
async def test_send_message_via_delivery_sets_private_gateway_recipient(monkeypatch):
    from agent.util.message_util import send_message_via_delivery

    outputmessage = {
        "_id": "out-2",
        "platform": "wechat",
        "chatroom_name": None,
        "expect_output_timestamp": 1711411200,
        "message_type": "text",
        "message": "hello",
        "metadata": {"gateway": {"account_id": "bot-a"}},
    }

    def fake_send_message_via_context(*args, **kwargs):
        return outputmessage

    context = {
        "character": {"_id": "character-1"},
        "user": {
            "_id": "user-1",
            "platforms": {"wechat": {"id": "wx-user-1"}},
        },
        "conversation": {
            "platform": "wechat",
            "chatroom_name": None,
            "conversation_info": {
                "input_messages": [
                    {
                        "metadata": {
                            "gateway": {
                                "account_id": "bot-a",
                            }
                        }
                    }
                ]
            },
        },
    }
    delivery_service = AsyncMock()
    delivery_service.deliver = AsyncMock()

    monkeypatch.setattr(
        "agent.util.message_util.send_message_via_context",
        fake_send_message_via_context,
    )

    outputmessage = await send_message_via_delivery(
        context=context,
        delivery_service=delivery_service,
        message="hello",
        message_type="text",
        expect_output_timestamp=1711411200,
    )

    assert outputmessage["metadata"]["gateway"]["to_platform_id"] == "wx-user-1"
    delivery_service.deliver.assert_awaited_once()
