import time


class IdentityService:
    def __init__(
        self,
        external_identity_dao,
        binding_ticket_dao,
        bind_session_service,
        message_gateway,
        reply_waiter,
        bind_base_url: str,
        target_character_id: str,
    ):
        self.external_identity_dao = external_identity_dao
        self.binding_ticket_dao = binding_ticket_dao
        self.bind_session_service = bind_session_service
        self.message_gateway = message_gateway
        self.reply_waiter = reply_waiter
        self.bind_base_url = bind_base_url
        self.target_character_id = target_character_id

    def issue_or_reuse_binding_ticket(self, metadata: dict, now_ts: int):
        reusable = self.binding_ticket_dao.find_reusable_ticket(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
            now_ts=now_ts,
        )
        if reusable:
            return reusable

        recent_count = self.binding_ticket_dao.count_recent_tickets(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
            since_ts=now_ts - 3600,
        )
        if recent_count >= 5:
            raise ValueError("bind_ticket_rate_limited")

        return self.binding_ticket_dao.create_ticket(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
            bind_base_url=self.bind_base_url,
            now_ts=now_ts,
        )

    def handle_inbound(self, inbound_payload: dict):
        metadata = inbound_payload["metadata"]
        now_ts = int(time.time())
        coke_account_id = metadata.get("cokeAccountId")
        if coke_account_id:
            bridge_request_id = self.message_gateway.enqueue(
                account_id=coke_account_id,
                character_id=self.target_character_id,
                text=inbound_payload["messages"][-1]["content"],
                inbound={
                    "tenant_id": metadata["tenantId"],
                    "channel_id": metadata["channelId"],
                    "conversation_id": metadata["conversationId"],
                    "platform": metadata["platform"],
                    "end_user_id": metadata["endUserId"],
                    "external_id": metadata["externalId"],
                    "external_message_id": metadata["conversationId"],
                    "timestamp": now_ts,
                },
            )
            reply = self.reply_waiter.wait_for_reply(bridge_request_id)
            return {"status": "ok", "reply": reply}

        external_identity = self.external_identity_dao.find_active_identity(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
        )
        if not external_identity:
            bind_token = metadata.get("contextToken")
            if bind_token:
                external_identity = self.bind_session_service.consume_matching_session(
                    bind_token=bind_token,
                    source="clawscale",
                    tenant_id=metadata["tenantId"],
                    channel_id=metadata["channelId"],
                    platform=metadata["platform"],
                    external_end_user_id=metadata["externalId"],
                    now_ts=now_ts,
                )
            if not external_identity:
                external_identity = (
                    self.bind_session_service.consume_matching_session_from_text(
                        text=inbound_payload["messages"][-1]["content"],
                        source="clawscale",
                        tenant_id=metadata["tenantId"],
                        channel_id=metadata["channelId"],
                        platform=metadata["platform"],
                        external_end_user_id=metadata["externalId"],
                        now_ts=now_ts,
                    )
                )

        if not external_identity:
            try:
                ticket = self.issue_or_reuse_binding_ticket(metadata, now_ts=now_ts)
            except ValueError:
                return {
                    "status": "bind_required",
                    "reply": "请稍后再试绑定账号",
                }
            return {
                "status": "bind_required",
                "reply": f"请先绑定账号: {ticket['bind_url']}",
                "bind_url": ticket["bind_url"],
            }

        bridge_request_id = self.message_gateway.enqueue(
            account_id=external_identity["account_id"],
            character_id=self.target_character_id,
            text=inbound_payload["messages"][-1]["content"],
            inbound={
                "tenant_id": metadata["tenantId"],
                "channel_id": metadata["channelId"],
                "conversation_id": metadata["conversationId"],
                "platform": metadata["platform"],
                "end_user_id": metadata["endUserId"],
                "external_id": metadata["externalId"],
                "external_message_id": metadata["conversationId"],
                "timestamp": now_ts,
            },
        )
        reply = self.reply_waiter.wait_for_reply(bridge_request_id)
        return {"status": "ok", "reply": reply}
