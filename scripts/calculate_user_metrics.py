# -*- coding: utf-8 -*-
import sys
import time
from datetime import datetime, timedelta

from bson import ObjectId

sys.path.append(".")
from util.log_util import get_logger

logger = get_logger(__name__)
from conf.config import CONF
from connector.ecloud.ecloud_api import Ecloud_API
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO


def get_user_first_message_time(mongo_db, user_id):
    """获取用户第一条消息的时间"""
    try:
        input_msg = mongo_db.db["inputmessages"].find_one(
            {"from_user": user_id},
            sort=[("input_timestamp", 1)],
            projection={"input_timestamp": 1},
        )
        output_msg = mongo_db.db["outputmessages"].find_one(
            {"to_user": user_id},
            sort=[("input_timestamp", 1)],
            projection={"input_timestamp": 1},
        )

        times = []
        if input_msg and "input_timestamp" in input_msg:
            times.append(input_msg["input_timestamp"])
        if output_msg and "input_timestamp" in output_msg:
            times.append(output_msg["input_timestamp"])

        return min(times) if times else None
    except Exception:
        return None


def get_l7d_score(mongo_db, user_id, current_timestamp):
    """计算 L7D 指标 (过去7天活跃天数)"""
    # 获取今天零点的时间戳
    dt_today = datetime.fromtimestamp(current_timestamp).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    score = 0

    # 获取过去7天的消息时间戳
    seven_days_ago = int((dt_today - timedelta(days=6)).timestamp())

    try:
        # 查询过去7天内的所有输入消息时间戳
        inputs = list(
            mongo_db.db["inputmessages"].find(
                {"from_user": user_id, "input_timestamp": {"$gte": seven_days_ago}},
                projection={"input_timestamp": 1},
            )
        )
        # 查询过去7天内的所有输出消息时间戳
        outputs = list(
            mongo_db.db["outputmessages"].find(
                {"to_user": user_id, "input_timestamp": {"$gte": seven_days_ago}},
                projection={"input_timestamp": 1},
            )
        )

        active_timestamps = [m["input_timestamp"] for m in inputs] + [
            m["input_timestamp"] for m in outputs
        ]
        if not active_timestamps:
            return 0

        active_dates = set()
        for ts in active_timestamps:
            active_dates.add(datetime.fromtimestamp(ts).date())

        # 统计最近7天内的活跃日期数
        today_date = dt_today.date()
        for i in range(7):
            check_date = today_date - timedelta(days=i)
            if check_date in active_dates:
                score += 1
        return score
    except Exception:
        return 0


def main():
    mongo_db = MongoDBBase()
    user_dao = UserDAO()

    # 使用系统提供的时间：2026-01-28
    current_time = 1769616000  # 2026-01-28 00:00:00 左右，或者直接用 time.time() 如果系统时间已同步
    # 实际上系统提示 current system time is Wednesday, January 28, 2026.
    current_time = time.time()

    users = user_dao.find_users(query={"is_character": {"$ne": True}})

    # 预获取所有 wxid 的 contact info，用于获取昵称和微信号
    wxid_list = []
    for u in users:
        platforms = u.get("platforms", {})
        wechat_info = platforms.get("wechat", {}) if isinstance(platforms, dict) else {}
        wxid = wechat_info.get("id")
        if wxid:
            wxid_list.append(wxid)

    # 获取最活跃50人用于 API 查询（由于 API 限制，这里假设我们只关心最活跃的一部分，或者分批查）
    # 但由于用户要求列出"所有用户"，我们尽量展示已有数据

    user_metrics = []

    print("正在计算指标，请稍候...")

    total_users = len(users)
    for idx, u in enumerate(users, 1):
        if idx % 50 == 0:
            logger.info(f"进度: {idx}/{total_users}")
        user_id = str(u["_id"])
        platforms = u.get("platforms", {})
        wechat_info = platforms.get("wechat", {}) if isinstance(platforms, dict) else {}
        wxid = wechat_info.get("id", "N/A")
        nickname = wechat_info.get("nickname", "N/A")
        alias_name = wechat_info.get("aliasName", "N/A")

        # 1. 第一条消息时间
        first_time = get_user_first_message_time(mongo_db, user_id)
        if not first_time:
            continue  # 无消息用户跳过

        # 2. 注册天数
        reg_days = (current_time - first_time) / 86400
        reg_days_int = int(reg_days) + 1  # 包含今天

        # 3. 总消息数
        input_count = mongo_db.count_documents("inputmessages", {"from_user": user_id})
        output_count = mongo_db.count_documents("outputmessages", {"to_user": user_id})
        total_messages = input_count + output_count

        # 4. 日平均交互次数
        avg_interactions = total_messages / max(1, reg_days_int)

        # 5. L7D 指标
        l7d_score = get_l7d_score(mongo_db, user_id, current_time)

        user_metrics.append(
            {
                "wxid": wxid,
                "aliasName": alias_name,
                "nickname": nickname,
                "l7d": l7d_score,
                "avg_interactions": round(avg_interactions, 2),
                "reg_days": reg_days_int,
                "total_messages": total_messages,
            }
        )

    # 按照 L7D 倒序，然后总消息数倒序
    user_metrics.sort(key=lambda x: (x["l7d"], x["total_messages"]), reverse=True)

    # 输出 CSV 格式
    # 根据用户偏好：wxid, aliasName, nickname, l7d, avg_interactions, reg_days
    # 序号由 1 开始

    for i, m in enumerate(user_metrics, 1):
        # CSV 格式输出，方便粘贴
        print(
            f"{i},{m['wxid']},{m['aliasName']},{m['nickname']},{m['l7d']},{m['avg_interactions']},{m['reg_days']}"
        )


if __name__ == "__main__":
    main()
