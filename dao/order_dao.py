# -*- coding: utf-8 -*-
"""
Order DAO - 订单数据访问层

用于门禁系统的订单管理。
"""

from datetime import datetime
from typing import Dict, Optional

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection

from conf.config import CONF
from util.log_util import get_logger

logger = get_logger(__name__)


class OrderDAO:
    """订单数据访问对象"""

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
        self.collection: Collection = self.db.get_collection("orders")

    def find_available_order(self, order_no: str) -> Optional[Dict]:
        """
        查找可用订单：存在、未绑定、未过期

        Args:
            order_no: 订单编号

        Returns:
            订单文档或 None
        """
        return self.collection.find_one(
            {
                "order_no": order_no,
                "bound_user_id": None,
                "expire_time": {"$gt": datetime.now()},
            }
        )

    def bind_to_user(self, order_no: str, user_id: ObjectId) -> bool:
        """
        绑定订单到用户（原子操作）

        Args:
            order_no: 订单编号
            user_id: 用户 ObjectId

        Returns:
            绑定是否成功
        """
        result = self.collection.update_one(
            {"order_no": order_no, "bound_user_id": None},
            {"$set": {"bound_user_id": user_id, "bound_at": datetime.now()}},
        )
        return result.modified_count > 0

    def get_by_order_no(self, order_no: str) -> Optional[Dict]:
        """
        根据订单号查询

        Args:
            order_no: 订单编号

        Returns:
            订单文档或 None
        """
        return self.collection.find_one({"order_no": order_no})

    def create_order(
        self, order_no: str, expire_time: datetime, metadata: Dict = None
    ) -> str:
        """
        创建订单

        Args:
            order_no: 订单编号
            expire_time: 过期时间
            metadata: 可选元数据

        Returns:
            插入的订单 ID
        """
        doc = {
            "order_no": order_no,
            "expire_time": expire_time,
            "bound_user_id": None,
            "bound_at": None,
            "created_at": datetime.now(),
            "metadata": metadata or {},
        }
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    def create_indexes(self):
        """创建必要的索引"""
        self.collection.create_index("order_no", unique=True)
        self.collection.create_index("bound_user_id")
        self.collection.create_index("expire_time")

    def close(self):
        """关闭连接"""
        self.client.close()
