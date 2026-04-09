import sys

sys.path.append(".")
import time

from util.log_util import get_logger

logger = get_logger(__name__)

from conf.config import CONF
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.time_util import date2str

target_user_alias = CONF.get("default_character_alias", "coke")
supported_hardcode = ("删除 ", "重新生成")


def _resolve_target_character_id() -> str | None:
    characters = UserDAO().find_characters({"name": target_user_alias}, limit=1)
    if not characters:
        return None
    return str(characters[0]["_id"])


def handle_hardcode(context, message):
    mongo = MongoDBBase()
    if str(message).startswith("删除 "):
        pid = str(message).replace("删除 ", "")
        pid = pid.strip()
        mongo.delete_vector("embeddings", pid)

    if str(message).startswith("重新生成"):
        target_character_id = _resolve_target_character_id()
        if not target_character_id:
            logger.warning("未找到目标角色，跳过重新生成 dailynews")
            return

        date_str = date2str(int(time.time()))
        mongo.delete_one("dailynews", {"cid": target_character_id, "date": date_str})
