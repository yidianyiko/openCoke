import hashlib
import sys
from datetime import datetime
from typing import List, Optional

sys.path.append(".")

from util.log_util import get_logger

logger = get_logger(__name__)

from http import HTTPStatus

import dashscope

from dao.mongo import MongoDBBase

# Embedding cache collection name
EMBEDDING_CACHE_COLLECTION = "embedding_cache"


def _hash_text(text: str, model: str) -> str:
    """Generate a hash key for caching based on text and model."""
    content = f"{model}:{text}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_cached_embedding(text: str, model: str) -> Optional[List[float]]:
    """Retrieve cached embedding from MongoDB."""
    try:
        mongo = MongoDBBase()
        text_hash = _hash_text(text, model)
        cached = mongo.find_one(
            EMBEDDING_CACHE_COLLECTION, {"text_hash": text_hash, "model": model}
        )
        if cached and "embedding" in cached:
            # Update last_accessed timestamp
            mongo.update_one(
                EMBEDDING_CACHE_COLLECTION,
                {"text_hash": text_hash, "model": model},
                {"$set": {"last_accessed": datetime.utcnow()}},
            )
            logger.debug(f"Embedding cache hit for text hash: {text_hash[:16]}...")
            return cached["embedding"]
    except Exception as e:
        logger.warning(f"Failed to get cached embedding: {e}")
    return None


def _cache_embedding(text: str, model: str, embedding: List[float]) -> bool:
    """Store embedding in MongoDB cache."""
    try:
        mongo = MongoDBBase()
        text_hash = _hash_text(text, model)
        now = datetime.utcnow()
        doc = {
            "text_hash": text_hash,
            "model": model,
            "embedding": embedding,
            "text_preview": text[:100] if len(text) > 100 else text,
            "created_at": now,
            "last_accessed": now,
        }
        # Upsert to handle race conditions
        mongo.get_collection(EMBEDDING_CACHE_COLLECTION).update_one(
            {"text_hash": text_hash, "model": model}, {"$set": doc}, upsert=True
        )
        logger.debug(f"Embedding cached for text hash: {text_hash[:16]}...")
        return True
    except Exception as e:
        logger.warning(f"Failed to cache embedding: {e}")
        return False


def embedding_by_aliyun(
    text: str, model: str = "text-embedding-v3", use_cache: bool = True
) -> Optional[List[float]]:
    """
    Generate embedding for text using DashScope API with optional caching.

    Args:
        text: Text to generate embedding for
        model: Embedding model to use
        use_cache: Whether to use MongoDB cache (default: True)

    Returns:
        List of floats representing the embedding, or None if failed
    """
    if not text or not text.strip():
        return None

    # Try cache first
    if use_cache:
        cached = _get_cached_embedding(text, model)
        if cached is not None:
            return cached

    # Call DashScope API
    resp = dashscope.TextEmbedding.call(model=model, input=text)
    if resp.status_code == HTTPStatus.OK:
        output = resp.output
        embedding = output["embeddings"][0]["embedding"]

        # Cache the result
        if use_cache:
            _cache_embedding(text, model, embedding)

        return embedding
    else:
        logger.warning(
            f"DashScope embedding API failed: {resp.status_code} - {resp.message if hasattr(resp, 'message') else 'Unknown error'}"
        )
        return None


def init_embedding_cache_index():
    """Initialize index for embedding cache collection."""
    try:
        mongo = MongoDBBase()
        collection = mongo.get_collection(EMBEDDING_CACHE_COLLECTION)
        # Create compound index on text_hash + model for fast lookups
        collection.create_index([("text_hash", 1), ("model", 1)], unique=True)
        # Create index on last_accessed for cleanup queries
        collection.create_index("last_accessed")
        logger.info("Embedding cache indexes initialized")
    except Exception as e:
        logger.warning(f"Failed to create embedding cache indexes: {e}")


def get_embedding_cache_stats() -> dict:
    """Get statistics about the embedding cache."""
    try:
        mongo = MongoDBBase()
        total = mongo.count_documents(EMBEDDING_CACHE_COLLECTION)
        return {"total_cached": total, "collection": EMBEDDING_CACHE_COLLECTION}
    except Exception as e:
        logger.warning(f"Failed to get cache stats: {e}")
        return {"error": str(e)}


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
        message_type: text/voice/image

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
