# 提醒任务识别实现方案

> 基于现有架构的提醒功能完整实现方案
> 
> 创建日期：2024-11-21

---

## 一、方案概述

### 1.1 需求回顾

从用户回复中识别提醒任务，支持：
1. ✅ 常见时间相关的自然语言识别
2. ✅ 绝对时间和相对时间，模糊时间需确认
3. ✅ 周期模式（每天、每周等）
4. ✅ 单句多提醒识别

### 1.2 实现方向

- **Schema 扩展**：在 `QiaoyunChatResponseAgent.default_output_schema` 中新增 `DetectedReminders` 字段
- **复用机制**：利用 `conversation.conversation_info.future` 实现到期派发
- **扩展存储**：新增 `reminders` 集合支持多提醒和周期功能

---

## 二、技术决策点

### 决策点 1：存储方案选择

**问题**：现有 `future` 字段只能存储单个行动，如何支持多提醒？

**方案 A**：最小改动（仅支持单提醒）
- 优点：改动小，快速验证
- 缺点：功能受限，无法支持多提醒和周期

**方案 B**：新增 reminders 集合（推荐）
- 优点：完整功能，支持多提醒、周期、历史记录
- 缺点：需要新增数据库集合和 DAO 层

**❓ 请选择：你希望采用哪个方案？**
- 输入 `A` = 最小改动，快速验证
- 输入 `B` = 完整功能，生产可用

---

### 决策点 2：与现有 future 机制的关系

**问题**：提醒任务和现有的"主动消息"都使用 `future` 字段，如何避免冲突？

**方案 A**：提醒优先
- 有提醒时，暂停主动消息
- 提醒发送完后，恢复主动消息

**方案 B**：分离机制
- 提醒使用新的 `reminders` 集合
- `future` 字段仅用于主动消息
- 两者独立运行

**❓ 请选择：你希望采用哪个方案？**
- 输入 `A` = 提醒优先
- 输入 `B` = 分离机制（推荐）

---

### 决策点 3：周期提醒的实现方式

**问题**：如何实现"每天9点提醒"这类周期任务？

**方案 A**：触发后续订
- 提醒触发后，计算下次时间并更新
- 简单直接，但需要处理续订逻辑

**方案 B**：Cron 表达式
- 使用 cron 表达式存储周期规则
- 灵活强大，但解析复杂

**❓ 请选择：你希望采用哪个方案？**
- 输入 `A` = 触发后续订（推荐）
- 输入 `B` = Cron 表达式

---

### 决策点 4：模糊时间确认流程

**问题**：用户说"1:43 提醒我"，如何确认是上午还是下午？

**方案 A**：智能推断 + 确认
- LLM 根据上下文推断（如晚上说的可能是明天）
- 不确定时追加确认问题

**方案 B**：始终确认
- 所有模糊时间都要求用户确认
- 更安全但体验略差

**❓ 请选择：你希望采用哪个方案？**
- 输入 `A` = 智能推断 + 确认（推荐）
- 输入 `B` = 始终确认

---

## 三、最终方案确定

**已选择方案**：
1. ✅ 方案 B - 新增 reminders 集合（完整功能）
2. ✅ 方案 B - 分离机制（提醒与主动消息独立）
3. ✅ 方案 A - 触发后续订（周期提醒）
4. ✅ 方案 A - 智能推断 + 确认（模糊时间）

---

## 四、数据库设计

### 4.1 新增集合：reminders

```javascript
{
    _id: ObjectId,
    
    // 关联信息
    conversation_id: String,      // 关联的会话ID
    user_id: String,              // 用户ID
    character_id: String,         // 角色ID
    
    // 提醒标识
    reminder_id: String,          // 唯一ID（UUID），用于去重
    title: String,                // 提醒标题，如"开会"
    
    // 时间信息
    next_trigger_time: Number,    // 下次触发时间（Unix秒）
    time_original: String,        // 原始时间文本，如"明天下午3点"
    timezone: String,             // 时区，默认 "Asia/Shanghai"
    
    // 周期信息
    recurrence: {
        enabled: Boolean,         // 是否启用周期
        type: String,             // daily/weekly/monthly/yearly
        interval: Number,         // 间隔，如每2天
        end_time: Number,         // 结束时间（可选）
        max_count: Number         // 最大重复次数（可选）
    },
    
    // 提醒内容
    action_template: String,      // 到期时发送的消息模板
    
    // 状态管理
    status: String,               // pending/confirmed/triggered/cancelled/completed
    requires_confirmation: Boolean, // 是否需要用户确认
    confirmation_prompt: String,  // 确认提示语
    
    // 元数据
    created_at: Number,           // 创建时间
    updated_at: Number,           // 更新时间
    triggered_count: Number,      // 已触发次数
    last_triggered_at: Number     // 上次触发时间
}
```

### 4.2 索引设计

```javascript
// 按会话查询
db.reminders.createIndex({"conversation_id": 1})

// 按状态和触发时间查询（后台轮询使用）
db.reminders.createIndex({
    "status": 1, 
    "next_trigger_time": 1
})

// 唯一性约束
db.reminders.createIndex({"reminder_id": 1}, {unique: true})

// 按用户查询
db.reminders.createIndex({"user_id": 1, "status": 1})
```

---

## 五、核心实现

### 5.1 Schema 扩展

修改 `qiaoyun/agent/qiaoyun_chat_response_agent.py`：

```python
default_output_schema = {
    "type": "object",
    "properties": {
        # ... 现有字段保持不变 ...
        
        "DetectedReminders": {
            "type": "array",
            "description": "从用户消息中识别到的提醒任务列表，可能为空",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "提醒的简短标题，如'开会'、'吃药'"
                    },
                    "time_original": {
                        "type": "string",
                        "description": "用户原始的时间表达，如'明天下午3点'、'30分钟后'"
                    },
                    "time_resolved": {
                        "type": "string",
                        "description": "解析后的绝对时间，格式：YYYY年MM月DD日HH时MM分"
                    },
                    "time_type": {
                        "type": "string",
                        "enum": ["absolute", "relative", "ambiguous"],
                        "description": "时间类型：绝对时间/相对时间/模糊时间"
                    },
                    "requires_confirmation": {
                        "type": "boolean",
                        "description": "是否需要用户确认（如1:43不确定上午下午）"
                    },
                    "confirmation_prompt": {
                        "type": "string",
                        "description": "需要确认时的提示语"
                    },
                    "recurrence": {
                        "type": "object",
                        "description": "周期信息，如果不是周期提醒则为null",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["daily", "weekly", "monthly", "yearly"],
                                "description": "周期类型"
                            },
                            "interval": {
                                "type": "number",
                                "description": "间隔数，如每2天则为2"
                            }
                        }
                    },
                    "action_template": {
                        "type": "string",
                        "description": "到期时要说的话，如'该开会了'"
                    }
                },
                "required": ["title", "time_original", "action_template"]
            }
        }
    }
}
```

---

## 六、实现步骤

接下来我将分步骤创建以下文件：

1. **DAO 层**：`dao/reminder_dao.py` - 提醒数据访问层
2. **工具函数**：扩展 `util/time_util.py` - 增强时间解析
3. **Agent 改造**：修改 `qiaoyun_chat_response_agent.py` 的 `_posthandle`
4. **后台处理**：修改 `qiaoyun_background_handler.py` 添加提醒派发
5. **测试用例**：创建测试文件

准备开始实现，请确认是否继续？


---

## 七、部署步骤

### 7.1 数据库初始化

```python
# 创建索引
from dao.reminder_dao import ReminderDAO

dao = ReminderDAO()
dao.create_indexes()
dao.close()

print("提醒功能数据库初始化完成")
```

### 7.2 验证安装

运行测试：

```bash
python tests/test_reminder_feature.py
```

### 7.3 启动服务

确保后台处理器正在运行：

```bash
# 后台处理器会自动调用 handle_pending_reminders()
python qiaoyun/runner/qiaoyun_background_handler.py
```

---

## 八、文件清单

### 新增文件

1. **dao/reminder_dao.py** - 提醒数据访问层
2. **tests/test_reminder_feature.py** - 测试用例
3. **doc/reminder_usage_guide.md** - 使用指南
4. **doc/reminder_implementation_plan.md** - 实现方案（本文档）

### 修改文件

1. **qiaoyun/agent/qiaoyun_chat_response_agent.py**
   - 扩展 `default_output_schema` 添加 `DetectedReminders` 字段
   - 修改 `_posthandle()` 添加 `_handle_reminders()` 调用
   - 新增 `_handle_reminders()` 方法
   - 新增 `_parse_reminder_time()` 方法

2. **util/time_util.py**
   - 新增 `parse_relative_time()` - 相对时间解析
   - 新增 `calculate_next_recurrence()` - 周期计算
   - 新增 `is_time_in_past()` - 过期判断
   - 新增 `format_time_friendly()` - 友好格式化

3. **qiaoyun/runner/qiaoyun_background_handler.py**
   - 新增 `handle_pending_reminders()` 函数
   - 在 `background_handler()` 中调用提醒处理

---

## 九、测试场景

### 场景 1：简单提醒

**输入**：明天下午3点提醒我开会

**预期**：
- AI 回复确认
- 数据库创建提醒记录
- 到期时发送提醒消息

### 场景 2：模糊时间确认

**输入**：1:43提醒我

**预期**：
- AI 询问是上午还是下午
- 不创建提醒记录（等待确认）

### 场景 3：周期提醒

**输入**：每天早上8点提醒我吃药

**预期**：
- 创建周期提醒
- 每天8点触发
- 触发后自动续订下一天

### 场景 4：多提醒

**输入**：明天10点提醒我开会，下午3点提醒我写报告

**预期**：
- 创建2条提醒记录
- 分别在指定时间触发

---

## 十、性能考虑

### 10.1 数据库索引

已创建的索引：
- `conversation_id` - 按会话查询
- `status + next_trigger_time` - 后台轮询
- `reminder_id` - 唯一性约束
- `user_id + status` - 按用户查询

### 10.2 查询优化

```javascript
// 后台轮询查询（已优化）
db.reminders.find({
    "status": {"$in": ["confirmed", "pending"]},
    "next_trigger_time": {
        "$lte": now,
        "$gte": now - 1800
    }
}).limit(100)
```

### 10.3 并发控制

使用会话锁避免并发冲突：

```python
lock = lock_manager.acquire_lock("conversation", conversation_id, timeout=120, max_wait=1)
```

---

## 十一、监控与日志

### 11.1 关键日志

```python
# 创建提醒
logger.info(f"创建提醒: {reminder['title']} at {timestamp}")

# 触发提醒
logger.info(f"提醒已发送: {reminder['title']}")

# 周期续订
logger.info(f"周期提醒已续订: {reminder['title']} -> {next_time}")
```

### 11.2 监控指标

建议监控：
- 待触发提醒数量
- 提醒触发成功率
- 提醒处理延迟
- 周期提醒续订率

---

## 十二、总结

### 实现的功能

✅ 从用户消息中识别提醒任务  
✅ 支持绝对时间、相对时间、模糊时间  
✅ 支持周期提醒（每天/每周/每月/每年）  
✅ 支持单句多提醒识别  
✅ 智能确认机制  
✅ 与现有 future 机制分离  
✅ 完整的数据持久化  
✅ 后台自动派发  

### 技术亮点

- **最小侵入**：复用现有架构，不破坏原有功能
- **分离设计**：提醒与主动消息独立运行
- **扩展性强**：易于添加新的时间模式和周期类型
- **生产可用**：完整的错误处理和并发控制

### 下一步

1. 运行测试验证功能
2. 在测试环境部署
3. 收集用户反馈
4. 根据需要扩展功能

---

**方案完成时间**：2024-11-21  
**预计开发时间**：2-3天  
**风险等级**：低
