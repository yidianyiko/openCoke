# Reminder V2 迁移方案

## 1. 背景与目标

### 1.1 当前问题

| 问题 | 描述 |
|------|------|
| 字段冗余 | `_id` + `reminder_id`、`title` + `action_template` 重复 |
| 格式不标准 | Unix 时间戳，自定义 recurrence 对象 |
| 状态复杂 | 5 种状态 (pending/confirmed/triggered/completed/cancelled) |
| time_period 复杂 | 自定义时间窗口逻辑，增加系统复杂度 |
| Tool 功能不完整 | 缺少截止日、提前提醒等功能 |

### 1.2 目标

- 采用 **iCal RRULE** 标准格式处理周期提醒
- 采用 **ISO 8601** 时间格式
- 用 **BYHOUR/BYMINUTE** 替代 time_period
- 简化状态为 **2 种** (0=Normal, 2=Completed)
- 新增 **截止日 + 提前提醒** 功能
- 重新设计 Tool 层接口

---

## 2. 数据结构设计

### 2.1 新数据结构

```typescript
interface CokeReminder {
  // === Identity ===
  _id: ObjectId;                     // MongoDB 自动生成，业务直接使用
  user_id: string;
  conversation_id: string;
  character_id: string;

  // === Content ===
  title: string;                     // "开会", "喝水"

  // === Time ===
  start_date: string;                // ISO 8601: "2025-01-01T09:00:00+08:00"
  due_date?: string;                 // 可选截止日
  reminders?: string[];              // 提前提醒: ["TRIGGER:-PT1H", "TRIGGER:-PT10M"]
  timezone: string;                  // "Asia/Shanghai"

  // === Recurrence ===
  repeat_flag?: string;              // iCal RRULE (含 BYHOUR/BYMINUTE)

  // === Status ===
  status: number;                    // 0=Normal, 2=Completed
  triggered_count: number;

  // === Metadata ===
  created_at: string;                // ISO 8601
  updated_at: string;                // ISO 8601
}
```

### 2.2 字段映射（旧 → 新）

| 旧字段 | 新字段 | 变化说明 |
|--------|--------|----------|
| `_id` | `_id` | 保留 |
| `reminder_id` | ❌ | 移除，统一用 `_id` |
| `user_id` | `user_id` | 保留 |
| `conversation_id` | `conversation_id` | 保留 |
| `character_id` | `character_id` | 保留 |
| `title` | `title` | 保留 |
| `action_template` | ❌ | 移除，运行时生成 |
| `next_trigger_time` | `start_date` | Unix → ISO 8601 |
| `time_original` | ❌ | 移除 |
| `timezone` | `timezone` | 保留 |
| `recurrence` (object) | `repeat_flag` | 对象 → RRULE 字符串 |
| `time_period` | ❌ | 移除，用 BYHOUR/BYMINUTE |
| `period_state` | ❌ | 移除 |
| `status` (5种) | `status` (2种) | pending/confirmed → 0, completed/cancelled → 2 |
| `triggered_count` | `triggered_count` | 保留 |
| `last_triggered_at` | ❌ | 移除 |
| `created_at` | `created_at` | Unix → ISO 8601 |
| `updated_at` | `updated_at` | Unix → ISO 8601 |
| ❌ | `due_date` | **新增** |
| ❌ | `reminders` | **新增** |

---

## 3. RRULE 规范

### 3.1 基础语法

```
RRULE:FREQ=<频率>;INTERVAL=<间隔>;[BYDAY=<星期>];[BYHOUR=<小时>];[BYMINUTE=<分钟>];[COUNT=<次数>];[UNTIL=<结束日期>]
```

### 3.2 频率类型

| FREQ | 含义 | 示例 |
|------|------|------|
| `MINUTELY` | 每分钟 | 每30分钟 |
| `HOURLY` | 每小时 | 每小时、每2小时 |
| `DAILY` | 每天 | 每天、每3天 |
| `WEEKLY` | 每周 | 每周一、每周一三五 |
| `MONTHLY` | 每月 | 每月1号、每月15号 |
| `YEARLY` | 每年 | 每年1月1日 |

### 3.3 时间窗口模拟（BYHOUR + BYMINUTE）

**场景**：工作日 9:00-18:00 每小时提醒

```
# 旧方式 (time_period)
{
  "recurrence": {"type": "hourly", "interval": 1},
  "time_period": {
    "enabled": true,
    "start_time": "09:00",
    "end_time": "18:00",
    "active_days": [1, 2, 3, 4, 5]
  }
}

# 新方式 (RRULE)
RRULE:FREQ=HOURLY;INTERVAL=1;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9,10,11,12,13,14,15,16,17,18
```

**场景**：每天 9:30-17:30 每30分钟提醒

```
# start_date = "2025-01-01T09:30:00+08:00"
RRULE:FREQ=MINUTELY;INTERVAL=30;BYHOUR=9,10,11,12,13,14,15,16,17;BYMINUTE=0,30
```

### 3.4 常见 RRULE 示例

| 用户需求 | RRULE |
|----------|-------|
| 每天9点 | `RRULE:FREQ=DAILY` |
| 每周一 | `RRULE:FREQ=WEEKLY;BYDAY=MO` |
| 工作日每天 | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR` |
| 每小时 | `RRULE:FREQ=HOURLY` |
| 每2小时 | `RRULE:FREQ=HOURLY;INTERVAL=2` |
| 每30分钟 | `RRULE:FREQ=MINUTELY;INTERVAL=30` |
| 9-18点每小时 | `RRULE:FREQ=HOURLY;BYHOUR=9,10,11,12,13,14,15,16,17,18` |
| 工作日9-18点每小时 | `RRULE:FREQ=HOURLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9,10,11,12,13,14,15,16,17,18` |
| 每月1号 | `RRULE:FREQ=MONTHLY;BYMONTHDAY=1` |
| 共10次 | `RRULE:FREQ=DAILY;COUNT=10` |
| 到月底 | `RRULE:FREQ=DAILY;UNTIL=20250131T235959Z` |

### 3.5 提前提醒（TRIGGER）

采用 iCal VALARM 的 TRIGGER 格式：

| 格式 | 含义 |
|------|------|
| `TRIGGER:-PT1H` | 提前1小时 |
| `TRIGGER:-PT30M` | 提前30分钟 |
| `TRIGGER:-PT10M` | 提前10分钟 |
| `TRIGGER:-P1D` | 提前1天 |
| `TRIGGER:PT0S` | 到期时刻 |

**示例**：截止前1天和1小时各提醒一次

```json
{
  "due_date": "2025-01-15T18:00:00+08:00",
  "reminders": ["TRIGGER:-P1D", "TRIGGER:-PT1H"]
}
```

---

## 4. 接口设计

### 4.1 Tool 层接口（对 LLM 暴露）

#### 设计决策：多个独立工具 vs 单一工具

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **多个独立工具** | 5 个函数 | 职责单一、参数简洁、LLM 更准确 | 工具数量多 |
| 单一工具 + action | 1 个函数 | 统一入口 | 参数爆炸、条件复杂、易误用 |

**选择：多个独立工具**

原因：
1. **主流实践**：OpenAI、Anthropic 的 function calling 都推荐职责单一的工具
2. **参数清晰**：每个工具只有相关参数，减少误用
3. **LLM 更准确**：工具名本身就表达意图，减少歧义
4. **易于扩展**：新增功能不影响现有工具

#### 工具列表：

#### 4.1.1 create_reminder

```python
@tool
def create_reminder(
    # 必填
    title: str,                      # 提醒内容
    trigger_time: str,               # 触发时间（自然语言/ISO格式）
    
    # 周期设置（可选）
    recurrence_type: str = "none",   # "none"|"minutely"|"hourly"|"daily"|"weekly"|"monthly"
    recurrence_interval: int = 1,    # 间隔
    recurrence_days: str = None,     # 星期 "1,2,3,4,5" 或 "MO,TU,WE"
    time_window_start: int = None,   # 时间窗口开始小时 (0-23)
    time_window_end: int = None,     # 时间窗口结束小时 (0-23)
    max_count: int = None,           # 最大触发次数
    end_date: str = None,            # 结束日期
    
    # 截止日设置（可选）
    due_date: str = None,            # 截止日期
    remind_before: str = None,       # 提前提醒 "1d,1h,10m"
) -> dict:
    """
    创建提醒
    
    Returns:
        {"success": True, "reminder_id": "xxx", "message": "已创建提醒..."}
    """
```

#### 4.1.2 update_reminder

```python
@tool
def update_reminder(
    keyword: str,                    # 匹配关键字
    
    # 更新内容（可选）
    new_title: str = None,
    new_trigger_time: str = None,
    new_recurrence_type: str = None,
    new_recurrence_interval: int = None,
    new_due_date: str = None,
) -> dict:
    """
    按关键字更新提醒
    
    Returns:
        {"success": True, "updated_count": 1, "reminders": [...]}
    """
```

#### 4.1.3 delete_reminder

```python
@tool
def delete_reminder(
    keyword: str,                    # 匹配关键字
    delete_all: bool = False,        # 是否删除所有匹配项
) -> dict:
    """
    按关键字删除提醒
    
    Returns:
        {"success": True, "deleted_count": 1, "reminders": [...]}
    """
```

#### 4.1.4 list_reminders

```python
@tool
def list_reminders(
    # 时间过滤
    time_filter: str = "all",        # "all"|"today"|"tomorrow"|"week"|"overdue"
    start_date: str = None,          # 自定义开始日期（自然语言/ISO格式）
    end_date: str = None,            # 自定义结束日期
    
    # 其他过滤
    include_completed: bool = False, # 是否包含已完成
    keyword: str = None,             # 可选关键字过滤
) -> dict:
    """
    查询提醒列表
    
    时间过滤选项:
    - all: 所有提醒
    - today: 今天的提醒
    - tomorrow: 明天的提醒
    - week: 本周的提醒
    - overdue: 已过期未完成的
    - 或使用 start_date/end_date 自定义范围
    
    用户场景映射:
    - "今天还有什么提醒" -> time_filter="today"
    - "明天有什么安排" -> time_filter="tomorrow"
    - "这周有什么待办" -> time_filter="week"
    - "有哪些过期了还没做" -> time_filter="overdue"
    - "查一下下周的提醒" -> start_date="下周一", end_date="下周日"
    
    Returns:
        {"success": True, "count": 5, "reminders": [...]}
    """
```

#### 4.1.5 complete_reminder

```python
@tool
def complete_reminder(
    keyword: str,                    # 匹配关键字
) -> dict:
    """
    标记提醒为完成
    
    Returns:
        {"success": True, "completed_count": 1}
    """
```

### 4.2 Service 层接口

```python
class ReminderService:
    """提醒服务层 - 业务逻辑封装"""
    
    def __init__(self, dao: ReminderDAO, scheduler: ReminderScheduler):
        self.dao = dao
        self.scheduler = scheduler
    
    # === 核心业务 ===
    
    async def create(
        self,
        user_id: str,
        conversation_id: str,
        character_id: str,
        title: str,
        start_date: datetime,
        repeat_flag: str = None,
        due_date: datetime = None,
        reminders: list[str] = None,
        timezone: str = "Asia/Shanghai",
    ) -> str:
        """创建提醒，返回 _id"""
        # 1. 构建文档
        # 2. 写入 MongoDB
        # 3. 添加到 APScheduler
        # 4. 返回 ID
    
    async def update_by_keyword(
        self,
        user_id: str,
        keyword: str,
        updates: dict,
    ) -> tuple[int, list[dict]]:
        """按关键字更新"""
    
    async def delete_by_keyword(
        self,
        user_id: str,
        keyword: str,
    ) -> tuple[int, list[dict]]:
        """按关键字删除"""
    
    async def complete(self, reminder_id: str) -> bool:
        """标记完成"""
    
    async def list_by_user(
        self,
        user_id: str,
        time_filter: str = "all",
        start_date: datetime = None,
        end_date: datetime = None,
        include_completed: bool = False,
    ) -> list[dict]:
        """获取用户提醒（支持时间过滤）"""
    
    # === RRULE 工具 ===
    
    def build_rrule(
        self,
        freq: str,
        interval: int = 1,
        byday: list[str] = None,
        byhour: list[int] = None,
        byminute: list[int] = None,
        count: int = None,
        until: datetime = None,
    ) -> str:
        """构建 RRULE 字符串"""
    
    def parse_time_window(
        self,
        start_hour: int,
        end_hour: int,
    ) -> list[int]:
        """解析时间窗口为 BYHOUR 列表"""
        return list(range(start_hour, end_hour + 1))
    
    def parse_remind_before(self, remind_str: str) -> list[str]:
        """解析提前提醒字符串 "1d,1h,10m" -> ["TRIGGER:-P1D", "TRIGGER:-PT1H", "TRIGGER:-PT10M"]"""
    
    def get_display_message(self, reminder: dict) -> str:
        """生成显示消息（运行时拼接）"""
        return f"记得{reminder['title']}"
```

### 4.3 DAO 层接口（纯 CRUD）

```python
class ReminderDAO:
    """数据访问层 - 纯 CRUD，无业务逻辑"""
    
    def __init__(self, collection):
        self.collection = collection
    
    # === 基础 CRUD ===
    
    def create(self, doc: dict) -> str:
        """插入文档，返回 str(_id)"""
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)
    
    def get_by_id(self, reminder_id: str) -> dict | None:
        """按 _id 获取"""
        return self.collection.find_one({"_id": ObjectId(reminder_id)})
    
    def update(self, reminder_id: str, updates: dict) -> bool:
        """更新文档"""
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = self.collection.update_one(
            {"_id": ObjectId(reminder_id)},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    def delete(self, reminder_id: str) -> bool:
        """删除文档"""
        result = self.collection.delete_one({"_id": ObjectId(reminder_id)})
        return result.deleted_count > 0
    
    # === 查询 ===
    
    def find_by_user(
        self,
        user_id: str,
        status: int = None,
        start_date: str = None,
        end_date: str = None,
    ) -> list[dict]:
        """按用户查询（支持时间范围过滤）"""
        query = {"user_id": user_id}
        if status is not None:
            query["status"] = status
        if start_date or end_date:
            query["start_date"] = {}
            if start_date:
                query["start_date"]["$gte"] = start_date
            if end_date:
                query["start_date"]["$lte"] = end_date
        return list(self.collection.find(query))
    
    def find_by_keyword(
        self,
        user_id: str,
        keyword: str,
        status: int = None,
    ) -> list[dict]:
        """按关键字模糊查询"""
        if not keyword or not keyword.strip():
            return []
        query = {
            "user_id": user_id,
            "title": {"$regex": keyword, "$options": "i"}
        }
        if status is not None:
            query["status"] = status
        return list(self.collection.find(query))
    
    def find_pending_before(self, before_time: datetime) -> list[dict]:
        """查询待触发的提醒"""
        return list(self.collection.find({
            "status": 0,
            "start_date": {"$lte": before_time.isoformat()}
        }))
    
    # === 批量操作 ===
    
    def delete_by_ids(self, ids: list[str]) -> int:
        """批量删除"""
        object_ids = [ObjectId(id) for id in ids]
        result = self.collection.delete_many({"_id": {"$in": object_ids}})
        return result.deleted_count
    
    def update_by_ids(self, ids: list[str], updates: dict) -> int:
        """批量更新"""
        object_ids = [ObjectId(id) for id in ids]
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = self.collection.update_many(
            {"_id": {"$in": object_ids}},
            {"$set": updates}
        )
        return result.modified_count
    
    # === 状态变更 ===
    
    def mark_completed(self, reminder_id: str) -> bool:
        """标记为完成 (status=2)"""
        return self.update(reminder_id, {"status": 2})
    
    def increment_triggered_count(self, reminder_id: str) -> bool:
        """触发计数 +1"""
        result = self.collection.update_one(
            {"_id": ObjectId(reminder_id)},
            {
                "$inc": {"triggered_count": 1},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            }
        )
        return result.modified_count > 0
```

### 4.4 Scheduler 层接口

```python
class ReminderScheduler:
    """APScheduler 调度管理"""
    
    def __init__(self, scheduler: AsyncScheduler):
        self.scheduler = scheduler
    
    async def schedule(
        self,
        reminder_id: str,
        trigger_time: datetime,
    ) -> str:
        """添加调度任务"""
        job = await self.scheduler.add_schedule(
            func_or_task_id="reminder_executor:execute",
            trigger=DateTrigger(run_time=trigger_time),
            args=[reminder_id],
            id=f"reminder_{reminder_id}",
        )
        return job.id
    
    async def reschedule(
        self,
        reminder_id: str,
        new_trigger_time: datetime,
    ) -> bool:
        """重新调度"""
        job_id = f"reminder_{reminder_id}"
        try:
            await self.scheduler.modify_schedule(
                job_id,
                trigger=DateTrigger(run_time=new_trigger_time),
            )
            return True
        except Exception:
            return False
    
    async def cancel(self, reminder_id: str) -> bool:
        """取消调度"""
        job_id = f"reminder_{reminder_id}"
        try:
            await self.scheduler.remove_schedule(job_id)
            return True
        except Exception:
            return False
    
    def get_next_trigger(
        self,
        start_date: datetime,
        repeat_flag: str,
        after: datetime = None,
    ) -> datetime | None:
        """计算下次触发时间"""
        if not repeat_flag:
            return start_date if start_date > (after or datetime.now()) else None
        
        from dateutil.rrule import rrulestr
        rule = rrulestr(repeat_flag, dtstart=start_date)
        return rule.after(after or datetime.now(), inc=False)
```

---

## 5. 数据迁移

### 5.1 迁移脚本

```python
# scripts/migrate_reminder_v2.py

import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from dateutil.rrule import rrule, DAILY, WEEKLY, MONTHLY, HOURLY, MINUTELY

def migrate_reminder(old: dict) -> dict:
    """转换单条提醒数据"""
    
    # 1. 时间格式转换
    start_date = datetime.fromtimestamp(
        old["next_trigger_time"], 
        tz=timezone.utc
    ).isoformat()
    
    created_at = datetime.fromtimestamp(
        old.get("created_at", 0),
        tz=timezone.utc
    ).isoformat()
    
    updated_at = datetime.fromtimestamp(
        old.get("updated_at", 0),
        tz=timezone.utc
    ).isoformat()
    
    # 2. 状态映射
    old_status = old.get("status", "pending")
    new_status = 2 if old_status in ("completed", "cancelled") else 0
    
    # 3. 周期转换
    repeat_flag = convert_recurrence(old)
    
    # 4. 构建新文档
    return {
        "_id": old["_id"],
        "user_id": old["user_id"],
        "conversation_id": old.get("conversation_id", ""),
        "character_id": old.get("character_id", ""),
        "title": old["title"],
        "start_date": start_date,
        "due_date": None,
        "reminders": None,
        "timezone": old.get("timezone", "Asia/Shanghai"),
        "repeat_flag": repeat_flag,
        "status": new_status,
        "triggered_count": old.get("triggered_count", 0),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def convert_recurrence(old: dict) -> str | None:
    """转换周期配置为 RRULE"""
    recurrence = old.get("recurrence")
    if not recurrence or recurrence.get("type") == "none":
        return None
    
    freq_map = {
        "minutely": "MINUTELY",
        "hourly": "HOURLY",
        "daily": "DAILY",
        "weekly": "WEEKLY",
        "monthly": "MONTHLY",
    }
    
    rec_type = recurrence.get("type", "daily")
    freq = freq_map.get(rec_type, "DAILY")
    interval = recurrence.get("interval", 1)
    
    parts = [f"RRULE:FREQ={freq}"]
    
    if interval > 1:
        parts.append(f"INTERVAL={interval}")
    
    # 转换 days_of_week
    if "days_of_week" in recurrence:
        day_map = {0: "SU", 1: "MO", 2: "TU", 3: "WE", 4: "TH", 5: "FR", 6: "SA"}
        days = [day_map[d] for d in recurrence["days_of_week"]]
        parts.append(f"BYDAY={','.join(days)}")
    
    # 转换 time_period 为 BYHOUR
    time_period = old.get("time_period")
    if time_period and time_period.get("enabled"):
        start_h = int(time_period["start_time"].split(":")[0])
        end_h = int(time_period["end_time"].split(":")[0])
        hours = ",".join(str(h) for h in range(start_h, end_h + 1))
        parts.append(f"BYHOUR={hours}")
        
        # active_days 也需要转换
        if "active_days" in time_period:
            day_map = {1: "MO", 2: "TU", 3: "WE", 4: "TH", 5: "FR", 6: "SA", 7: "SU"}
            days = [day_map[d] for d in time_period["active_days"]]
            if f"BYDAY=" not in ";".join(parts):
                parts.append(f"BYDAY={','.join(days)}")
    
    # 转换 max_count
    if recurrence.get("max_count"):
        parts.append(f"COUNT={recurrence['max_count']}")
    
    # 转换 end_time
    if recurrence.get("end_time"):
        end_dt = datetime.fromtimestamp(recurrence["end_time"], tz=timezone.utc)
        parts.append(f"UNTIL={end_dt.strftime('%Y%m%dT%H%M%SZ')}")
    
    return ";".join(parts)


async def run_migration(dry_run: bool = True):
    """执行迁移"""
    from dao.mongo import get_mongo_client
    
    client = get_mongo_client()
    db = client.coke
    old_collection = db.reminders
    new_collection = db.reminders_v2
    
    # 备份原集合
    if not dry_run:
        print("Backing up original collection...")
        pipeline = [{"$out": "reminders_backup"}]
        old_collection.aggregate(pipeline)
    
    # 迁移数据
    cursor = old_collection.find({})
    total = 0
    success = 0
    failed = []
    
    for old_doc in cursor:
        total += 1
        try:
            new_doc = migrate_reminder(old_doc)
            if dry_run:
                print(f"[DRY RUN] Would migrate: {old_doc['_id']}")
            else:
                new_collection.replace_one(
                    {"_id": new_doc["_id"]},
                    new_doc,
                    upsert=True
                )
            success += 1
        except Exception as e:
            failed.append({"id": str(old_doc["_id"]), "error": str(e)})
        
        if total % 100 == 0:
            print(f"Progress: {total} processed, {success} success, {len(failed)} failed")
    
    print(f"\n=== Migration Complete ===")
    print(f"Total: {total}")
    print(f"Success: {success}")
    print(f"Failed: {len(failed)}")
    
    if failed:
        print("\nFailed records:")
        for f in failed[:10]:
            print(f"  - {f['id']}: {f['error']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    
    asyncio.run(run_migration(dry_run=not args.execute))
```

### 5.2 迁移步骤

```bash
# 1. 预览迁移（不执行）
PYTHONPATH=/home/ydyk/workspace/active-projects/coke \
python scripts/migrate_reminder_v2.py --dry-run

# 2. 执行迁移
PYTHONPATH=/home/ydyk/workspace/active-projects/coke \
python scripts/migrate_reminder_v2.py --execute

# 3. 验证迁移结果
# 检查 reminders_v2 集合数量
# 检查 RRULE 格式正确性

# 4. 切换集合（需修改 DAO 配置）
# 5. 删除旧集合（可选）
```

---

## 6. 实施计划

### Phase 1: 准备工作

| 任务 | 描述 | 预计时间 |
|------|------|----------|
| 创建 ReminderDAO V2 | 纯 CRUD 接口 | 2h |
| 创建 ReminderService | 业务逻辑封装 | 4h |
| 创建 ReminderScheduler | APScheduler 封装 | 2h |
| 单元测试 | 各层接口测试 | 4h |

### Phase 2: Tool 层重构

| 任务 | 描述 | 预计时间 |
|------|------|----------|
| 拆分 reminder_tool | 5 个独立工具 | 4h |
| RRULE 构建器 | build_rrule 函数 | 2h |
| 时间窗口转换 | BYHOUR/BYMINUTE | 1h |
| 提前提醒解析 | parse_remind_before | 1h |
| 集成测试 | Tool → Service → DAO | 4h |

### Phase 3: 数据迁移

| 任务 | 描述 | 预计时间 |
|------|------|----------|
| 编写迁移脚本 | migrate_reminder_v2.py | 2h |
| 本地测试 | 小数据量验证 | 2h |
| 生产备份 | reminders_backup | 0.5h |
| 执行迁移 | --execute | 0.5h |
| 验证 & 切换 | 切换到新集合 | 1h |

### Phase 4: 清理

| 任务 | 描述 | 预计时间 |
|------|------|----------|
| 删除旧代码 | time_period 相关逻辑 | 2h |
| 删除旧字段 | action_template, reminder_id 等 | 1h |
| 更新文档 | API 文档 | 1h |

---

## 7. 回滚方案

### 7.1 数据回滚

```bash
# 恢复备份
mongosh coke --eval "db.reminders_v2.drop(); db.reminders_backup.renameCollection('reminders');"
```

### 7.2 代码回滚

```bash
git revert <commit-hash>
```

### 7.3 兼容性保证

迁移期间保持双写：
1. 新 DAO 同时写入 `reminders` 和 `reminders_v2`
2. 读取优先从 `reminders_v2`，fallback 到 `reminders`
3. 验证稳定后切断双写

---

## 8. 验收标准

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 迁移脚本 dry-run 无报错
- [ ] 生产数据迁移成功率 > 99.9%
- [ ] RRULE 解析正确（含 BYHOUR/BYMINUTE）
- [ ] 新 Tool 接口可正常创建/查询/更新/删除提醒
- [ ] APScheduler 正常调度触发
- [ ] 旧数据兼容性验证通过
