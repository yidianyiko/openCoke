from unittest.mock import MagicMock


def test_reply_waiter_consumes_first_pending_text_reply():
    from connector.clawscale_bridge.reply_waiter import ReplyWaiter

    mongo = MagicMock()
    mongo.find_one.side_effect = [
        None,
        {
            "_id": "out_1",
            "platform": "wechat",
            "status": "pending",
            "message_type": "text",
            "message": "收到",
            "metadata": {
                "source": "clawscale",
                "bridge_request_id": "br_1",
                "delivery_mode": "request_response",
            },
        },
    ]

    waiter = ReplyWaiter(mongo=mongo, poll_interval_seconds=0.01, timeout_seconds=1)
    reply = waiter.wait_for_reply("br_1")

    assert reply == "收到"
    mongo.update_one.assert_called_once()
