from agent.runner import rollback_detection


def test_product_notification_pending_message_does_not_interrupt_user_turn(monkeypatch):
    monkeypatch.setattr(
        rollback_detection,
        "read_all_inputmessages",
        lambda u_id, c_id, platform, status: [
            {
                "_id": "current",
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "causal_inbound_event_id": "direct_evt",
                    },
                },
            },
            {
                "_id": "product_notification",
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "business_conversation_key": "product-notification:acct_1",
                    },
                },
            },
        ],
    )

    assert (
        rollback_detection.is_new_message_coming_in(
            "acct_1",
            "char_1",
            "business",
            current_message_ids=["current"],
        )
        is False
    )


def test_new_non_request_response_user_message_still_interrupts_user_turn(monkeypatch):
    monkeypatch.setattr(
        rollback_detection,
        "read_all_inputmessages",
        lambda u_id, c_id, platform, status: [
            {
                "_id": "current",
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "causal_inbound_event_id": "direct_evt",
                    },
                },
            },
            {
                "_id": "new_direct",
                "metadata": {
                    "source": "manual",
                },
            },
        ],
    )

    assert (
        rollback_detection.is_new_message_coming_in(
            "acct_1",
            "char_1",
            "business",
            current_message_ids=["current"],
        )
        is True
    )


def test_direct_request_response_new_event_does_not_interrupt_inflight_sync_turn(
    monkeypatch,
):
    monkeypatch.setattr(
        rollback_detection,
        "read_all_inputmessages",
        lambda u_id, c_id, platform, status: [
            {
                "_id": "current",
                "input_timestamp": 100,
                "status": "pending",
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "business_conversation_key": "bc_direct",
                        "causal_inbound_event_id": "current_evt",
                    },
                },
            },
            {
                "_id": "new_direct",
                "input_timestamp": 101,
                "status": "pending",
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "business_conversation_key": "bc_direct",
                        "causal_inbound_event_id": "new_direct_evt",
                    },
                },
            },
        ],
    )

    assert (
        rollback_detection.is_new_message_coming_in(
            "acct_1",
            "char_1",
            "business",
            current_message_ids=["current"],
        )
        is False
    )


def test_older_pending_message_does_not_interrupt_newer_turn(monkeypatch):
    monkeypatch.setattr(
        rollback_detection,
        "read_all_inputmessages",
        lambda u_id, c_id, platform, status: [
            {
                "_id": "older_direct",
                "input_timestamp": 100,
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "causal_inbound_event_id": "older_evt",
                    },
                },
            },
            {
                "_id": "current",
                "input_timestamp": 101,
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "causal_inbound_event_id": "current_evt",
                    },
                },
            },
        ],
    )

    assert (
        rollback_detection.is_new_message_coming_in(
            "acct_1",
            "char_1",
            "business",
            current_message_ids=["current"],
        )
        is False
    )


def test_newer_handled_non_request_response_message_interrupts_older_inflight_turn(
    monkeypatch,
):
    def fake_read_all_inputmessages(u_id, c_id, platform, status):
        assert status is None
        return [
            {
                "_id": "current",
                "input_timestamp": 100,
                "status": "pending",
                "metadata": {
                    "source": "clawscale",
                    "business_protocol": {
                        "delivery_mode": "request_response",
                        "causal_inbound_event_id": "current_evt",
                    },
                },
            },
            {
                "_id": "newer_direct",
                "input_timestamp": 101,
                "status": "handled",
                "metadata": {
                    "source": "manual",
                },
            },
        ]

    monkeypatch.setattr(
        rollback_detection,
        "read_all_inputmessages",
        fake_read_all_inputmessages,
    )

    assert (
        rollback_detection.is_new_message_coming_in(
            "acct_1",
            "char_1",
            "business",
            current_message_ids=["current"],
        )
        is True
    )
