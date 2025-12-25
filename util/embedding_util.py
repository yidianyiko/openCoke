import sys

sys.path.append(".")

import logging
from logging import getLogger

logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

from http import HTTPStatus

import dashscope

from dao.mongo import MongoDBBase


def embedding_by_aliyun(text, model="text - embedding - v3"):
    resp = dashscope.TextEmbedding.call(model=model, input=text)
    if resp.status_code == HTTPStatus.OK:
        output = resp.output
        return output["embeddings"][0]["embedding"]
    else:
        return None


def upsert_one(key, value, metadata, collection_name="embeddings"):
    mongo = MongoDBBase()
    key_embedding = embedding_by_aliyun(key)
    value_embedding = embedding_by_aliyun(value)
    if "type" not in metadata:
        metadata["type"] = "character_global"

    already = mongo.find_one(
        collection_name, query={"metadata.type": metadata["type"], "key": key}
    )

    if already is None:
        mid = mongo.insert_vector(
            collection_name=collection_name,
            key=key,
            key_embedding=key_embedding,
            value=value,
            value_embedding=value_embedding,
            metadata=metadata,
        )
        return mid
    else:
        mb = mongo.update_vector(
            collection_name=collection_name,
            doc_id=str(already["_id"]),
            key=key,
            key_embedding=key_embedding,
            value=value,
            value_embedding=value_embedding,
            metadata=metadata,
        )
        if mb:
            return str(already["_id"])

    return None


def store_chat_message(
    message: str,
    from_user: str,
    to_user: str,
    character_id: str,
    user_id: str,
    timestamp: int,
    message_type: str = "text",
) -> str:
    """
    Store a chat message as embedding for future retrieval.

    Args:
        message: Message content
        from_user: Sender user ID
        to_user: Receiver user ID
        character_id: Character ID
        user_id: User ID (human)
        timestamp: Message timestamp
        message_type: text / voice/image

    Returns:
        Inserted document ID, or None if failed
    """
    if not message or len(message.strip()) < 2:
        return None  # Skip empty or very short messages

    mongo = MongoDBBase()

    # Generate embedding for message content
    message_embedding = embedding_by_aliyun(message)
    if message_embedding is None:
        logger.warning(f"Failed to generate embedding for message: {message[:50]}...")
        return None

    # Create metadata
    metadata = {
        "type": "chat_history",
        "cid": character_id,
        "uid": user_id,
        "from_user": from_user,
        "to_user": to_user,
        "timestamp": timestamp,
        "message_type": message_type,
    }

    # Store (key = message content, value = same for chat)
    doc_id = mongo.insert_vector(
        collection_name="embeddings",
        key=message,
        key_embedding=message_embedding,
        value=message,
        value_embedding=message_embedding,
        metadata=metadata,
    )

    logger.debug(f"Stored chat message embedding: {doc_id}")
    return doc_id
