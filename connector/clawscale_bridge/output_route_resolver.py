import uuid


class OutputRouteResolver:
    def __init__(self, external_identity_dao, clawscale_push_route_dao=None):
        self.external_identity_dao = external_identity_dao
        self.clawscale_push_route_dao = clawscale_push_route_dao

    def build_push_metadata(
        self,
        account_id: str,
        now_ts: int,
        conversation_id: str | None = None,
        platform: str | None = None,
    ):
        target = None
        if self.clawscale_push_route_dao and conversation_id and platform:
            target = self.clawscale_push_route_dao.find_route_for_conversation(
                account_id=account_id,
                conversation_id=conversation_id,
                platform=platform,
            )
        if not target and self.clawscale_push_route_dao and platform:
            target = self.clawscale_push_route_dao.find_latest_route_for_account(
                account_id=account_id,
                platform=platform,
            )
        if not target:
            target = self.external_identity_dao.find_primary_push_target(
                account_id=account_id, source="clawscale"
            )
        if not target:
            return {}
        return {
            "source": "clawscale",
            "route_via": "clawscale",
            "delivery_mode": "push",
            "tenant_id": target["tenant_id"],
            "channel_id": target["channel_id"],
            "platform": target["platform"],
            "external_end_user_id": target["external_end_user_id"],
            "push_idempotency_key": f"push_{uuid.uuid4().hex}",
        }
