import sys

sys.path.append(".")
import time
import traceback
import uuid

from util.log_util import get_logger

logger = get_logger(__name__)

from bson import ObjectId

from agent.runner.identity import get_agent_entity_id
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.profile_util import resolve_profile_label
from util.message_log_util import format_std_message_for_log, should_log_message_content
from util.time_util import get_message_timestamp, safe_timestamp_compare, timestamp2str


def messages_to_str(messages, language="cn"):
    if len(messages) == 0:
        return ""

    messages_str_lines = []
    for message in messages:
        messages_str_lines.append(message_to_str(message, language))

    return "\n".join(messages_str_lines)


def message_to_str(message, language="cn"):
    try:
        # BUG-003 fix: Use .get() with default instead of direct key access
        message_type = message.get("message_type", "text")
        if message_type in ["text", "voice"]:
            return normal_message_to_str(message, language=language)
        if message_type in ["reference"]:
            return reference_message_to_str(message, language=language)
        if message_type in ["image"]:
            return image_message_to_str(message, language=language)
    except Exception:
        logger.error(traceback.format_exc())
        return ""
    return ""


def _resolve_talker_name(talker, message):
    platform = message.get("platform")
    default_name = message.get("from_user") or "未知用户"
    if not isinstance(talker, dict) or talker is None:
        return default_name
    if platform:
        conversation_profiles = talker.get("conversation_profiles")
        if isinstance(conversation_profiles, dict):
            profile = conversation_profiles.get(platform)
            if isinstance(profile, dict):
                nickname = profile.get("nickname")
                if nickname:
                    return nickname
    return resolve_profile_label(talker, default_name)


def _resolve_business_coke_account_display_name(message):
    if not isinstance(message, dict):
        return None
    if message.get("platform") != "business":
        return None

    metadata = message.get("metadata")
    if not isinstance(metadata, dict):
        return None

    coke_account = metadata.get("coke_account")
    if not isinstance(coke_account, dict):
        return None

    display_name = coke_account.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()
    return None


def normal_message_to_str(message, language="cn"):
    # BUG-004 & BUG-010 fix: Use validated timestamp extraction
    if "input_timestamp" in message:
        message_time = get_message_timestamp(message)
    elif "expect_output_timestamp" in message:
        # Check if message is in the future (not yet sent)
        if not safe_timestamp_compare(
            message["expect_output_timestamp"], int(time.time()), default_result=False
        ):
            return ""  # 如果expect_output_timestamp比now大，证明还没发出去
        message_time = get_message_timestamp(message)
    else:
        # No timestamp available, use current time as fallback
        message_time = int(time.time())

    user_dao = UserDAO()
    from_user = message.get("from_user")
    talker_name = _resolve_business_coke_account_display_name(message)
    if not talker_name:
        talker = user_dao.get_user_by_id(from_user) if from_user else None
        talker_name = _resolve_talker_name(talker, message)
    time_str = timestamp2str(message_time)

    if language == "cn":
        message_type_map = {"text": "文本", "voice": "语音"}
        message_type_str = "文本"
        msg_type = message.get("message_type", "text")
        if msg_type in message_type_map:
            message_type_str = message_type_map[msg_type]

    message_content = message.get("message", "") or ""
    return (
        "（"
        + time_str
        + " "
        + talker_name
        + "发来了"
        + message_type_str
        + "消息）"
        + message_content
    )


def reference_message_to_str(message, language="cn"):
    # BUG-004 & BUG-010 fix: Use validated timestamp extraction
    if "input_timestamp" in message:
        message_time = get_message_timestamp(message)
    elif "expect_output_timestamp" in message:
        # Check if message is in the future (not yet sent)
        if not safe_timestamp_compare(
            message["expect_output_timestamp"], int(time.time()), default_result=False
        ):
            return ""  # 如果expect_output_timestamp比now大，证明还没发出去
        message_time = get_message_timestamp(message)
    else:
        # No timestamp available, use current time as fallback
        message_time = int(time.time())

    user_dao = UserDAO()
    from_user = message.get("from_user")
    talker_name = _resolve_business_coke_account_display_name(message)
    if not talker_name:
        talker = user_dao.get_user_by_id(from_user) if from_user else None
        talker_name = _resolve_talker_name(talker, message)
    time_str = timestamp2str(message_time)

    message_content = message.get("message", "") or ""
    # BUG-005 fix: Use .get() for nested metadata access
    metadata = message.get("metadata", {})
    reference = metadata.get("reference", {})
    reference_user = reference.get("user", "")
    reference_text = reference.get("text", "")
    return (
        "（"
        + time_str
        + " "
        + talker_name
        + "发来了一条引用消息）"
        + message_content
        + "「引用了"
        + reference_user
        + "的消息："
        + reference_text
        + "」"
    )


def image_message_to_str(message, language="cn"):
    # BUG-004 & BUG-010 fix: Use validated timestamp extraction
    if "input_timestamp" in message:
        message_time = get_message_timestamp(message)
    elif "expect_output_timestamp" in message:
        # Check if message is in the future (not yet sent)
        if not safe_timestamp_compare(
            message["expect_output_timestamp"], int(time.time()), default_result=False
        ):
            return ""  # 如果expect_output_timestamp比now大，证明还没发出去
        message_time = get_message_timestamp(message)
    else:
        # No timestamp available, use current time as fallback
        message_time = int(time.time())

    user_dao = UserDAO()
    from_user = message.get("from_user")
    talker_name = _resolve_business_coke_account_display_name(message)
    if not talker_name:
        talker = user_dao.get_user_by_id(from_user) if from_user else None
        talker_name = _resolve_talker_name(talker, message)
    time_str = timestamp2str(message_time)

    mongo = MongoDBBase()
    image_str = ""

    message_content = message.get("message", "") or ""
    if str(message_content).startswith(("「", "照片")) == True:
        image_id = str(message_content).replace("「", "")
        image_id = image_id.replace("」", "")
        image_id = image_id.replace("照片", "", 1)

        image = mongo.get_vector_by_id("embeddings", image_id)

        if image is not None:
            image_str = image["key"] + "：" + image["value"]

    return (
        "（"
        + time_str
        + " "
        + talker_name
        + "发来了一条图片消息）"
        + message_content
        + "."
        + image_str
    )


# {
#     "_id": xxx,  # 内置id
#     "expect_output_timestamp": xxx,  # 预期输出的时间戳秒级
#     "handled_timestamp": xxx,  # 处理完毕时的时间戳秒级
#     "status": "pending",  # 标记处理状态：pending待处理，handled处理完毕，canceled不处理，failed处理失败
#     "from_user": "xxx",  # 来源uid
#     "platform": "xxx",  # 来源平台
#     "chatroom_name": None,  # 如果有值，则来自群聊；否则是私聊
#     "to_user": "xxx", # 目标用户uid；群聊时，值为None
#     "message_type": "xxxx",  # 包括：
#     "message": "xxx",  # 实际消息，格式另行约定
#     "metadata": {
#         "file_path": "xxx", # 所包含的文件路径
#     }
# }


def send_message_via_context(
    context, message, message_type="text", expect_output_timestamp=None, metadata=None
):
    """
    通过 context 发送消息，自动从 inputmessage 复制 metadata

    Args:
        context: 上下文信息
        message: 消息内容
        message_type: 消息类型
        expect_output_timestamp: 预期输出时间戳
        metadata: 额外的 metadata（会与 inputmessage 的 metadata 合并）
    """
    # 如果没有提供 metadata，尝试从 inputmessage 复制
    if metadata is None:
        metadata = {}

    status = "pending"
    handled_timestamp = expect_output_timestamp
    is_proactive_message = context.get("message_source") in {"future", "reminder"}
    account_id = None
    if not is_proactive_message:
        # 从 inputmessage 复制 metadata（用于需要回传信息的平台）
        input_messages = (
            context.get("conversation", {})
            .get("conversation_info", {})
            .get("input_messages", [])
        )
        if input_messages and len(input_messages) > 0:
            first_input = input_messages[0]
            input_metadata = first_input.get("metadata", {})
            # 将 inputmessage 的 metadata 合并到输出消息
            metadata = {**input_metadata, **metadata}
        metadata = _inject_business_key_into_clawscale_reply_metadata(
            context=context,
            metadata=metadata,
        )
        status, handled_timestamp, metadata = (
            _enforce_single_clawscale_sync_reply_per_turn(
                context=context,
                status=status,
                handled_timestamp=handled_timestamp,
                metadata=metadata,
            )
        )
    elif get_agent_entity_id(context.get("user")):
        account_id = get_agent_entity_id(context.get("user"))
        clawscale_metadata = build_clawscale_push_metadata(
            account_id, context=context
        )
        if clawscale_metadata:
            metadata = {**clawscale_metadata, **metadata}
        else:
            status = "failed"
            handled_timestamp = int(time.time())
            metadata = {
                **metadata,
                "delivery_mode": "push",
                "failure_reason": "missing_clawscale_business_conversation_key",
            }
            logger.warning(
                "missing_clawscale_business_conversation_key: failed to build "
                "clawscale proactive output for account_id=%s conversation_id=%s",
                account_id,
                _extract_clawscale_conversation_id_from_context(context),
            )

    return send_message(
        platform=None if is_proactive_message else context["conversation"]["platform"],
        from_user=None if is_proactive_message else get_agent_entity_id(context.get("character")),
        to_user=None if is_proactive_message else get_agent_entity_id(context.get("user")),
        chatroom_name=None if is_proactive_message else context["conversation"]["chatroom_name"],
        message=message,
        message_type=message_type,
        status=status,
        expect_output_timestamp=expect_output_timestamp,
        handled_timestamp=handled_timestamp,
        account_id=account_id,
        metadata=metadata,
    )


def _enforce_single_clawscale_sync_reply_per_turn(
    *, context: dict | None, status: str, handled_timestamp: int | None, metadata: dict | None
) -> tuple[str, int | None, dict]:
    if not isinstance(metadata, dict):
        return status, handled_timestamp, {} if metadata is None else metadata
    if not isinstance(context, dict):
        return status, handled_timestamp, metadata
    if metadata.get("source") != "clawscale":
        return status, handled_timestamp, metadata

    business_protocol = metadata.get("business_protocol")
    if not isinstance(business_protocol, dict):
        business_protocol = {}
    delivery_mode = business_protocol.get("delivery_mode") or metadata.get(
        "delivery_mode"
    )
    if delivery_mode != "request_response":
        return status, handled_timestamp, metadata

    if not context.get("_clawscale_sync_reply_emitted"):
        context["_clawscale_sync_reply_emitted"] = True
        return status, handled_timestamp, metadata

    failure_metadata = {
        **metadata,
        "failure_reason": "unexpected_extra_request_response_output",
    }
    logger.warning(
        "unexpected_extra_request_response_output: dropped extra sync reply for "
        "business_conversation_key=%s causal_inbound_event_id=%s",
        business_protocol.get("business_conversation_key"),
        business_protocol.get("causal_inbound_event_id"),
    )
    return "failed", int(time.time()), failure_metadata


def _inject_business_key_into_clawscale_reply_metadata(
    *, context: dict | None, metadata: dict | None
) -> dict:
    if not isinstance(metadata, dict):
        return {} if metadata is None else metadata
    if metadata.get("source") != "clawscale":
        return metadata

    business_protocol = metadata.get("business_protocol")
    if not isinstance(business_protocol, dict):
        business_protocol = {}

    delivery_mode = business_protocol.get("delivery_mode") or metadata.get(
        "delivery_mode"
    )
    if delivery_mode != "request_response":
        return metadata

    if business_protocol.get("business_conversation_key"):
        return metadata

    business_conversation_key = _extract_clawscale_conversation_id_from_context(context)
    if business_conversation_key is None:
        return metadata

    return {
        **metadata,
        "business_protocol": {
            **business_protocol,
            "delivery_mode": "request_response",
            "business_conversation_key": business_conversation_key,
        },
    }


def build_clawscale_push_metadata(
    user_id: str, now_ts: int | None = None, context: dict | None = None
):
    business_conversation_key = _extract_clawscale_conversation_id_from_context(context)
    if business_conversation_key is None:
        return {}

    metadata = {
        "business_conversation_key": business_conversation_key,
        "output_id": uuid.uuid4().hex,
        "delivery_mode": "push",
        "idempotency_key": uuid.uuid4().hex,
        "trace_id": uuid.uuid4().hex,
    }
    causal_inbound_event_id = _extract_causal_inbound_event_id_from_context(context)
    if causal_inbound_event_id is not None:
        metadata["causal_inbound_event_id"] = causal_inbound_event_id
    return metadata


def _extract_clawscale_conversation_id_from_context(
    context: dict | None,
) -> str | None:
    if not isinstance(context, dict):
        return None

    conversation = context.get("conversation", {})
    conversation_info = conversation.get("conversation_info", {})

    business_conversation_key = conversation.get("business_conversation_key")
    if business_conversation_key is None:
        business_conversation_key = conversation_info.get("business_conversation_key")
    if business_conversation_key is not None:
        return str(business_conversation_key)

    for message_list_key in ("input_messages", "chat_history"):
        conversation_id = _extract_clawscale_conversation_id_from_messages(
            conversation_info.get(message_list_key)
        )
        if conversation_id is not None:
            return conversation_id
    return None


def _extract_clawscale_conversation_id_from_messages(messages) -> str | None:
    if not isinstance(messages, list):
        return None

    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        metadata = message.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        business_conversation_key = metadata.get("business_conversation_key")
        if business_conversation_key is not None:
            return str(business_conversation_key)
    return None


def _extract_causal_inbound_event_id_from_context(context: dict | None) -> str | None:
    if not isinstance(context, dict):
        return None

    causal_inbound_event_id = context.get("causal_inbound_event_id")
    if causal_inbound_event_id is not None:
        return str(causal_inbound_event_id)
    return None


def _normalize_clawscale_platform(platform: str | None) -> str | None:
    if platform == "wechat":
        return "wechat_personal"
    return platform


def send_message(
    platform,
    from_user,
    to_user,
    chatroom_name,
    message,
    message_type="text",
    status="pending",
    expect_output_timestamp=None,
    handled_timestamp=None,
    account_id=None,
    metadata={},
):
    mongo = MongoDBBase()
    now = int(time.time())
    if expect_output_timestamp is None:
        expect_output_timestamp = now
    if handled_timestamp is None:
        handled_timestamp = expect_output_timestamp

    outputmessage = {
        "expect_output_timestamp": expect_output_timestamp,  # 预期输出的时间戳秒级
        "handled_timestamp": handled_timestamp,  # 处理完毕时的时间戳秒级
        "status": status,  # 标记处理状态：pending待处理，handled处理完毕，canceled不处理，failed处理失败
        "message_type": message_type,  # 包括：
        "message": message,  # 实际消息，格式另行约定
        "metadata": metadata,
    }
    if account_id is not None:
        outputmessage["account_id"] = account_id
    if from_user is not None:
        outputmessage["from_user"] = from_user
    if platform is not None:
        outputmessage["platform"] = platform
    if chatroom_name is not None:
        outputmessage["chatroom_name"] = chatroom_name
    if to_user is not None:
        outputmessage["to_user"] = to_user

    mid = mongo.insert_one("outputmessages", outputmessage)

    if mid is not None:
        outputmessage["_id"] = ObjectId(mid)
        if should_log_message_content():
            logger.info(f"写入输出消息: {format_std_message_for_log(outputmessage)}")
        return outputmessage
    else:
        return None
