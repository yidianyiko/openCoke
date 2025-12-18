# -*- coding: utf-8 -*-
"""
Context Retrieve Tool for Agno Agent

This tool provides vector search capabilities for retrieving:
- Character global settings (角色全局人物设定)
- Character private settings (角色私有设定)
- User profile (用户个人设定)
- Character knowledge (角色知识)
- User reminders (用户待办提醒)

Requirements: 3.1
"""

import logging
from typing import Optional

from dao.mongo import MongoDBBase
from util.embedding_util import embedding_by_aliyun

logger = logging.getLogger(__name__)


def _merge_results_embedding(merged_results: dict, results: list, bar_min: float, bar_max: float, weight: float) -> dict:
    """
    Merge embedding search results with weighted scoring.
    
    Args:
        merged_results: Existing merged results dict
        results: New results to merge
        bar_min: Minimum similarity threshold
        bar_max: Maximum similarity threshold
        weight: Weight factor for scoring
    
    Returns:
        Updated merged results dict
    """
    for result in results:
        # Cap similarity at bar_max
        if result["similarity"] > bar_max:
            result["similarity"] = bar_max
        # Skip results below threshold
        if result["similarity"] < bar_min:
            continue

        # Calculate weighted score
        result_weight = weight * (result["similarity"] - bar_min) / (bar_max - bar_min)

        # Merge results
        result_id = str(result["_id"])
        if result_id not in merged_results:
            merged_results[result_id] = {
                "_id": result_id,
                "key": result["key"],
                "value": result["value"],
                "similarity": result["similarity"],
                "weight": result_weight
            }
        else:
            merged_results[result_id]["weight"] += result_weight

    return merged_results


def _merge_results_text(merged_results: dict, results: list, total_weight: float) -> dict:
    """
    Merge text/keyword search results with weighted scoring.
    
    Args:
        merged_results: Existing merged results dict
        results: New results to merge
        total_weight: Total weight to distribute among results
    
    Returns:
        Updated merged results dict
    """
    if len(results) == 0:
        return merged_results
    
    # Distribute weight evenly
    result_weight = total_weight / len(results)
    
    # Merge results
    for result in results:
        result_id = str(result["_id"])
        if result_id not in merged_results:
            merged_results[result_id] = {
                "_id": result_id,
                "key": result["key"],
                "value": result["value"],
                "weight": result_weight
            }
        else:
            merged_results[result_id]["weight"] += result_weight

    return merged_results


def _top_n(results: dict, n: int, photo_prefix: bool = False) -> str:
    """
    Get top N results sorted by weight and format as string.
    
    Args:
        results: Dict of results with weight scores
        n: Number of top results to return
        photo_prefix: Whether to add photo prefix to results
    
    Returns:
        Formatted string of top N results
    """
    # Sort by weight descending
    sorted_items = sorted(
        results.items(),
        key=lambda x: x[1]['weight'],
        reverse=True
    )
    
    # Get top N
    top_n_results = [item[1] for item in sorted_items[:n]]

    # Format as string
    top_n_str_list = []
    for result in top_n_results:
        line = str(result["key"] + "：" + result["value"]).strip()
        if photo_prefix:
            line = "「照片" + str(result["_id"]) + "」" + line
        top_n_str_list.append(line)
    
    return "\n".join(top_n_str_list)


def _search_embeddings(
    mongo: MongoDBBase,
    query_question: str,
    query_keywords: str,
    metadata_type: str,
    character_id: str,
    user_id: Optional[str] = None,
    top_k: int = 8,
    result_limit: int = 6
) -> str:
    """
    Perform vector and keyword search for embeddings.
    
    Args:
        mongo: MongoDB connection
        query_question: Question for vector search
        query_keywords: Keywords for text search (comma-separated)
        metadata_type: Type of embedding (character_global, character_private, user, character_knowledge)
        character_id: Character ID
        user_id: User ID (optional, required for some types)
        top_k: Number of results for vector search
        result_limit: Final number of results to return
    
    Returns:
        Formatted string of search results
    """
    merged_results = {}
    
    # Build metadata filter
    metadata_filter = {
        "type": metadata_type,
        "cid": character_id
    }
    if user_id and metadata_type in ["character_private", "user"]:
        metadata_filter["uid"] = user_id
    
    # Skip if no query
    if not query_question or query_question == "空":
        return ""
    
    # Vector search on key embedding
    emb_query = embedding_by_aliyun(query_question)
    results = mongo.vector_search(
        "embeddings",
        query_embedding=emb_query,
        embedding_field="key_embedding",
        metadata_filters=metadata_filter,
        top_k=top_k,
    )
    merged_results = _merge_results_embedding(merged_results, results, 0.3, 1, 0.7)

    # Vector search on value embedding
    results = mongo.vector_search(
        "embeddings",
        query_embedding=emb_query,
        embedding_field="value_embedding",
        metadata_filters=metadata_filter,
        top_k=top_k,
    )
    merged_results = _merge_results_embedding(merged_results, results, 0.3, 1, 0.3)

    # Keyword search on key field
    if query_keywords:
        for keyword in str(query_keywords).split(","):
            keyword = keyword.strip()
            if not keyword:
                continue
            keyword_results = mongo.find_many("embeddings", query={
                "key": {"$in": [keyword]},
                "metadata": metadata_filter,
            }, limit=5)
            merged_results = _merge_results_text(merged_results, keyword_results, 1)

    # Keyword search on value field
    if query_keywords:
        for keyword in str(query_keywords).split(","):
            keyword = keyword.strip()
            if not keyword:
                continue
            keyword_results = mongo.find_many("embeddings", query={
                "value": {"$in": [keyword]},
                "metadata": metadata_filter,
            }, limit=5)
            merged_results = _merge_results_text(merged_results, keyword_results, 1)

    return _top_n(merged_results, result_limit)


def _search_chat_history(
    mongo: MongoDBBase,
    query_question: str,
    query_keywords: str,
    character_id: str,
    user_id: str,
    top_k: int = 15,
    result_limit: int = 10
) -> str:
    """
    Search for semantically relevant chat history messages.
    
    Args:
        mongo: MongoDB connection
        query_question: Question for vector search
        query_keywords: Keywords for text search (comma-separated)
        character_id: Character ID
        user_id: User ID
        top_k: Number of results for vector search
        result_limit: Final number of results to return
    
    Returns:
        Formatted string of relevant chat history messages
    """
    merged_results = {}
    
    # Build metadata filter for chat_history type
    metadata_filter = {
        "type": "chat_history",
        "cid": character_id,
        "uid": user_id
    }
    
    # Skip if no query
    if not query_question and not query_keywords:
        return ""
    
    # Vector search on message content
    if query_question:
        emb_query = embedding_by_aliyun(query_question)
        if emb_query:
            results = mongo.vector_search(
                "embeddings",
                query_embedding=emb_query,
                embedding_field="key_embedding",
                metadata_filters=metadata_filter,
                top_k=top_k,
            )
            merged_results = _merge_results_embedding(merged_results, results, 0.4, 1, 0.8)
    
    # Keyword search
    if query_keywords:
        for keyword in str(query_keywords).split(","):
            keyword = keyword.strip()
            if not keyword:
                continue
            keyword_results = mongo.find_many("embeddings", query={
                "key": {"$regex": keyword, "$options": "i"},
                "metadata": metadata_filter,
            }, limit=5)
            merged_results = _merge_results_text(merged_results, keyword_results, 0.5)
    
    # Format results with timestamp info
    sorted_items = sorted(
        merged_results.items(),
        key=lambda x: x[1]['weight'],
        reverse=True
    )
    
    top_n_results = [item[1] for item in sorted_items[:result_limit]]
    
    # Format as string with message content
    result_lines = []
    for result in top_n_results:
        message = str(result["value"]).strip()
        if message:
            result_lines.append(f"- {message}")
    
    return "\n".join(result_lines)


def context_retrieve_tool(
    character_setting_query: str = "",
    character_setting_keywords: str = "",
    user_profile_query: str = "",
    user_profile_keywords: str = "",
    character_knowledge_query: str = "",
    character_knowledge_keywords: str = "",
    chat_history_query: str = "",
    chat_history_keywords: str = "",
    character_id: str = "",
    user_id: str = ""
) -> dict:
    """
    向量检索工具，检索角色全局设定、角色私有设定、用户资料、角色知识、相关历史对话
    
    Args:
        character_setting_query: 角色设定检索问题
        character_setting_keywords: 角色设定检索关键词（逗号分隔）
        user_profile_query: 用户资料检索问题
        user_profile_keywords: 用户资料检索关键词（逗号分隔）
        character_knowledge_query: 角色知识检索问题
        character_knowledge_keywords: 角色知识检索关键词（逗号分隔）
        chat_history_query: 历史对话检索问题
        chat_history_keywords: 历史对话检索关键词（逗号分隔）
        character_id: 角色ID
        user_id: 用户ID
    
    Returns:
        检索结果 dict，包含 character_global, character_private, user, character_knowledge, confirmed_reminders, relevant_history 字段
    """
    mongo = MongoDBBase()
    
    return_resp = {
        "character_global": "",
        "character_private": "",
        "user": "",
        "character_knowledge": "",
        "confirmed_reminders": "",
        "relevant_history": ""
    }
    
    try:
        # 角色全局人物设定
        return_resp["character_global"] = _search_embeddings(
            mongo=mongo,
            query_question=character_setting_query,
            query_keywords=character_setting_keywords,
            metadata_type="character_global",
            character_id=character_id,
            user_id=None,
            top_k=8,
            result_limit=6
        )
        
        # 角色私有设定
        return_resp["character_private"] = _search_embeddings(
            mongo=mongo,
            query_question=character_setting_query,
            query_keywords=character_setting_keywords,
            metadata_type="character_private",
            character_id=character_id,
            user_id=user_id,
            top_k=8,
            result_limit=6
        )
        
        # 用户个人设定
        return_resp["user"] = _search_embeddings(
            mongo=mongo,
            query_question=user_profile_query,
            query_keywords=user_profile_keywords,
            metadata_type="user",
            character_id=character_id,
            user_id=user_id,
            top_k=8,
            result_limit=6
        )
        
        # 角色知识
        return_resp["character_knowledge"] = _search_embeddings(
            mongo=mongo,
            query_question=character_knowledge_query,
            query_keywords=character_knowledge_keywords,
            metadata_type="character_knowledge",
            character_id=character_id,
            user_id=None,
            top_k=8,
            result_limit=6
        )
        
        # Chat history retrieval (semantically relevant messages)
        if chat_history_query or chat_history_keywords:
            return_resp["relevant_history"] = _search_chat_history(
                mongo=mongo,
                query_question=chat_history_query,
                query_keywords=chat_history_keywords,
                character_id=character_id,
                user_id=user_id,
                top_k=15,
                result_limit=10
            )
            logger.info(f"Retrieved relevant history messages")
        
        # 用户待办提醒
        try:
            from dao.reminder_dao import ReminderDAO
            from util.time_util import format_time_friendly
            
            reminder_dao = ReminderDAO()
            items = reminder_dao.find_reminders_by_user(user_id, status="confirmed")
            lines = []
            for c in items[:50]:
                t = str(c.get("title", ""))
                st = str(c.get("status", ""))
                ts = int(c.get("next_trigger_time", 0) or 0)
                time_str = format_time_friendly(ts) if ts > 0 else ""
                line = t
                if st:
                    line = line + " · " + st
                if time_str:
                    line = line + " · " + time_str
                lines.append(line)
            return_resp["confirmed_reminders"] = "\n".join(lines)
            reminder_dao.close()
        except Exception as e:
            logger.warning(f"Failed to retrieve reminders: {e}")
            
    except Exception as e:
        logger.error(f"Error in context_retrieve_tool: {e}")
        raise
    
    return return_resp
