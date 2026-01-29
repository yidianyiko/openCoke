# -*- coding: utf-8 -*-
"""
测试用 context fixtures
"""
import time

from bson import ObjectId


def get_full_context() -> dict:
    """获取完整的测试 context"""
    return {
        "user": {
            "_id": ObjectId(),
            "platforms": {"wechat": {"id": "wxid_test_user", "nickname": "测试用户"}},
        },
        "character": {
            "_id": ObjectId(),
            "platforms": {"wechat": {"id": "wxid_test_char", "nickname": "测试角色"}},
            "user_info": {
                "description": "测试角色描述",
                "status": {"place": "家里", "action": "休息"},
            },
        },
        "conversation": {
            "_id": ObjectId(),
            "conversation_info": {
                "chat_history": [],
                "input_messages": [{"type": "text", "content": "你好"}],
                "input_messages_str": "你好",
                "chat_history_str": "",
                "time_str": "2024年12月25日",
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
    }


def get_minimal_context() -> dict:
    """获取最小化测试 context"""
    return {
        "user": {"_id": ObjectId()},
        "character": {"_id": ObjectId()},
        "conversation": {"_id": ObjectId()},
        "relation": {"_id": ObjectId()},
    }


def get_context_for_reminder() -> dict:
    """获取提醒场景的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "明天早上8点提醒我开会"}
    ]
    return ctx


def get_context_with_context_retrieve() -> dict:
    """获取包含 context_retrieve 的 context"""
    ctx = get_full_context()
    ctx["context_retrieve"]["confirmed_reminders"] = "1. 明天早上8点 - 开会提醒"
    return ctx


def get_context_for_reminder_conflict() -> dict:
    """获取提醒冲突检测的 context"""
    ctx = get_full_context()
    ctx["context_retrieve"]["confirmed_reminders"] = (
        "1. 明天早上8点 - 开会\n" "2. 明天早上8点 - 吃药\n" "3. 明天早上8点 - 健身"
    )
    return ctx


def get_context_with_multimodal_response() -> dict:
    """获取包含多模态响应的 context"""
    ctx = get_full_context()
    ctx["MultiModalResponses"] = [
        {"type": "text", "content": "这是文本回复"},
        {"type": "image", "url": "https://example.com/image.jpg"},
    ]
    return ctx


def get_context_for_voice_message() -> dict:
    """获取语音消息的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "voice", "content": "[语音消息] 你好啊"}
    ]
    return ctx


def get_context_for_image_message() -> dict:
    """获取图片消息的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "image", "url": "https://example.com/image.jpg", "content": "[图片]"}
    ]
    return ctx


def get_context_with_history() -> dict:
    """获取带有聊天历史的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["chat_history"] = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮你的吗？"},
        {"role": "user", "content": "今天天气怎么样"},
    ]
    ctx["conversation"]["conversation_info"][
        "chat_history_str"
    ] = "用户: 你好\n助手: 你好！有什么可以帮你的吗？\n用户: 今天天气怎么样"
    return ctx


def get_context_with_long_history() -> dict:
    """获取长对话历史的 context"""
    ctx = get_full_context()
    history = []
    for i in range(50):
        history.append({"role": "user", "content": f"用户消息_{i}"})
        history.append({"role": "assistant", "content": f"助手回复_{i}"})
    ctx["conversation"]["conversation_info"]["chat_history"] = history
    return ctx


def get_context_for_repeated_message() -> dict:
    """获取重复消息场景的 context"""
    ctx = get_full_context()
    ctx["repeated_input_notice"] = "用户重复发送了相同的消息"
    return ctx


def get_context_for_turn_dedup() -> dict:
    """获取 turn-level 消息去重场景的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["turn_sent_contents"] = [
        "已经发送过的内容1",
        "已经发送过的内容2",
    ]
    return ctx


def get_context_with_relation() -> dict:
    """获取完整关系数据的 context"""
    ctx = get_full_context()
    ctx["relation"]["relationship"] = {
        "closeness": 75,
        "trustness": 80,
        "dislike": 5,
        "status": "聊天中",
    }
    ctx["relation"]["user_info"] = {
        "realname": "张三",
        "hobbyname": "小张",
        "description": "喜欢编程的程序员",
    }
    return ctx


def get_context_with_invalid_objectid() -> dict:
    """获取包含无效 ObjectId 的 context"""
    return {
        "user": {"_id": "invalid_object_id"},
        "character": {"_id": "also_invalid"},
        "conversation": {"_id": "not_valid_either"},
        "relation": {"_id": "nope"},
    }


def get_context_with_wrong_types() -> dict:
    """获取包含错误类型字段的 context"""
    ctx = get_full_context()
    ctx["relation"]["relationship"]["closeness"] = "not_a_number"
    ctx["relation"]["relationship"]["trustness"] = [1, 2, 3]
    ctx["conversation"]["conversation_info"]["chat_history"] = "should_be_list"
    return ctx


def get_context_with_missing_fields() -> dict:
    """获取缺失字段的 context"""
    return {
        "user": {"_id": ObjectId()},
        "character": {"_id": ObjectId()},
        "conversation": {"_id": ObjectId()},  # 缺少 conversation_info
        "relation": {"_id": ObjectId()},
    }


def get_context_with_boundary_values() -> dict:
    """获取边界值的 context"""
    ctx = get_full_context()
    ctx["relation"]["relationship"] = {
        "closeness": 0,
        "trustness": 100,
        "dislike": 100,
        "status": "边界测试",
    }
    return ctx


def get_context_with_out_of_range_values() -> dict:
    """获取超出范围值的 context"""
    ctx = get_full_context()
    ctx["relation"]["relationship"] = {
        "closeness": -10,
        "trustness": 150,
        "dislike": 0,
        "status": "超范围测试",
    }
    return ctx


def get_context_with_very_long_history() -> dict:
    """获取超长历史的 context"""
    ctx = get_full_context()
    history = []
    for i in range(500):
        history.append({"role": "user", "content": f"这是一条很长的用户消息_{i}" * 10})
        history.append(
            {"role": "assistant", "content": f"这是一条很长的助手回复_{i}" * 10}
        )
    ctx["conversation"]["conversation_info"]["chat_history"] = history
    return ctx


def get_context_with_binary_like_content() -> dict:
    """获取包含二进制类似内容的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "正常文本\x00带有空字符"}
    ]
    return ctx
