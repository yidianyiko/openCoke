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


def get_empty_message() -> dict:
    """获取空消息"""
    return {
        "type": "text",
        "content": "",
        "timestamp": int(time.time()),
    }


def get_concurrent_messages(user_id: str, count: int = 10) -> list:
    """获取并发消息"""
    timestamp = int(time.time())
    return [
        {
            "message_id": str(uuid.uuid4()),
            "user_id": user_id,
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
                    "content": f"用户{user_id}的消息_{i}",
                    "timestamp": base_time + i * len(user_ids) + j,
                }
            )
    return messages


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
