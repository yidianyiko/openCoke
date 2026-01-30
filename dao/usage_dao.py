# -*- coding: utf-8 -*-
"""
Usage DAO - 用量记录数据访问层

用于持久化和查询 Agent 调用的 token 用量。
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from pymongo import DESCENDING, MongoClient
from pymongo.collection import Collection

from conf.config import CONF
from util.log_util import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "usage_records"


class UsageDAO:
    """用量记录数据访问对象"""

    def __init__(
        self,
        mongo_uri: str = "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/",
        db_name: str = CONF["mongodb"]["mongodb_name"],
    ):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection: Collection = self.db.get_collection(COLLECTION_NAME)

    def insert_usage_record(self, record: Dict) -> str:
        """
        插入用量记录

        Args:
            record: 用量记录字典

        Returns:
            插入的记录 ID
        """
        result = self.collection.insert_one(record)
        return str(result.inserted_id)

    def get_daily_summary(self, date: datetime = None) -> Dict:
        """
        获取日用量汇总

        Args:
            date: 指定日期，默认为今天

        Returns:
            汇总数据，包含 total_tokens, total_input, total_output, count, by_agent
        """
        if date is None:
            date = datetime.now()

        # 当日开始和结束时间
        start_of_day = datetime(date.year, date.month, date.day)
        end_of_day = start_of_day + timedelta(days=1)

        # 聚合查询
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_of_day, "$lt": end_of_day}}},
            {
                "$group": {
                    "_id": "$agent_name",
                    "total_input": {"$sum": "$input_tokens"},
                    "total_output": {"$sum": "$output_tokens"},
                    "total_tokens": {"$sum": "$total_tokens"},
                    "count": {"$sum": 1},
                    "avg_duration": {"$avg": "$duration"},
                }
            },
        ]

        results = list(self.collection.aggregate(pipeline))

        # 整理结果
        by_agent = {}
        total_input = 0
        total_output = 0
        total_tokens = 0
        total_count = 0

        for r in results:
            agent_name = r["_id"]
            by_agent[agent_name] = {
                "input_tokens": r["total_input"],
                "output_tokens": r["total_output"],
                "total_tokens": r["total_tokens"],
                "count": r["count"],
                "avg_duration": r["avg_duration"],
            }
            total_input += r["total_input"]
            total_output += r["total_output"]
            total_tokens += r["total_tokens"]
            total_count += r["count"]

        return {
            "date": start_of_day.strftime("%Y-%m-%d"),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_tokens,
            "total_calls": total_count,
            "by_agent": by_agent,
        }

    def get_user_daily_summary(self, user_id: str, date: datetime = None) -> Dict:
        """
        获取指定用户的日用量汇总

        Args:
            user_id: 用户 ID
            date: 指定日期，默认为今天

        Returns:
            用户的日用量汇总
        """
        if date is None:
            date = datetime.now()

        start_of_day = datetime(date.year, date.month, date.day)
        end_of_day = start_of_day + timedelta(days=1)

        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {"$gte": start_of_day, "$lt": end_of_day},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_input": {"$sum": "$input_tokens"},
                    "total_output": {"$sum": "$output_tokens"},
                    "total_tokens": {"$sum": "$total_tokens"},
                    "count": {"$sum": 1},
                }
            },
        ]

        results = list(self.collection.aggregate(pipeline))

        if not results:
            return {
                "user_id": user_id,
                "date": start_of_day.strftime("%Y-%m-%d"),
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "total_calls": 0,
            }

        r = results[0]
        return {
            "user_id": user_id,
            "date": start_of_day.strftime("%Y-%m-%d"),
            "total_input_tokens": r["total_input"],
            "total_output_tokens": r["total_output"],
            "total_tokens": r["total_tokens"],
            "total_calls": r["count"],
        }

    def get_recent_records(
        self, limit: int = 100, user_id: Optional[str] = None
    ) -> List[Dict]:
        """
        获取最近的用量记录

        Args:
            limit: 返回数量限制
            user_id: 可选，筛选指定用户

        Returns:
            记录列表
        """
        query = {}
        if user_id:
            query["user_id"] = user_id

        cursor = self.collection.find(query).sort("timestamp", DESCENDING).limit(limit)
        return list(cursor)

    def create_indexes(self):
        """创建必要的索引"""
        self.collection.create_index("timestamp")
        self.collection.create_index("user_id")
        self.collection.create_index("agent_name")
        self.collection.create_index([("timestamp", DESCENDING)])
        logger.info(f"[UsageDAO] Indexes created for {COLLECTION_NAME}")

    def close(self):
        """关闭连接"""
        self.client.close()
