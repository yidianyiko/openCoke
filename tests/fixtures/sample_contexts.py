# -*- coding: utf-8 -*-
"""
标准测试 Context 数据
"""
from bson import ObjectId
from datetime import datetime


def get_minimal_context():
    """最小化的测试 context"""
    return {
        "user": {"_id": ObjectId(), "platforms": {"wechat": {"id": "test_user"}}},
        "character": {"_id": ObjectId(), "platforms": {"wechat": {"id": "test_char"}}},
        "conversation": {"_id": ObjectId(), "conversation_info": {"chat_history": []}},
        "relation": {"_id": ObjectId()},
    }


def get_full_context():
    """完整的测试 context"""
    return {
        "user": {
            "_id": ObjectId(),
            "platforms": {
                "wechat": {"id": "wxid_test_user", "nickname": "测试用户"}
            },
        },
        "character": {
            "_id": ObjectId(),
            "platforms": {
                "wechat": {"id": "wxid_test_char", "nickname": "测试角色"}
            },
            "user_info": {
                "description": "测试角色描述",
                "status": {"place": "家里", "action": "休息"},
            },
        },
        "conversation": {
            "_id": ObjectId(),
            "conversation_info": {
                "chat_history": [],
                "input_messages": [],
                "input_messages_str": "",
                "chat_history_str": "",
                "time_str": datetime.now().strftime("%Y年%m月%d日"),
                "photo_history": [],
                "future": {"timestamp": None, "action": None},
                "turn_sent_contents": [],
            },
        },
        "relation": {
            "_id": ObjectId(),
            "uid": "test_uid",
            "cid": "test_cid",
            "relationship": {
                "closeness": 50,
                "trustness": 50,
                "dislike": 0,
                "status": "空闲",
            },
            "user_info": {"realname": "", "hobbyname": "", "description": ""},
            "character_info": {
                "longterm_purpose": "",
                "shortterm_purpose": "",
                "attitude": "",
            },
        },
        "news_str": "",
        "repeated_input_notice": "",
        "MultiModalResponses": [],
        "context_retrieve": {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": "",
        },
        "query_rewrite": {
            "InnerMonologue": "",
            "CharacterSettingQueryQuestion": "",
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": "",
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": "",
        },
    }


def get_context_with_history():
    """带有聊天历史的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["chat_history"] = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！很高兴见到你"},
        {"role": "user", "content": "今天天气怎么样？"},
    ]
    ctx["conversation"]["conversation_info"]["chat_history_str"] = (
        "用户: 你好\n角色: 你好！很高兴见到你\n用户: 今天天气怎么样？"
    )
    return ctx
