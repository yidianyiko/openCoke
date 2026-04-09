from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass

import requests

from conf.config import CONF
from connector.clawscale_bridge.gateway_user_provision_client import (
    GatewayUserProvisionClient,
)
from dao.clawscale_push_route_dao import ClawscalePushRouteDAO
from dao.mongo import MongoDBBase


def _mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


class RouteRepairRequired(RuntimeError):
    def __init__(self, *, account_id: str, conversation_id: str, reason: str):
        self.account_id = account_id
        self.conversation_id = conversation_id
        self.reason = reason
        super().__init__(
            f"route_repair_required:{account_id}:{conversation_id}:{reason}"
        )


@dataclass(frozen=True)
class GatewayDeliveryRouteClient:
    api_url: str
    api_key: str
    timeout_seconds: float = 10.0

    def upsert_route(self, **payload):
        response = requests.post(
            self.api_url.rstrip("/"),
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not body.get("ok"):
            raise RuntimeError(
                f"gateway_delivery_route_upsert_failed:{body.get('error', 'unknown') if isinstance(body, dict) else 'invalid_response'}"
            )
        return body["data"]


class BackfillDeliveryRoutesService:
    def __init__(
        self,
        *,
        iter_business_conversations,
        resolve_exact_current_peer,
        ensure_user_ready,
        upsert_route,
    ):
        self._iter_business_conversations = iter_business_conversations
        self._resolve_exact_current_peer = resolve_exact_current_peer
        self._ensure_user_ready = ensure_user_ready
        self._upsert_route = upsert_route

    def backfill_account(self, account_id: str, display_name: str | None = None):
        self._ensure_user_ready(account_id=account_id, display_name=display_name)

        routes_written = 0
        for conversation in self._iter_business_conversations(account_id):
            conversation_id = str(
                conversation.get("_id") or conversation.get("conversation_id") or ""
            ).strip()
            business_conversation_key = str(
                conversation.get("business_conversation_key") or ""
            ).strip()
            if not conversation_id:
                raise RouteRepairRequired(
                    account_id=account_id,
                    conversation_id="unknown",
                    reason="missing_conversation_id",
                )
            if not business_conversation_key:
                raise RouteRepairRequired(
                    account_id=account_id,
                    conversation_id=conversation_id,
                    reason="missing_business_conversation_key",
                )

            peer = self._resolve_exact_current_peer(conversation)
            if not isinstance(peer, dict):
                raise RouteRepairRequired(
                    account_id=account_id,
                    conversation_id=conversation_id,
                    reason="peer_not_mappable",
                )

            required_fields = (
                "tenant_id",
                "conversation_id",
                "channel_id",
                "end_user_id",
                "external_end_user_id",
            )
            missing_fields = [
                field
                for field in required_fields
                if not isinstance(peer.get(field), str) or not peer[field].strip()
            ]
            if missing_fields:
                raise RouteRepairRequired(
                    account_id=account_id,
                    conversation_id=conversation_id,
                    reason=f"missing_peer_fields:{','.join(missing_fields)}",
                )

            self._upsert_route(
                tenant_id=peer["tenant_id"],
                conversation_id=peer["conversation_id"],
                account_id=account_id,
                business_conversation_key=business_conversation_key,
                channel_id=peer["channel_id"],
                end_user_id=peer["end_user_id"],
                external_end_user_id=peer["external_end_user_id"],
            )
            routes_written += 1

        return {"account_id": account_id, "routes_written": routes_written}


def build_default_service():
    bridge_conf = CONF["clawscale_bridge"]
    mongo = MongoDBBase(
        connection_string=_mongo_uri(),
        db_name=CONF["mongodb"]["mongodb_name"],
    )
    legacy_route_dao = ClawscalePushRouteDAO(
        mongo_uri=_mongo_uri(),
        db_name=CONF["mongodb"]["mongodb_name"],
    )
    provision_client = GatewayUserProvisionClient(
        api_url=bridge_conf["user_provision_api_url"],
        api_key=bridge_conf["identity_api_key"],
    )
    delivery_routes_client = GatewayDeliveryRouteClient(
        api_url=bridge_conf.get("delivery_routes_api_url")
        or bridge_conf["user_provision_api_url"].replace(
            "/coke-users/provision", "/delivery-routes"
        ),
        api_key=bridge_conf["identity_api_key"],
    )

    def iter_business_conversations(account_id: str):
        return mongo.get_collection("conversations").find(
            {
                "$or": [
                    {"user_id": account_id},
                    {"account_id": account_id},
                ],
                "business_conversation_key": {"$exists": True, "$ne": ""},
            }
        )

    def resolve_exact_current_peer(conversation):
        conversation_id = str(
            conversation.get("_id") or conversation.get("conversation_id") or ""
        )
        legacy_route = legacy_route_dao.find_route_for_conversation(
            account_id=str(conversation.get("user_id") or conversation.get("account_id")),
            conversation_id=conversation_id,
            platform="wechat_personal",
        )
        if not legacy_route:
            return None

        end_user_id = legacy_route.get("end_user_id")
        if not end_user_id:
            return None

        return {
            "tenant_id": legacy_route.get("tenant_id"),
            "conversation_id": conversation_id,
            "channel_id": legacy_route.get("channel_id"),
            "end_user_id": end_user_id,
            "external_end_user_id": legacy_route.get("external_end_user_id"),
        }

    def ensure_user_ready(account_id: str, display_name: str | None = None):
        return provision_client.ensure_user(
            account_id=account_id,
            display_name=display_name,
        )

    return BackfillDeliveryRoutesService(
        iter_business_conversations=iter_business_conversations,
        resolve_exact_current_peer=resolve_exact_current_peer,
        ensure_user_ready=ensure_user_ready,
        upsert_route=delivery_routes_client.upsert_route,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill exact Clawscale delivery routes for already-established Coke business conversations."
    )
    parser.add_argument("--account-id", action="append", required=True)
    parser.add_argument("--display-name", default=None)
    args = parser.parse_args()

    service = build_default_service()
    summaries = []
    started_at = int(time.time())
    for account_id in args.account_id:
        summaries.append(
            service.backfill_account(account_id=account_id, display_name=args.display_name)
        )

    print(
        json.dumps(
            {
                "ok": True,
                "started_at": started_at,
                "accounts": summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
