import asyncio
import json
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_send_serializes_openclaw_rpc_payload():
    from api.openclaw_client import OpenClawClient

    client = OpenClawClient("ws://openclaw.example.com", "token-123")
    client._ws = AsyncMock()

    await client.send(
        account_id="bot-a",
        channel="wechat",
        idempotency_key="reply-1",
        to="wx-user-1",
        message="hello",
        media_url=None,
    )

    sent = json.loads(client._ws.send.await_args.args[0])
    assert sent == {
        "method": "send",
        "params": {
            "accountId": "bot-a",
            "channel": "wechat",
            "idempotencyKey": "reply-1",
            "to": "wx-user-1",
            "message": "hello",
        },
    }


@pytest.mark.asyncio
async def test_concurrent_send_reuses_single_lazy_connection(monkeypatch):
    from api.openclaw_client import OpenClawClient

    ws = AsyncMock()
    connect_calls = []

    async def fake_connect(*args, **kwargs):
        connect_calls.append((args, kwargs))
        await asyncio.sleep(0)
        return ws

    monkeypatch.setattr("api.openclaw_client.websockets.connect", fake_connect)

    client = OpenClawClient("ws://openclaw.example.com", "token-123")

    await asyncio.gather(
        client.send(
            account_id="bot-a",
            channel="wechat",
            idempotency_key="reply-1",
            to="wx-user-1",
            message="hello",
        ),
        client.send(
            account_id="bot-a",
            channel="wechat",
            idempotency_key="reply-2",
            to="wx-user-1",
            message="again",
        ),
    )

    assert len(connect_calls) == 1
    assert ws.send.await_count == 2
