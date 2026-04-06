from unittest.mock import MagicMock


def test_output_route_resolver_returns_primary_push_target():
    from connector.clawscale_bridge.output_route_resolver import OutputRouteResolver

    dao = MagicMock()
    dao.find_primary_push_target.return_value = {
        "tenant_id": "ten_1",
        "channel_id": "ch_1",
        "platform": "wechat_personal",
        "external_end_user_id": "wxid_123",
        "source": "clawscale",
    }

    resolver = OutputRouteResolver(external_identity_dao=dao)
    metadata = resolver.build_push_metadata("user_1", now_ts=1710000000)

    assert metadata["route_via"] == "clawscale"
    assert metadata["delivery_mode"] == "push"
    assert metadata["tenant_id"] == "ten_1"
