import secrets


class WechatBindSessionService:
    def __init__(
        self,
        bind_session_dao,
        external_identity_dao,
        connect_url_template: str,
        ttl_seconds: int,
    ):
        self.bind_session_dao = bind_session_dao
        self.external_identity_dao = external_identity_dao
        self.connect_url_template = connect_url_template
        self.ttl_seconds = ttl_seconds

    def _mask_identity(self, external_end_user_id: str) -> str:
        if len(external_end_user_id) <= 4:
            return "*" * len(external_end_user_id)
        visible_prefix = 5 if external_end_user_id.startswith("wxid_") else 4
        return (
            f"{external_end_user_id[:visible_prefix]}"
            f"***{external_end_user_id[-4:]}"
        )

    def _serialize_state(self, session: dict) -> dict:
        return {
            "status": session["status"],
            "connect_url": session.get("connect_url"),
            "expires_at": session.get("expires_at"),
            "masked_identity": session.get("masked_identity"),
        }

    def create_or_reuse_session(self, account_id: str, now_ts: int):
        active_identity = self.external_identity_dao.find_active_identity_for_account(
            account_id
        )
        if active_identity:
            return {
                "status": "bound",
                "masked_identity": self._mask_identity(
                    active_identity["external_end_user_id"]
                ),
            }

        session = self.bind_session_dao.find_active_session_for_account(
            account_id, now_ts
        )
        if session:
            return self._serialize_state(session)

        bind_token = f"ctx_{secrets.token_urlsafe(18)}"
        session = {
            "session_id": f"bs_{secrets.token_hex(8)}",
            "account_id": account_id,
            "bind_token": bind_token,
            "status": "pending",
            "connect_url": self.connect_url_template.replace(
                "{bind_token}", bind_token
            ),
            "created_at": now_ts,
            "expires_at": now_ts + self.ttl_seconds,
        }
        created = self.bind_session_dao.create_session(session)
        return self._serialize_state(created)

    def get_status(self, account_id: str, now_ts: int):
        active_identity = self.external_identity_dao.find_active_identity_for_account(
            account_id
        )
        if active_identity:
            return {
                "status": "bound",
                "masked_identity": self._mask_identity(
                    active_identity["external_end_user_id"]
                ),
            }

        session = self.bind_session_dao.find_latest_session_for_account(account_id)
        if not session:
            return {"status": "unbound"}
        if session["expires_at"] <= now_ts:
            return {"status": "expired"}
        return self._serialize_state(session)

    def consume_matching_session(
        self,
        bind_token: str,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        now_ts: int,
    ):
        if not bind_token:
            return None

        session = self.bind_session_dao.find_active_session_by_bind_token(
            bind_token, now_ts
        )
        if not session:
            return None

        active_identity = self.external_identity_dao.find_active_identity_for_account(
            session["account_id"]
        )
        if active_identity:
            if active_identity["external_end_user_id"] != external_end_user_id:
                return None
            self.bind_session_dao.mark_bound(
                session_id=session["session_id"],
                masked_identity=self._mask_identity(external_end_user_id),
                external_end_user_id=external_end_user_id,
                now_ts=now_ts,
            )
            return active_identity

        identity = self.external_identity_dao.activate_identity(
            source=source,
            tenant_id=tenant_id,
            channel_id=channel_id,
            platform=platform,
            external_end_user_id=external_end_user_id,
            account_id=session["account_id"],
            now_ts=now_ts,
        )
        if not isinstance(identity, dict):
            identity = self.external_identity_dao.find_active_identity(
                source=source,
                tenant_id=tenant_id,
                channel_id=channel_id,
                platform=platform,
                external_end_user_id=external_end_user_id,
            )
        self.bind_session_dao.mark_bound(
            session_id=session["session_id"],
            masked_identity=self._mask_identity(external_end_user_id),
            external_end_user_id=external_end_user_id,
            now_ts=now_ts,
        )
        return identity
