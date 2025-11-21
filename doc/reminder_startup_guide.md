# Reminder 功能启动说明

## 自动启动

✅ **是的，reminder 功能会自动启动！**

当你使用标准启动脚本时：

```bash
source qiaoyun/runner/qiaoyun_start.sh
```

系统会自动启动两个处理器：
1. **主处理器** - 处理用户消息，识别提醒任务
2. **后台处理器** - 每秒检查并发送到期的提醒

---

## ⚠️ 重要配置

### 细粒度控制（v2.0）

在 `qiaoyun/runner/qiaoyun_start.sh` 中：

```bash
# Daily Agent: 每日新闻、主动消息等
export DISABLE_DAILY_AGENTS="true"        # ❌ 禁用

# Background Agent: 提醒功能、未来消息等
export DISABLE_BACKGROUND_AGENTS="false"  # ✅ 启用
```

**已配置**：启动脚本已设置为推荐配置：
- ❌ 禁用 Daily Agent（节省资源）
- ✅ 启用 Background Agent（包括提醒功能）

详细配置说明请查看：`doc/background_tasks_configuration.md`

---

## 启动流程

```
qiaoyun_start.sh
    ↓
qiaoyun_runner.py
    ↓
    ├─ run_main_agent()        (处理用户消息)
    │   └─ main_handler()
    │       └─ QiaoyunChatResponseAgent
    │           └─ 识别 DetectedReminders
    │               └─ 保存到 reminders 集合
    │
    └─ run_background_agent()  (后台任务，每秒执行)
        └─ background_handler()
            ├─ handle_status()              (更新角色状态)
            ├─ handle_proactive_message()   (主动消息)
            ├─ handle_pending_future_message() (未来消息)
            └─ handle_pending_reminders()   ✅ (提醒派发)
```

---

## 首次启动前的准备

### 1. 初始化数据库

```bash
# 确保在虚拟环境中
source myenv/bin/activate

# 运行初始化脚本
python scripts/init_reminder_feature.py
```

这会创建必要的数据库索引。

### 2. 运行测试（可选）

```bash
python tests/test_reminder_feature.py
```

### 3. 启动服务

```bash
source qiaoyun/runner/qiaoyun_start.sh
```

---

## 验证 Reminder 功能是否运行

### 方法 1：查看日志

启动后，日志中应该能看到：

```
INFO:qiaoyun.runner.qiaoyun_background_handler:start character proactive agent...
INFO:qiaoyun.runner.qiaoyun_background_handler:发现 X 个待触发的提醒
INFO:qiaoyun.runner.qiaoyun_background_handler:提醒已发送: XXX
```

### 方法 2：测试对话

向 AI 发送消息：

```
用户：明天下午3点提醒我开会
AI：好的，我会在明天下午3点提醒你开会的~
```

然后查询数据库：

```python
from dao.reminder_dao import ReminderDAO

dao = ReminderDAO()
reminders = dao.find_reminders_by_user("你的user_id")
print(f"当前提醒数: {len(reminders)}")
for r in reminders:
    print(f"- {r['title']}: {r['status']}")
```

### 方法 3：检查进程

```bash
ps -ef | grep qiaoyun_runner.py
```

应该能看到运行中的进程。

---

## 常见问题

### Q1: 启动后提醒不工作？

**检查清单**：
1. ✅ `DISABLE_DAILY_TASKS` 是否设置为 `"false"`
2. ✅ 数据库索引是否已创建（运行初始化脚本）
3. ✅ 后台处理器是否在运行（查看日志）
4. ✅ 提醒时间是否在 30 分钟窗口内

### Q2: 如何临时禁用提醒功能？

修改启动脚本：

```bash
export DISABLE_DAILY_TASKS="true"
```

然后重启服务。

### Q3: 提醒功能会影响性能吗？

不会。后台处理器每秒只执行一次数据库查询，且有索引优化：

```javascript
// 高效查询
db.reminders.find({
    "status": {"$in": ["confirmed", "pending"]},
    "next_trigger_time": {"$lte": now, "$gte": now - 1800}
}).limit(100)
```

### Q4: 如何查看所有提醒？

```python
from dao.reminder_dao import ReminderDAO

dao = ReminderDAO()

# 查看所有提醒
all_reminders = dao.collection.find({})
for r in all_reminders:
    print(f"{r['title']}: {r['status']} at {r['next_trigger_time']}")

# 查看待触发的提醒
import time
pending = dao.find_pending_reminders(int(time.time()))
print(f"待触发: {len(pending)} 个")
```

---

## 重启服务

如果修改了配置，需要重启：

```bash
# 1. 按 Ctrl+C 停止日志监听（但服务仍在运行）

# 2. 手动杀死进程
ps -ef | grep qiaoyun_runner.py | grep -v grep | awk '{print $2}' | xargs kill

# 3. 重新启动
source qiaoyun/runner/qiaoyun_start.sh
```

或者直接重新执行启动脚本（它会自动杀死旧进程）：

```bash
source qiaoyun/runner/qiaoyun_start.sh
```

---

## 总结

✅ **Reminder 功能会自动启动**（前提是 `DISABLE_DAILY_TASKS="false"`）  
✅ **无需额外配置**（只需运行初始化脚本创建索引）  
✅ **与现有功能完全兼容**（不影响主动消息等其他功能）  

---

**更新时间**：2024-11-21  
**状态**：✅ 已配置完成
