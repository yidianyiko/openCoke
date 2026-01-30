# 门禁系统设计文档

## 概述

为非微信平台设计的访问控制系统，用户需发送有效订单编号才能使用服务。系统与平台解耦，通过配置决定各平台是否启用门禁。

## 需求摘要

- 平台无关，通过 `config.json` 配置各平台是否启用
- 仅支持订单编号验证
- 本地 MongoDB 存储订单，后续外部同步
- 一对一绑定：一个订单号只能绑定一个用户
- 有效期跟随订单（订单表存储过期时间）
- 未验证用户返回固定提示语
- 任意消息自动匹配：直接查数据库验证

## 整体架构

```
用户消息 → Connector → 门禁检查点 → 正常流程
                            ↓
                      [未验证?]
                            ↓
                    尝试订单匹配 → 匹配成功 → 绑定用户 → 正常流程
                            ↓
                       匹配失败
                            ↓
                    返回固定提示语
```

**核心设计思路：**

1. **检查点位置**：在 `MessageDispatcher.dispatch()` 中，与现有的黑名单检查同层级
2. **平台配置**：`config.json` 中配置各平台是否启用门禁
3. **新增 MongoDB 集合**：`orders` 存储订单信息
4. **验证逻辑**：未通过门禁的消息，先尝试作为订单号查询，匹配则绑定并放行

## 数据模型

### 订单集合 `orders`

```python
{
    "_id": ObjectId("..."),
    "order_no": "ORD20240101001",      # 订单编号，唯一索引
    "expire_time": datetime(...),       # 过期时间
    "bound_user_id": ObjectId(...),     # 已绑定的用户ID，null表示未绑定
    "bound_at": datetime(...),          # 绑定时间
    "created_at": datetime(...),        # 订单创建时间
    "metadata": {}                      # 预留扩展字段（来源、备注等）
}
```

### 用户集合 `users` 扩展

在现有用户文档中增加字段：

```python
{
    # ... 现有字段 ...
    "access": {
        "order_no": "ORD20240101001",   # 绑定的订单号
        "granted_at": datetime(...),     # 授权时间
        "expire_time": datetime(...)     # 过期时间（冗余存储，便于查询）
    }
}
```

### 设计考量

- **订单表独立**：便于后续外部同步，与用户表解耦
- **双向关联**：订单记录绑定用户，用户记录绑定订单，查询灵活
- **过期时间冗余**：用户表冗余存储过期时间，避免每次联表查询

## 配置结构

### config.json 新增配置

```json
{
    "access_control": {
        "enabled": true,
        "platforms": {
            "wechat": false,
            "langbot_telegram": true,
            "langbot_feishu": true
        },
        "deny_message": "[系统消息] 请发送有效订单编号开通服务",
        "expire_message": "[系统消息] 您的服务已过期，请发送新的订单编号续期",
        "success_message": "[系统消息] 验证成功，服务有效期至 {expire_time}"
    }
}
```

### 配置说明

| 字段 | 说明 |
|------|------|
| `enabled` | 全局开关，false 时所有平台不启用门禁 |
| `platforms` | 各平台独立开关，true 启用门禁 |
| `deny_message` | 未验证用户收到的提示 |
| `expire_message` | 过期用户收到的提示 |
| `success_message` | 验证成功提示，`{expire_time}` 为占位符 |

### 判断逻辑

```python
def is_gate_enabled(platform: str) -> bool:
    config = get_config()["access_control"]
    if not config["enabled"]:
        return False
    return config["platforms"].get(platform, False)
```

## 验证流程

### 在 MessageDispatcher.dispatch() 中的位置

```python
def dispatch(self, msg_ctx: MessageContext) -> Tuple[str, Optional[Dict]]:
    context = msg_ctx.context

    # 1. 黑名单检查（现有逻辑）
    if context["relation"]["relationship"]["dislike"] >= 100:
        return ("blocked", None)

    # 2. 门禁检查（新增）
    gate_result = self._check_access_gate(msg_ctx)
    if gate_result:
        return gate_result

    # 3. 管理员命令检查（现有逻辑）
    # ... 后续现有逻辑 ...
```

### 门禁检查核心逻辑

```python
def _check_access_gate(self, msg_ctx: MessageContext) -> Optional[Tuple[str, Dict]]:
    platform = msg_ctx.context["platform"]

    # 0. 管理员豁免
    if str(msg_ctx.context["user"]["_id"]) == self.admin_user_id:
        return None

    # 1. 该平台是否启用门禁
    if not is_gate_enabled(platform):
        return None  # 不启用，直接放行

    user = msg_ctx.context["user"]
    message = msg_ctx.input_messages[0]["message"]

    # 2. 用户是否已有有效授权
    access = user.get("access")
    if access and access["expire_time"] > datetime.now():
        return None  # 有效授权，放行

    # 3. 尝试将消息作为订单号匹配
    order = self.order_dao.find_available_order(message.strip())
    if order:
        # 绑定订单到用户
        self._bind_order_to_user(order, user)
        return ("gate_success", {"expire_time": order["expire_time"]})

    # 4. 匹配失败，返回对应提示
    if access:  # 曾有授权但已过期
        return ("gate_expired", None)
    else:  # 从未授权
        return ("gate_denied", None)
```

### 返回状态处理

| 状态 | 行为 |
|------|------|
| `gate_denied` | 发送 `deny_message`，不进入 AI 流程 |
| `gate_expired` | 发送 `expire_message`，不进入 AI 流程 |
| `gate_success` | 发送 `success_message`，继续正常流程 |

## DAO 层设计

### 新增文件

```
dao/
  └── order_dao.py          # 订单数据访问层

agent/runner/
  └── access_gate.py        # 门禁检查逻辑封装
```

### OrderDAO 核心方法

```python
class OrderDAO:
    def __init__(self, db):
        self.collection = db["orders"]

    def find_available_order(self, order_no: str) -> Optional[Dict]:
        """查找可用订单：存在、未绑定、未过期"""
        return self.collection.find_one({
            "order_no": order_no,
            "bound_user_id": None,
            "expire_time": {"$gt": datetime.now()}
        })

    def bind_to_user(self, order_no: str, user_id: ObjectId) -> bool:
        """绑定订单到用户（原子操作）"""
        result = self.collection.update_one(
            {"order_no": order_no, "bound_user_id": None},
            {"$set": {"bound_user_id": user_id, "bound_at": datetime.now()}}
        )
        return result.modified_count > 0

    def get_by_order_no(self, order_no: str) -> Optional[Dict]:
        """根据订单号查询"""
        return self.collection.find_one({"order_no": order_no})
```

### UserDAO 扩展方法

```python
# 在现有 user_dao.py 中新增
def update_access(self, user_id: ObjectId, order_no: str, expire_time: datetime):
    """更新用户访问授权"""
    return self.collection.update_one(
        {"_id": user_id},
        {"$set": {
            "access.order_no": order_no,
            "access.granted_at": datetime.now(),
            "access.expire_time": expire_time
        }}
    )
```

### 索引设计

```python
# orders 集合索引
orders.create_index("order_no", unique=True)
orders.create_index("bound_user_id")
orders.create_index("expire_time")

# users 集合索引（可选，加速过期查询）
users.create_index("access.expire_time")
```

## 边界情况与错误处理

### 并发绑定竞争

**场景**：两个用户同时发送同一个订单号

**解决方案**：使用 MongoDB 原子操作，`update_one` 的条件包含 `bound_user_id: None`，只有一个能成功

```python
result = collection.update_one(
    {"order_no": order_no, "bound_user_id": None},
    {"$set": {"bound_user_id": user_id, ...}}
)
if result.modified_count == 0:
    # 已被其他用户绑定
    return None
```

### 用户跨平台场景

**场景**：用户在 Telegram 验证通过，后来又用微信联系

**处理**：授权绑定在用户级别，不在平台级别。同一用户（通过 `users` 表的多平台关联）共享授权状态

### 订单过期后重新验证

**场景**：用户订单过期，发送新订单号续期

**处理**：正常流程，新订单绑定后覆盖用户的 `access` 字段

### 管理员豁免

管理员（`admin_user_id`）自动豁免门禁检查

## 实现清单

### 需要修改的现有文件

| 文件 | 修改内容 |
|------|----------|
| `conf/config.json` | 新增 `access_control` 配置块 |
| `dao/user_dao.py` | 新增 `update_access()` 方法 |
| `agent/runner/message_processor.py` | 在 `dispatch()` 中集成门禁检查 |

### 需要新增的文件

| 文件 | 内容 |
|------|------|
| `dao/order_dao.py` | 订单数据访问层 |
| `agent/runner/access_gate.py` | 门禁检查逻辑封装 |

### 数据库变更

| 操作 | 说明 |
|------|------|
| 创建 `orders` 集合 | 存储订单数据 |
| 创建索引 | `order_no` 唯一索引等 |
| `users` 集合扩展 | 新增 `access` 字段（无需迁移，字段不存在视为未授权） |

### 不在本次实现范围（YAGNI）

- 订单导入脚本（后续单独开发）
- 管理后台界面
- 订单统计/报表
- 多订单绑定支持
