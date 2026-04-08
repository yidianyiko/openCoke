from unittest.mock import MagicMock


def test_output_dispatcher_marks_message_handled_after_successful_post():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    mongo.find_one.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "pending",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }

    dispatcher = ClawScaleOutputDispatcher(
        mongo=mongo,
        session=MagicMock(),
        outbound_api_url="https://gateway.local/api/outbound",
    )
    dispatcher.session.post.return_value.status_code = 200

    handled = dispatcher.dispatch_once()

    assert handled is True
    mongo.update_one.assert_called()


def test_output_dispatcher_posts_to_configured_outbound_url_with_api_key():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    mongo.find_one.return_value = {
        "_id": "out_1",
        "platform": "wechat",
        "status": "pending",
        "message": "记得开会",
        "metadata": {
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "push_idempotency_key": "push_1",
        },
    }

    session = MagicMock()
    session.post.return_value.status_code = 200

    dispatcher = ClawScaleOutputDispatcher(
        mongo=mongo,
        session=session,
        outbound_api_url="https://gateway.local/api/outbound",
        outbound_api_key="outbound-secret",
    )

    dispatcher.dispatch_once()

    session.post.assert_called_once_with(
        "https://gateway.local/api/outbound",
        json={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "end_user_id": "wxid_123",
            "text": "记得开会",
            "idempotency_key": "push_1",
        },
        headers={"Authorization": "Bearer outbound-secret"},
        timeout=15,
    )
