import sys
sys.path.append(".")
import time

from qiaoyun.agent.qiaoyun_chat_response_agent import QiaoyunChatResponseAgent
from qiaoyun.runner.context import context_prepare
from dao.user_dao import UserDAO
from dao.conversation_dao import ConversationDAO

def main():
    user_dao = UserDAO()
    conversation_dao = ConversationDAO()

    character_alias = "qiaoyun"
    from conf.config import CONF
    _characters_conf = CONF.get("characters") or (CONF.get("aliyun") or {}).get("characters") or {}
    character_wechat_id = _characters_conf.get(character_alias)
    characters = user_dao.find_characters({
        "platforms.wechat.id": character_wechat_id
    })
    if not characters:
        print("character not found")
        return
    character = characters[0]

    # 选取一个用户与该角色的会话或创建
    users = user_dao.find_users({"platforms.wechat.id": {"$ne": character["platforms"]["wechat"]["id"]}}, 1)
    if not users:
        print("no user found")
        return
    user = users[0]

    conversation_id, _ = conversation_dao.get_or_create_private_conversation(
        platform="wechat",
        user_id1=user["platforms"]["wechat"]["id"],
        nickname1=user["platforms"]["wechat"]["nickname"],
        user_id2=character["platforms"]["wechat"]["id"],
        nickname2=character["platforms"]["wechat"]["nickname"],
    )
    conversation = conversation_dao.get_conversation_by_id(conversation_id)

    # 构造一条最新输入消息
    conversation["conversation_info"]["input_messages"] = [
        {
            "_id": "manual",
            "input_timestamp": int(time.time()),
            "handled_timestamp": None,
            "status": "handling",
            "platform": "wechat",
            "chatroom_name": None,
            "message_type": "text",
            "message": "五分钟后提醒我刷牙",
            "metadata": {},
            "from_user": str(user["_id"]),
            "to_user": str(character["_id"])
        }
    ]

    ctx = context_prepare(user, character, conversation)

    agent = QiaoyunChatResponseAgent(ctx)
    results = agent.run()
    for r in results:
        if r.get("status") == "message":
            resp = r.get("resp") or {}
            print("DetectedReminders:", resp.get("DetectedReminders"))
            print("MultiModalResponses:", resp.get("MultiModalResponses"))

if __name__ == "__main__":
    main()