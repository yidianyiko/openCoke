# -*- coding: utf-8 -*-
"""
标准测试消息数据
"""
import time
from datetime import datetime


def get_text_message(content="测试消息"):
    """文本消息"""
    return {
        "type": "text",
        "content": content,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_voice_message(content="语音内容", duration=5):
    """语音消息"""
    return {
        "type": "voice",
        "content": content,
        "duration": duration,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_image_message(url="https://example.com/image.jpg"):
    """图片消息"""
    return {
        "type": "image",
        "url": url,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_multimodal_response():
    """多模态响应"""
    return [
        {"type": "text", "content": "这是文本回复"},
        {"type": "voice", "content": "这是语音回复", "emotion": "高兴"},
    ]


def get_chat_history(length=5):
    """生成聊天历史"""
    history = []
    for i in range(length):
        if i % 2 == 0:
            history.append({"role": "user", "content": f"用户消息 {i+1}"})
        else:
            history.append({"role": "assistant", "content": f"助手回复 {i+1}"})
    return history


# ============ Reminder Related Messages ============


def get_reminder_create_message(time_str="明天早上8点", content="开会"):
    """创建提醒的消息"""
    return {
        "type": "text",
        "content": f"提醒我{time_str}{content}",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_reminder_cancel_message(keyword="开会"):
    """取消提醒的消息"""
    return {
        "type": "text",
        "content": f"取消{keyword}的提醒",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_reminder_list_message():
    """查询提醒列表的消息"""
    return {
        "type": "text",
        "content": "我有哪些提醒？",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_recurring_reminder_message(recurrence_type="daily"):
    """周期提醒的消息"""
    recurrence_text = {
        "daily": "每天早上7点",
        "weekly": "每周一早上9点",
        "monthly": "每月第一天上午10点",
    }
    return {
        "type": "text",
        "content": f"提醒我{recurrence_text.get(recurrence_type, '每天')}吃药",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


# ============ Multimodal Messages ============


def get_mixed_modal_message():
    """多模态混合消息"""
    return [
        {"type": "text", "content": "看看这张图片"},
        {"type": "image", "url": "https://example.com/photo.jpg"},
    ]


def get_voice_with_text_message():
    """语音+文本消息"""
    return {
        "type": "voice",
        "content": "语音转写内容",
        "duration": 10,
        "text_fallback": "如果语音播放失败，请查看此文本",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


# ============ Special Scenario Messages ============


def get_long_message(length=500):
    """长文本消息"""
    return {
        "type": "text",
        "content": "这是一段很长的消息。" * (length // 10),
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_empty_message():
    """空消息"""
    return {
        "type": "text",
        "content": "",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_emoji_message():
    """表情消息"""
    return {
        "type": "text",
        "content": "😄👍❤️",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_special_chars_message():
    """特殊字符消息"""
    return {
        "type": "text",
        "content": "测试<script>alert('xss')</script>特殊\n字符\t处理",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_proactive_trigger_message(action="询问用户近况"):
    """主动消息触发"""
    return {
        "type": "system",
        "source": "proactive",
        "action": action,
        "timestamp": int(time.time()),
    }


def get_reminder_trigger_message(reminder_id="test_reminder", title="开会提醒"):
    """提醒触发消息"""
    return {
        "type": "system",
        "source": "reminder",
        "reminder_id": reminder_id,
        "title": title,
        "timestamp": int(time.time()),
    }


# ============ Response Messages ============


def get_text_response(content="好的，我明白了"):
    """文本回复"""
    return {"type": "text", "content": content}


def get_voice_response(content="这是语音回复", emotion="高兴"):
    """语音回复"""
    return {"type": "voice", "content": content, "emotion": emotion}


def get_photo_response(photo_id="photo_001"):
    """图片回复"""
    return {"type": "photo", "content": photo_id}


def get_multimodal_response_full():
    """完整多模态响应"""
    return [
        {"type": "text", "content": "这是文本回复"},
        {"type": "voice", "content": "这是语音回复", "emotion": "高兴"},
        {"type": "photo", "content": "photo_001"},
    ]


# ============ Edge Case Messages ============


def get_rapid_fire_messages(count=5):
    """快速连续消息"""
    base_time = int(time.time())
    return [
        {
            "type": "text",
            "content": f"连续消息 {i+1}",
            "timestamp": base_time + i,
            "sender": "test_user",
        }
        for i in range(count)
    ]


def get_duplicate_messages(content="重复内容", count=3):
    """重复消息"""
    base_time = int(time.time())
    return [
        {
            "type": "text",
            "content": content,
            "timestamp": base_time + i * 10,
            "sender": "test_user",
        }
        for i in range(count)
    ]


# ============ Malformed and Invalid Messages ============


def get_malformed_message():
    """格式错误的消息（缺少必要字段）"""
    return {
        "type": "text",
        # missing content field
        "timestamp": int(time.time()),
    }


def get_message_with_invalid_type():
    """无效类型的消息"""
    return {
        "type": "unknown_type",
        "content": "测试内容",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_message_with_null_content():
    """内容为 null 的消息"""
    return {
        "type": "text",
        "content": None,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_message_with_wrong_timestamp():
    """时间戳错误的消息"""
    return {
        "type": "text",
        "content": "测试内容",
        "timestamp": "not_a_timestamp",  # should be int
        "sender": "test_user",
    }


def get_message_with_future_timestamp():
    """未来时间戳的消息"""
    return {
        "type": "text",
        "content": "来自未来的消息",
        "timestamp": int(time.time()) + 86400 * 365,  # 1 year in future
        "sender": "test_user",
    }


def get_message_with_very_old_timestamp():
    """很久以前的消息"""
    return {
        "type": "text",
        "content": "很旧的消息",
        "timestamp": 0,  # epoch time
        "sender": "test_user",
    }


# ============ Boundary Condition Messages ============


def get_single_char_message():
    """单字符消息"""
    return {
        "type": "text",
        "content": "嘿",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_whitespace_only_message():
    """纯空白消息"""
    return {
        "type": "text",
        "content": "   \n\t\r   ",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_extremely_long_message(length=10000):
    """极长消息"""
    return {
        "type": "text",
        "content": "超长内容" * (length // 4),
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_unicode_edge_case_message():
    """Unicode 边界情况消息"""
    return {
        "type": "text",
        "content": "\u0000\u001f\ufffe\uffff\ud800\udfff",  # Invalid unicode chars
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_multiline_message():
    """多行消息"""
    return {
        "type": "text",
        "content": "第一行\n第二行\n第三行\n\n空行后的内容",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


# ============ Voice Message Variants ============


def get_voice_message_with_long_duration(duration=300):
    """超长语音消息"""
    return {
        "type": "voice",
        "content": "这是一段很长的语音消息内容",
        "duration": duration,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_voice_message_with_zero_duration():
    """零时长语音消息"""
    return {
        "type": "voice",
        "content": "",
        "duration": 0,
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_voice_message_with_transcription_error():
    """转写失败的语音消息"""
    return {
        "type": "voice",
        "content": "[ASR_ERROR]",
        "duration": 5,
        "transcription_status": "failed",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


# ============ Image Message Variants ============


def get_image_message_with_invalid_url():
    """无效 URL 的图片消息"""
    return {
        "type": "image",
        "url": "not_a_valid_url",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_image_message_with_broken_url():
    """损坏 URL 的图片消息"""
    return {
        "type": "image",
        "url": "https://broken-domain-12345.com/image.jpg",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_image_message_with_description():
    """带描述的图片消息"""
    return {
        "type": "image",
        "url": "https://example.com/image.jpg",
        "description": "一张美丽的风景照，蓝天白云大海",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


# ============ Reminder Message Variants ============


def get_reminder_with_vague_time():
    """模糊时间的提醒消息"""
    return {
        "type": "text",
        "content": "记得过两天提醒我做个事",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_reminder_with_past_time():
    """过去时间的提醒消息"""
    return {
        "type": "text",
        "content": "昨天早上8点提醒我开会",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_reminder_with_conflicting_info():
    """信息冲突的提醒消息"""
    return {
        "type": "text",
        "content": "明天早上8点和明天下午3点都提醒我开同一个会",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_recurring_reminder_with_complex_pattern():
    """复杂周期的提醒消息"""
    return {
        "type": "text",
        "content": "每个月最后一个工作日下午3点提醒我提交月报",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


# ============ System Message Variants ============


def get_system_message_user_joined():
    """用户加入系统消息"""
    return {
        "type": "system",
        "source": "user_event",
        "event": "joined",
        "user_id": "new_user_123",
        "timestamp": int(time.time()),
    }


def get_system_message_user_left():
    """用户离开系统消息"""
    return {
        "type": "system",
        "source": "user_event",
        "event": "left",
        "user_id": "leaving_user_456",
        "timestamp": int(time.time()),
    }


def get_system_message_error():
    """系统错误消息"""
    return {
        "type": "system",
        "source": "error",
        "error_code": "RATE_LIMIT_EXCEEDED",
        "error_message": "请求过于频繁，请稍后再试",
        "timestamp": int(time.time()),
    }


# ============ Concurrent Processing Messages ============


def get_concurrent_messages(user_id="test_user", count=10):
    """生成并发处理测试用的消息（相同时间戳）"""
    current_time = int(time.time())
    return [
        {
            "type": "text",
            "content": f"并发消息_{i}",
            "timestamp": current_time,  # Same timestamp
            "sender": user_id,
            "message_id": f"msg_{current_time}_{i}",
        }
        for i in range(count)
    ]


def get_interleaved_messages(user_ids=None, messages_per_user=3):
    """多用户交错消息"""
    if user_ids is None:
        user_ids = ["user_a", "user_b", "user_c"]
    base_time = int(time.time())
    messages = []
    for i in range(messages_per_user):
        for j, user_id in enumerate(user_ids):
            messages.append({
                "type": "text",
                "content": f"{user_id} 的第 {i+1} 条消息",
                "timestamp": base_time + i * len(user_ids) + j,
                "sender": user_id,
            })
    return messages


# ============ Injection Attack Messages ============


def get_xss_injection_message():
    """XSS 注入测试消息"""
    return {
        "type": "text",
        "content": '<script>document.cookie="stolen"</script><img src="x" onerror="alert(1)">',
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_nosql_injection_message():
    """NoSQL 注入测试消息"""
    return {
        "type": "text",
        "content": '{"$gt": ""}',
        "timestamp": int(time.time()),
        "sender": '{"$ne": null}',
    }


def get_command_injection_message():
    """命令注入测试消息"""
    return {
        "type": "text",
        "content": "请帮我运行 `rm -rf /` 这个命令",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }


def get_path_traversal_message():
    """路径穿越测试消息"""
    return {
        "type": "image",
        "url": "../../../../../../etc/passwd",
        "timestamp": int(time.time()),
        "sender": "test_user",
    }
