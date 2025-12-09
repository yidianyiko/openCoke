# 提醒重复触发问题修复

## 问题描述

用户报告提醒功能出现重复触发的问题：
- 用户在 00:24:16 发送消息"三分钟后提醒我刷牙"
- 系统正确创建了提醒
- 但在 00:25:24-00:25:28 期间，短短4秒内发送了12条"提醒：刷牙"消息
- 日志显示"发现 30 个待触发的提醒"

## 根本原因

1. **后台处理器每秒执行一次**
   - `agent_runner.py` 中 `background_handler()` 每秒被调用一次
   - 每次调用都会查询待触发的提醒

2. **状态管理问题**
   - `find_pending_reminders()` 查询 `status` 为 `"confirmed"` 或 `"pending"` 的提醒
   - 触发后调用 `mark_as_triggered()` 只更新了 `last_triggered_at` 和 `triggered_count`
   - **没有修改 `status` 字段**
   - 导致同一个提醒在30分钟时间窗口内被重复查询和触发

3. **时间窗口过大**
   - 原来的时间窗口是1800秒（30分钟）
   - 意味着一个提醒在触发后的30分钟内都可能被重复查询到

## 修复方案

### 1. 修改 `mark_as_triggered()` 方法

**文件**: `dao/reminder_dao.py`

```python
def mark_as_triggered(self, reminder_id: str) -> bool:
    """标记提醒为已触发（将状态改为 triggered，避免重复触发）"""
    update_data = {
        "status": "triggered",  # 关键修改：将状态改为 triggered
        "last_triggered_at": int(time.time()),
        "updated_at": int(time.time())
    }
    result = self.collection.update_one(
        {"reminder_id": reminder_id},
        {
            "$set": update_data,
            "$inc": {"triggered_count": 1}
        }
    )
    return result.modified_count > 0
```

### 2. 缩短时间窗口

**文件**: `dao/reminder_dao.py`

```python
def find_pending_reminders(self, current_time: int, time_window: int = 60) -> List[Dict]:
    """
    查找待触发的提醒
    
    Args:
        current_time: 当前时间戳
        time_window: 时间窗口（秒），默认60秒，避免重复触发
    """
    query = {
        "status": {"$in": ["confirmed", "pending"]},
        "next_trigger_time": {
            "$lte": current_time,
            "$gte": current_time - time_window  # 从1800秒改为60秒
        }
    }
    return list(self.collection.find(query))
```

### 3. 优化提醒处理流程

**文件**: `agent/runner/agent_background_handler.py`

确保状态转换流程清晰：

```
非周期提醒:
confirmed -> (触发) -> triggered -> (完成) -> completed

周期提醒:
confirmed -> (触发) -> triggered -> (重新调度) -> confirmed -> ...
```

## 状态转换图

```
创建提醒
   ↓
confirmed (待触发)
   ↓
[后台处理器查询到]
   ↓
triggered (已触发，不会再被查询)
   ↓
   ├─→ completed (非周期提醒完成)
   └─→ confirmed (周期提醒重新调度)
```

## 测试验证

运行测试脚本验证修复：

```bash
python tests/test_reminder_duplicate_fix.py
```

测试覆盖：
1. 非周期提醒状态变化正确
2. 周期提醒状态变化正确
3. 时间窗口正确限制查询范围

## 影响范围

- `dao/reminder_dao.py`: 修改 `mark_as_triggered()` 和 `find_pending_reminders()`
- `agent/runner/agent_background_handler.py`: 优化注释，逻辑保持不变

## 修复效果

- ✅ 提醒触发后立即将状态改为 `triggered`，不会被重复查询
- ✅ 时间窗口从30分钟缩短到60秒，减少误触发风险
- ✅ 周期提醒重新调度时状态正确恢复为 `confirmed`
- ✅ 非周期提醒触发后正确标记为 `completed`

## 部署建议

1. 备份数据库中的 `reminders` 集合
2. 部署新代码
3. 清理数据库中状态异常的提醒（可选）：
   ```javascript
   // 将所有 status 为 "triggered" 且不是周期提醒的改为 "completed"
   db.reminders.updateMany(
     {
       "status": "triggered",
       "recurrence.enabled": false
     },
     {
       $set: { "status": "completed" }
     }
   )
   ```

## 日期

2024-12-09
