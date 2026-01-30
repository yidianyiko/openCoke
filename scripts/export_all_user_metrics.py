# -*- coding: utf-8 -*-
import sys
import time
import csv
import os
from datetime import datetime, timedelta
from bson import ObjectId

sys.path.append(".")
from util.log_util import get_logger
logger = get_logger(__name__)
from conf.config import CONF
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO

def get_message_times(mongo_db, user_id):
    """获取用户第一条和最后一条消息的时间"""
    try:
        # user_id is string, but let's be safe and check both string and ObjectId if needed
        # though usually it's string in messages
        query = {"from_user": user_id}
        out_query = {"to_user": user_id}
        
        # First message
        input_first = mongo_db.db["inputmessages"].find_one(
            query,
            sort=[("input_timestamp", 1)],
            projection={"input_timestamp": 1}
        )
        output_first = mongo_db.db["outputmessages"].find_one(
            out_query,
            sort=[("input_timestamp", 1)],
            projection={"input_timestamp": 1}
        )
        
        # Last message
        input_last = mongo_db.db["inputmessages"].find_one(
            query,
            sort=[("input_timestamp", -1)],
            projection={"input_timestamp": 1}
        )
        output_last = mongo_db.db["outputmessages"].find_one(
            out_query,
            sort=[("input_timestamp", -1)],
            projection={"input_timestamp": 1}
        )
        
        first_times = []
        if input_first and "input_timestamp" in input_first: 
            first_times.append(input_first["input_timestamp"])
        if output_first and "input_timestamp" in output_first: 
            first_times.append(output_first["input_timestamp"])
        
        last_times = []
        if input_last and "input_timestamp" in input_last: 
            last_times.append(input_last["input_timestamp"])
        if output_last and "input_timestamp" in output_last: 
            last_times.append(output_last["input_timestamp"])
            
        first_time = min(first_times) if first_times else None
        last_time = max(last_times) if last_times else None
        
        return first_time, last_time
    except Exception as e:
        logger.error(f"Error getting message times for {user_id}: {e}")
        return None, None

def get_l7d_score(mongo_db, user_id, current_timestamp):
    """计算 L7D 指标 (过去7天活跃天数)"""
    dt_today = datetime.fromtimestamp(current_timestamp).replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = int((dt_today - timedelta(days=6)).timestamp())
    
    try:
        inputs = list(mongo_db.db["inputmessages"].find(
            {"from_user": user_id, "input_timestamp": {"$gte": seven_days_ago}},
            projection={"input_timestamp": 1}
        ))
        outputs = list(mongo_db.db["outputmessages"].find(
            {"to_user": user_id, "input_timestamp": {"$gte": seven_days_ago}},
            projection={"input_timestamp": 1}
        ))
        
        active_timestamps = [m["input_timestamp"] for m in inputs] + [m["input_timestamp"] for m in outputs]
        if not active_timestamps:
            return 0
            
        active_dates = set()
        for ts in active_timestamps:
            active_dates.add(datetime.fromtimestamp(ts).date())
            
        return len(active_dates)
    except Exception:
        return 0

def format_ts(ts):
    if not ts: return "N/A"
    try:
        # Handle millisecond timestamps
        if ts > 1e11:
            ts = ts / 1000
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)

from connector.ecloud.ecloud_api import Ecloud_API

def update_user_info_via_api(user_dao, wxid, current_user_doc):
    """Call ecloud API to get missing info and update DB"""
    try:
        target_alias = CONF.get("default_character_alias", "luoyun")
        resp = Ecloud_API.getContact(wxid, target_alias)
        if resp and resp.get("code") == "1000" and resp.get("data"):
            contact = resp["data"][0]
            # Update the database record
            update_data = {
                "user_wechat_info": contact,
                "platforms.wechat.aliasName": contact.get("aliasName"),
                "platforms.wechat.nickname": contact.get("nickName")
            }
            user_dao.update_user(str(current_user_doc["_id"]), update_data)
            return contact.get("aliasName"), contact.get("nickName")
    except Exception as e:
        logger.error(f"API update failed for {wxid}: {e}")
    return None, None

def is_dec_14_24(ts):
    """Check if timestamp is between Dec 14 and Dec 24, 2025"""
    dt = datetime.fromtimestamp(ts)
    # Ensure it's 2025
    if dt.year != 2025 or dt.month != 12:
        return False
    return 14 <= dt.day <= 24

def main():
    mongo_db = MongoDBBase()
    user_dao = UserDAO()
    current_time = time.time()
    
    users = user_dao.find_users(query={"is_character": {"$ne": True}})
    total_users = len(users)
    
    output_dir = "scripts/output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    filepath = os.path.join(output_dir, "all_users_detailed_metrics.csv")
    
    headers = [
        "微信ID (wxid)", 
        "微信号 (aliasName)", 
        "昵称 (nickName)", 
        "输入消息总数", 
        "最近活跃时间", 
        "创建时间", 
        "L7D", 
        "日平均交互次数", 
        "注册天数",
        "14~24号创建"
    ]
    
    user_records = []
    
    logger.info(f"开始处理 {total_users} 个用户数据...")
    
    for idx, u in enumerate(users, 1):
        if idx % 20 == 0:
            logger.info(f"进度: {idx}/{total_users}")
            
        user_id = str(u["_id"])
        platforms = u.get("platforms", {})
        wechat_info = platforms.get("wechat", {}) if isinstance(platforms, dict) else {}
        
        wxid = wechat_info.get("id", "N/A")
        
        # aliasName and nickname might be in platforms.wechat or user_wechat_info
        user_wechat_info = u.get("user_wechat_info", {})
        alias_name = user_wechat_info.get("aliasName") or wechat_info.get("aliasName")
        nickname = user_wechat_info.get("nickName") or wechat_info.get("nickname")
        
        # If still missing, try API
        if (not alias_name or alias_name == "N/A") and wxid != "N/A":
            logger.info(f"正在为 {wxid} 调用 API 获取信息...")
            api_alias, api_nick = update_user_info_via_api(user_dao, wxid, u)
            if api_alias: alias_name = api_alias
            if api_nick: nickname = api_nick
            time.sleep(0.5) # Rate limit
            
        alias_name = alias_name or "N/A"
        nickname = nickname or "N/A"
        
        creation_time = u.get("_id").generation_time.timestamp()
        
        first_time, last_time = get_message_times(mongo_db, user_id)
        
        start_time = first_time if first_time else creation_time
        reg_days = int((current_time - start_time) / 86400) + 1
        
        input_count = mongo_db.count_documents("inputmessages", {"from_user": user_id})
        output_count = mongo_db.count_documents("outputmessages", {"to_user": user_id})
        total_messages = input_count + output_count
        
        avg_interactions = round(total_messages / max(1, reg_days), 2)
        l7d_score = get_l7d_score(mongo_db, user_id, current_time)
        
        is_target_period = "YES" if is_dec_14_24(creation_time) else "NO"
        
        user_records.append([
            wxid,
            alias_name,
            nickname,
            input_count,
            format_ts(last_time),
            format_ts(creation_time),
            l7d_score,
            avg_interactions,
            reg_days,
            is_target_period
        ])
    
    # 按照 L7D 和总交互数排序
    user_records.sort(key=lambda x: (x[6], x[7]), reverse=True)
    
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(user_records)
        
    logger.info(f"数据已导出至: {filepath}")
    print(f"Successfully exported data for {len(user_records)} users to {filepath}")

if __name__ == "__main__":
    main()
