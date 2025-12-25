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


def get_context_with_long_history():
    """带有长聊天历史的 context（测试上下文截断）"""
    ctx = get_full_context()
    history = []
    for i in range(20):
        history.append({"role": "user", "content": f"用户消息 {i+1}"})
        history.append({"role": "assistant", "content": f"助手回复 {i+1}"})
    ctx["conversation"]["conversation_info"]["chat_history"] = history
    ctx["conversation"]["conversation_info"]["chat_history_str"] = "\n".join(
        [f"{'用户' if m['role'] == 'user' else '角色'}: {m['content']}" for m in history]
    )
    return ctx


def get_context_for_reminder():
    """提醒场景的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "帮我设置一个明天早上8点的提醒"}
    ]
    ctx["conversation"]["conversation_info"]["input_messages_str"] = "帮我设置一个明天早上8点的提醒"
    return ctx


def get_context_for_proactive_message():
    """主动消息场景的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["future"] = {
        "timestamp": int(datetime.now().timestamp()),
        "action": "询问用户今天的计划",
    }
    ctx["message_source"] = "proactive"
    return ctx


def get_context_with_relation():
    """带有完整关系数据的 context"""
    ctx = get_full_context()
    ctx["relation"] = {
        "_id": ObjectId(),
        "uid": "test_uid",
        "cid": "test_cid",
        "relationship": {
            "closeness": 75,
            "trustness": 80,
            "dislike": 0,
            "status": "空闲",
            "description": "老朋友关系",
        },
        "user_info": {
            "realname": "张三",
            "hobbyname": "小张",
            "description": "喜欢运动和阅读",
        },
        "character_info": {
            "longterm_purpose": "帮助用户建立良好的生活习惯",
            "shortterm_purpose": "今天帮助用户完成工作任务",
            "attitude": "友好且热情",
        },
    }
    return ctx


def get_context_for_voice_message():
    """语音消息场景的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "voice", "content": "语音转写内容：今天天气真好", "duration": 5}
    ]
    ctx["conversation"]["conversation_info"]["input_messages_str"] = (
        "[语音消息] 语音转写内容：今天天气真好"
    )
    return ctx


def get_context_for_image_message():
    """图片消息场景的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "image", "url": "https://example.com/image.jpg", "description": "一张风景照片"}
    ]
    ctx["conversation"]["conversation_info"]["input_messages_str"] = (
        "[图片消息] 一张风景照片"
    )
    ctx["conversation"]["conversation_info"]["photo_history"] = [
        "用户发送了一张风景照片"
    ]
    return ctx


def get_context_with_context_retrieve():
    """带有上下文检索结果的 context"""
    ctx = get_full_context()
    ctx["context_retrieve"] = {
        "character_global": "角色是一个友好的AI助手，善于倾听和帮助用户。",
        "character_private": "对这个用户特别关心，记得用户喜欢喝咖啡。",
        "user": "用户是一名程序员，平时工作比较忙。",
        "character_knowledge": "今天是周三，天气晴朗。",
        "confirmed_reminders": "明天早上8点提醒用户开会",
    }
    return ctx


def get_context_with_multimodal_response():
    """多模态响应场景的 context"""
    ctx = get_full_context()
    ctx["MultiModalResponses"] = [
        {"type": "text", "content": "好的，我来帮你处理"},
        {"type": "voice", "content": "这是语音回复", "emotion": "高兴"},
        {"type": "photo", "content": "photo_001"},
    ]
    return ctx


def get_context_for_repeated_message():
    """重复消息场景的 context"""
    ctx = get_full_context()
    ctx["repeated_input_notice"] = (
        "【特别注意】用户刚才发送的消息「你好」与之前发送过的消息完全相同。"
        "不要重复之前的回复！应该用完全不同的方式回应。"
    )
    ctx["conversation"]["conversation_info"]["chat_history"] = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！很高兴见到你"},
        {"role": "user", "content": "你好"},
    ]
    return ctx


def get_context_for_turn_dedup():
    """turn-level 消息去重场景的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["turn_sent_contents"] = [
        "你好！",
        "有什么可以帮你的？",
    ]
    return ctx


# ============ Relationship Level Contexts ============


def get_context_with_new_user_relation():
    """新用户关系 context（低亲密度 0-20）"""
    ctx = get_full_context()
    ctx["relation"] = {
        "_id": ObjectId(),
        "uid": "new_user_uid",
        "cid": "test_cid",
        "relationship": {
            "closeness": 10,
            "trustness": 15,
            "dislike": 0,
            "status": "空闲",
            "description": "刚认识的用户",
        },
        "user_info": {
            "realname": "",
            "hobbyname": "",
            "description": "",
        },
        "character_info": {
            "longterm_purpose": "建立初步信任关系",
            "shortterm_purpose": "了解用户基本情况",
            "attitude": "礼貌但保持距离",
        },
    }
    return ctx


def get_context_with_regular_user_relation():
    """普通用户关系 context（中等亲密度 30-60）"""
    ctx = get_full_context()
    ctx["relation"] = {
        "_id": ObjectId(),
        "uid": "regular_user_uid",
        "cid": "test_cid",
        "relationship": {
            "closeness": 45,
            "trustness": 50,
            "dislike": 5,
            "status": "空闲",
            "description": "熟悉的用户",
        },
        "user_info": {
            "realname": "李明",
            "hobbyname": "小明",
            "description": "程序员，喜欢技术",
        },
        "character_info": {
            "longterm_purpose": "帮助用户提高工作效率",
            "shortterm_purpose": "协助处理日常事务",
            "attitude": "友好热情",
        },
    }
    return ctx


def get_context_with_close_user_relation():
    """亲密用户关系 context（高亲密度 70-100）"""
    ctx = get_full_context()
    ctx["relation"] = {
        "_id": ObjectId(),
        "uid": "close_user_uid",
        "cid": "test_cid",
        "relationship": {
            "closeness": 85,
            "trustness": 90,
            "dislike": 0,
            "status": "开心",
            "description": "非常亲密的老朋友",
        },
        "user_info": {
            "realname": "张伟",
            "hobbyname": "小伟",
            "description": "认识多年的朋友，喜欢户外运动和阅读",
        },
        "character_info": {
            "longterm_purpose": "成为用户最信赖的伙伴",
            "shortterm_purpose": "分享生活点滴，互相支持",
            "attitude": "亲切随意，可以开玩笑",
        },
    }
    return ctx


def get_context_with_low_trust_relation():
    """低信任度关系 context"""
    ctx = get_full_context()
    ctx["relation"] = {
        "_id": ObjectId(),
        "uid": "low_trust_uid",
        "cid": "test_cid",
        "relationship": {
            "closeness": 40,
            "trustness": 20,
            "dislike": 30,
            "status": "警惕",
            "description": "用户曾有不良行为记录",
        },
        "user_info": {
            "realname": "",
            "hobbyname": "",
            "description": "需要谨慎对待的用户",
        },
        "character_info": {
            "longterm_purpose": "观察用户行为变化",
            "shortterm_purpose": "保持警惕但不失礼貌",
            "attitude": "谨慎保守",
        },
    }
    return ctx


# ============ History Length Contexts ============


def get_context_with_no_history():
    """无历史记录 context（初始对话状态）"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["chat_history"] = []
    ctx["conversation"]["conversation_info"]["chat_history_str"] = ""
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "你好，我是新用户"}
    ]
    ctx["conversation"]["conversation_info"]["input_messages_str"] = "你好，我是新用户"
    return ctx


def get_context_with_short_history():
    """短历史记录 context（2-5轮对话）"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["chat_history"] = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！很高兴认识你"},
        {"role": "user", "content": "你叫什么名字？"},
        {"role": "assistant", "content": "我是你的AI助手"},
        {"role": "user", "content": "好的，记住了"},
    ]
    ctx["conversation"]["conversation_info"]["chat_history_str"] = (
        "用户: 你好\n角色: 你好！很高兴认识你\n"
        "用户: 你叫什么名字？\n角色: 我是你的AI助手\n"
        "用户: 好的，记住了"
    )
    return ctx


def get_context_with_very_long_history():
    """超长历史记录 context（50轮对话，测试极端情况）"""
    ctx = get_full_context()
    history = []
    for i in range(50):
        history.append({"role": "user", "content": f"这是用户的第{i+1}条消息，内容比较长以测试上下文截断功能"})
        history.append({"role": "assistant", "content": f"这是助手的第{i+1}条回复，同样内容较长用于测试"})
    ctx["conversation"]["conversation_info"]["chat_history"] = history
    ctx["conversation"]["conversation_info"]["chat_history_str"] = "\n".join(
        [f"{'用户' if m['role'] == 'user' else '角色'}: {m['content']}" for m in history]
    )
    return ctx


# ============ Edge Case Contexts ============


def get_context_with_missing_fields():
    """缺少字段的 context（测试向后兼容）"""
    return {
        "user": {"_id": ObjectId(), "platforms": {}},
        "character": {"_id": ObjectId()},
        "conversation": {"_id": ObjectId()},
        "relation": {"_id": ObjectId()},
    }


def get_context_with_null_values():
    """包含 null 值的 context"""
    ctx = get_full_context()
    ctx["user"]["platforms"]["wechat"]["nickname"] = None
    ctx["character"]["user_info"]["description"] = None
    ctx["relation"]["user_info"]["realname"] = None
    ctx["conversation"]["conversation_info"]["future"]["action"] = None
    return ctx


def get_context_with_empty_strings():
    """包含空字符串的 context"""
    ctx = get_full_context()
    ctx["user"]["platforms"]["wechat"]["nickname"] = ""
    ctx["character"]["user_info"]["description"] = ""
    ctx["news_str"] = ""
    ctx["repeated_input_notice"] = ""
    return ctx


def get_context_with_unicode_content():
    """包含特殊 Unicode 字符的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "测试表情😀🎉和特殊字符→←↑↓以及生僻字𠀀𠀁"}
    ]
    ctx["conversation"]["conversation_info"]["input_messages_str"] = (
        "测试表情😀🎉和特殊字符→←↑↓以及生僻字𠀀𠀁"
    )
    return ctx


def get_context_with_html_injection():
    """包含潜在 HTML/XSS 注入的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "<script>alert('xss')</script><img src=x onerror=alert(1)>"}
    ]
    ctx["user"]["platforms"]["wechat"]["nickname"] = "<b>Bold Name</b>"
    return ctx


def get_context_with_sql_injection():
    """包含潜在 SQL 注入的 context（测试 NoSQL 安全性）"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "'; DROP TABLE users; --"}
    ]
    ctx["user"]["platforms"]["wechat"]["id"] = "user_id'; DELETE FROM users WHERE '1'='1"
    return ctx


def get_context_with_extremely_long_message():
    """包含极长消息的 context"""
    ctx = get_full_context()
    long_content = "这是一个非常长的消息" * 500  # ~5000 字符
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": long_content}
    ]
    ctx["conversation"]["conversation_info"]["input_messages_str"] = long_content
    return ctx


def get_context_with_binary_like_content():
    """包含类似二进制内容的 context"""
    ctx = get_full_context()
    binary_like = "\x00\x01\x02\x03\xff\xfe\xfd"
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": f"正常文本{binary_like}混合内容"}
    ]
    return ctx


# ============ Proactive Message Contexts ============


def get_context_for_scheduled_proactive():
    """预定主动消息的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["future"] = {
        "timestamp": int(datetime.now().timestamp()) + 3600,
        "action": "下午问候用户",
        "proactive_times": 3,
        "status": "scheduled",
    }
    ctx["message_source"] = "proactive"
    return ctx


def get_context_for_expired_proactive():
    """过期主动消息的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["future"] = {
        "timestamp": int(datetime.now().timestamp()) - 7200,  # 2小时前
        "action": "早安问候",
        "proactive_times": 1,
        "status": "pending",
    }
    ctx["message_source"] = "proactive"
    return ctx


# ============ Multiple Input Message Contexts ============


def get_context_with_multiple_text_messages():
    """多条连续文本消息的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "第一条消息"},
        {"type": "text", "content": "第二条消息"},
        {"type": "text", "content": "第三条消息"},
    ]
    ctx["conversation"]["conversation_info"]["input_messages_str"] = (
        "第一条消息\n第二条消息\n第三条消息"
    )
    return ctx


def get_context_with_mixed_multimodal_input():
    """混合多模态输入的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "看看这张图片"},
        {"type": "image", "url": "https://example.com/photo.jpg", "description": "用户分享的照片"},
        {"type": "voice", "content": "这是语音补充说明", "duration": 8},
    ]
    ctx["conversation"]["conversation_info"]["photo_history"] = [
        "用户分享了一张照片"
    ]
    return ctx


# ============ Reminder Related Contexts ============


def get_context_with_existing_reminders():
    """已有提醒的 context"""
    ctx = get_full_context()
    ctx["context_retrieve"]["confirmed_reminders"] = (
        "1. 明天早上8点 - 开会提醒\n"
        "2. 每天下午3点 - 喝水提醒\n"
        "3. 下周一上午10点 - 项目汇报"
    )
    return ctx


def get_context_for_reminder_cancellation():
    """取消提醒场景的 context"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "取消开会的提醒"}
    ]
    ctx["context_retrieve"]["confirmed_reminders"] = "1. 明天早上8点 - 开会提醒"
    return ctx


def get_context_for_reminder_conflict():
    """提醒冲突场景的 context（同一时间多个提醒）"""
    ctx = get_full_context()
    ctx["conversation"]["conversation_info"]["input_messages"] = [
        {"type": "text", "content": "明天早上8点提醒我开会"}
    ]
    ctx["context_retrieve"]["confirmed_reminders"] = (
        "1. 明天早上8点 - 吃药提醒\n"
        "2. 明天早上8点 - 锻炼提醒"
    )
    return ctx


# ============ Error Condition Contexts ============


def get_context_with_invalid_objectid():
    """包含无效 ObjectId 的 context（用于测试错误处理）"""
    return {
        "user": {"_id": "invalid_object_id", "platforms": {"wechat": {"id": "test"}}},
        "character": {"_id": "also_invalid", "platforms": {"wechat": {"id": "char"}}},
        "conversation": {"_id": "bad_id", "conversation_info": {}},
        "relation": {"_id": "wrong_format"},
    }


def get_context_with_wrong_types():
    """包含错误类型字段的 context"""
    ctx = get_full_context()
    ctx["relation"]["relationship"]["closeness"] = "should_be_int"  # 应该是 int
    ctx["relation"]["relationship"]["trustness"] = [50]  # 应该是 int
    ctx["conversation"]["conversation_info"]["chat_history"] = "should_be_list"  # 应该是 list
    return ctx


def get_context_with_boundary_values():
    """包含边界值的 context"""
    ctx = get_full_context()
    ctx["relation"]["relationship"]["closeness"] = 0  # 最小值
    ctx["relation"]["relationship"]["trustness"] = 100  # 最大值
    ctx["relation"]["relationship"]["dislike"] = 100  # 最大值
    ctx["conversation"]["conversation_info"]["future"]["timestamp"] = 0
    return ctx


def get_context_with_out_of_range_values():
    """包含超出范围值的 context（用于测试验证）"""
    ctx = get_full_context()
    ctx["relation"]["relationship"]["closeness"] = -10  # 负值
    ctx["relation"]["relationship"]["trustness"] = 150  # 超过100
    ctx["relation"]["relationship"]["dislike"] = 999  # 远超范围
    return ctx
