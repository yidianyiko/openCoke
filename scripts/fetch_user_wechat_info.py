# -*- coding: utf-8 -*-
"""
获取活跃用户微信信息脚本

通过 ecloud getContact API 获取用户的微信号(aliasName)和昵称(nickName)信息。
仅查询显示，不写入数据库。

Usage:
    # 查询单个用户
    python scripts/fetch_user_wechat_info.py --wxid wxid_xxx

    # 查询多个用户（逗号分隔）
    python scripts/fetch_user_wechat_info.py --wxid wxid_xxx,wxid_yyy

    # 查询最活跃的50个用户（默认）
    python scripts/fetch_user_wechat_info.py

    # 查询最活跃的N个用户
    python scripts/fetch_user_wechat_info.py --top 100
"""
import sys
import time

sys.path.append(".")

from dotenv import load_dotenv

load_dotenv()

import argparse
from datetime import datetime

from bson import ObjectId

from util.log_util import get_logger

logger = get_logger(__name__)

from conf.config import CONF
from connector.ecloud.ecloud_api import Ecloud_API
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO


def format_timestamp(timestamp):
    """将时间戳格式化为可读日期"""
    if not timestamp:
        return "N/A"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, TypeError):
        return str(timestamp)


def get_user_creation_time(user_id):
    """从用户ID的ObjectId中提取创建时间"""
    try:
        obj_id = ObjectId(user_id)
        creation_time = obj_id.generation_time.timestamp()
        return creation_time
    except Exception:
        return None


def get_user_last_message_time(mongo_db, user_id):
    """获取用户最后一条消息的时间"""
    try:
        input_cursor = (
            mongo_db.db["inputmessages"]
            .find({"from_user": user_id})
            .sort("input_timestamp", -1)
            .limit(1)
        )
        input_msgs = list(input_cursor)
        input_msg = input_msgs[0] if input_msgs else None

        output_cursor = (
            mongo_db.db["outputmessages"]
            .find({"to_user": user_id})
            .sort("input_timestamp", -1)
            .limit(1)
        )
        output_msgs = list(output_cursor)
        output_msg = output_msgs[0] if output_msgs else None

        input_time = (
            input_msg.get("input_timestamp", -float("inf"))
            if input_msg
            else -float("inf")
        )
        output_time = (
            output_msg.get("input_timestamp", -float("inf"))
            if output_msg
            else -float("inf")
        )

        last_time = max(input_time, output_time)
        return last_time if last_time != -float("inf") else None
    except Exception:
        return None


def count_user_messages(mongo_db, user_id):
    """统计用户的消息数量"""
    input_count = mongo_db.count_documents("inputmessages", {"from_user": user_id})
    output_count = mongo_db.count_documents("outputmessages", {"to_user": user_id})
    return input_count, output_count


def fetch_contact_info_batch(wxid_list, target_user_alias=None):
    """
    通过 ecloud API 批量获取联系人信息

    Args:
        wxid_list: wxid 列表
        target_user_alias: 角色别名

    Returns:
        dict: wxid -> contact_info 的映射
    """
    if target_user_alias is None:
        target_user_alias = CONF.get("default_character_alias", "luoyun")

    results = {}

    # API 每次最多支持20个，需要分批
    batch_size = 20
    for i in range(0, len(wxid_list), batch_size):
        batch = wxid_list[i : i + batch_size]
        wcid_str = ",".join(batch)

        try:
            logger.info(f"正在查询第 {i//batch_size + 1} 批，共 {len(batch)} 个用户...")
            resp_json = Ecloud_API.getContact(wcid_str, target_user_alias)

            if resp_json and resp_json.get("code") == "1000":
                data_list = resp_json.get("data", [])
                for contact in data_list:
                    user_name = contact.get("userName", "")
                    results[user_name] = {
                        "nickName": contact.get("nickName", ""),
                        "aliasName": contact.get("aliasName", ""),
                        "remark": contact.get("remark", ""),
                        "signature": contact.get("signature", ""),
                        "sex": contact.get("sex", 0),
                    }
            else:
                logger.warning(f"API 返回失败: {resp_json}")

            # 遵循 API 调用间隔要求 (300-800ms)
            time.sleep(1)

        except Exception as e:
            logger.error(f"获取联系人信息失败: {e}")

    return results


def fetch_single_user(wxid, target_user_alias=None):
    """查询单个用户信息"""
    if target_user_alias is None:
        target_user_alias = CONF.get("default_character_alias", "luoyun")

    print(f"\n查询用户: {wxid}")
    print("=" * 60)

    try:
        resp_json = Ecloud_API.getContact(wxid, target_user_alias)

        if resp_json and resp_json.get("code") == "1000":
            data_list = resp_json.get("data", [])
            if data_list:
                contact = data_list[0]
                print(f"微信ID (userName):  {contact.get('userName', 'N/A')}")
                print(f"微信号 (aliasName): {contact.get('aliasName', 'N/A')}")
                print(f"昵称 (nickName):    {contact.get('nickName', 'N/A')}")
                print(f"备注 (remark):      {contact.get('remark', 'N/A')}")
                print(f"签名 (signature):   {contact.get('signature', 'N/A')}")
                print(f"性别 (sex):         {contact.get('sex', 'N/A')}")
                return contact
            else:
                print("未找到用户信息")
        else:
            print(f"API 返回失败: {resp_json}")

    except Exception as e:
        print(f"查询失败: {e}")

    return None


def list_top_active_users_with_api(top_n=50):
    """列出最活跃用户并通过API获取微信信息"""
    logger.info(f"开始获取最活跃的 {top_n} 个用户...")

    mongo_db = MongoDBBase()
    user_dao = UserDAO()

    try:
        # 获取所有非角色用户
        users = user_dao.find_users(query={"is_character": {"$ne": True}})

        if not users:
            logger.info("未找到任何用户")
            return

        total_users = len(users)
        logger.info(f"共找到 {total_users} 个用户，正在分析活跃度...")

        # 收集用户数据
        user_data = []
        for user in users:
            user_id = str(user.get("_id", "N/A"))

            platforms = user.get("platforms", {})
            wechat_info = (
                platforms.get("wechat", {}) if isinstance(platforms, dict) else {}
            )
            wechat_id = (
                wechat_info.get("id", "N/A") if isinstance(wechat_info, dict) else "N/A"
            )

            creation_time = get_user_creation_time(user_id)
            input_count, output_count = count_user_messages(mongo_db, user_id)
            total_count = input_count + output_count
            last_message_time = get_user_last_message_time(mongo_db, user_id)

            user_data.append(
                {
                    "user_id": user_id,
                    "wechat_id": wechat_id,
                    "input_count": input_count,
                    "output_count": output_count,
                    "total_count": total_count,
                    "last_active_time": last_message_time,
                    "creation_time": creation_time,
                }
            )

        # 按总消息数排序，获取前N名
        user_data.sort(key=lambda x: x["total_count"], reverse=True)
        top_users = user_data[:top_n]

        # 收集所有 wxid 并通过 API 获取信息
        wxid_list = [u["wechat_id"] for u in top_users if u["wechat_id"] != "N/A"]
        logger.info(f"正在通过 API 获取 {len(wxid_list)} 个用户的微信信息...")

        contact_info_map = fetch_contact_info_batch(wxid_list)
        logger.info(f"成功获取 {len(contact_info_map)} 个用户的信息")

        # 打印结果
        print("\n" + "=" * 160)
        print(f"最活跃的 {top_n} 个用户（含 API 获取的微信号和昵称）")
        print("=" * 160)
        print(
            "{:<6} {:<26} {:<20} {:<18} {:<10} {:<10} {:<22} {:<22}".format(
                "排名",
                "微信ID (wxid)",
                "微信号 (aliasName)",
                "昵称 (nickName)",
                "输入消息",
                "输出消息",
                "最近活跃时间",
                "创建时间",
            )
        )
        print("-" * 160)

        for i, user in enumerate(top_users, 1):
            wechat_id = user["wechat_id"] if user["wechat_id"] else "N/A"

            # 从 API 结果获取信息
            api_info = contact_info_map.get(wechat_id, {})
            alias_name = api_info.get("aliasName", "") or "N/A"
            nick_name = api_info.get("nickName", "") or "N/A"

            # 截断显示
            wechat_id_display = wechat_id[:24] if wechat_id else "N/A"
            alias_name_display = alias_name[:18] if alias_name else "N/A"
            nick_name_display = nick_name[:16] if nick_name else "N/A"

            last_active_str = (
                format_timestamp(user["last_active_time"])
                if user["last_active_time"]
                else "N/A"
            )
            creation_str = (
                format_timestamp(user["creation_time"])
                if user["creation_time"]
                else "N/A"
            )

            print(
                "{:<6} {:<26} {:<20} {:<18} {:<10} {:<10} {:<22} {:<22}".format(
                    i,
                    wechat_id_display,
                    alias_name_display,
                    nick_name_display,
                    user["input_count"],
                    user["output_count"],
                    last_active_str,
                    creation_str,
                )
            )

        print("=" * 160)

        # 统计
        has_alias = sum(
            1
            for u in top_users
            if contact_info_map.get(u["wechat_id"], {}).get("aliasName")
        )
        has_nick = sum(
            1
            for u in top_users
            if contact_info_map.get(u["wechat_id"], {}).get("nickName")
        )
        print(
            f"\n统计: 有微信号(aliasName): {has_alias}/{top_n}, 有昵称(nickName): {has_nick}/{top_n}"
        )

        logger.info("查询完成")

    except Exception as e:
        logger.error(f"获取用户信息时发生错误: {e}")
        raise


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="获取活跃用户微信信息")
    parser.add_argument(
        "--wxid",
        type=str,
        help="查询指定的 wxid（多个用逗号分隔）",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="查询最活跃的前N个用户（默认: 50）",
    )
    parser.add_argument(
        "--character",
        type=str,
        default=None,
        help="指定角色别名（默认使用配置中的 default_character_alias）",
    )
    args = parser.parse_args()

    if args.wxid:
        # 查询指定用户
        wxid_list = [w.strip() for w in args.wxid.split(",")]
        if len(wxid_list) == 1:
            fetch_single_user(wxid_list[0], args.character)
        else:
            results = fetch_contact_info_batch(wxid_list, args.character)
            print("\n" + "=" * 80)
            print("查询结果")
            print("=" * 80)
            print("{:<26} {:<20} {:<20}".format("微信ID", "微信号", "昵称"))
            print("-" * 80)
            for wxid in wxid_list:
                info = results.get(wxid, {})
                print(
                    "{:<26} {:<20} {:<20}".format(
                        wxid[:24],
                        (info.get("aliasName") or "N/A")[:18],
                        (info.get("nickName") or "N/A")[:18],
                    )
                )
    else:
        # 查询最活跃用户
        list_top_active_users_with_api(top_n=args.top)


if __name__ == "__main__":
    main()
