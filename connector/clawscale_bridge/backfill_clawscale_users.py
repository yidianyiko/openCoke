from __future__ import annotations

import json
import logging
import os
import time

from conf.config import CONF
from connector.clawscale_bridge.gateway_identity_client import GatewayIdentityClient
from dao.external_identity_dao import ExternalIdentityDAO

logger = logging.getLogger(__name__)

REQUIRED_IDENTITY_FIELDS = (
    "tenant_id",
    "channel_id",
    "platform",
    "external_end_user_id",
    "account_id",
)
RESET_CONFIRMATION_ENV_VAR = "ALLOW_WECHAT_PERSONAL_RESET"
RESET_CONFIRMATION_ENV_VALUE = "yes"


def require_personal_wechat_reset_confirmation() -> None:
    if os.getenv(RESET_CONFIRMATION_ENV_VAR) != RESET_CONFIRMATION_ENV_VALUE:
        raise RuntimeError("personal_wechat_reset_confirmation_required")


def _mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


def _is_valid_active_identity(identity) -> bool:
    if not isinstance(identity, dict):
        return False
    for field in REQUIRED_IDENTITY_FIELDS:
        value = identity.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _is_legacy_wechat_personal_identity(identity) -> bool:
    return isinstance(identity, dict) and identity.get("platform") == "wechat_personal"


def _touch_identity_timestamp(external_identity_dao, identity, now_ts: int) -> None:
    collection = getattr(external_identity_dao, "collection", None)
    if collection is None:
        return

    try:
        collection.update_one(
            {
                "source": "clawscale",
                "tenant_id": identity["tenant_id"],
                "channel_id": identity["channel_id"],
                "platform": identity["platform"],
                "external_end_user_id": identity["external_end_user_id"],
            },
            {"$set": {"updated_at": now_ts}},
        )
    except Exception as exc:  # pragma: no cover - operational guardrail
        logger.warning(
            "failed to persist backfill timestamp for tenant_id=%s channel_id=%s external_end_user_id=%s: %s",
            identity["tenant_id"],
            identity["channel_id"],
            identity["external_end_user_id"],
            exc,
        )


def _persist_clawscale_user_id(external_identity_dao, identity, clawscale_user_id: str) -> None:
    collection = getattr(external_identity_dao, "collection", None)
    if collection is None:
        raise AttributeError("external_identity_collection_unavailable")

    collection.update_one(
        {
            "source": "clawscale",
            "tenant_id": identity["tenant_id"],
            "channel_id": identity["channel_id"],
            "platform": identity["platform"],
            "external_end_user_id": identity["external_end_user_id"],
        },
        {"$set": {"clawscale_user_id": clawscale_user_id}},
    )


def backfill_active_identities(external_identity_dao, gateway_identity_client, now_ts):
    summary = {"scanned": 0, "updated": 0, "skipped": 0, "failed": 0}

    for identity in external_identity_dao.iter_active_clawscale_identities():
        summary["scanned"] += 1

        if not _is_legacy_wechat_personal_identity(identity):
            summary["skipped"] += 1
            continue

        if not _is_valid_active_identity(identity):
            summary["skipped"] += 1
            logger.warning("skipping malformed clawscale identity row: %s", identity)
            continue

        if identity.get("clawscale_user_id"):
            summary["skipped"] += 1
            continue

        try:
            gateway_identity = gateway_identity_client.bind_identity(
                tenant_id=identity["tenant_id"],
                channel_id=identity["channel_id"],
                external_id=identity["external_end_user_id"],
                coke_account_id=identity["account_id"],
            )
            clawscale_user_id = gateway_identity.get("clawscale_user_id")
            if not isinstance(clawscale_user_id, str) or not clawscale_user_id.strip():
                raise ValueError("gateway_identity_missing_clawscale_user_id")

            _persist_clawscale_user_id(
                external_identity_dao,
                identity,
                clawscale_user_id,
            )
            _touch_identity_timestamp(external_identity_dao, identity, now_ts)
            summary["updated"] += 1
        except Exception as exc:
            summary["failed"] += 1
            logger.warning(
                "failed to backfill clawscale identity for tenant_id=%s channel_id=%s external_end_user_id=%s: %s",
                identity["tenant_id"],
                identity["channel_id"],
                identity["external_end_user_id"],
                exc,
            )
            continue

    return summary


def main():
    require_personal_wechat_reset_confirmation()

    bridge_conf = CONF["clawscale_bridge"]
    mongo_uri = _mongo_uri()
    external_identity_dao = ExternalIdentityDAO(
        mongo_uri=mongo_uri,
        db_name=CONF["mongodb"]["mongodb_name"],
    )
    gateway_identity_client = GatewayIdentityClient(
        api_url=bridge_conf["identity_api_url"],
        api_key=bridge_conf["identity_api_key"],
    )
    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=int(time.time()),
    )
    print(json.dumps(summary, ensure_ascii=False))
    if summary.get("failed", 0) > 0:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    main()
