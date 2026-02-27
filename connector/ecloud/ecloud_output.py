import sys

sys.path.append(".")
import copy
import time
import traceback

from util.log_util import get_logger

logger = get_logger(__name__)
import asyncio

from dotenv import load_dotenv

load_dotenv()
from conf.config import CONF
from connector.ecloud.ecloud_adapter import std_to_ecloud_message
from connector.ecloud.ecloud_api import Ecloud_API
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from entity.message import save_outputmessage


async def run_ecloud_output():
    while True:
        await asyncio.sleep(1)
        await output_handler()


async def main():
    await asyncio.gather(run_ecloud_output())


async def output_handler():
    mongo = MongoDBBase()
    user_dao = UserDAO()

    try:
        # 寻找要发送的message
        now = int(time.time())
        message = mongo.find_one(
            "outputmessages",
            {
                "platform": "wechat",
                # "from_user": target_user_id,
                "status": "pending",
                "expect_output_timestamp": {
                    "$lte": now
                },  # 修复：使用 $lte 而不是 $lt，确保当前时间的消息也能被发送
            },
        )

        if message is None:
            return

        logger.info("sending...")
        logger.info(message)

        target_user_id = message["from_user"]

        character = user_dao.get_user_by_id(target_user_id)
        if character is None:
            raise Exception("character not found: " + str(target_user_id))

        # 确定输出人wcid
        user = user_dao.get_user_by_id(message["to_user"])
        if user is None:
            raise Exception("character not found: " + str(target_user_id))

        target_user_alias = character["name"]
        wid_map = CONF.get("ecloud", {}).get("wId", {})
        wid = wid_map.get(target_user_alias)
        if wid is None:
            for _alias, _wid in wid_map.items():
                wid = _wid
                break
        if wid is None:
            raise Exception(
                "ecloud wId not configured for alias: " + str(target_user_alias)
            )

        # 实际发送
        ecloud = std_to_ecloud_message(message)
        ecloud["wId"] = wid
        if message["chatroom_name"] is None:
            # 私聊：安全获取用户微信账号
            wechat_info = user.get("platforms", {}).get("wechat", {})
            wcid = wechat_info.get("account") or wechat_info.get("id")
            if not wcid:
                raise Exception(f"user {message['to_user']} missing wechat account/id")
            ecloud["wcId"] = wcid
        else:
            ecloud["wcId"] = message["chatroom_name"]
            # 群聊回复时，添加 @原发送者
            original_sender_wxid = message.get("metadata", {}).get(
                "original_sender_wxid"
            )
            if original_sender_wxid:
                ecloud["at"] = original_sender_wxid

        logger.info("sending ecloud message...")
        logger.info(ecloud)

        # 分类型发送消息
        resp_json = {"code": 1001}
        if message["message_type"] in ["text"]:
            resp_json = Ecloud_API.sendText(ecloud)
        if message["message_type"] in ["voice"]:
            resp_json = Ecloud_API.sendVoice(ecloud)
            if resp_json["code"] != "1000":
                logger.info("sending voice error, fall back to text")
                # 使用深拷贝避免修改原消息对象
                fallback_message = copy.deepcopy(message)
                fallback_message["message_type"] = "text"
                ecloud = std_to_ecloud_message(fallback_message)
                ecloud["wId"] = wid
                if message["chatroom_name"] is None:
                    # 私聊：安全获取用户微信账号
                    wechat_info = user.get("platforms", {}).get("wechat", {})
                    wcid = wechat_info.get("account") or wechat_info.get("id")
                    if wcid:
                        ecloud["wcId"] = wcid
                else:
                    ecloud["wcId"] = message["chatroom_name"]
                    # 群聊回复时，添加 @原发送者
                    original_sender_wxid = message.get("metadata", {}).get(
                        "original_sender_wxid"
                    )
                    if original_sender_wxid:
                        ecloud["at"] = original_sender_wxid
                resp_json = Ecloud_API.sendText(ecloud)
        if message["message_type"] in ["image"]:
            resp_json = Ecloud_API.sendImage(ecloud)

        logger.info(resp_json)

        now = int(time.time())
        message["status"] = "handled"
        message["handled_timestamp"] = now
        save_outputmessage(message)

    except Exception:
        logger.error(traceback.format_exc())
        now = int(time.time())
        message["status"] = "failed"
        message["handled_timestamp"] = now
        save_outputmessage(message)


if __name__ == "__main__":
    asyncio.run(main())
