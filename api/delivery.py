from __future__ import annotations

import asyncio
import time
from typing import Any, Dict


class DeliveryService:
    def __init__(self, mongo, openclaw_client):
        self.mongo = mongo
        self.openclaw_client = openclaw_client

    async def deliver(self, outputmessage: Dict[str, Any]) -> None:
        delay = max(0, int(outputmessage.get("expect_output_timestamp", 0)) - int(time.time()))
        if delay:
            await asyncio.sleep(delay)

        gateway = (outputmessage.get("metadata") or {}).get("gateway", {})
        try:
            await self.openclaw_client.send(
                account_id=gateway["account_id"],
                channel=outputmessage["platform"],
                idempotency_key=str(outputmessage["_id"]),
                to=gateway.get("to_platform_id"),
                group_id=outputmessage.get("chatroom_name"),
                message=outputmessage.get("message") if outputmessage.get("message_type") == "text" else None,
                media_url=(outputmessage.get("metadata") or {}).get("url"),
            )
        except Exception:
            self.mongo.update_one(
                "outputmessages",
                {"_id": outputmessage["_id"]},
                {
                    "$set": {
                        "status": "failed",
                        "handled_timestamp": int(time.time()),
                    }
                },
            )
            raise

        self.mongo.update_one(
            "outputmessages",
            {"_id": outputmessage["_id"]},
            {
                "$set": {
                    "status": "handled",
                    "handled_timestamp": int(time.time()),
                }
            },
        )

