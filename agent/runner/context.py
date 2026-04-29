import sys

sys.path.append(".")
import time
from zoneinfo import ZoneInfo

from util.log_util import get_logger

logger = get_logger(__name__)

from bson import ObjectId

from agent.prompt.character import get_character_prompt
from agent.runner.identity import get_agent_entity_id
from agent.util.message_util import messages_to_str
from conf.config import CONF
from dao.conversation_dao import ConversationDAO
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO  # noqa: F401 - preserved as a patch seam for tests
from util.profile_util import resolve_profile_label
from util.time_util import date2str, get_default_timezone, timestamp2str


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

    # BUG-001 fix: Handle None message content safely
    current_msg = (input_messages[-1].get("message") or "").strip()
    current_user = input_messages[-1].get("from_user")

    if not current_msg:
        return False, None

    # 从历史对话中提取最近5条该用户的消息
    recent_user_msgs = []
    for msg in reversed(chat_history):
        # BUG-C01 fix: Skip None items in chat_history
        if msg is None:
            continue
        if msg.get("from_user") == current_user:
            message_content = msg.get("message") or ""
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
        # BUG-C01 fix: Skip None items in chat_history
        if msg is None:
            continue
        if msg.get("from_user") == character_user_id:
            # BUG-002 fix: Handle None message content safely
            content = (msg.get("message") or "").strip()
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
    recent_responses = get_recent_character_responses(
        chat_history, character_user_id, limit
    )

    if not recent_responses:
        return ""

    # 构建禁止重复的提示
    forbidden_list = "【你最近发送过的消息（严禁重复或发送类似内容）】\n"
    for i, resp in enumerate(recent_responses, 1):
        # 截断过长的消息
        display_resp = resp[:100] + "..." if len(resp) > 100 else resp
        forbidden_list += f"{i}. 「{display_resp}」\n"

    return forbidden_list


def _resolve_user_timezone_context(user):
    timezone_value = user.get("timezone")
    timezone_source = user.get("timezone_source")
    timezone_status = user.get("timezone_status")

    if timezone_value:
        try:
            effective_timezone = ZoneInfo(str(timezone_value)).key
            return {
                "timezone": effective_timezone,
                "effective_timezone": effective_timezone,
                "timezone_source": timezone_source or "legacy_preserved",
                "timezone_status": timezone_status or "user_confirmed",
                "zoneinfo": ZoneInfo(effective_timezone),
            }
        except (KeyError, Exception):
            logger.warning(
                f"Invalid stored timezone '{timezone_value}', falling back to default"
            )

    default_timezone = get_default_timezone()
    default_timezone_key = default_timezone.key
    return {
        "effective_timezone": default_timezone_key,
        "timezone_source": timezone_source or "deployment_default",
        "timezone_status": timezone_status or "system_inferred",
        "zoneinfo": default_timezone,
    }


def context_prepare(user, character, conversation):
    user_id = get_agent_entity_id(user)
    character_id = get_agent_entity_id(character)
    if not user_id or not character_id:
        raise ValueError("Invalid user or character ID: id/_id cannot be None")

    context = {
        "user": user,
        "character": character,
        "conversation": conversation,
        "platform": conversation.get("platform", ""),
    }
    context["user"].setdefault("id", user_id)
    context["character"].setdefault("id", character_id)

    context["user"].setdefault("nickname", resolve_profile_label(user, "用户"))
    context["character"].setdefault(
        "nickname", resolve_profile_label(character, "角色")
    )

    timezone_context = _resolve_user_timezone_context(context["user"])
    user_tz = timezone_context.pop("zoneinfo")
    if "timezone" not in timezone_context:
        context["user"].pop("timezone", None)
    context["user"].update(timezone_context)

    # ========== 使用文件配置的角色提示词 ==========
    # 优先从 Python 文件读取，便于版本控制和快速迭代
    character_name = character.get("name", "")
    file_based_prompt = get_character_prompt(character_name)
    if file_based_prompt:
        # 确保 user_info 存在
        if "user_info" not in context["character"]:
            context["character"]["user_info"] = {}
        # 使用文件配置覆盖数据库中的 description
        context["character"]["user_info"]["description"] = file_based_prompt
        logger.debug(f"[CharacterPrompt] 使用文件配置的提示词: {character_name}")

    mongo = MongoDBBase()
    relation = mongo.find_one("relations", {"uid": user_id, "cid": character_id})

    # 检测是否为新用户（relation 不存在时为首次对话）
    is_new_user = False
    if relation is None:
        is_new_user = True
        logger.info(f"[新用户检测] 首次对话，创建 relation")
        realtion_id = mongo.insert_one(
            "relations", get_default_relation(user, character, conversation["platform"])
        )
        relation = mongo.find_one("relations", {"_id": ObjectId(realtion_id)})

    if "chat_history" not in context["conversation"]["conversation_info"]:
        context["conversation"]["conversation_info"]["chat_history"] = []
    if "input_messages" not in context["conversation"]["conversation_info"]:
        context["conversation"]["conversation_info"]["input_messages"] = []

    if "photo_history" not in context["conversation"]["conversation_info"]:
        context["conversation"]["conversation_info"]["photo_history"] = []

    # 获取消息的输入时间戳（用于相对时间计算的基准）
    # 使用第一条输入消息的时间戳，确保"5分钟后"是从用户发送消息的时间开始计算
    input_messages = context["conversation"]["conversation_info"].get(
        "input_messages", []
    )
    if input_messages and len(input_messages) > 0:
        context["input_timestamp"] = input_messages[0].get(
            "input_timestamp", int(time.time())
        )
    else:
        context["input_timestamp"] = int(time.time())

    # BUG-006 High fix: Handle corrupted relation data with missing "relationship" field
    if "relationship" not in relation:
        relation["relationship"] = {"closeness": 20, "trustness": 20, "dislike": 0}

    if "dislike" not in relation["relationship"]:
        relation["relationship"]["dislike"] = 0

    if "status" not in relation["relationship"]:
        relation["relationship"]["status"] = "空闲"

    context["conversation"]["conversation_info"]["time_str"] = timestamp2str(
        int(context["input_timestamp"]), week=True, tz=user_tz
    )

    # 获取聊天历史
    chat_history = context["conversation"]["conversation_info"]["chat_history"]

    # 群聊场景：使用 context_message_count 获取群聊上下文
    chatroom_name = context["conversation"].get("chatroom_name")
    if chatroom_name:
        # 从配置中读取群聊上下文消息数量
        group_config = CONF.get("group_chat", {})
        context_message_count = group_config.get("context_message_count", 10)

        # 获取群聊最近消息（包含用户消息和机器人回复）
        conversation_dao = ConversationDAO()
        recent_group_messages = conversation_dao.get_recent_group_messages(
            chatroom_name, limit=context_message_count
        )

        # 将群聊消息转换为上下文格式
        if recent_group_messages:
            # 复用 messages_to_str 进行格式化（与私聊格式一致）
            context["group_chat_context"] = messages_to_str(
                recent_group_messages,
                tz=user_tz,
            )
            logger.info(f"[群聊上下文] 加载了 {len(recent_group_messages)} 条群聊消息")
        else:
            context["group_chat_context"] = ""
    else:
        context["group_chat_context"] = ""

    # V2.7 优化：只取最近 15 条历史对话，减少 token 消耗
    recent_chat_history = chat_history[-15:] if len(chat_history) > 15 else chat_history
    context["conversation"]["conversation_info"]["chat_history_str"] = messages_to_str(
        recent_chat_history,
        tz=user_tz,
    )
    context["conversation"]["conversation_info"]["input_messages_str"] = (
        messages_to_str(
            context["conversation"]["conversation_info"]["input_messages"],
            tz=user_tz,
        )
    )

    date_str = date2str(int(time.time()), tz=user_tz)
    news = mongo.find_one("dailynews", {"date": date_str, "cid": character_id})
    if news is None:
        context["news_str"] = ""
    else:
        context["news_str"] = news.get("news", "")

    context["relation"] = relation

    # 设置新用户标志，用于控制 onboarding 流程
    context["is_new_user"] = is_new_user
    if is_new_user:
        logger.info("[新用户检测] is_new_user=True，将注入 onboarding 提示词")

    # 重复消息检测
    is_repeated, repeated_msg = detect_repeated_input(
        context["conversation"]["conversation_info"]["input_messages"],
        context["conversation"]["conversation_info"]["chat_history"],
    )
    if is_repeated:
        # 获取角色最近的回复，明确告诉LLM不要重复这些内容
        character_user_id = character_id
        recent_responses = get_recent_character_responses(
            context["conversation"]["conversation_info"]["chat_history"],
            character_user_id,
            limit=5,
        )

        logger.info(f"[重复消息检测] 检测到用户重复消息: 「{repeated_msg}」")
        logger.info(f"[重复消息检测] 角色ID: {character_user_id}")
        logger.info(
            f"[重复消息检测] 角色最近的回复({len(recent_responses)}条): {recent_responses}"
        )

        # 构建禁止重复的提示
        forbidden_list = ""
        if recent_responses:
            forbidden_list = "\n禁止重复或说以下类似的内容：\n"
            for i, resp in enumerate(recent_responses, 1):
                forbidden_list += f"- 「{resp}」\n"

        context["repeated_input_notice"] = (
            f"【特别注意】用户刚才发送的消息「{repeated_msg}」与之前发送过的消息完全相同.不要重复之前的回复！应该用完全不同的方式回应，或主动转换话题，或简短结束当前话题.{forbidden_list}"
        )
        logger.info(f"[重复消息检测] 生成的提示: {context['repeated_input_notice']}")
    else:
        context["repeated_input_notice"] = ""

    # ========== Agno 迁移：设置 Prompt 模板所需字段的默认值 ==========
    # Requirements: 6.2

    # 顶层字段默认值
    context.setdefault("MultiModalResponses", [])

    # V2.10 新增：主动消息防重复提示
    # V2.15 优化：扩展到所有消息场景，不只是主动消息
    # 在 context_prepare 阶段就生成，避免 AI 重复问相同问题
    character_user_id = character_id
    context["proactive_forbidden_messages"] = detect_repeated_proactive_output(
        context["conversation"]["conversation_info"]["chat_history"],
        character_user_id,
        limit=3,
    )

    # context_retrieve 相关字段（由 ContextRetrieveAgent 填充）
    context.setdefault(
        "context_retrieve",
        {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": "",
            "relevant_history": "",
        },
    )

    # query_rewrite 相关字段（由 QueryRewriteAgent 填充）
    context.setdefault(
        "query_rewrite",
        {
            "InnerMonologue": "",
            "CharacterSettingQueryQuestion": "",
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": "",
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": "",
        },
    )

    # user/character 字段默认值
    context["character"].setdefault(
        "user_info", {"description": "", "status": {"place": "未知", "action": "未知"}}
    )
    if "status" not in context["character"]["user_info"]:
        context["character"]["user_info"]["status"] = {
            "place": "未知",
            "action": "未知",
        }

    # relation 字段默认值
    context["relation"].setdefault(
        "user_info", {"realname": "", "hobbyname": "", "description": ""}
    )
    context["relation"].setdefault(
        "character_info",
        {"longterm_purpose": "", "shortterm_purpose": "", "attitude": ""},
    )

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
    user_id = get_agent_entity_id(user)
    character_id = get_agent_entity_id(character)
    return {
        "uid": user_id,
        "cid": character_id,
        "user_info": {
            "realname": "",
            "hobbyname": "",
            "description": "在聊天里认识的朋友",
        },
        "character_info": {
            "longterm_purpose": "帮用户实现他们想实现的生活目标（比如日程管理，定期提醒等），在用户需要完成目标时督促他，关心并用户的生活（吃饭，喝水等），也在用户低落时给予鼓励.",
            "shortterm_purpose": "随便认识一下这位朋友，少量闲聊，不聊也行",
            "attitude": "略微好奇",
            "status": "空闲",
        },
        "relationship": {
            "description": "在聊天里认识的朋友",
            "closeness": 20,
            "trustness": 20,
            "dislike": 0,
        },
    }
