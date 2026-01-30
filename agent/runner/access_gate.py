# -*- coding: utf-8 -*-
"""
Access Gate - 门禁系统

用于控制用户访问，需要有效订单才能使用服务。
"""

from datetime import datetime
from typing import Dict, Optional, Tuple

from bson import ObjectId

from conf.config import CONF
from dao.order_dao import OrderDAO
from dao.user_dao import UserDAO
from util.log_util import get_logger

logger = get_logger(__name__)


class AccessGate:
    """门禁检查器"""

    def __init__(self):
        self.config = CONF.get("access_control", {})
        self.order_dao = OrderDAO()
        self.user_dao = UserDAO()

    def is_enabled(self, platform: str) -> bool:
        """检查指定平台是否启用门禁"""
        if not self.config.get("enabled", False):
            return False
        return self.config.get("platforms", {}).get(platform, False)

    def check(
        self,
        platform: str,
        user: Dict,
        message: str,
        admin_user_id: str,
    ) -> Optional[Tuple[str, Optional[Dict]]]:
        """
        执行门禁检查

        Args:
            platform: 平台名称
            user: 用户文档
            message: 用户消息内容
            admin_user_id: 管理员用户ID

        Returns:
            None: 放行
            ("gate_denied", None): 未验证用户
            ("gate_expired", None): 授权已过期
            ("gate_success", {"expire_time": ...}): 验证成功
        """
        # 管理员豁免
        if admin_user_id and str(user["_id"]) == admin_user_id:
            return None

        # 检查平台是否启用门禁
        if not self.is_enabled(platform):
            return None

        user_id = user["_id"]
        access = user.get("access")

        # 检查是否有有效授权
        if access and access.get("expire_time"):
            if access["expire_time"] > datetime.now():
                return None  # 有效授权，放行

        # 尝试将消息作为订单号匹配
        order_no = message.strip()
        order = self.order_dao.find_available_order(order_no)

        if order:
            # 绑定订单到用户
            if self.order_dao.bind_to_user(order_no, user_id):
                expire_time = order["expire_time"]
                self.user_dao.update_access(user_id, order_no, expire_time)
                logger.info(
                    f"Access gate: user {user_id} bound to order {order_no}, "
                    f"expires {expire_time}"
                )
                return ("gate_success", {"expire_time": expire_time})
            else:
                # 订单已被其他用户绑定（并发竞争失败）
                logger.warning(
                    f"Access gate: order {order_no} bind failed (already bound)"
                )

        # 匹配失败，返回对应提示
        if access:  # 曾有授权但已过期
            return ("gate_expired", None)
        else:  # 从未授权
            return ("gate_denied", None)

    def get_message(self, gate_type: str, expire_time: datetime = None) -> str:
        """
        获取门禁提示消息

        Args:
            gate_type: gate_denied | gate_expired | gate_success
            expire_time: 过期时间（用于 gate_success）

        Returns:
            提示消息文本
        """
        if gate_type == "gate_denied":
            return self.config.get(
                "deny_message", "[系统消息] 请发送有效订单编号开通服务"
            )
        elif gate_type == "gate_expired":
            return self.config.get(
                "expire_message", "[系统消息] 您的服务已过期，请发送新的订单编号续期"
            )
        elif gate_type == "gate_success":
            msg = self.config.get(
                "success_message", "[系统消息] 验证成功，服务有效期至 {expire_time}"
            )
            if expire_time:
                return msg.format(expire_time=expire_time.strftime("%Y-%m-%d %H:%M"))
            return msg
        return ""

    def close(self):
        """关闭连接"""
        self.order_dao.close()
        self.user_dao.close()
