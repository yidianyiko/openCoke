from __future__ import annotations

import asyncio
import json

import websockets


class OpenClawClient:
    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self._ws = None
        self._connect_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._ws is not None:
            return

        async with self._connect_lock:
            if self._ws is not None:
                return
            self._ws = await websockets.connect(
                self.url,
                additional_headers={"Authorization": f"Bearer {self.token}"},
            )

    async def stop(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send(
        self,
        *,
        account_id: str,
        channel: str,
        idempotency_key: str,
        to: str | None = None,
        group_id: str | None = None,
        message: str | None = None,
        media_url: str | None = None,
    ) -> None:
        await self.start()

        payload = {
            "method": "send",
            "params": {
                "accountId": account_id,
                "channel": channel,
                "idempotencyKey": idempotency_key,
            },
        }
        if to is not None:
            payload["params"]["to"] = to
        if group_id is not None:
            payload["params"]["groupId"] = group_id
        if message is not None:
            payload["params"]["message"] = message
        if media_url is not None:
            payload["params"]["mediaUrl"] = media_url
        await self._ws.send(json.dumps(payload))
