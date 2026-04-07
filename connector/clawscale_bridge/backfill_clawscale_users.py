from __future__ import annotations

import json
import time

from conf.config import CONF
from connector.clawscale_bridge.gateway_identity_client import GatewayIdentityClient
from dao.external_identity_dao import ExternalIdentityDAO


def _mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


def backfill_active_identities(external_identity_dao, gateway_identity_client, now_ts):
    summary = {"scanned": 0, "updated": 0, "skipped": 0}

    for identity in external_identity_dao.iter_active_clawscale_identities():
        summary["scanned"] += 1
        if identity.get("clawscale_user_id"):
            summary["skipped"] += 1
            continue

        gateway_identity = gateway_identity_client.bind_identity(
            tenant_id=identity["tenant_id"],
            channel_id=identity["channel_id"],
            external_id=identity["external_end_user_id"],
            coke_account_id=identity["account_id"],
        )
        clawscale_user_id = gateway_identity.get("clawscale_user_id")
        if not clawscale_user_id:
            raise ValueError("gateway_identity_missing_clawscale_user_id")

        external_identity_dao.set_clawscale_user_id(
            source="clawscale",
            tenant_id=identity["tenant_id"],
            channel_id=identity["channel_id"],
            platform=identity["platform"],
            external_end_user_id=identity["external_end_user_id"],
            clawscale_user_id=clawscale_user_id,
        )
        summary["updated"] += 1

    return summary


def main():
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
    return summary


if __name__ == "__main__":
    main()
