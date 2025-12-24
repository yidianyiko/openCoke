import sys
sys.path.append(".")
import copy
import os
import time
import traceback
import logging
from logging import getLogger
logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)

from bson import ObjectId

from dao.mongo import MongoDBBase
from util.time_util import timestamp2str, date2str
from agent.util.message_util import messages_to_str


def _convert_objectid_to_str(obj):
    """
    递归将 dict 中的 ObjectId 转换为字符串
    
    确保 session_state 可以进行 JSON 序列化，用于 Agno Workflow 传递
    
    Args:
        obj: 任意对象（dict, list, ObjectId, 或其他）
        
    Returns:
        转换后的对象，所有 ObjectId 都被转换为字符串
        
    Requirements: 6.1
    """
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _convert_objectid_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_objectid_to_str(item) for item in obj]
    else:
        return obj


def detect_repeated_input(input_messages, chat_history):
    """
    检测用户最近5条消息中是否有与当前消息完全相同的
    
    Args:
        input_messages: 当前待处理的消息列表
        chat_history: 历史对话列表
    
    Returns:
        tuple: (是否检测到重复, 重复的消息内容)
    """
    if not input_messages or not chat_history:
        return False, None
    
    current_msg = input_messages[-1].get("message", "").strip()
    current_user = input_messages[-1].get("from_user")
    
    if not current_msg:
        return False, None
    
    # 从历史对话中提取最近5条该用户的消息
    recent_user_msgs = []
    for msg in reversed(chat_history):
        if msg.get("from_user") == current_user:
            message_content = msg.get("message", "") or ""
            recent_user_msgs.append(message_content.strip())
            if len(recent_user_msgs) >= 5:
                break
    
    # 检查是否完全相同
    for old_msg in recent_user_msgs:
        if current_msg == old_msg:
            return True, current_msg
    
    return False, None


def get_recent_character_responses(chat_history, character_user_id, limit=5):
    """
    获取角色最近的回复内容
    
    Args:
        chat_history: 历史对话列表
        character_user_id: 角色的用户ID
        limit: 最多获取多少条
    
    Returns:
        list: 最近的回复内容列表
    """
    if not chat_history:
        return []
    
    recent_responses = []
    for msg in reversed(chat_history):
        if msg.get("from_user") == character_user_id:
            content = msg.get("message", "").strip()
            if content and content not in recent_responses:
                recent_responses.append(content)
                if len(recent_responses) >= limit:
                    break
    
    return recent_responses


def detect_repeated_proactive_output(chat_history, character_user_id, limit=3):
    """
    检测角色最近的主动消息内容，用于防止主动消息重复
    
    Args:
        chat_history: 历史对话列表
        character_user_id: 角色的用户ID
        limit: 检查最近多少条角色消息
    
    Returns:
        str: 禁止重复的提示文本，如果没有历史消息则返回空字符串
    """
    recent_responses = get_recent_character_responses(chat_history, character_user_id, limit)
    
    if not recent_responses:
        return ""
    
    # 构建禁止重复的提示
    forbidden_list = "【你最近发送过的消息（严禁重复或发送类似内容）】\n"
    for i, resp in enumerate(recent_responses, 1):
        # 截断过长的消息
        display_resp = resp[:100] + "..." if len(resp) > 100 else resp
        forbidden_list += f"{i}. 「{display_resp}」\n"
    
    return forbidden_list


def context_prepare(user, character, conversation):
    context = {
        "user": user,
        "character": character,
        "conversation": conversation
    }

    mongo = MongoDBBase()
    relation = mongo.find_one("relations", {"uid": str(user["_id"]), "cid": str(character["_id"])})
    if relation is None:
        realtion_id = mongo.insert_one("relations", get_default_relation(user, character, conversation["platform"]))
        relation = mongo.find_one("relations", {"_id": ObjectId(realtion_id)})

    if "chat_history" not in context["conversation"]["conversation_info"]:
        context["conversation"]["conversation_info"]["chat_history"] = []
    if "input_messages" not in context["conversation"]["conversation_info"]:
        context["conversation"]["conversation_info"]["input_messages"] = []
    
    if "photo_history" not in context["conversation"]["conversation_info"]:
        context["conversation"]["conversation_info"]["photo_history"] = []
    
    # 获取消息的输入时间戳（用于相对时间计算的基准）
    # 使用第一条输入消息的时间戳，确保"5分钟后"是从用户发送消息的时间开始计算
    input_messages = context["conversation"]["conversation_info"].get("input_messages", [])
    if input_messages and len(input_messages) > 0:
        context["input_timestamp"] = input_messages[0].get("input_timestamp", int(time.time()))
    else:
        context["input_timestamp"] = int(time.time())

    if "future" not in context["conversation"]["conversation_info"]:
        context["conversation"]["conversation_info"]["future"] = {
            "timestamp": None,
            "action": None
        }
    
    if "dislike" not in relation["relationship"]:
        relation["relationship"]["dislike"] = 0
    
    if "status" not in relation["relationship"]:
        relation["relationship"]["status"] = "空闲"
    
    context["conversation"]["conversation_info"]["time_str"] = timestamp2str(int(time.time()), week=True)
    # V2.7 优化：只取最近 15 条历史对话，减少 token 消耗
    chat_history = context["conversation"]["conversation_info"]["chat_history"]
    recent_chat_history = chat_history[-15:] if len(chat_history) > 15 else chat_history
    context["conversation"]["conversation_info"]["chat_history_str"] = messages_to_str(recent_chat_history)
    context["conversation"]["conversation_info"]["input_messages_str"] = messages_to_str(context["conversation"]["conversation_info"]["input_messages"])

    date_str = date2str(int(time.time()))
    news = mongo.find_one("dailynews", {"date": date_str, "cid": str(character["_id"])})
    if news is None:
        context["news_str"] = ""
    else:
        context["news_str"] = news["news"]
    
    context["relation"] = relation

    # 重复消息检测
    is_repeated, repeated_msg = detect_repeated_input(
        context["conversation"]["conversation_info"]["input_messages"],
        context["conversation"]["conversation_info"]["chat_history"]
    )
    if is_repeated:
        # 获取角色最近的回复，明确告诉LLM不要重复这些内容
        character_user_id = str(character["_id"])
        recent_responses = get_recent_character_responses(
            context["conversation"]["conversation_info"]["chat_history"],
            character_user_id,
            limit=5
        )
        
        logger.info(f"[重复消息检测] 检测到用户重复消息: 「{repeated_msg}」")
        logger.info(f"[重复消息检测] 角色ID: {character_user_id}")
        logger.info(f"[重复消息检测] 角色最近的回复({len(recent_responses)}条): {recent_responses}")
        
        # 构建禁止重复的提示
        forbidden_list = ""
        if recent_responses:
            forbidden_list = "\n你刚才说过的话（禁止重复或说类似的内容）：\n"
            for i, resp in enumerate(recent_responses, 1):
                forbidden_list += f"- 「{resp}」\n"
        
        context["repeated_input_notice"] = f"【特别注意】用户刚才发送的消息「{repeated_msg}」与之前发送过的消息完全相同。请务必不要重复之前的回复！你应该用完全不同的方式回应，或主动转换话题，或简短结束当前话题。{forbidden_list}"
        logger.info(f"[重复消息检测] 生成的提示: {context['repeated_input_notice']}")
    else:
        context["repeated_input_notice"] = ""

    # ========== Agno 迁移：设置 Prompt 模板所需字段的默认值 ==========
    # Requirements: 6.2
    
    # 顶层字段默认值
    context.setdefault("MultiModalResponses", [])
    
    # V2.10 新增：主动消息防重复提示（默认为空，由 handle_pending_future_message 填充）
    context.setdefault("proactive_forbidden_messages", "")
    
    # context_retrieve 相关字段（由 ContextRetrieveAgent 填充）
    context.setdefault("context_retrieve", {
        "character_global": "",
        "character_private": "",
        "user": "",
        "character_knowledge": "",
        "confirmed_reminders": "",
        "relevant_history": ""
    })
    
    # query_rewrite 相关字段（由 QueryRewriteAgent 填充）
    context.setdefault("query_rewrite", {
        "InnerMonologue": "",
        "CharacterSettingQueryQuestion": "",
        "CharacterSettingQueryKeywords": "",
        "UserProfileQueryQuestion": "",
        "UserProfileQueryKeywords": "",
        "CharacterKnowledgeQueryQuestion": "",
        "CharacterKnowledgeQueryKeywords": ""
    })
    
    # user 字段默认值
    context["user"].setdefault("platforms", {})
    context["user"]["platforms"].setdefault("wechat", {
        "id": "",
        "nickname": "用户"
    })
    
    # character 字段默认值
    context["character"].setdefault("platforms", {})
    context["character"]["platforms"].setdefault("wechat", {
        "id": "",
        "nickname": "角色"
    })
    context["character"].setdefault("user_info", {
        "description": "",
        "status": {"place": "未知", "action": "未知"}
    })
    if "status" not in context["character"]["user_info"]:
        context["character"]["user_info"]["status"] = {"place": "未知", "action": "未知"}
    
    # relation 字段默认值
    context["relation"].setdefault("user_info", {
        "realname": "",
        "hobbyname": "",
        "description": ""
    })
    context["relation"].setdefault("character_info", {
        "longterm_purpose": "",
        "shortterm_purpose": "",
        "attitude": ""
    })
    
    # ========== ObjectId 序列化处理 ==========
    # Requirements: 6.1
    # 确保 session_state 可以进行 JSON 序列化
    context = _convert_objectid_to_str(context)

    return context

def context_prepare_charonly(character):
    context = {
        "character": character,
    }
    
    return context

def get_default_relation(user, character, platform):
    return {
        "uid": str(user["_id"]),
        "cid": str(character["_id"]),
        "user_info": {
            "realname": "",
            "hobbyname": "",
            "description": "在微信上认识的新朋友",
        },
        "character_info": {
            "longterm_purpose": "帮用户实现他们想实现的生活目标（比如日程管理，定期提醒等），在用户需要完成目标时督促他，关心并用户的生活（吃饭，喝水等），也在用户低落时给予鼓励。",
            "shortterm_purpose": "随便认识一下这位朋友，少量闲聊，不聊也行",
            "attitude": "略微好奇",
            "status": "空闲"
        },
        "relationship": {
            "description": "在微信上认识的新朋友",
            "closeness": 20,
            "trustness": 20,
            "dislike": 0,
        },
    }
