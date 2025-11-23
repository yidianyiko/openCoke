# 提醒任务识别方案可行性分析

> 基于 Luoyun Project 现有架构的提醒功能实现方案评估
> 
> 分析日期：2024-11-21

---

## 更新说明

- 不再计划编写 `doc/reminder_usage_guide.md` 与 `doc/reminder_implementation_plan.md`，以本文件与代码为主要参考。
- 模糊时间的识别与分类由 LLM 完成；工具层仅解析明确的绝对/相对时间，不对模糊表达进行检测。遇到无法解析或不确定的表达，由 Agent 走确认流程。

## 目录

1. [方案概述](#1-方案概述)
2. [现有架构分析](#2-现有架构分析)
3. [方案可行性评估](#3-方案可行性评估)
4. [技术实现路径](#4-技术实现路径)
5. [风险与挑战](#5-风险与挑战)
6. [改进建议](#6-改进建议)
7. [结论](#7-结论)

---

## 1. 方案概述

### 1.1 目标

从用户回复中结构化识别提醒任务，支持：
- 绝对/相对时间识别
- 周期模式识别
- 单句多提醒解析
- 模糊时间确认机制

### 1.2 核心设计

**输出 Schema 扩展**：在 `QiaoyunChatResponseAgent` 的 `default_output_schema` 中新增 `DetectedReminders` 字段（非必填，可为空数组）。

**复用现有机制**：通过 `conversation.conversation_info.future` 完成到期派发与发送。

**最小改动原则**：不改动消息发送分支、数据库结构，仅扩展 Agent 输出和处理逻辑。

---

## 2. 现有架构分析

### 2.1 相关模块现状

#### 2.1.1 QiaoyunChatResponseAgent

**位置**：`qiaoyun/agent/qiaoyun_chat_response_agent.py`

**当前 Schema**（第 72-145 行）：
```python
default_output_schema = {
    "type": "object",
    "properties": {
        "InnerMonologue": {...},
        "ChatResponse": {...},
        "MultiModalResponses": {...},
        "ChatCatelogue": {...},
        "RelationChange": {...},
        "FutureResponse": {
            "type": "object",
            "properties": {
                "FutureResponseTime": {"type": "string"},
                "FutureResponseAction": {"type": "string"}
            }
        }
    }
}
```

**现有 future 机制**（第 174-194 行）：
```python
def _posthandle(self):
    future_resp = self.resp.get("FutureResponse", {...})
    if future_resp.get("FutureResponseAction", "无") != "无":
        if random.random() < (0.25 ** (future_proactive_times + 1) + 0.05):
            self.context["conversation"]["conversation_info"]["future"]["timestamp"] = str2timestamp(...)
            self.context["conversation"]["conversation_info"]["future"]["action"] = ...
```

**关键发现**：
- ✅ 已有 `FutureResponse` 字段用于主动消息规划
- ✅ 已有 `future.timestamp` 和 `future.action` 机制
- ⚠️ **单槽限制**：只能存储一个未来行动
- ⚠️ **概率触发**：有随机性，不适合确定性提醒



#### 2.1.2 QiaoyunFutureChatResponseAgent

**位置**：`qiaoyun/agent/background/qiaoyun_future_chat_response_agent.py`

**后台派发逻辑**（第 175-194 行）：
```python
def _posthandle(self):
    self.context["conversation"]["conversation_info"]["future"]["proactive_times"] += 1
    future_resp = self.resp.get("FutureResponse", {...})
    if random.random() < (0.15 ** (future_proactive_times + 1)):
        # 续订下一次主动消息
        self.context["conversation"]["conversation_info"]["future"]["timestamp"] = ...
        self.context["conversation"]["conversation_info"]["future"]["action"] = ...
    else:
        # 清空
        self.context["conversation"]["conversation_info"]["future"]["timestamp"] = None
        self.context["conversation"]["conversation_info"]["future"]["action"] = None
```

**关键发现**：
- ✅ 已有续订机制（可用于周期提醒）
- ⚠️ **概率衰减**：主动消息有频率限制，不适合确定性提醒
- ⚠️ **单次触发**：每次只处理一个 future action

#### 2.1.3 Background Handler

**位置**：`qiaoyun/runner/qiaoyun_background_handler.py`

**派发检查逻辑**（第 216-420 行）：
```python
def handle_pending_future_message():
    conversations = conversation_dao.find_conversations(query={
        "conversation_info.future.action": {"$ne": None, "$exists": True},
        "conversation_info.future.timestamp": {
            "$lt": now,      # 到期
            "$gt": now - 1800  # 半小时内
        }
    })
    
    for conversation in conversations:
        # 执行 FutureMessageAgent
        # 发送消息
        # 更新 conversation
```

**关键发现**：
- ✅ 已有定时轮询机制（每秒检查）
- ✅ 已有到期判断逻辑
- ✅ 已有消息发送流程
- ⚠️ **半小时窗口**：超过半小时的提醒会被忽略
- ⚠️ **状态检查**：需要角色"空闲"才发送

### 2.2 数据结构现状

#### 2.2.1 Conversation.conversation_info

```python
"conversation_info": {
    "time_str": "2024年01月01日12时30分 星期一",
    "chat_history": [...],
    "input_messages": [...],
    "photo_history": [...],
    "future": {
        "timestamp": int,           # Unix 秒
        "action": str,              # 行动描述
        "proactive_times": int      # 主动次数
    }
}
```

**限制**：
- ❌ **单槽设计**：只能存一个 future action
- ❌ **无元数据**：action 是纯文本，无结构化信息
- ❌ **无周期信息**：无法表达 recurrence



---

## 3. 方案可行性评估

### 3.1 ✅ 可行部分

#### 3.1.1 Schema 扩展（完全可行）

**方案**：在 `default_output_schema` 中新增 `DetectedReminders` 字段。

**可行性**：⭐⭐⭐⭐⭐
- LLM 支持结构化输出（已验证）
- 不影响现有字段
- 向后兼容（非必填字段）

**实现难度**：低

#### 3.1.2 时间解析（可行）

**方案**：在 `_posthandle` 中解析时间字符串（工具层仅负责明确的绝对/相对时间解析，模糊不在工具层判断）。

**可行性**：⭐⭐⭐⭐
- 已有 `util/time_util.py` 的 `str2timestamp` 函数
- 支持中文时间格式："2024年12月05日09时00分"
- 可扩展相对时间解析
- 模糊表达由 LLM 标注为 `time_type=ambiguous` 或 `requires_confirmation=true`，不由工具层判断

**实现难度**：中等（需增强相对时间解析）

#### 3.1.3 模糊确认机制（可行）

**方案**：当 LLM 输出 `time_type=ambiguous` 或 `requires_confirmation=true` 时，在 `ChatResponse/MultiModalResponses` 中追加确认问题（工具层不进行“模糊检测”）。

**可行性**：⭐⭐⭐⭐
- 可在 `_posthandle` 中修改 `MultiModalResponses`
- 不影响原有回复生成逻辑

**实现难度**：低

#### 3.1.4 复用现有派发（部分可行）

**方案**：写入 `future.timestamp/action` 触发后台发送。

**可行性**：⭐⭐⭐
- ✅ 轮询机制已存在
- ✅ 发送流程已完善
- ⚠️ **单槽限制**：只能存一个提醒
- ⚠️ **概率干扰**：现有逻辑有随机性

**实现难度**：中等（需改造单槽限制）

### 3.2 ⚠️ 存在挑战的部分

#### 3.2.1 单槽限制（核心问题）

**现状**：
```python
"future": {
    "timestamp": int,
    "action": str,
    "proactive_times": int
}
```

**问题**：
- 只能存储一个未来行动
- 多条提醒会互相覆盖
- 周期提醒与普通主动消息冲突

**方案建议的处理**：
> "对已确认的提醒，选取'最近的一条'写入 future；其余保留在会话上下文"

**可行性评估**：⭐⭐
- ❌ **会话上下文不持久化**：`context` 只在内存中，处理完即销毁
- ❌ **无队列机制**：无法存储多个待发提醒
- ⚠️ **需改造数据结构**：需要将 `future` 改为数组或引入新集合



#### 3.2.2 周期续订机制（需改造）

**方案建议**：
> "在 `future.action` 中内嵌 JSON 元数据，格式：`提醒：<title>｜{"id":"...","recurrence":{...}}`"

**可行性评估**：⭐⭐⭐
- ✅ 技术上可行（字符串拼接）
- ⚠️ **解析复杂度**：需在多处解析 JSON
- ⚠️ **向后兼容**：现有 action 是纯文本，需兼容处理
- ⚠️ **可读性差**：混合格式不利于调试

**更好的方案**：
```python
"future": {
    "timestamp": int,
    "action": str,
    "reminder_metadata": {  # 新增字段
        "id": str,
        "recurrence": {...},
        "action_template": str
    }
}
```

#### 3.2.3 时区处理（需完善）

**现状**：
- 系统使用 Unix 时间戳（UTC）
- `time_util.py` 未显式处理时区
- 默认使用服务器本地时区

**问题**：
- 用户可能在不同时区
- "明天9点"的解析依赖会话时区
- 跨时区用户会出错

**方案建议**：
> "默认会话时区；无时区信息按 Asia/Shanghai 兜底"

**可行性评估**：⭐⭐⭐⭐
- ✅ 可在 `conversation_info` 中存储时区
- ✅ 可在 `str2timestamp` 中传入时区参数
- ⚠️ 需改造现有时间工具函数

#### 3.2.4 过期时间处理（需明确策略）

**方案建议**：
> "过去时间滚动或提示确认；绝不过期直接派发"

**问题**：
- "昨天3点提醒"应该如何处理？
  - 滚动到今天3点？
  - 滚动到明天3点？
  - 直接拒绝？
- "1:43"（未指定AM/PM）如何滚动？

**建议策略**：
1. **绝对过期时间**：标记 `requires_confirmation=true`，让用户重新指定
2. **相对时间**：基于当前时间计算，不会过期
3. **模糊时间**：必须确认，不自动滚动

### 3.3 ❌ 不可行部分

#### 3.3.1 "保留在会话上下文"（不可行）

**方案原文**：
> "其余保留在会话上下文（后续扩展可引入队列，但本期先不改存储结构）"

**问题**：
- ❌ `context` 是临时对象，处理完即销毁
- ❌ 无法跨请求保留数据
- ❌ 重启后丢失

**必须改动**：需要持久化存储（数据库）

#### 3.3.2 "不需改动的模块"（部分不准确）

**方案声称不需改动**：
- `qiaoyun_background_handler.py:311-383`（消息发送分支）
- `qiaoyun/util/message_util.py`（统一写库与展示）

**实际情况**：
- ✅ 消息发送逻辑确实不需改动
- ⚠️ **但 background_handler 需要改动**：
  - 需要解析 `action` 中的 JSON 元数据
  - 需要实现周期续订逻辑
  - 需要处理多提醒队列



---

## 4. 技术实现路径

### 4.1 方案 A：最小改动方案（单提醒）

**适用场景**：快速验证，只支持单个提醒

#### 4.1.1 Schema 扩展

```python
# qiaoyun/agent/qiaoyun_chat_response_agent.py
default_output_schema = {
    "properties": {
        # ... 现有字段 ...
        "DetectedReminder": {  # 单数，只识别一个
            "type": "object",
            "description": "识别到的提醒任务（如有多个只取最近的一个）",
            "properties": {
                "title": {"type": "string"},
                "time_original": {"type": "string"},
                "time_resolved_iso": {"type": "string"},
                "time_type": {"type": "string", "enum": ["absolute", "relative"]},
                "requires_confirmation": {"type": "boolean"},
                "confirmation_prompt": {"type": "string"},
                "action_template": {"type": "string"}
            }
        }
    }
}
```

#### 4.1.2 时间解析增强

```python
# util/time_util.py 新增函数
def parse_relative_time(text, base_timestamp=None):
    """解析相对时间：30分钟后、两小时后、明天"""
    if base_timestamp is None:
        base_timestamp = int(time.time())
    
    # 正则匹配
    patterns = [
        (r'(\d+)分钟后', lambda m: base_timestamp + int(m.group(1)) * 60),
        (r'(\d+)小时后', lambda m: base_timestamp + int(m.group(1)) * 3600),
        (r'明天', lambda m: base_timestamp + 86400),
        # ... 更多模式
    ]
    
    for pattern, calculator in patterns:
        match = re.search(pattern, text)
        if match:
            return calculator(match)
    
    return None
```

#### 4.1.3 _posthandle 改造

```python
# qiaoyun/agent/qiaoyun_chat_response_agent.py
def _posthandle(self):
    # ... 现有逻辑 ...
    
    # 处理提醒
    reminder = self.resp.get("DetectedReminder")
    if reminder and reminder.get("title"):
        if reminder.get("requires_confirmation"):
            # 追加确认问题到回复
            confirmation = reminder.get("confirmation_prompt", "请确认提醒时间")
            self.resp["MultiModalResponses"].append({
                "type": "text",
                "content": confirmation
            })
            # 不写入 future，等待用户确认
        else:
            # 解析时间
            timestamp = None
            if reminder.get("time_resolved_iso"):
                timestamp = iso_to_timestamp(reminder["time_resolved_iso"])
            elif reminder.get("time_type") == "relative":
                timestamp = parse_relative_time(reminder["time_original"])
            
            if timestamp and timestamp > int(time.time()):
                # 写入 future
                self.context["conversation"]["conversation_info"]["future"]["timestamp"] = timestamp
                self.context["conversation"]["conversation_info"]["future"]["action"] = reminder["action_template"]
                logger.info(f"设置提醒：{reminder['title']} at {timestamp}")
```

**优点**：
- ✅ 改动最小
- ✅ 不改数据库结构
- ✅ 快速验证

**缺点**：
- ❌ 只支持单个提醒
- ❌ 无周期功能
- ❌ 与主动消息冲突



### 4.2 方案 B：完整方案（多提醒 + 周期）

**适用场景**：生产环境，完整功能

#### 4.2.1 数据库改造

**新增集合：reminders**

```javascript
{
    _id: ObjectId,
    conversation_id: String,      // 关联会话
    user_id: String,              // 用户ID
    character_id: String,         // 角色ID
    
    // 提醒信息
    reminder_id: String,          // 去重ID（UUID）
    title: String,                // 提醒标题
    action_template: String,      // 到期发送的内容
    
    // 时间信息
    next_trigger_time: Number,    // 下次触发时间（Unix秒）
    time_original: String,        // 原始时间文本
    timezone: String,             // 时区
    
    // 周期信息
    recurrence: {
        type: String,             // none/daily/weekly/monthly/cron
        pattern: String,          // 周期模式
        until: Number,            // 结束时间
        count: Number             // 重复次数
    },
    
    // 状态
    status: String,               // pending/confirmed/triggered/cancelled
    requires_confirmation: Boolean,
    confirmation_prompt: String,
    
    // 元数据
    created_at: Number,
    updated_at: Number,
    triggered_count: Number       // 已触发次数
}
```

**索引**：
```javascript
db.reminders.createIndex({"conversation_id": 1})
db.reminders.createIndex({"status": 1, "next_trigger_time": 1})
db.reminders.createIndex({"reminder_id": 1}, {unique: true})
```

#### 4.2.2 Schema 扩展（完整版）

```python
# qiaoyun/agent/qiaoyun_chat_response_agent.py
"DetectedReminders": {
    "type": "array",
    "description": "识别到的提醒任务列表",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "time_original": {"type": "string"},
            "time_resolved_iso": {"type": "string"},
            "timestamp": {"type": "number"},
            "time_type": {"type": "string", "enum": ["absolute", "relative"]},
            "timezone": {"type": "string"},
            "requires_confirmation": {"type": "boolean"},
            "confirmation_prompt": {"type": "string"},
            "recurrence": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "pattern": {"type": "string"},
                    "until": {"type": "number"},
                    "count": {"type": "number"}
                }
            },
            "action_template": {"type": "string"}
        }
    }
}
```

#### 4.2.3 _posthandle 改造（完整版）

```python
def _posthandle(self):
    # ... 现有逻辑 ...
    
    # 处理提醒列表
    reminders = self.resp.get("DetectedReminders", [])
    if not reminders:
        return
    
    mongo = MongoDBBase()
    conversation_id = str(self.context["conversation"]["_id"])
    user_id = str(self.context["user"]["_id"])
    character_id = str(self.context["character"]["_id"])
    
    confirmed_reminders = []
    needs_confirmation = []
    
    for reminder in reminders:
        # 解析时间
        timestamp = self._parse_reminder_time(reminder)
        
        if reminder.get("requires_confirmation") or timestamp is None:
            needs_confirmation.append(reminder)
        else:
            # 去重检查
            existing = mongo.find_one("reminders", {
                "conversation_id": conversation_id,
                "reminder_id": reminder.get("id"),
                "status": {"$in": ["pending", "confirmed"]}
            })
            if existing:
                continue
            
            # 写入数据库
            reminder_doc = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "character_id": character_id,
                "reminder_id": reminder.get("id", str(uuid.uuid4())),
                "title": reminder.get("title"),
                "action_template": reminder.get("action_template"),
                "next_trigger_time": timestamp,
                "time_original": reminder.get("time_original"),
                "timezone": reminder.get("timezone", "Asia/Shanghai"),
                "recurrence": reminder.get("recurrence", {"type": "none"}),
                "status": "confirmed",
                "requires_confirmation": False,
                "created_at": int(time.time()),
                "triggered_count": 0
            }
            mongo.insert_one("reminders", reminder_doc)
            confirmed_reminders.append(reminder)
    
    # 追加确认问题
    if needs_confirmation:
        confirmation_text = "我需要确认一下提醒时间：\n"
        for r in needs_confirmation:
            confirmation_text += f"- {r['title']}: {r.get('confirmation_prompt', '请明确时间')}\n"
        
        self.resp["MultiModalResponses"].append({
            "type": "text",
            "content": confirmation_text
        })
    
    # 日志
    if confirmed_reminders:
        logger.info(f"已设置 {len(confirmed_reminders)} 个提醒")

def _parse_reminder_time(self, reminder):
  