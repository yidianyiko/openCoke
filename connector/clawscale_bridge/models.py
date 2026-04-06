from dataclasses import dataclass
from typing import Any


@dataclass
class BridgeInboundPayload:
    tenant_id: str
    channel_id: str
    conversation_id: str
    platform: str
    end_user_id: str
    external_id: str
    external_message_id: str
    sender: str
    text: str
    timestamp: int
    metadata: dict[str, Any]
