"""LangBot message format adapter.

Converts between LangBot webhook format and Coke standard message format.
"""
from util.log_util import get_logger

logger = get_logger(__name__)


def langbot_webhook_to_std(webhook_payload: dict) -> dict:
    """
    Convert LangBot webhook payload to Coke standard message format.

    Args:
        webhook_payload: LangBot webhook event payload

    Returns:
        Coke standard inputmessage format
    """
    event_type = webhook_payload.get("event_type", "")
    data = webhook_payload.get("data", {})

    # Extract common fields
    bot_uuid = data.get("bot_uuid", "")
    adapter_name = data.get("adapter_name", "")
    sender = data.get("sender", {})
    sender_id = sender.get("id", "")
    sender_name = sender.get("name", "")
    timestamp = data.get("timestamp", 0)
    message_parts = data.get("message", [])

    # Determine if group or person message
    is_group = event_type == "bot.group_message"
    group_data = data.get("group", {})
    chatroom_name = group_data.get("id") if is_group else None

    # Extract message content and type
    message_type, message_content, extra_metadata = _extract_message_content(message_parts)

    # Build metadata
    metadata = {
        "langbot_adapter": adapter_name,
        "langbot_bot_uuid": bot_uuid,
        "langbot_sender_id": sender_id,
        "langbot_sender_name": sender_name,
        "langbot_target_type": "group" if is_group else "person",
        "langbot_event_uuid": webhook_payload.get("uuid", ""),
    }

    if is_group:
        metadata["langbot_group_id"] = group_data.get("id", "")
        metadata["langbot_group_name"] = group_data.get("name", "")

    # Merge extra metadata (e.g., image URL)
    metadata.update(extra_metadata)

    return {
        "input_timestamp": timestamp,
        "handled_timestamp": None,
        "status": "pending",
        "platform": "langbot",
        "chatroom_name": chatroom_name,
        "message_type": message_type,
        "message": message_content,
        "metadata": metadata,
    }


def _extract_message_content(message_parts: list) -> tuple[str, str, dict]:
    """
    Extract message type, content, and extra metadata from message parts.

    Args:
        message_parts: List of message components from LangBot

    Returns:
        Tuple of (message_type, message_content, extra_metadata)
    """
    if not message_parts:
        return "text", "", {}

    # Collect all text parts
    text_parts: list[str] = []
    extra_metadata: dict = {}
    detected_type = "text"

    for part in message_parts:
        part_type = part.get("type", "")

        if part_type == "Plain":
            text_parts.append(part.get("text", ""))
        elif part_type == "Image":
            detected_type = "image"
            extra_metadata["url"] = part.get("url", "")
        elif part_type == "Voice":
            detected_type = "voice"
            extra_metadata["url"] = part.get("url", "")
        # Add more types as needed

    message_content = "".join(text_parts)

    return detected_type, message_content, extra_metadata


def std_to_langbot_message(outputmessage: dict) -> dict:
    """
    Convert Coke standard outputmessage to LangBot Send API format.

    Args:
        outputmessage: Coke standard outputmessage

    Returns:
        Dict with bot_uuid, target_type, target_id, message_chain
    """
    metadata = outputmessage.get("metadata", {})
    message_type = outputmessage.get("message_type", "text")
    message_content = outputmessage.get("message", "")

    # Build message chain based on type
    if message_type == "text":
        message_chain = [{"type": "Plain", "text": message_content}]
    elif message_type == "image":
        message_chain = [{"type": "Image", "url": metadata.get("url", "")}]
    elif message_type == "voice":
        message_chain = [{"type": "Voice", "url": metadata.get("url", "")}]
    else:
        # Fallback to text
        message_chain = [{"type": "Plain", "text": message_content}]

    return {
        "bot_uuid": metadata.get("langbot_bot_uuid", ""),
        "target_type": metadata.get("langbot_target_type", "person"),
        "target_id": metadata.get("langbot_target_id", ""),
        "message_chain": message_chain,
    }

