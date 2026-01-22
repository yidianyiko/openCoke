# Reminder V2 系统设计

> **状态**: 已评审
> **日期**: 2026-01-22
> **作者**: Claude + 用户协作

## 执行摘要

基于苏格拉底式对话分析，设计全新的提醒系统 V2：
- **全新架构**：Tool → Service → DAO 三层分离
- **iCal 标准**：RRULE 周期规则，ISO 8601 时间格式
- **APScheduler**：替代轮询调度器
- **并行运行**：V1/V2 独立，无需兼容

---

## 第一部分：需求分析

### 核心场景

| 场景 | 示例 | 支持 |
|------|------|------|
| 单次定时提醒 | "明天 9 点提醒我开会" | ✅ |
| 周期提醒 | "每天 9 点提醒我喝水" | ✅ |
| 时间窗口周期 | "工作日 9-18 点每小时提醒" | ✅ |
| GTD 快速收集 | "记一下要买牛奶"（无时间） | ✅ |
| 截止日提醒 | "周五前完成报告，提前 1 天提醒" | ✅ |
| 日历导入 | 读取外部日历生成提醒 | ✅ |

### 设计决策

| 维度 | 决策 |
|------|------|
| 日历同步 | 仅导入（单向） |
| 截止日 | 硬截止 + 多个提前提醒点 |
| 时区 | 用户级配置 |
| 周期复杂度 | 完整 RRULE 能力 |
| 状态 | 3 状态：active/triggered/completed |
| GTD 分类 | 仅 inbox |
| 来源追踪 | 不追踪 |
| 时间格式 | ISO 8601 带时区 |
| ID 设计 | 仅 `_id`（移除 reminder_id） |

---

## 第二部分：数据结构

### 目标结构

```typescript
interface CokeReminderV2 {
  // === 标识 ===
  _id: ObjectId;
  user_id: string;
  conversation_id: string;       // 必须：私聊/群聊会话
  character_id: string;          // 保留：避免额外查询

  // === 内容 ===
  title: string;
  list_id: string;               // GTD: "inbox" 默认

  // === 时间规则（iCal 风格）===
  dtstart: string | null;        // ISO 8601 开始/触发时间
  dtend: string | null;          // ISO 8601 截止时间
  rrule: string | null;          // 重复规则
  alarms: string[] | null;       // 提前提醒 ["PT1H", "P1D"]

  // === 状态 ===
  status: string;                // active/triggered/completed
  triggered_count: number;

  // === 元数据 ===
  created_at: string;            // ISO 8601
  updated_at: string;            // ISO 8601
}
```

**集合名：** `reminders_v2`

**字段数：** 13 个（不含 _id）

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `_id` | ObjectId | 自动 | MongoDB 主键 |
| `user_id` | string | ✅ | 提醒所属用户 |
| `conversation_id` | string | ✅ | 发送目标会话（支持群聊） |
| `character_id` | string | ✅ | 发送角色 |
| `title` | string | ✅ | 提醒内容 |
| `list_id` | string | ✅ | GTD 列表，默认 "inbox" |
| `dtstart` | string \| null | - | 开始/触发时间，ISO 8601 |
| `dtend` | string \| null | - | 截止时间，ISO 8601 |
| `rrule` | string \| null | - | iCal RRULE 周期规则 |
| `alarms` | string[] \| null | - | 提前提醒，ISO 8601 Duration |
| `status` | string | ✅ | active/triggered/completed |
| `triggered_count` | number | ✅ | 触发次数，默认 0 |
| `created_at` | string | ✅ | 创建时间，ISO 8601 |
| `updated_at` | string | ✅ | 更新时间，ISO 8601 |

### 索引设计

```javascript
db.reminders_v2.createIndex({ "user_id": 1, "status": 1 })
db.reminders_v2.createIndex({ "conversation_id": 1 })
db.reminders_v2.createIndex({ "list_id": 1, "user_id": 1, "status": 1 })
db.reminders_v2.createIndex({ "status": 1, "dtstart": 1 })  // 过渡期
```

---

## 第三部分：RRULE 规范

### 格式说明

使用 iCal RRULE 标准（RFC 5545），不带 `RRULE:` 前缀。

### 常见示例

| 用户需求 | rrule 值 |
|----------|----------|
| 单次提醒 | `null` |
| 每天 | `FREQ=DAILY` |
| 每周一 | `FREQ=WEEKLY;BYDAY=MO` |
| 工作日 | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR` |
| 每小时 | `FREQ=HOURLY` |
| 9-18点每小时 | `FREQ=HOURLY;BYHOUR=9,10,11,12,13,14,15,16,17,18` |
| 工作日9-18点每小时 | `FREQ=HOURLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9,10,11,12,13,14,15,16,17,18` |
| 每月1号 | `FREQ=MONTHLY;BYMONTHDAY=1` |
| 每月第2个周三 | `FREQ=MONTHLY;BYDAY=2WE` |
| 每月最后一天 | `FREQ=MONTHLY;BYMONTHDAY=-1` |
| 共10次后停止 | `FREQ=DAILY;COUNT=10` |
| 到12月31日 | `FREQ=DAILY;UNTIL=20261231T235959Z` |

### 提前提醒格式

使用 ISO 8601 Duration 格式：

| 含义 | 格式 |
|------|------|
| 提前 10 分钟 | `PT10M` |
| 提前 1 小时 | `PT1H` |
| 提前 1 天 | `P1D` |
| 提前 1 周 | `P1W` |

示例：`alarms: ["P1D", "PT1H"]` = 提前 1 天和 1 小时各提醒一次

### 解析库

Python: `python-dateutil` 的 `rrulestr()`

```python
from dateutil.rrule import rrulestr
rule = rrulestr("FREQ=DAILY;BYHOUR=9", dtstart=datetime.now())
next_time = rule.after(datetime.now())
```

---

## 第四部分：系统架构

### 架构图

```
┌─────────────────────────────────────────────────────────┐
│                      新系统 (V2)                         │
├─────────────────────────────────────────────────────────┤
│  Tool 层        │  reminder_tools_v2.py (<500行)        │
│  Service 层     │  reminder_service.py (业务逻辑)       │
│  DAO 层         │  reminder_dao_v2.py (纯 CRUD)         │
│  调度层         │  APScheduler (Job Store: MongoDB)     │
│  数据层         │  reminders_v2 集合                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                      旧系统 (V1) - 并行运行              │
├─────────────────────────────────────────────────────────┤
│  reminder_tools.py (3000行)                             │
│  reminder_dao.py                                        │
│  轮询调度器 (agent_background_handler.py)               │
│  reminders 集合                                          │
└─────────────────────────────────────────────────────────┘
```

### 文件结构

```
agent/agno_agent/
├── tools/
│   ├── reminder_tools.py        # V1（保留，并行运行）
│   └── reminder_tools_v2.py     # V2（新，<500行）
│
├── services/                    # 新目录
│   └── reminder_service.py      # 新增（无 V1）

dao/
├── reminder_dao.py              # V1（保留）
└── reminder_dao_v2.py           # V2（新）

agent/runner/
├── agent_background_handler.py  # V1 轮询调度器（保留）
└── reminder_scheduler.py        # V2 APScheduler（新）
```

### 命名约定

- 仅与 V1 对应的文件加 `_v2` 后缀
- 新增文件（如 Service 层）不加后缀

---

## 第五部分：层级设计

### DAO 层

```python
# dao/reminder_dao_v2.py

class ReminderDAOV2:
    """V2 数据访问层 - 纯 CRUD"""

    COLLECTION = "reminders_v2"

    def create(self, doc: dict) -> str:
        """插入文档，返回 str(_id)"""

    def get_by_id(self, reminder_id: str) -> dict | None:
        """按 _id 获取"""

    def update(self, reminder_id: str, updates: dict) -> bool:
        """更新文档"""

    def delete(self, reminder_id: str) -> bool:
        """删除文档"""

    def find_by_user(
        self,
        user_id: str,
        status: str | None = None,
        list_id: str | None = None,
    ) -> list[dict]:
        """按用户查询"""

    def find_by_conversation(self, conversation_id: str) -> list[dict]:
        """按会话查询"""
```

### Service 层

```python
# agent/agno_agent/services/reminder_service.py

class ReminderService:
    """业务逻辑层"""

    def __init__(self, dao: ReminderDAOV2, scheduler: ReminderScheduler):
        self.dao = dao
        self.scheduler = scheduler

    # === 核心操作 ===

    async def create(
        self,
        user_id: str,
        conversation_id: str,
        character_id: str,
        title: str,
        dtstart: str | None = None,
        dtend: str | None = None,
        rrule: str | None = None,
        alarms: list[str] | None = None,
        list_id: str = "inbox",
    ) -> str:
        """创建提醒"""
        # 1. 构建文档
        # 2. 写入 MongoDB
        # 3. 注册到 APScheduler
        # 4. 返回 ID

    async def complete(self, reminder_id: str) -> bool:
        """标记完成"""

    async def delete(self, reminder_id: str) -> bool:
        """删除提醒"""

    async def update(self, reminder_id: str, updates: dict) -> bool:
        """更新提醒"""

    # === 查询 ===

    async def list_by_user(
        self,
        user_id: str,
        status: str | None = None,
        list_id: str | None = None,
    ) -> list[dict]:
        """获取用户提醒列表"""

    # === 工具方法 ===

    def build_rrule(self, freq: str, **kwargs) -> str:
        """构建 RRULE 字符串"""

    def parse_alarms(self, alarm_str: str) -> list[str]:
        """解析提前提醒 "1天,1小时" -> ["P1D", "PT1H"]"""
```

### Tool 层

```python
# agent/agno_agent/tools/reminder_tools_v2.py

@tool
def reminder_tool_v2(
    action: str,           # create/update/delete/filter/complete
    title: str = None,
    trigger_time: str = None,
    # ... 其他参数
    session_state: dict = None,
) -> dict:
    """
    V2 提醒工具

    保持单工具 + action 模式（LLM 已适应）
    内部调用 ReminderService
    """
    service = get_reminder_service()

    if action == "create":
        return await service.create(...)
    elif action == "filter":
        return await service.list_by_user(...)
    elif action == "complete":
        return await service.complete(...)
    elif action == "delete":
        return await service.delete(...)
    elif action == "update":
        return await service.update(...)
```

**Tool 层职责：**
- 参数解析和校验
- Session state 处理
- 调用 Service
- 格式化返回结果

**目标：<500 行**

### 调度层

```python
# agent/runner/reminder_scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore

class ReminderScheduler:
    """APScheduler 调度管理"""

    def __init__(self, mongo_client):
        jobstores = {
            'default': MongoDBJobStore(
                database='coke',
                collection='apscheduler_jobs',
                client=mongo_client
            )
        }
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)

    def start(self):
        """启动调度器"""
        self.scheduler.start()

    async def schedule_reminder(
        self,
        reminder_id: str,
        trigger_time: datetime,
    ):
        """添加单次触发任务"""
        self.scheduler.add_job(
            func=self.execute_reminder,
            trigger='date',
            run_date=trigger_time,
            id=f"reminder_{reminder_id}",
            args=[reminder_id],
            replace_existing=True,
        )

    async def schedule_recurring(
        self,
        reminder_id: str,
        dtstart: datetime,
        rrule: str,
    ):
        """添加周期任务"""
        # 使用 dateutil 解析 rrule
        # 计算下次触发时间
        # 添加到调度器

    async def cancel(self, reminder_id: str):
        """取消调度"""
        job_id = f"reminder_{reminder_id}"
        self.scheduler.remove_job(job_id)

    async def execute_reminder(self, reminder_id: str):
        """触发时执行"""
        # 1. 从 reminders_v2 获取提醒
        # 2. 获取会话和角色信息
        # 3. 发送消息
        # 4. 更新状态/计数
        # 5. 如果是周期提醒，计算并注册下次触发
```

---

## 第六部分：实施计划

### 阶段划分

| 阶段 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| **Phase 1** | DAO V2 + 数据结构 | `reminder_dao_v2.py` | 无 |
| **Phase 2** | Service 层 | `reminder_service.py` | Phase 1 |
| **Phase 3** | APScheduler 集成 | `reminder_scheduler.py` | Phase 2 |
| **Phase 4** | Tool V2 | `reminder_tools_v2.py` | Phase 2, 3 |
| **Phase 5** | 切换流量到 V2 | Agent 配置 | Phase 4 |
| **Phase 6** | 下线 V1（可选） | 清理代码 | Phase 5 稳定后 |

### 成功标准

| 标准 | 验收条件 |
|------|----------|
| **可维护性** | `reminder_tools_v2.py` < 500 行 |
| **标准化** | 周期提醒使用 RFC 5545 RRULE 格式 |
| **稳定性** | 所有 E2E 测试通过 |
| **性能** | APScheduler 触发延迟 < 5 秒 |

---

## 第七部分：与 V1 对比

### 移除的字段

| 字段 | 移除原因 |
|------|----------|
| `reminder_id` | 冗余，统一用 `_id` |
| `action_template` | 运行时生成 |
| `next_trigger_time` | APScheduler 管理 |
| `time_original` | 无用 |
| `timezone` | 合并到 ISO 8601 |
| `recurrence` | 用 `rrule` 替代 |
| `time_period` | 合并到 rrule BYHOUR |
| `period_state` | 无用 |
| `last_triggered_at` | 不需要 |

### 新增的字段

| 字段 | 用途 |
|------|------|
| `list_id` | GTD 列表支持 |
| `dtstart` | ISO 8601 开始时间 |
| `dtend` | ISO 8601 截止时间 |
| `rrule` | iCal 周期规则 |
| `alarms` | 提前提醒数组 |

### 架构变化

| 维度 | V1 | V2 |
|------|-----|-----|
| 代码行数 | 3000+ 行 | <500 行 |
| 分层 | Tool + DAO | Tool + Service + DAO |
| 调度器 | 轮询 | APScheduler |
| 时间格式 | Unix 时间戳 | ISO 8601 |
| 周期格式 | 自定义对象 | iCal RRULE |

---

## 附录：相关文件

**新系统文件（待创建）：**
- `dao/reminder_dao_v2.py`
- `agent/agno_agent/services/reminder_service.py`
- `agent/agno_agent/tools/reminder_tools_v2.py`
- `agent/runner/reminder_scheduler.py`

**旧系统文件（保留并行）：**
- `dao/reminder_dao.py`
- `agent/agno_agent/tools/reminder_tools.py`
- `agent/runner/agent_background_handler.py`

**相关文档：**
- `doc/plans/2026-01-22-gtd-task-system-p0.md` - GTD P0（已实施）
- `doc/plans/gtd-p1-roadmap.md` - GTD P1 路线图
