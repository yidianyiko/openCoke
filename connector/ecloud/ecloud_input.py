import logging
import sys
import time

import requests
from flask import Flask, jsonify, request

sys.path.append(".")
from dotenv import load_dotenv

load_dotenv()
# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s-%(name)s-%(levelname)s-%(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

from conf.config import CONF
from connector.ecloud.ecloud_adapter import (
    ecloud_message_to_std,
    is_group_message,
    should_respond_to_group_message,
)
from connector.ecloud.ecloud_api import Ecloud_API
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.redis_client import RedisClient
from util.redis_stream import publish_input_event

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency until redis is installed
    redis = None

mongo = MongoDBBase()
user_dao = UserDAO()
redis_conf = RedisClient.from_config()
redis_client = (
    redis.Redis(host=redis_conf.host, port=redis_conf.port, db=redis_conf.db)
    if redis is not None
    else None
)


def _publish_stream_event(message_id: str, platform: str, ts: int) -> None:
    if redis_client is None:
        return
    publish_input_event(
        redis_client,
        message_id,
        platform,
        ts,
        stream_key=redis_conf.stream_key,
    )

# Whitelist dictionary-wcId as key, forwarding URL as value
# You can modify this dictionary as needed
whitelist = {
    "wxid_phyyedw9xap22": "http://example.com/forward1",
    "wxid_1dfgh4fs8vz22": "http://example.com/forward2",
    # Add more entries as needed
}

user_whitelist = []
# user_whitelist = ["LeanInWind", "z4656207", "wxid_vex849hfamd822", "samueli", "DoonsSong", "annie--y"]

supported_message_types = [
    # 私聊消息
    "60001",  # 私聊文本
    "60014",  # 私聊引用
    "60004",  # 私聊语音
    "60002",  # 私聊图片
    # 群聊消息
    "80001",  # 群聊文本
    "80014",  # 群聊引用
    "80004",  # 群聊语音
    "80002",  # 群聊图片
]


@app.route("/message", methods=["POST"])
def handle_message():
    """
    Handle incoming message requests and forward them based on wcId
    """
    if not request.is_json:
        logger.warning("Request is not JSON")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    # Get the JSON data
    data = request.get_json()
    logger.info(data)

    # Extract wcId from the request
    wcId = data.get("wcId")

    if not wcId:
        logger.warning("No wcId in request")
        return jsonify({"status": "error", "message": "No wcId provided"}), 400

    # Check if wcId is in whitelist
    if wcId in whitelist:
        forward_url = whitelist[wcId]

        try:
            # Forward the request to the corresponding URL
            logger.info(f"Forwarding request for wcId {wcId} to {forward_url}")
            response = requests.post(
                forward_url, json=data, headers={"Content-Type": "application/json"}
            )

            # Return the response from the forwarded request
            return jsonify(
                {
                    "status": "success",
                    "message": f"Request forwarded to {forward_url}",
                    "forward_status": response.status_code,
                    "forward_response": (
                        response.json()
                        if response.headers.get("content-type") == "application/json"
                        else response.text
                    ),
                }
            )

        except requests.RequestException as e:
            logger.error(f"Error forwarding request: {str(e)}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Error forwarding request: {str(e)}",
                    }
                ),
                500,
            )
    else:
        logger.info("message incoming, handling...")

        # 支持的类型
        if data["messageType"] not in supported_message_types:
            logger.info("not supported message type.")
            return (
                jsonify(
                    {"status": "success", "message": "not supported message type."}
                ),
                200,
            )

        # 白名单
        if len(user_whitelist) != 0:
            if data["data"]["fromUser"] not in user_whitelist:
                logger.info("user not in white list, ignore this message")
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "user not in white list, ignore this message",
                        }
                    ),
                    200,
                )

        # 验证character或者user是否存在
        characters = user_dao.find_characters(
            {"platforms.wechat.id": data["data"]["toUser"]}
        )

        if len(characters) == 0:
            return (
                jsonify(
                    {"status": "success", "message": "character not exist, skip..."}
                ),
                200,
            )

        cid = str(characters[0]["_id"])
        character = characters[0]

        # 群消息特殊处理
        if is_group_message(data):
            group_config = CONF.get("ecloud", {}).get("group_chat", {})
            bot_wxid = data["data"]["toUser"]
            bot_nickname = character.get("name", "")

            if not should_respond_to_group_message(
                data, group_config, bot_wxid, bot_nickname
            ):
                logger.info("group message filtered by reply policy")
                return (
                    jsonify(
                        {
                            "status": "success",
                            "message": "group message filtered by reply policy",
                        }
                    ),
                    200,
                )

        # 用 id 字段查询（fromUser 是 wxid，存储在 id 字段）
        users = user_dao.find_users({"platforms.wechat.id": data["data"]["fromUser"]})

        # 如果用户不存在，则创建一个
        if len(users) == 0:
            logger.info("user not exist, create a new one")
            target_user_alias = characters[0]["name"]

            # 安全获取用户信息
            try:
                resp_json = Ecloud_API.getContact(
                    data["data"]["fromUser"], target_user_alias
                )
                logger.info(resp_json)

                # 检查 API 返回是否成功
                if not resp_json or resp_json.get("code") != "1000":
                    logger.error(
                        f"getContact API failed: {resp_json.get('message', 'unknown error')}"
                    )
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "failed to get user contact info",
                            }
                        ),
                        500,
                    )

                # 检查 data 数组是否非空
                contact_data = resp_json.get("data", [])
                if not contact_data:
                    logger.error("getContact returned empty data array")
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "user contact info not found",
                            }
                        ),
                        500,
                    )

                user_wechat_info = contact_data[0]
            except Exception as e:
                logger.error(f"getContact exception: {str(e)}")
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"failed to get user contact: {str(e)}",
                        }
                    ),
                    500,
                )

            uid = user_dao.create_user(
                {
                    "is_character": False,  # 是否是角色
                    "name": user_wechat_info.get("userName", data["data"]["fromUser"]),
                    "platforms": {
                        "wechat": {
                            "id": data["data"]["fromUser"],  # 微信统一id
                            "account": user_wechat_info.get(
                                "userName", data["data"]["fromUser"]
                            ),
                            "nickname": user_wechat_info.get("nickName", ""),
                        },
                    },
                    "status": "normal",  # normal | stopped
                    "user_info": {},
                    "user_wechat_info": user_wechat_info,
                }
            )
        else:
            uid = str(users[0]["_id"])

        # 标准化数据
        std = ecloud_message_to_std(data)
        std["from_user"] = uid
        std["to_user"] = cid

        # 消息去重：检查 newMsgId 是否已存在
        new_msg_id = std.get("metadata", {}).get("new_msg_id")
        if new_msg_id:
            existing = mongo.find_one(
                "inputmessages", {"metadata.new_msg_id": new_msg_id}
            )
            if existing:
                logger.info(f"duplicate message detected, newMsgId={new_msg_id}")
                return (
                    jsonify(
                        {"status": "success", "message": "duplicate message, skipped"}
                    ),
                    200,
                )

        # 插入到数据库
        inserted_id = mongo.insert_one("inputmessages", std)
        _publish_stream_event(
            inserted_id,
            std.get("platform", "wechat"),
            int(std.get("input_timestamp", time.time())),
        )

        return jsonify({"status": "success", "message": "message handing..."}), 200


if __name__ == "__main__":
    logger.info("Starting Flask forwarding service")
    app.run(host="0.0.0.0", port=8080, debug=False)
