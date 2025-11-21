# 提醒功能实现：核心问题与方案选型

## 核心问题汇总

### 🔴 问题 1：单槽限制（最严重）

**现状**：
```python
"future": {
    "timestamp": int,      # 只能存一个时间
    "action": str,         # 只能存一个行动
    "proactive_times": int
}
```

**冲突**：
- 提醒任务 vs 主动消息（如"挑一条今天的新闻聊聊"）会互相覆盖
- 多条提醒（"明天9点开会，下午3点买票"）只能保留一个
- 周期提醒会阻塞其他 future 行动

**原方案说法**：
> "其余保留在会话上下文"

**问题**：❌ context 是临时对象，处理完即销毁，无法持久化

---

### 🟡 问题 2：概率触发机制不适合确定性提醒

**现状**：
```python
# QiaoyunChatResponseAgent._posthandle
if random.random() < (0.25 ** (future_proactive_times + 1) + 0.05):
    # 才会写入 future
```

**问题**：
- 提醒任务需要 100% 确定性触发
- 现有逻辑有随机性，不适合提醒场景
- `proactive_times` 衰减会影响提醒可靠性

---

### 🟡 问题 3：半小时窗口限制

**现状**：
```python
# qiaoyun_background_handler.py
"conversation_info.future.timestamp": {
    "$lt": now,
    "$gt": now - 1800  # 只处理半小时内的
}
```

**问题**：
- 如果系统停机超过 30 分钟，提醒会丢失
- 不符合提醒场景的可靠性要求

---

### 🟢 问题 4：时区处理缺失

**现状**：
- 系统使用 Unix 时间戳，但未显式管理时区
- `time_util.py` 依赖服务器本地时区

**影响**：
- "明天9点"的解析依赖会话时区
- 跨时区用户会出错

---

### 🟢 问题 5：action 字段无结构化元数据

**原方案建议**：
> "action_payload 格式：人类可读前缀 + 内嵌 JSON 元数据"
> 例如：`提醒：吃药｜{"id":"...","recurrence":{...}}`

**问题**：
- 混合格式解析复杂
- 向后兼容性差
- 调试困难

---

## 方案选型

### 方案 A：最小改动（单提醒，无周期）⭐⭐⭐

**适用场景**：快速验证 MVP

**改动范围**：
1. Schema 新增 `DetectedReminder`（单数，只识别一个）
2. `_posthandle` 解析并写入 `future`
3. 增强 `time_util.py` 支持相对时间
4. 去除概率判断（提醒场景 100% 写入）

**优点**：
- ✅ 改动最小（约 100 行代码）
- ✅ 不改数据库结构
- ✅ 1-2 天可完成

**缺点**：
- ❌ 只支持单个提醒
- ❌ 无周期功能
- ❌ 与主动消息冲突（需二选一）

**适合吗？** 如果只是验证 LLM 识别能力，可以用这个方案。

---

### 方案 B：引入提醒队列（推荐）⭐⭐⭐⭐⭐

**核心思路**：新增 `reminders` 集合，与 `future` 分离

**数据结构**：
```python
# MongoDB: reminders 集合
{
    "_id": ObjectId,
    "conversation_id": str,
    "user_id": str,
    "character_id": str,
    "title": str,
    "trigger_timestamp": int,
    "action_template": str,
    "status": "pending" | "sent" | "canceled",
    "recurrence": {
        "type": "none" | "daily" | "weekly" | "cron",
        "pattern": str,
        "until": int,
        "count": int
    },
    "created_at": int,
    "metadata": {...}
}
```

**改动范围**：
1. Schema 新增 `DetectedReminders`（复数，数组）
2. `_posthandle` 写入 `reminders` 集合（不写 `future`）
3. `background_handler` 新增 `handle_pending_reminders()` 函数
4. 周期提醒在发送后自动续订（插入新记录）

**优点**：
- ✅ 支持多提醒
- ✅ 支持周期提醒
- ✅ 不与主动消息冲突
- ✅ 可扩展（优先级、分类、编辑、删除）
- ✅ 可靠性高（独立存储）

**缺点**：
- ⚠️ 需要新增集合（改动数据库）
- ⚠️ 代码量较大（约 300-400 行）
- ⚠️ 需要 3-5 天开发

**适合吗？** 如果要做完整的提醒功能，强烈推荐这个方案。

---

### 方案 C：扩展 future 为数组（折中）⭐⭐⭐⭐

**核心思路**：将 `future` 改为数组，支持多个行动

**数据结构**：
```python
"conversation_info": {
    "futures": [  # 改为数组
        {
            "type": "reminder" | "proactive",  # 区分类型
            "timestamp": int,
            "action": str,
            "reminder_metadata": {  # 提醒专用
                "id": str,
                "title": str,
                "recurrence": {...}
            }
        }
    ]
}
```

**改动范围**：
1. 数据迁移：`future` → `futures[]`
2. Schema 新增 `DetectedReminders`（复数）
3. `_posthandle` 写入 `futures` 数组
4. `background_handler` 遍历 `futures` 数组处理

**优点**：
- ✅ 支持多提醒
- ✅ 支持周期提醒
- ✅ 提醒与主动消息共存
- ✅ 不需要新集合

**缺点**：
- ⚠️ 需要数据迁移（改动现有字段）
- ⚠️ `conversation_info` 会变大
- ⚠️ 需要兼容现有代码

**适合吗？** 如果不想新增集合，可以考虑。

---

## 推荐方案

### 🎯 短期（1-2周）：方案 B（提醒队列）

**理由**：
1. **架构清晰**：提醒与主动消息分离，职责明确
2. **可扩展性强**：后续可加优先级、分类、用户管理
3. **可靠性高**：独立存储，不受其他功能影响
4. **符合原方案目标**：支持多提醒、周期、确认机制

**实施步骤**：
1. 新增 `reminders` 集合
2. 扩展 Schema 和 `_posthandle`
3. 实现 `handle_pending_reminders()`
4. 测试用例覆盖

---

## 需要你决策的问题

### Q1：是否接受新增数据库集合？
- **是** → 方案 B（推荐）
- **否** → 方案 C 或 方案 A

### Q2：是否需要支持多提醒？
- **是** → 方案 B 或 C
- **否** → 方案 A

### Q3：是否需要周期提醒？
- **是** → 方案 B 或 C
- **否** → 方案 A

### Q4：提醒与主动消息是否需要共存？
- **是** → 方案 B 或 C
- **否** → 方案 A（提醒会覆盖主动消息）

### Q5：开发时间预期？
- **1-2天快速验证** → 方案 A
- **3-5天完整功能** → 方案 B
- **2-3天折中方案** → 方案 C

---

## 我的建议

**选择方案 B**，理由：
1. 提醒是确定性功能，应该独立存储
2. 后续扩展空间大（用户可查看/编辑/删除提醒）
3. 不影响现有主动消息机制
4. 符合"最小改动"原则（不改现有逻辑，只新增）

**请告诉我你的选择，我会生成详细的实施计划。**
