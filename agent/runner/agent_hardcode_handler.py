import sys

sys.path.append(".")
import time

from util.log_util import get_logger

logger = get_logger(__name__)

from conf.config import CONF
from dao.mongo import MongoDBBase
from util.time_util import date2str

target_user_alias = CONF.get("default_character_alias", "coke")
supported_hardcode = ("删除 ", "重新生成")


def handle_hardcode(context, message):
    mongo = MongoDBBase()
    if str(message).startswith("删除 "):
        pid = str(message).replace("删除 ", "")
        pid = pid.strip()
        mongo.delete_vector("embeddings", pid)

    if str(message).startswith("重新生成"):
        target_user_id = CONF["characters"][target_user_alias]

        date_str = date2str(int(time.time()))
        mongo.delete_one("dailynews", {"cid": target_user_id, "date": date_str})
