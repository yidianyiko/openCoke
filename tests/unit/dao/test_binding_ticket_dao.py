from unittest.mock import MagicMock


def test_binding_ticket_reuses_existing_pending_ticket():
    from dao.binding_ticket_dao import BindingTicketDAO

    dao = BindingTicketDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()
    dao.collection.find_one.return_value = {
        "ticket_id": "bt_123",
        "status": "pending",
        "bind_url": "https://coke.local/bind/bt_123",
    }

    ticket = dao.find_reusable_ticket(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_1",
        now_ts=1710000000,
    )

    assert ticket["ticket_id"] == "bt_123"
