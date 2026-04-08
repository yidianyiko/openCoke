import sys

sys.path.append(".")
import time
import traceback

from util.log_util import get_logger

logger = get_logger(__name__)

from bson import ObjectId

from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
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
    platforms = talker.get("platforms")
    if isinstance(platforms, dict):
        pinfo = platforms.get(platform)
        if isinstance(pinfo, dict):
            nickname = pinfo.get("nickname")
            if nickname:
                return nickname
    nickname = talker.get("nickname")
    if nickname:
        return nickname
    return default_name


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

    is_proactive_message = context.get("message_source") in {"future", "reminder"}
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
        elif context.get("user", {}).get("_id"):
            metadata = {
                **build_clawscale_push_metadata(
                    str(context["user"]["_id"]), context=context
                ),
                **metadata,
            }
    elif context.get("user", {}).get("_id"):
        metadata = {
            **build_clawscale_push_metadata(str(context["user"]["_id"]), context=context),
            **metadata,
        }

    return send_message(
        platform=context["conversation"]["platform"],
        from_user=str(context["character"]["_id"]),
        to_user=str(context["user"]["_id"]),
        chatroom_name=context["conversation"]["chatroom_name"],
        message=message,
        message_type=message_type,
        status="pending",
        expect_output_timestamp=expect_output_timestamp,
        metadata=metadata,
    )


def build_clawscale_push_metadata(
    user_id: str, now_ts: int | None = None, context: dict | None = None
):
    from conf.config import CONF
    from connector.clawscale_bridge.output_route_resolver import OutputRouteResolver
    from dao.clawscale_push_route_dao import ClawscalePushRouteDAO
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(
        mongo_uri="mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name=CONF["mongodb"]["mongodb_name"],
    )
    clawscale_push_route_dao = ClawscalePushRouteDAO(
        mongo_uri="mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name=CONF["mongodb"]["mongodb_name"],
    )
    resolver = OutputRouteResolver(dao, clawscale_push_route_dao=clawscale_push_route_dao)
    conversation_id = None
    platform = None
    if context:
        conversation_id = context.get("conversation_id")
        if conversation_id is None:
            conversation_id = context.get("conversation", {}).get("_id")
        if conversation_id is not None:
            conversation_id = str(conversation_id)
        platform = context.get("conversation", {}).get("platform") or context.get(
            "platform"
        )
    return resolver.build_push_metadata(
        str(user_id),
        now_ts or int(time.time()),
        conversation_id=conversation_id,
        platform=platform,
    )


def send_message(
    platform,
    from_user,
    to_user,
    chatroom_name,
    message,
    message_type="text",
    status="pending",
    expect_output_timestamp=None,
    metadata={},
):
    mongo = MongoDBBase()
    now = int(time.time())
    if expect_output_timestamp is None:
        expect_output_timestamp = now

    outputmessage = {
        "expect_output_timestamp": expect_output_timestamp,  # 预期输出的时间戳秒级
        "handled_timestamp": expect_output_timestamp,  # 处理完毕时的时间戳秒级
        "status": status,  # 标记处理状态：pending待处理，handled处理完毕，canceled不处理，failed处理失败
        "from_user": from_user,  # 来源uid
        "platform": platform,  # 来源平台
        "chatroom_name": chatroom_name,  # 如果有值，则来自群聊；否则是私聊
        "to_user": to_user,  # 目标用户uid；群聊时，值为None
        "message_type": message_type,  # 包括：
        "message": message,  # 实际消息，格式另行约定
        "metadata": metadata,
    }

    mid = mongo.insert_one("outputmessages", outputmessage)

    if mid is not None:
        outputmessage["_id"] = ObjectId(mid)
        if should_log_message_content():
            logger.info(f"写入输出消息: {format_std_message_for_log(outputmessage)}")
        return outputmessage
    else:
        return None
