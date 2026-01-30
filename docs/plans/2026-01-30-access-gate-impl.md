# Access Gate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a platform-agnostic access control system where users must provide valid order numbers to use the service.

**Architecture:** Gate check integrated into `MessageDispatcher.dispatch()` alongside existing blacklist check. New `orders` collection stores order data. User documents extended with `access` field for authorization state.

**Tech Stack:** Python 3.12+, MongoDB, pytest

---

## Task 1: Create OrderDAO

**Files:**
- Create: `dao/order_dao.py`
- Test: `tests/unit/dao/test_order_dao.py`

**Step 1: Write the failing test**

Create `tests/unit/dao/test_order_dao.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for OrderDAO"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from bson import ObjectId


class TestOrderDAO:
    """Tests for OrderDAO class"""

    @pytest.fixture
    def mock_collection(self):
        """Create a mock MongoDB collection"""
        return MagicMock()

    @pytest.fixture
    def order_dao(self, mock_collection):
        """Create OrderDAO with mocked collection"""
        with patch("dao.order_dao.MongoClient") as mock_client:
            mock_db = MagicMock()
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.__getitem__.return_value = mock_db

            from dao.order_dao import OrderDAO
            dao = OrderDAO()
            dao.collection = mock_collection
            return dao

    @pytest.mark.unit
    def test_find_available_order_returns_valid_order(self, order_dao, mock_collection):
        """Should return order when it exists, is unbound, and not expired"""
        future_time = datetime.now() + timedelta(days=30)
        expected_order = {
            "_id": ObjectId(),
            "order_no": "ORD123456",
            "expire_time": future_time,
            "bound_user_id": None,
        }
        mock_collection.find_one.return_value = expected_order

        result = order_dao.find_available_order("ORD123456")

        assert result == expected_order
        mock_collection.find_one.assert_called_once()
        call_args = mock_collection.find_one.call_args[0][0]
        assert call_args["order_no"] == "ORD123456"
        assert call_args["bound_user_id"] is None

    @pytest.mark.unit
    def test_find_available_order_returns_none_when_not_found(self, order_dao, mock_collection):
        """Should return None when order doesn't exist"""
        mock_collection.find_one.return_value = None

        result = order_dao.find_available_order("NONEXISTENT")

        assert result is None

    @pytest.mark.unit
    def test_bind_to_user_success(self, order_dao, mock_collection):
        """Should return True when binding succeeds"""
        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_collection.update_one.return_value = mock_result
        user_id = ObjectId()

        result = order_dao.bind_to_user("ORD123456", user_id)

        assert result is True
        mock_collection.update_one.assert_called_once()

    @pytest.mark.unit
    def test_bind_to_user_fails_when_already_bound(self, order_dao, mock_collection):
        """Should return False when order is already bound"""
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_collection.update_one.return_value = mock_result
        user_id = ObjectId()

        result = order_dao.bind_to_user("ORD123456", user_id)

        assert result is False

    @pytest.mark.unit
    def test_get_by_order_no(self, order_dao, mock_collection):
        """Should return order by order_no"""
        expected_order = {"_id": ObjectId(), "order_no": "ORD123456"}
        mock_collection.find_one.return_value = expected_order

        result = order_dao.get_by_order_no("ORD123456")

        assert result == expected_order
        mock_collection.find_one.assert_called_once_with({"order_no": "ORD123456"})
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && pytest tests/unit/dao/test_order_dao.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'dao.order_dao'`

**Step 3: Write minimal implementation**

Create `dao/order_dao.py`:

```python
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
        return self.collection.find_one({
            "order_no": order_no,
            "bound_user_id": None,
            "expire_time": {"$gt": datetime.now()}
        })

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
            {"$set": {"bound_user_id": user_id, "bound_at": datetime.now()}}
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

    def create_order(self, order_no: str, expire_time: datetime, metadata: Dict = None) -> str:
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
            "metadata": metadata or {}
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
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && pytest tests/unit/dao/test_order_dao.py -v`

Expected: PASS (5 tests)

**Step 5: Commit**

```bash
cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate
git add dao/order_dao.py tests/unit/dao/test_order_dao.py
git commit -m "feat(dao): add OrderDAO for access gate system"
```

---

## Task 2: Extend UserDAO with update_access method

**Files:**
- Modify: `dao/user_dao.py`
- Test: `tests/unit/dao/test_user_dao_access.py`

**Step 1: Write the failing test**

Create `tests/unit/dao/test_user_dao_access.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for UserDAO access-related methods"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from bson import ObjectId


class TestUserDAOAccess:
    """Tests for UserDAO access methods"""

    @pytest.fixture
    def mock_collection(self):
        return MagicMock()

    @pytest.fixture
    def user_dao(self, mock_collection):
        with patch("dao.user_dao.MongoClient") as mock_client:
            mock_db = MagicMock()
            mock_db.get_collection.return_value = mock_collection
            mock_client.return_value.__getitem__.return_value = mock_db

            from dao.user_dao import UserDAO
            dao = UserDAO()
            dao.collection = mock_collection
            return dao

    @pytest.mark.unit
    def test_update_access_success(self, user_dao, mock_collection):
        """Should update user access fields"""
        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_collection.update_one.return_value = mock_result

        user_id = ObjectId()
        order_no = "ORD123456"
        expire_time = datetime.now() + timedelta(days=30)

        result = user_dao.update_access(user_id, order_no, expire_time)

        assert result is True
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"_id": user_id}
        update_set = call_args[0][1]["$set"]
        assert update_set["access.order_no"] == order_no
        assert update_set["access.expire_time"] == expire_time
        assert "access.granted_at" in update_set

    @pytest.mark.unit
    def test_update_access_user_not_found(self, user_dao, mock_collection):
        """Should return False when user not found"""
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_collection.update_one.return_value = mock_result

        user_id = ObjectId()
        result = user_dao.update_access(user_id, "ORD123", datetime.now())

        assert result is False
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && pytest tests/unit/dao/test_user_dao_access.py -v`

Expected: FAIL with `AttributeError: 'UserDAO' object has no attribute 'update_access'`

**Step 3: Write minimal implementation**

Add to `dao/user_dao.py` (after `upsert_user` method, around line 346):

```python
    def update_access(self, user_id: ObjectId, order_no: str, expire_time) -> bool:
        """
        更新用户访问授权

        Args:
            user_id: 用户 ObjectId
            order_no: 订单编号
            expire_time: 过期时间

        Returns:
            更新是否成功
        """
        from datetime import datetime

        result = self.collection.update_one(
            {"_id": user_id},
            {"$set": {
                "access.order_no": order_no,
                "access.granted_at": datetime.now(),
                "access.expire_time": expire_time
            }}
        )
        return result.modified_count > 0
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && pytest tests/unit/dao/test_user_dao_access.py -v`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate
git add dao/user_dao.py tests/unit/dao/test_user_dao_access.py
git commit -m "feat(dao): add update_access method to UserDAO"
```

---

## Task 3: Add access_control configuration

**Files:**
- Modify: `conf/config.json`

**Step 1: Add configuration**

Add `access_control` block to `conf/config.json` (after `langbot` section):

```json
    "access_control": {
        "enabled": false,
        "platforms": {
            "wechat": false,
            "langbot_telegram": false,
            "langbot_feishu": false
        },
        "deny_message": "[系统消息] 请发送有效订单编号开通服务",
        "expire_message": "[系统消息] 您的服务已过期，请发送新的订单编号续期",
        "success_message": "[系统消息] 验证成功，服务有效期至 {expire_time}"
    }
```

**Step 2: Verify config loads**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && python -c "from conf.config import CONF; print(CONF.get('access_control', {}).get('enabled'))"`

Expected: `False`

**Step 3: Commit**

```bash
cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate
git add conf/config.json
git commit -m "feat(config): add access_control configuration"
```

---

## Task 4: Create AccessGate module

**Files:**
- Create: `agent/runner/access_gate.py`
- Test: `tests/unit/runner/test_access_gate.py`

**Step 1: Write the failing test**

Create `tests/unit/runner/test_access_gate.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for AccessGate"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from bson import ObjectId


class TestAccessGate:
    """Tests for AccessGate class"""

    @pytest.fixture
    def mock_order_dao(self):
        return MagicMock()

    @pytest.fixture
    def mock_user_dao(self):
        return MagicMock()

    @pytest.fixture
    def access_config(self):
        return {
            "enabled": True,
            "platforms": {
                "wechat": False,
                "langbot_telegram": True,
            },
            "deny_message": "[系统消息] 请发送有效订单编号开通服务",
            "expire_message": "[系统消息] 您的服务已过期",
            "success_message": "[系统消息] 验证成功，有效期至 {expire_time}",
        }

    @pytest.fixture
    def access_gate(self, mock_order_dao, mock_user_dao, access_config):
        with patch("agent.runner.access_gate.CONF", {"access_control": access_config, "admin_user_id": "admin123"}):
            from agent.runner.access_gate import AccessGate
            gate = AccessGate()
            gate.order_dao = mock_order_dao
            gate.user_dao = mock_user_dao
            return gate

    @pytest.mark.unit
    def test_check_returns_none_when_disabled(self, access_config):
        """Should return None when access control is disabled"""
        access_config["enabled"] = False
        with patch("agent.runner.access_gate.CONF", {"access_control": access_config, "admin_user_id": ""}):
            from agent.runner.access_gate import AccessGate
            gate = AccessGate()

            result = gate.check(
                platform="langbot_telegram",
                user={"_id": ObjectId()},
                message="hello",
                admin_user_id=""
            )

            assert result is None

    @pytest.mark.unit
    def test_check_returns_none_for_disabled_platform(self, access_gate):
        """Should return None when platform has gate disabled"""
        result = access_gate.check(
            platform="wechat",
            user={"_id": ObjectId()},
            message="hello",
            admin_user_id=""
        )

        assert result is None

    @pytest.mark.unit
    def test_check_returns_none_for_admin(self, access_gate):
        """Should return None for admin user (exempt)"""
        admin_id = ObjectId()

        result = access_gate.check(
            platform="langbot_telegram",
            user={"_id": admin_id},
            message="hello",
            admin_user_id=str(admin_id)
        )

        assert result is None

    @pytest.mark.unit
    def test_check_returns_none_for_valid_access(self, access_gate):
        """Should return None when user has valid access"""
        future_time = datetime.now() + timedelta(days=30)
        user = {
            "_id": ObjectId(),
            "access": {
                "order_no": "ORD123",
                "expire_time": future_time
            }
        }

        result = access_gate.check(
            platform="langbot_telegram",
            user=user,
            message="hello",
            admin_user_id=""
        )

        assert result is None

    @pytest.mark.unit
    def test_check_returns_denied_for_new_user(self, access_gate, mock_order_dao):
        """Should return gate_denied for user without access"""
        mock_order_dao.find_available_order.return_value = None
        user = {"_id": ObjectId()}

        result = access_gate.check(
            platform="langbot_telegram",
            user=user,
            message="hello",
            admin_user_id=""
        )

        assert result == ("gate_denied", None)

    @pytest.mark.unit
    def test_check_returns_expired_for_expired_access(self, access_gate, mock_order_dao):
        """Should return gate_expired when access has expired"""
        mock_order_dao.find_available_order.return_value = None
        past_time = datetime.now() - timedelta(days=1)
        user = {
            "_id": ObjectId(),
            "access": {
                "order_no": "ORD123",
                "expire_time": past_time
            }
        }

        result = access_gate.check(
            platform="langbot_telegram",
            user=user,
            message="hello",
            admin_user_id=""
        )

        assert result == ("gate_expired", None)

    @pytest.mark.unit
    def test_check_binds_order_on_valid_order_message(self, access_gate, mock_order_dao, mock_user_dao):
        """Should bind order and return success when message matches valid order"""
        future_time = datetime.now() + timedelta(days=30)
        order = {
            "_id": ObjectId(),
            "order_no": "ORD123456",
            "expire_time": future_time,
            "bound_user_id": None
        }
        mock_order_dao.find_available_order.return_value = order
        mock_order_dao.bind_to_user.return_value = True
        mock_user_dao.update_access.return_value = True

        user_id = ObjectId()
        user = {"_id": user_id}

        result = access_gate.check(
            platform="langbot_telegram",
            user=user,
            message="ORD123456",
            admin_user_id=""
        )

        assert result[0] == "gate_success"
        assert result[1]["expire_time"] == future_time
        mock_order_dao.bind_to_user.assert_called_once_with("ORD123456", user_id)
        mock_user_dao.update_access.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && pytest tests/unit/runner/test_access_gate.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.runner.access_gate'`

**Step 3: Write minimal implementation**

Create `agent/runner/access_gate.py`:

```python
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
                "deny_message",
                "[系统消息] 请发送有效订单编号开通服务"
            )
        elif gate_type == "gate_expired":
            return self.config.get(
                "expire_message",
                "[系统消息] 您的服务已过期，请发送新的订单编号续期"
            )
        elif gate_type == "gate_success":
            msg = self.config.get(
                "success_message",
                "[系统消息] 验证成功，服务有效期至 {expire_time}"
            )
            if expire_time:
                return msg.format(expire_time=expire_time.strftime("%Y-%m-%d %H:%M"))
            return msg
        return ""

    def close(self):
        """关闭连接"""
        self.order_dao.close()
        self.user_dao.close()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && pytest tests/unit/runner/test_access_gate.py -v`

Expected: PASS (8 tests)

**Step 5: Commit**

```bash
cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate
git add agent/runner/access_gate.py tests/unit/runner/test_access_gate.py
git commit -m "feat(runner): add AccessGate module for access control"
```

---

## Task 5: Integrate AccessGate into MessageDispatcher

**Files:**
- Modify: `agent/runner/message_processor.py:360-407`
- Test: `tests/unit/runner/test_message_dispatcher_gate.py`

**Step 1: Write the failing test**

Create `tests/unit/runner/test_message_dispatcher_gate.py`:

```python
# -*- coding: utf-8 -*-
"""Unit tests for MessageDispatcher access gate integration"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from bson import ObjectId


class TestMessageDispatcherGate:
    """Tests for MessageDispatcher with access gate"""

    @pytest.fixture
    def mock_access_gate(self):
        return MagicMock()

    @pytest.fixture
    def msg_ctx(self):
        """Create a mock MessageContext"""
        ctx = MagicMock()
        ctx.context = {
            "user": {"_id": ObjectId()},
            "platform": "langbot_telegram",
            "relation": {
                "relationship": {"dislike": 0},
                "character_info": {"status": "空闲"}
            }
        }
        ctx.input_messages = [{"message": "hello"}]
        return ctx

    @pytest.mark.unit
    def test_dispatch_calls_access_gate(self, msg_ctx, mock_access_gate):
        """Should call access gate check in dispatch"""
        mock_access_gate.check.return_value = None

        with patch("agent.runner.message_processor.AccessGate", return_value=mock_access_gate):
            from agent.runner.message_processor import MessageDispatcher
            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate

            result = dispatcher.dispatch(msg_ctx)

            mock_access_gate.check.assert_called_once()
            assert result == ("normal", None)

    @pytest.mark.unit
    def test_dispatch_returns_gate_denied(self, msg_ctx, mock_access_gate):
        """Should return gate_denied when access gate denies"""
        mock_access_gate.check.return_value = ("gate_denied", None)

        with patch("agent.runner.message_processor.AccessGate", return_value=mock_access_gate):
            from agent.runner.message_processor import MessageDispatcher
            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate

            result = dispatcher.dispatch(msg_ctx)

            assert result == ("gate_denied", None)

    @pytest.mark.unit
    def test_dispatch_returns_gate_success(self, msg_ctx, mock_access_gate):
        """Should return gate_success when order verification succeeds"""
        expire_time = datetime.now() + timedelta(days=30)
        mock_access_gate.check.return_value = ("gate_success", {"expire_time": expire_time})

        with patch("agent.runner.message_processor.AccessGate", return_value=mock_access_gate):
            from agent.runner.message_processor import MessageDispatcher
            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate

            result = dispatcher.dispatch(msg_ctx)

            assert result[0] == "gate_success"
            assert result[1]["expire_time"] == expire_time

    @pytest.mark.unit
    def test_dispatch_blocked_takes_priority(self, msg_ctx, mock_access_gate):
        """Blacklist check should run before access gate"""
        msg_ctx.context["relation"]["relationship"]["dislike"] = 100
        mock_access_gate.check.return_value = None

        with patch("agent.runner.message_processor.AccessGate", return_value=mock_access_gate):
            from agent.runner.message_processor import MessageDispatcher
            dispatcher = MessageDispatcher("test")
            dispatcher.access_gate = mock_access_gate

            result = dispatcher.dispatch(msg_ctx)

            assert result == ("blocked", None)
            mock_access_gate.check.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && pytest tests/unit/runner/test_message_dispatcher_gate.py -v`

Expected: FAIL (access gate not integrated yet)

**Step 3: Modify MessageDispatcher**

Edit `agent/runner/message_processor.py`:

1. Add import at top (around line 30):
```python
from agent.runner.access_gate import AccessGate
```

2. Modify `MessageDispatcher.__init__` (around line 373-375):
```python
    def __init__(self, worker_tag: str):
        self.worker_tag = worker_tag
        self.admin_user_id = CONF.get("admin_user_id", "")
        self.access_gate = AccessGate()
```

3. Modify `MessageDispatcher.dispatch` method (lines 377-406), insert gate check after blacklist:
```python
    def dispatch(self, msg_ctx: MessageContext) -> Tuple[str, Optional[Dict]]:
        """
        分发消息到对应处理器

        Returns:
            (dispatch_type, extra_data)
           -("blocked", None): 用户被拉黑
           -("gate_denied", None): 门禁未通过
           -("gate_expired", None): 门禁已过期
           -("gate_success", {"expire_time": ...}): 门禁验证成功
           -("hardcode", {"command": ...}): 硬指令
           -("hold", None): 角色繁忙
           -("normal", None): 正常消息
        """
        context = msg_ctx.context
        input_messages = msg_ctx.input_messages

        # 检查拉黑
        if context["relation"]["relationship"]["dislike"] >= 100:
            return ("blocked", None)

        # 检查门禁
        gate_result = self.access_gate.check(
            platform=context.get("platform", ""),
            user=context["user"],
            message=str(input_messages[0].get("message", "")),
            admin_user_id=self.admin_user_id,
        )
        if gate_result:
            return gate_result

        # 检查硬指令
        if str(context["user"]["_id"]) == self.admin_user_id and str(
            input_messages[0]["message"]
        ).startswith(self.SUPPORTED_HARDCODE):
            return ("hardcode", {"command": input_messages[0]["message"]})

        # 检查繁忙状态
        if context["relation"]["character_info"].get("status", "空闲") not in ["空闲"]:
            logger.info(f"{self.worker_tag} hold message as character busy...")
            return ("hold", None)

        return ("normal", None)
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && source .venv/bin/activate && pytest tests/unit/runner/test_message_dispatcher_gate.py -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate
git add agent/runner/message_processor.py tests/unit/runner/test_message_dispatcher_gate.py
git commit -m "feat(runner): integrate AccessGate into MessageDispatcher"
```

---

## Task 6: Handle gate responses in agent_handler

**Files:**
- Modify: `agent/runner/agent_handler.py`
- Reference: Check how `blocked` status is handled

**Step 1: Find blocked handling pattern**

Run: `cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate && grep -n "blocked" agent/runner/agent_handler.py | head -20`

**Step 2: Add gate response handling**

Locate where `dispatch_type == "blocked"` is handled and add similar handling for gate types.

The pattern should be:
```python
elif dispatch_type == "gate_denied":
    gate_msg = self.access_gate.get_message("gate_denied")
    await self._send_system_message(msg_ctx, gate_msg)
    self.finalizer.finalize_blocked(msg_ctx)  # Reuse blocked finalizer

elif dispatch_type == "gate_expired":
    gate_msg = self.access_gate.get_message("gate_expired")
    await self._send_system_message(msg_ctx, gate_msg)
    self.finalizer.finalize_blocked(msg_ctx)

elif dispatch_type == "gate_success":
    expire_time = dispatch_data.get("expire_time")
    gate_msg = self.access_gate.get_message("gate_success", expire_time)
    await self._send_system_message(msg_ctx, gate_msg)
    # Continue to normal processing - don't return, let it fall through
```

**Step 3: Commit**

```bash
cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate
git add agent/runner/agent_handler.py
git commit -m "feat(runner): handle gate responses in agent_handler"
```

---

## Task 7: Run full test suite and format

**Step 1: Run formatter**

```bash
cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate
source .venv/bin/activate
black . && isort .
```

**Step 2: Run unit tests**

```bash
pytest -m unit -v
```

Expected: All unit tests pass

**Step 3: Commit formatting changes**

```bash
git add -A
git commit -m "style: format code with black and isort"
```

---

## Task 8: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add access control section**

Add under "### MongoDB Collections":

```markdown
### Access Control (Gate System)

**Configuration (conf/config.json):**
```json
"access_control": {
    "enabled": false,
    "platforms": {
        "wechat": false,
        "langbot_telegram": true,
        "langbot_feishu": true
    },
    "deny_message": "[系统消息] 请发送有效订单编号开通服务",
    "expire_message": "[系统消息] 您的服务已过期，请发送新的订单编号续期",
    "success_message": "[系统消息] 验证成功，服务有效期至 {expire_time}"
}
```

**How it works:**
- Platform-agnostic: each platform can independently enable/disable gate
- Users must send valid order number to gain access
- Orders stored in `orders` collection, bound 1:1 to users
- User access state stored in `users.access` field
- Admin user (configured via `admin_user_id`) is exempt
```

**Step 2: Commit**

```bash
cd /home/ydyk/workspace/active-projects/coke/.worktrees/access-gate
git add CLAUDE.md
git commit -m "docs: add access control system documentation"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create OrderDAO | `dao/order_dao.py`, `tests/unit/dao/test_order_dao.py` |
| 2 | Extend UserDAO | `dao/user_dao.py`, `tests/unit/dao/test_user_dao_access.py` |
| 3 | Add config | `conf/config.json` |
| 4 | Create AccessGate | `agent/runner/access_gate.py`, `tests/unit/runner/test_access_gate.py` |
| 5 | Integrate into dispatcher | `agent/runner/message_processor.py`, `tests/unit/runner/test_message_dispatcher_gate.py` |
| 6 | Handle in agent_handler | `agent/runner/agent_handler.py` |
| 7 | Format and test | - |
| 8 | Update docs | `CLAUDE.md` |
