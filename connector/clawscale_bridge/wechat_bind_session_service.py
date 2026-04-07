import re
import secrets
from urllib.parse import urlsplit


class WechatBindSessionService:
    def __init__(
        self,
        bind_session_dao,
        external_identity_dao,
        gateway_identity_client,
        bind_base_url: str,
        public_connect_url_template: str,
        ttl_seconds: int,
    ):
        self.bind_session_dao = bind_session_dao
        self.external_identity_dao = external_identity_dao
        self.gateway_identity_client = gateway_identity_client
        self.bind_base_url = bind_base_url.rstrip("/")
        self.public_connect_url_template = public_connect_url_template
        self.ttl_seconds = ttl_seconds

    def _is_public_connect_url_available(self) -> bool:
        if (
            not isinstance(self.public_connect_url_template, str)
            or "{bind_token}" not in self.public_connect_url_template
        ):
            return False

        hostname = urlsplit(self.public_connect_url_template).hostname or ""
        return hostname != "placeholder.invalid"

    def _build_landing_url(self, bind_token: str) -> str:
        return f"{self.bind_base_url}/user/wechat-bind/entry/{bind_token}"

    def _build_public_connect_url(self, bind_token: str) -> str | None:
        if not self._is_public_connect_url_available():
            return None
        return self.public_connect_url_template.replace("{bind_token}", bind_token)

    def _generate_bind_code(self) -> str:
        return f"COKE-{secrets.randbelow(1_000_000):06d}"

    def _extract_bind_code(self, text: str) -> str | None:
        if not isinstance(text, str):
            return None
        match = re.search(r"\b(COKE-\d{6})\b", text.upper())
        if not match:
            return None
        return match.group(1)

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

    def _consume_session(
        self,
        session: dict,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        now_ts: int,
    ):
        current_identity = self.external_identity_dao.find_active_identity(
            source=source,
            tenant_id=tenant_id,
            channel_id=channel_id,
            platform=platform,
            external_end_user_id=external_end_user_id,
        )
        if current_identity:
            self.bind_session_dao.mark_bound(
                session_id=session["session_id"],
                masked_identity=self._mask_identity(external_end_user_id),
                external_end_user_id=external_end_user_id,
                now_ts=now_ts,
            )
            return current_identity

        gateway_identity = self.gateway_identity_client.bind_identity(
            tenant_id=tenant_id,
            channel_id=channel_id,
            external_id=external_end_user_id,
            coke_account_id=session["account_id"],
        )
        clawscale_user_id = None
        if isinstance(gateway_identity, dict):
            clawscale_user_id = gateway_identity.get("clawscale_user_id")

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
        if clawscale_user_id:
            persisted_identity = self.external_identity_dao.set_clawscale_user_id(
                source=source,
                tenant_id=tenant_id,
                channel_id=channel_id,
                platform=platform,
                external_end_user_id=external_end_user_id,
                clawscale_user_id=clawscale_user_id,
            )
            if isinstance(persisted_identity, dict):
                identity = persisted_identity
            elif isinstance(identity, dict):
                identity["clawscale_user_id"] = clawscale_user_id
        self.bind_session_dao.mark_bound(
            session_id=session["session_id"],
            masked_identity=self._mask_identity(external_end_user_id),
            external_end_user_id=external_end_user_id,
            now_ts=now_ts,
        )
        return identity

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
            "bind_code": self._generate_bind_code(),
            "status": "pending",
            "connect_url": self._build_landing_url(bind_token),
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

    def get_entry_page_context(self, bind_token: str, now_ts: int):
        session = self.bind_session_dao.find_active_session_by_bind_token(
            bind_token, now_ts
        )
        if not session:
            return {"status": "expired"}

        return {
            "status": "pending",
            "bind_code": session.get("bind_code"),
            "public_connect_url": self._build_public_connect_url(bind_token),
            "expires_at": session["expires_at"],
        }

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
        return self._consume_session(
            session=session,
            source=source,
            tenant_id=tenant_id,
            channel_id=channel_id,
            platform=platform,
            external_end_user_id=external_end_user_id,
            now_ts=now_ts,
        )

    def consume_matching_session_from_text(
        self,
        text: str,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        now_ts: int,
    ):
        bind_code = self._extract_bind_code(text)
        if not bind_code:
            return None

        session = self.bind_session_dao.find_active_session_by_bind_code(
            bind_code, now_ts
        )
        if not session:
            return None

        return self._consume_session(
            session=session,
            source=source,
            tenant_id=tenant_id,
            channel_id=channel_id,
            platform=platform,
            external_end_user_id=external_end_user_id,
            now_ts=now_ts,
        )
