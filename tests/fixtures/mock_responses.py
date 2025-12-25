# -*- coding: utf-8 -*-
"""
Mock 响应数据
"""
import time
import uuid


def get_mock_llm_response(content="这是模拟的 LLM 响应"):
    """模拟 LLM API 响应"""
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


def get_mock_embedding_response(dimension=1536):
    """模拟 Embedding API 响应"""
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": [0.1] * dimension, "index": 0}],
        "model": "text-embedding-ada-002",
        "usage": {"prompt_tokens": 8, "total_tokens": 8},
    }


def get_mock_mongodb_document():
    """模拟 MongoDB 文档"""
    from bson import ObjectId

    return {
        "_id": ObjectId(),
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "status": "active",
    }


def get_mock_reminder():
    """模拟提醒数据"""
    return {
        "reminder_id": str(uuid.uuid4()),
        "user_id": "test_user",
        "character_id": "test_char",
        "conversation_id": "test_conv",
        "title": "测试提醒",
        "action_template": "提醒：测试提醒",
        "next_trigger_time": int(time.time()) + 3600,
        "time_original": "1小时后",
        "timezone": "Asia/Shanghai",
        "recurrence": {"enabled": False},
        "status": "confirmed",
        "created_at": int(time.time()),
        "triggered_count": 0,
    }
