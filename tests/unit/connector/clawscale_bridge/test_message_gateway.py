from unittest.mock import MagicMock


def test_message_gateway_builds_wechat_compatible_input_message():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())
    doc = gateway.build_input_message(
        account_id="user_1",
        character_id="char_1",
        text="你好",
        bridge_request_id="br_1",
        inbound={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "conversation_id": "conv_1",
            "platform": "wechat_personal",
            "end_user_id": "wxid_123",
            "external_id": "ext_1",
            "external_message_id": "msg_1",
            "timestamp": 1710000000,
        },
    )

    assert doc["platform"] == "wechat"
    assert doc["from_user"] == "user_1"
    assert doc["to_user"] == "char_1"
    assert doc["metadata"]["source"] == "clawscale"
    assert doc["metadata"]["bridge_request_id"] == "br_1"
    assert doc["metadata"]["delivery_mode"] == "request_response"
    assert doc["metadata"]["clawscale"]["channel_id"] == "ch_1"

