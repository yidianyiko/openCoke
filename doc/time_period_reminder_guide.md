# 时间段提醒功能使用指南

## 功能概述

时间段提醒允许用户设置在特定时间段内按固定间隔重复提醒的功能.例如：
- "工作时间每30分钟提醒我喝水"
- "从早上9点到下午5点，每小时提醒我休息"
- "今天下午每半小时提醒我"

## 用户使用示例

### 示例 1：工作日提醒

**用户输入：**
```
工作时间每30分钟提醒我喝水
```

**系统行为：**
- 创建一个时间段提醒
- 时间段：周一到周五，09:00-18:00
- 间隔：每30分钟
- 首次触发：下一个工作日的09:00
- 后续触发：09:30, 10:00, 10:30, ..., 17:30, 18:00

### 示例 2：自定义时间段

**用户输入：**
```
从早上9点到下午5点，每小时提醒我休息一下
```

**系统行为：**
- 创建一个时间段提醒
- 时间段：每天 09:00-17:00
- 间隔：每60分钟
- 触发时间：09:00, 10:00, 11:00, ..., 17:00

### 示例 3：当天下午提醒

**用户输入：**
```
今天下午每半小时提醒我
```

**系统行为：**
- 创建一个时间段提醒
- 时间段：今天 13:00-18:00
- 间隔：每30分钟
- 触发时间：13:00, 13:30, 14:00, ..., 18:00

## LLM 调用参数

当 LLM 识别到时间段提醒意图时，应该调用 `reminder_tool` 并传入以下参数：

```python
reminder_tool(
    action="create",
    title="喝水",                          # 提醒标题
    trigger_time="2025年12月24日09时00分",  # 首次触发时间（时间段开始时间）
    recurrence_type="interval",            # 必须设为 "interval"
    recurrence_interval=30,                # 间隔分钟数
    period_start="09:00",                  # 时间段开始（HH:MM格式）
    period_end="18:00",                    # 时间段结束（HH:MM格式）
    period_days="1,2,3,4,5"               # 生效的星期几（可选）
)
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | str | 是 | 固定为 "create" |
| `title` | str | 是 | 提醒标题，如"喝水"、"休息" |
| `trigger_time` | str | 是 | 首次触发时间，建议设为时间段开始时间 |
| `recurrence_type` | str | 是 | 必须设为 "interval" |
| `recurrence_interval` | int | 是 | 间隔分钟数，如30表示每30分钟 |
| `period_start` | str | 是 | 时间段开始，格式 "HH:MM" |
| `period_end` | str | 是 | 时间段结束，格式 "HH:MM" |
| `period_days` | str | 否 | 生效的星期几，格式 "1,2,3,4,5"，不填表示每天 |

### period_days 说明

- `"1,2,3,4,5"` - 工作日（周一到周五）
- `"6,7"` - 周末（周六、周日）
- `"1,3,5"` - 周一、周三、周五
- 不填或 `None` - 每天生效

## 触发逻辑

### 时间段内触发

当当前时间在时间段内时：
1. 触发提醒
2. 计算下次触发时间 = 当前时间 + 间隔分钟数
3. 如果下次触发时间仍在时间段内，设置为下次触发时间
4. 如果下次触发时间超出时间段，跳到下一个有效日期的时间段开始时间

### 时间段外跳过

当当前时间不在时间段内时：
1. 不触发提醒
2. 计算下一个有效时间段的开始时间
3. 设置为下次触发时间

### 工作日限制

如果设置了 `period_days`：
1. 检查当前日期是否在生效日期内
2. 如果不在，跳到下一个有效日期的时间段开始时间

## 数据模型

```python
{
    "reminder_id": "uuid",
    "user_id": "user_123",
    "title": "喝水",
    "next_trigger_time": 1703145600,
    "recurrence": {
        "enabled": True,
        "type": "interval",
        "interval": 30
    },
    "time_period": {
        "enabled": True,
        "start_time": "09:00",
        "end_time": "18:00",
        "active_days": [1, 2, 3, 4, 5],
        "timezone": "Asia/Shanghai"
    },
    "period_state": {
        "today_first_trigger": None,
        "today_last_trigger": None,
        "today_trigger_count": 0
    },
    "status": "confirmed"
}
```

## 常见问题

### Q1: 如果用户说"工作时间"，如何理解？

A: "工作时间"默认理解为：
- 时间段：09:00-18:00
- 生效日期：周一到周五（1,2,3,4,5）

### Q2: 如果用户说"上午"、"下午"？

A: 预设时间段：
- "上午" → 08:00-12:00
- "下午" → 13:00-18:00
- "晚上" → 18:00-22:00

### Q3: 时间段提醒会在时间段结束后停止吗？

A: 是的.当计算出的下次触发时间超出时间段结束时间时，会自动跳到下一个有效日期的时间段开始时间.

### Q4: 如果今天不是有效日期（如周末），会怎样？

A: 系统会自动跳到下一个有效日期（如下周一）的时间段开始时间.

## 测试

运行测试：
```bash
python tests/test_time_period_reminder.py
```

## 实现细节

### 核心函数

1. **is_within_time_period** (`util/time_util.py`)
   - 判断给定时间戳是否在时间段内
   - 支持工作日限制

2. **calculate_next_period_trigger** (`util/time_util.py`)
   - 计算时间段提醒的下次触发时间
   - 处理时间段内外的不同逻辑

3. **handle_pending_reminders** (`agent/runner/agent_background_handler.py`)
   - 提醒触发主逻辑
   - 在触发前检查时间段
   - 自动重新计算下次触发时间

### 工作流程

```
用户输入 → ReminderDetectAgent (LLM) → reminder_tool → 数据库
                                              ↓
                                        time_period 字段
                                              ↓
定时任务 → find_pending_reminders → handle_pending_reminders
                                              ↓
                                    is_within_time_period?
                                         ↙        ↘
                                      是          否
                                      ↓           ↓
                                   触发提醒    重新计算
                                      ↓           ↓
                        calculate_next_period_trigger
```

## 版本历史

- V2.8 (2025-12-23): 新增时间段提醒功能
  - 支持时间段配置
  - 支持工作日限制
  - 自动跳过时间段外的触发
