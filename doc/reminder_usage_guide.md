# 提醒功能使用指南

## 一、功能概述

提醒功能允许 AI 角色从用户的对话中识别提醒任务，并在指定时间主动发送提醒消息。

### 支持的功能

✅ **时间识别**
- 绝对时间：2024年12月1日下午3点
- 相对时间：30分钟后、2小时后、明天
- 模糊时间：1:43（需要确认上午/下午）

✅ **周期提醒**
- 每天、每周、每月、每年
- 自定义间隔：每2天、每3周

✅ **多提醒识别**
- 一句话中识别多个提醒任务

✅ **智能确认**
- 模糊时间自动询问确认
- 过期时间提示重新设置

---

## 二、用户对话示例

### 示例 1：简单提醒

**用户**：明天下午3点提醒我开会

**AI 识别结果**：
```json
{
  "DetectedReminders": [
    {
      "title": "开会",
      "time_original": "明天下午3点",
      "time_resolved": "2024年11月22日15时00分",
      "time_type": "absolute",
      "requires_confirmation": false,
      "recurrence": {"enabled": false},
      "action_template": "该开会了哦"
    }
  ]
}
```

**AI 回复**：好的，我会在明天下午3点提醒你开会的~

---

### 示例 2：相对时间

**用户**：30分钟后提醒我关火

**AI 识别结果**：
```json
{
  "DetectedReminders": [
    {
      "title": "关火",
      "time_original": "30分钟后",
      "time_resolved": "",
      "time_type": "relative",
      "requires_confirmation": false,
      "recurrence": {"enabled": false},
      "action_template": "记得关火哦！"
    }
  ]
}
```

**AI 回复**：好的，30分钟后我会提醒你关火的！

---

### 示例 3：模糊时间（需确认）

**用户**：1:43提醒我吃药

**AI 识别结果**：
```json
{
  "DetectedReminders": [
    {
      "title": "吃药",
      "time_original": "1:43",
      "time_resolved": "",
      "time_type": "ambiguous",
      "requires_confirmation": true,
      "confirmation_prompt": "你是说明天凌晨1点43分，还是下午1点43分呢？",
      "recurrence": {"enabled": false},
      "action_template": "该吃药了"
    }
  ]
}
```

**AI 回复**：好的，不过我需要确认一下，你是说明天凌晨1点43分，还是下午1点43分呢？

---

### 示例 4：周期提醒

**用户**：每天早上8点提醒我吃药

**AI 识别结果**：
```json
{
  "DetectedReminders": [
    {
      "title": "吃药",
      "time_original": "每天早上8点",
      "time_resolved": "2024年11月22日08时00分",
      "time_type": "absolute",
      "requires_confirmation": false,
      "recurrence": {
        "enabled": true,
        "type": "daily",
        "interval": 1
      },
      "action_template": "早上好，记得吃药哦~"
    }
  ]
}
```

**AI 回复**：好的，我会每天早上8点提醒你吃药的！

---

### 示例 5：多个提醒

**用户**：明天上午10点提醒我开会，下午3点提醒我写报告

**AI 识别结果**：
```json
{
  "DetectedReminders": [
    {
      "title": "开会",
      "time_original": "明天上午10点",
      "time_resolved": "2024年11月22日10时00分",
      "time_type": "absolute",
      "requires_confirmation": false,
      "recurrence": {"enabled": false},
      "action_template": "该开会了"
    },
    {
      "title": "写报告",
      "time_original": "明天下午3点",
      "time_resolved": "2024年11月22日15时00分",
      "time_type": "absolute",
      "requires_confirmation": false,
      "recurrence": {"enabled": false},
      "action_template": "该写报告了哦"
    }
  ]
}
```

**AI 回复**：好的，我会在明天上午10点提醒你开会，下午3点提醒你写报告~

---

## 三、技术实现

### 3.1 数据流程

```
用户消息
    ↓
QiaoyunChatResponseAgent (识别提醒)
    ↓
_posthandle (处理提醒)
    ↓
ReminderDAO (保存到数据库)
    ↓
后台轮询 (handle_pending_reminders)
    ↓
到期发送提醒消息
    ↓
周期提醒续订 / 非周期标记完成
```

### 3.2 数据库查询

```python
from dao.reminder_dao import ReminderDAO

dao = ReminderDAO()

# 查询用户的所有提醒
reminders = dao.find_reminders_by_user("user_id_123")

# 查询待触发的提醒
pending = dao.find_pending_reminders(int(time.time()))

# 取消提醒
dao.cancel_reminder("reminder_id_xxx")
```

### 3.3 手动创建提醒

```python
from dao.reminder_dao import ReminderDAO
import time

dao = ReminderDAO()

reminder_data = {
    "conversation_id": "conv_123",
    "user_id": "user_456",
    "character_id": "char_789",
    "title": "测试提醒",
    "next_trigger_time": int(time.time()) + 3600,  # 1小时后
    "time_original": "1小时后",
    "timezone": "Asia/Shanghai",
    "recurrence": {
        "enabled": False
    },
    "action_template": "这是测试提醒",
    "status": "confirmed"
}

reminder_id = dao.create_reminder(reminder_data)
print(f"创建提醒成功: {reminder_id}")
```

---

## 四、配置说明

### 4.1 时间窗口

后台处理器默认只处理 30 分钟内的提醒，超过 30 分钟的会被忽略。

修改 `qiaoyun/runner/qiaoyun_background_handler.py`：

```python
# 修改时间窗口为 1 小时
reminders = reminder_dao.find_pending_reminders(now, time_window=3600)
```

### 4.2 禁用提醒功能

在环境变量中设置：

```bash
export DISABLE_DAILY_TASKS=true
```

或在 `conf/config.json` 中：

```json
{
  "disable_daily_tasks": true
}
```

---

## 五、常见问题

### Q1: 提醒没有触发？

**检查清单**：
1. 后台处理器是否在运行？
2. 提醒状态是否为 `confirmed`？
3. 触发时间是否在 30 分钟窗口内？
4. 角色是否处于"空闲"状态？
5. 用户是否被拉黑（dislike >= 100）？

### Q2: 如何查看所有提醒？

```python
from dao.reminder_dao import ReminderDAO

dao = ReminderDAO()
reminders = dao.find_reminders_by_user("user_id")

for r in reminders:
    print(f"{r['title']}: {r['status']} at {r['next_trigger_time']}")
```

### Q3: 如何取消提醒？

```python
dao.cancel_reminder("reminder_id")
```

### Q4: 周期提醒如何停止？

周期提醒会在以下情况自动停止：
- 达到 `max_count` 次数
- 超过 `end_time` 时间
- 手动取消

---

## 六、测试

运行测试用例：

```bash
python tests/test_reminder_feature.py
```

测试覆盖：
- DAO 层增删改查
- 时间解析函数
- 周期计算
- 完整工作流

---

## 七、注意事项

1. **时区处理**：默认使用 `Asia/Shanghai`，如需支持其他时区需扩展
2. **并发安全**：使用会话锁避免并发冲突
3. **性能优化**：建议为 `reminders` 集合创建索引
4. **数据清理**：定期清理已完成的提醒记录

---

## 八、未来扩展

- [ ] 支持更多时区
- [ ] 支持 Cron 表达式
- [ ] 提醒优先级
- [ ] 提醒分组
- [ ] 提醒历史记录查询
- [ ] 用户自定义提醒模板
