import uuid


class OutputRouteResolver:
    def __init__(self, external_identity_dao):
        self.external_identity_dao = external_identity_dao

    def build_push_metadata(self, account_id: str, now_ts: int):
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
