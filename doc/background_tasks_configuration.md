# 后台任务配置说明

## 配置概览

系统支持细粒度控制后台任务，可以分别启用/禁用不同类型的功能。

---

## 配置选项

### 1. DISABLE_DAILY_AGENTS

控制 **Daily Agent** 相关功能：

- ✅ 每日新闻生成（QiaoyunDailyAgent）
- ✅ 每日活动脚本
- ✅ 关系数值衰减（decrease_all）
- ✅ 角色状态更新（handle_status）
- ✅ 主动消息派发（handle_proactive_message）

**配置方式**：

```bash
# 禁用 daily agent
export DISABLE_DAILY_AGENTS="true"

# 启用 daily agent
export DISABLE_DAILY_AGENTS="false"
```

---

### 2. DISABLE_BACKGROUND_AGENTS

控制 **Background Agent** 相关功能：

- ✅ 未来消息派发（handle_pending_future_message）
- ✅ 提醒任务派发（handle_pending_reminders）

**配置方式**：

```bash
# 禁用 background agent
export DISABLE_BACKGROUND_AGENTS="true"

# 启用 background agent
export DISABLE_BACKGROUND_AGENTS="false"
```

---

### 3. DISABLE_DAILY_TASKS（兼容旧配置）

为了向后兼容，保留了旧的配置选项。

**行为**：如果设置为 `"true"`，会同时禁用 Daily 和 Background 功能。

```bash
# 禁用所有后台任务（等同于同时禁用 daily 和 background）
export DISABLE_DAILY_TASKS="true"
```

**优先级**：`DISABLE_DAILY_TASKS` > `DISABLE_DAILY_AGENTS` / `DISABLE_BACKGROUND_AGENTS`

---

## 推荐配置

### 场景 1：生产环境（推荐）

```bash
export DISABLE_DAILY_AGENTS="true"   # 禁用 daily（节省资源）
export DISABLE_BACKGROUND_AGENTS="false"  # 启用 background（提醒功能）
```

**效果**：
- ❌ 不生成每日新闻
- ❌ 不发送主动消息
- ✅ 支持未来消息
- ✅ 支持提醒功能

---

### 场景 2：完整功能

```bash
export DISABLE_DAILY_AGENTS="false"
export DISABLE_BACKGROUND_AGENTS="false"
```

**效果**：
- ✅ 所有功能都启用

---

### 场景 3：完全禁用

```bash
export DISABLE_DAILY_TASKS="true"
```

或

```bash
export DISABLE_DAILY_AGENTS="true"
export DISABLE_BACKGROUND_AGENTS="true"
```

**效果**：
- ❌ 所有后台任务都禁用

---

## 当前配置

在 `qiaoyun/runner/qiaoyun_start.sh` 中：

```bash
export DISABLE_DAILY_AGENTS="true"        # 禁用 daily agent
export DISABLE_BACKGROUND_AGENTS="false"  # 启用 background agent
```

这是**推荐的生产配置**，可以：
- 节省资源（不生成每日新闻等）
- 保留核心功能（提醒、未来消息）

---

## 功能对照表

| 功能 | 类型 | 控制变量 | 默认状态 |
|------|------|----------|----------|
| 每日新闻生成 | Daily | DISABLE_DAILY_AGENTS | ❌ 禁用 |
| 每日活动脚本 | Daily | DISABLE_DAILY_AGENTS | ❌ 禁用 |
| 关系数值衰减 | Daily | DISABLE_DAILY_AGENTS | ❌ 禁用 |
| 角色状态更新 | Daily | DISABLE_DAILY_AGENTS | ❌ 禁用 |
| 主动消息派发 | Daily | DISABLE_DAILY_AGENTS | ❌ 禁用 |
| 未来消息派发 | Background | DISABLE_BACKGROUND_AGENTS | ✅ 启用 |
| 提醒任务派发 | Background | DISABLE_BACKGROUND_AGENTS | ✅ 启用 |

---

## 修改配置

### 方法 1：修改启动脚本（推荐）

编辑 `qiaoyun/runner/qiaoyun_start.sh`：

```bash
export DISABLE_DAILY_AGENTS="true"
export DISABLE_BACKGROUND_AGENTS="false"
```

然后重启服务：

```bash
source qiaoyun/runner/qiaoyun_start.sh
```

---

### 方法 2：临时环境变量

```bash
# 临时启用 daily agent
export DISABLE_DAILY_AGENTS="false"
source qiaoyun/runner/qiaoyun_start.sh
```

---

### 方法 3：配置文件

在 `conf/config.json` 中添加：

```json
{
  "disable_daily_agents": true,
  "disable_background_agents": false
}
```

---

## 验证配置

启动服务后，查看日志：

```bash
tail -f qiaoyun/runner/qiaoyun_runner.log
```

**Daily Agent 禁用时**：
- ❌ 不会看到 "run daily agent..."
- ❌ 不会看到 "start character proactive agent..."

**Background Agent 启用时**：
- ✅ 会看到 "发现 X 个待触发的提醒"
- ✅ 会看到 "提醒已发送: XXX"

---

## 常见问题

### Q1: 为什么要分离 Daily 和 Background？

**原因**：
- Daily Agent 消耗较多资源（生成新闻、脚本等）
- Background Agent 是核心功能（提醒、未来消息）
- 生产环境可能只需要 Background 功能

### Q2: 禁用 Daily Agent 会影响提醒功能吗？

**不会**。提醒功能属于 Background Agent，完全独立。

### Q3: 如何只启用提醒功能，禁用其他所有功能？

目前 Background Agent 包含两个功能：
- 未来消息派发
- 提醒任务派发

如果只想要提醒功能，可以修改代码注释掉 `handle_pending_future_message()`。

或者在代码中添加更细粒度的控制：

```python
# 在 background_handler() 中
disable_future_message = os.getenv("DISABLE_FUTURE_MESSAGE", "false").lower() == "true"
disable_reminders = os.getenv("DISABLE_REMINDERS", "false").lower() == "true"

if not disable_background_agents and not disable_future_message:
    handle_pending_future_message()

if not disable_background_agents and not disable_reminders:
    handle_pending_reminders()
```

---

## 总结

✅ **已实现细粒度控制**  
✅ **Daily 和 Background 可独立配置**  
✅ **向后兼容旧配置**  
✅ **推荐配置已应用**（Daily 禁用，Background 启用）

---

**更新时间**：2024-11-21  
**配置版本**：v2.0
