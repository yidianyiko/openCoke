# -*- coding: utf-8 -*-
"""
测试用消息 fixtures
"""
import time
import uuid


def get_text_message(content: str = "你好") -> dict:
    """获取标准文本消息"""
    return {
        "type": "text",
        "content": content,
        "timestamp": int(time.time()),
    }


def get_voice_message() -> dict:
    """获取语音消息"""
    return {
        "type": "voice",
        "content": "[语音消息]",
        "duration": 3,
        "timestamp": int(time.time()),
    }


def get_reminder_create_message(time_str: str, title: str) -> dict:
    """获取创建提醒的消息"""
    return {
        "type": "text",
        "content": f"提醒我{time_str}{title}",
        "timestamp": int(time.time()),
    }


def get_reminder_cancel_message(keyword: str) -> dict:
    """获取取消提醒的消息"""
    return {
        "type": "text",
        "content": f"取消{keyword}的提醒",
        "timestamp": int(time.time()),
    }


def get_reminder_list_message() -> dict:
    """获取查询提醒列表的消息"""
    return {
        "type": "text",
        "content": "我有哪些提醒",
        "timestamp": int(time.time()),
    }


def get_recurring_reminder_message(recurrence_type: str) -> dict:
    """获取周期提醒消息"""
    type_map = {
        "daily": "每天早上8点提醒我吃药",
        "weekly": "每周一早上9点提醒我开会",
        "monthly": "每月1号提醒我交房租",
    }
    return {
        "type": "text",
        "content": type_map.get(recurrence_type, "每天提醒我"),
        "timestamp": int(time.time()),
    }


def get_reminder_trigger_message(reminder_id: str, title: str) -> dict:
    """获取提醒触发消息"""
    return {
        "type": "system",
        "source": "reminder",
        "reminder_id": reminder_id,
        "title": title,
        "timestamp": int(time.time()),
    }


def get_reminder_with_vague_time() -> dict:
    """获取模糊时间的提醒消息"""
    return {
        "type": "text",
        "content": "过两天提醒我买菜",
        "timestamp": int(time.time()),
    }


def get_reminder_with_past_time() -> dict:
    """获取过去时间的提醒消息"""
    return {
        "type": "text",
        "content": "昨天下午3点提醒我开会",
        "timestamp": int(time.time()),
    }


def get_reminder_with_conflicting_info() -> dict:
    """获取包含冲突时间的提醒消息"""
    return {
        "type": "text",
        "content": "早上8点提醒我开会，下午3点也要提醒",
        "timestamp": int(time.time()),
    }


def get_recurring_reminder_with_complex_pattern() -> dict:
    """获取复杂周期模式的提醒消息"""
    return {
        "type": "text",
        "content": "每个月最后一个工作日提醒我提交报表",
        "timestamp": int(time.time()),
    }


def get_message_with_null_content() -> dict:
    """获取 content 为 null 的消息"""
    return {
        "type": "text",
        "content": None,
        "timestamp": int(time.time()),
    }


def get_message_with_wrong_timestamp() -> dict:
    """获取时间戳类型错误的消息"""
    return {
        "type": "text",
        "content": "测试消息",
        "timestamp": "not_a_timestamp",
    }


def get_chat_history(length: int = 10) -> list:
    """获取聊天历史"""
    history = []
    base_time = int(time.time()) - length * 60
    for i in range(length):
        role = "user" if i % 2 == 0 else "assistant"
        history.append(
            {
                "role": role,
                "content": f"消息_{i}",
                "timestamp": base_time + i * 60,
            }
        )
    return history


def get_extremely_long_message(length: int = 10000) -> dict:
    """获取超长消息"""
    return {
        "type": "text",
        "content": "长消息内容" * (length // 5),
        "timestamp": int(time.time()),
    }


def get_long_message(length: int = 500) -> dict:
    """获取长消息"""
    return {
        "type": "text",
        "content": "a" * length,
        "timestamp": int(time.time()),
    }


def get_empty_message() -> dict:
    """获取空消息"""
    return {
        "type": "text",
        "content": "",
        "timestamp": int(time.time()),
    }


def get_concurrent_messages(user_id: str = "user", count: int = 10) -> list:
    """获取并发消息"""
    timestamp = int(time.time())
    return [
        {
            "message_id": str(uuid.uuid4()),
            "user_id": user_id,
            "sender": user_id,
            "content": f"并发消息_{i}",
            "timestamp": timestamp,
        }
        for i in range(count)
    ]


def get_interleaved_messages(user_ids: list, messages_per_user: int = 5) -> list:
    """获取交错的多用户消息"""
    messages = []
    base_time = int(time.time())
    for i in range(messages_per_user):
        for j, user_id in enumerate(user_ids):
            messages.append(
                {
                    "user_id": user_id,
                    "sender": user_id,
                    "content": f"用户{user_id}的消息_{i}",
                    "timestamp": base_time + i * len(user_ids) + j,
                }
            )
    return messages


def get_emoji_message() -> dict:
    """获取表情消息"""
    return {
        "type": "text",
        "content": "今天心情不错😄",
        "timestamp": int(time.time()),
    }


def get_special_chars_message() -> dict:
    """获取包含特殊字符的消息"""
    return {
        "type": "text",
        "content": "测试<script>alert('x')</script>",
        "timestamp": int(time.time()),
    }


def get_rapid_fire_messages(count: int = 5) -> list:
    """获取快速连续消息"""
    base_time = int(time.time())
    return [
        {"type": "text", "content": f"快速消息_{i}", "timestamp": base_time + i}
        for i in range(count)
    ]


def get_duplicate_messages(content: str, count: int = 3) -> list:
    """获取重复消息"""
    timestamp = int(time.time())
    return [
        {"type": "text", "content": content, "timestamp": timestamp}
        for _ in range(count)
    ]


def get_mixed_modal_message() -> list:
    """获取混合多模态消息"""
    return [
        {"type": "text", "content": "这是一条文字"},
        {"type": "image", "url": "https://example.com/image.jpg"},
    ]


def get_text_response(content: str) -> dict:
    """获取文本回复"""
    return {"type": "text", "content": content}


def get_voice_response(content: str, emotion: str) -> dict:
    """获取语音回复"""
    return {"type": "voice", "content": content, "emotion": emotion}


def get_photo_response(photo_id: str) -> dict:
    """获取图片回复"""
    return {"type": "photo", "content": photo_id}


def get_multimodal_response_full() -> list:
    """获取完整多模态响应"""
    return [
        {"type": "text", "content": "文本回复"},
        {"type": "voice", "content": "语音回复"},
        {"type": "photo", "content": "photo_001"},
    ]


def get_voice_message_with_long_duration(duration: int = 300) -> dict:
    """获取长时长语音消息"""
    return {
        "type": "voice",
        "content": "[语音消息]",
        "duration": duration,
        "timestamp": int(time.time()),
    }


def get_voice_message_with_zero_duration() -> dict:
    """获取零时长语音消息"""
    return {
        "type": "voice",
        "content": "[语音消息]",
        "duration": 0,
        "timestamp": int(time.time()),
    }


def get_voice_message_with_transcription_error() -> dict:
    """获取语音转写失败的消息"""
    return {
        "type": "voice",
        "content": "[ASR_ERROR] 转写失败",
        "duration": 5,
        "transcription_status": "failed",
        "timestamp": int(time.time()),
    }


def get_image_message_with_description() -> dict:
    """获取带描述的图片消息"""
    return {
        "type": "image",
        "url": "https://example.com/image.jpg",
        "description": "一张测试图片",
        "timestamp": int(time.time()),
    }


def get_image_message_with_invalid_url() -> dict:
    """获取无效URL的图片消息"""
    return {
        "type": "image",
        "url": "invalid-url",
        "timestamp": int(time.time()),
    }


def get_single_char_message() -> dict:
    """获取单字符消息"""
    return {"type": "text", "content": "A", "timestamp": int(time.time())}


def get_whitespace_only_message() -> dict:
    """获取纯空白消息"""
    return {"type": "text", "content": "   \n\t", "timestamp": int(time.time())}


def get_multiline_message() -> dict:
    """获取多行消息"""
    return {
        "type": "text",
        "content": "第一行\n第二行\n第三行",
        "timestamp": int(time.time()),
    }


def get_proactive_trigger_message(action: str) -> dict:
    """获取主动消息触发"""
    return {
        "type": "system",
        "source": "proactive",
        "action": action,
        "timestamp": int(time.time()),
    }


def get_malformed_message() -> dict:
    """获取缺少 content 的消息"""
    return {"type": "text", "timestamp": int(time.time())}


def get_message_with_invalid_type() -> dict:
    """获取无效类型消息"""
    return {"type": "unknown_type", "content": "测试", "timestamp": int(time.time())}


def get_message_with_future_timestamp() -> dict:
    """获取未来时间戳消息"""
    return {"type": "text", "content": "未来消息", "timestamp": int(time.time()) + 3600}


def get_message_with_very_old_timestamp() -> dict:
    """获取极旧时间戳消息"""
    return {"type": "text", "content": "很久以前", "timestamp": 0}


def get_system_message_user_joined() -> dict:
    """获取用户加入系统消息"""
    return {
        "type": "system",
        "event": "joined",
        "timestamp": int(time.time()),
    }


def get_system_message_user_left() -> dict:
    """获取用户离开系统消息"""
    return {
        "type": "system",
        "event": "left",
        "timestamp": int(time.time()),
    }


def get_system_message_error() -> dict:
    """获取系统错误消息"""
    return {
        "type": "system",
        "source": "error",
        "error_code": "ERR_TEST",
        "timestamp": int(time.time()),
    }


def get_xss_injection_message() -> dict:
    """获取 XSS 注入消息"""
    return {
        "type": "text",
        "content": "<script>alert('xss')</script><img onerror='alert(1)' src='x'>",
        "timestamp": int(time.time()),
    }


def get_nosql_injection_message() -> dict:
    """获取 NoSQL 注入消息"""
    return {
        "type": "text",
        "content": '{"$gt": ""}',
        "sender": '{"$ne": null}',
        "timestamp": int(time.time()),
    }


def get_path_traversal_message() -> dict:
    """获取路径穿越消息"""
    return {
        "type": "text",
        "content": "查看文件",
        "url": "../../../etc/passwd",
        "timestamp": int(time.time()),
    }


def get_command_injection_message() -> dict:
    """获取命令注入消息"""
    return {
        "type": "text",
        "content": "; rm -rf /; echo 'hacked'",
        "timestamp": int(time.time()),
    }
