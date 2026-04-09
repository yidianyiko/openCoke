import pytest
from unittest.mock import MagicMock


def test_backfill_delivery_routes_rejects_unmappable_conversation():
    from connector.clawscale_bridge.backfill_delivery_routes import (
        BackfillDeliveryRoutesService,
        RouteRepairRequired,
    )

    service = BackfillDeliveryRoutesService(
        iter_business_conversations=lambda account_id: [
            {"_id": "conv_1", "business_conversation_key": "bc_1"}
        ],
        resolve_exact_current_peer=lambda conversation: None,
        ensure_user_ready=MagicMock(),
        upsert_route=MagicMock(),
    )

    with pytest.raises(RouteRepairRequired) as exc:
        service.backfill_account("acc_missing_route")

    assert str(exc.value) == "route_repair_required:acc_missing_route:conv_1:peer_not_mappable"


def test_backfill_delivery_routes_provisions_account_and_upserts_exact_routes():
    from connector.clawscale_bridge.backfill_delivery_routes import (
        BackfillDeliveryRoutesService,
    )

    ensure_user_ready = MagicMock()
    upsert_route = MagicMock()
    service = BackfillDeliveryRoutesService(
        iter_business_conversations=lambda account_id: [
            {"_id": "conv_1", "business_conversation_key": "bc_1"},
            {"_id": "conv_2", "business_conversation_key": "bc_2"},
        ],
        resolve_exact_current_peer=lambda conversation: {
            "tenant_id": "ten_1",
            "conversation_id": str(conversation["_id"]),
            "channel_id": "ch_1",
            "end_user_id": "eu_1",
            "external_end_user_id": "wxid_1",
        },
        ensure_user_ready=ensure_user_ready,
        upsert_route=upsert_route,
    )

    summary = service.backfill_account("acc_1", display_name="Alice")

    assert summary == {"account_id": "acc_1", "routes_written": 2}
    ensure_user_ready.assert_called_once_with(
        account_id="acc_1", display_name="Alice"
    )
    assert upsert_route.call_count == 2
    upsert_route.assert_any_call(
        tenant_id="ten_1",
        conversation_id="conv_1",
        account_id="acc_1",
        business_conversation_key="bc_1",
        channel_id="ch_1",
        end_user_id="eu_1",
        external_end_user_id="wxid_1",
    )
