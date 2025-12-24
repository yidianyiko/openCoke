# 提醒系统改进总结

## 改进目标

1. **统一时间格式**：确保 LLM 输出标准的时间格式
2. **增强时间推理**：让 LLM 能够根据当前时间推理任意时间
3. **支持时间段提醒**：实现"从X点到Y点每隔Z分钟提醒"的功能

## 核心改进

### 1. 优化 Prompt - 增强时间推理能力

**问题：** LLM 有时输出不规范的时间格式（如"下午3点"、"15:00"）

**解决方案：** 在 Prompt 中注入当前时间，让 LLM 进行时间推理

**改进点：**
- 动态生成 `get_reminder_detect_instructions(current_time_str)` 函数
- 在 Prompt 中明确显示当前时间
- 提供详细的时间转换示例和规则
- 明确禁止的格式并说明后果

**示例：**
```python
## 当前时间
2025年12月23日15时30分 星期二

## 时间解析规则
你必须根据当前时间进行逻辑推理：
- "下午3点" → 如果当前是下午3点之前，则为"今天15时00分"；如果已过，则为"明天15时00分"
- "明天早上9点" → 计算明天的具体日期，输出"2025年12月24日09时00分"
```

### 2. 新增时间段提醒功能

**功能描述：** 支持在指定时间段内按固定间隔重复提醒

**使用场景：**
- "工作时间每30分钟提醒我喝水"
- "从早上9点到下午5点，每小时提醒我休息"
- "今天下午每半小时提醒我"

**数据模型扩展：**
```python
{
    "recurrence": {
        "enabled": True,
        "type": "interval",
        "interval": 30  # 间隔分钟数
    },
    "time_period": {
        "enabled": True,
        "start_time": "09:00",
        "end_time": "18:00",
        "active_days": [1, 2, 3, 4, 5],  # 工作日
        "timezone": "Asia/Shanghai"
    }
}
```

**新增工具函数：**
1. `is_within_time_period()` - 判断时间是否在时间段内
2. `calculate_next_period_trigger()` - 计算时间段提醒的下次触发时间

**触发逻辑：**
- 时间段内：正常触发，计算下次触发时间
- 时间段外：跳过触发，重新计算到下一个有效时间段
- 工作日限制：自动跳到下一个有效日期

### 3. 扩展 reminder_tool 参数

**新增参数：**
```python
def reminder_tool(
    action: str,
    title: Optional[str] = None,
    trigger_time: Optional[str] = None,
    recurrence_type: str = "none",
    recurrence_interval: int = 1,
    # 新增：时间段提醒参数
    period_start: Optional[str] = None,   # "09:00"
    period_end: Optional[str] = None,     # "18:00"
    period_days: Optional[str] = None     # "1,2,3,4,5"
) -> dict:
```

**LLM 调用示例：**
```python
# 用户说："工作时间每30分钟提醒我喝水"
reminder_tool(
    action="create",
    title="喝水",
    trigger_time="2025年12月24日09时00分",
    recurrence_type="interval",
    recurrence_interval=30,
    period_start="09:00",
    period_end="18:00",
    period_days="1,2,3,4,5"
)
```

## 文件修改清单

### 核心文件

1. **agent/prompt/agent_instructions_prompt.py**
   - 新增 `get_reminder_detect_instructions(current_time_str)` 函数
   - 增强时间解析规则和示例
   - 添加时间段提醒的 Prompt 说明

2. **agent/agno_agent/tools/reminder_tools.py**
   - 扩展 `reminder_tool` 参数（period_start, period_end, period_days）
   - 更新 `_create_reminder` 函数支持时间段配置
   - 优化确认消息展示时间段信息

3. **util/time_util.py**
   - 新增 `is_within_time_period()` 函数
   - 新增 `calculate_next_period_trigger()` 函数

4. **agent/runner/agent_background_handler.py**
   - 更新 `handle_pending_reminders()` 支持时间段判断
   - 在触发前检查是否在时间段内
   - 时间段外自动重新计算下次触发时间

5. **agent/agno_agent/workflows/prepare_workflow.py**
   - 动态注入当前时间到 ReminderDetectAgent 的 instructions
   - 临时更新 Agent 的 instructions 后恢复

### 测试和文档

6. **tests/test_time_period_reminder.py** (新增)
   - 测试时间段判断逻辑
   - 测试下次触发时间计算
   - 测试时间段提醒创建

7. **doc/time_period_reminder_guide.md** (新增)
   - 功能使用指南
   - LLM 调用参数说明
   - 触发逻辑说明
   - 常见问题解答

8. **doc/reminder_system_improvements_summary.md** (本文档)
   - 改进总结
   - 设计思路
   - 实现细节

## 设计思路

### 为什么不减少 LLM 依赖？

**结论：** 当前系统对 LLM 的依赖是合理且必要的

**原因：**
1. **自然语言理解本身需要 LLM**
   - 用户输入多样化："提醒我"、"别忘了"、"叫我"
   - 跨消息意图整合："提醒我" → "开会" → "下午三点"

2. **时间表达的多样性**
   - "下午3点"、"明天早上9点"、"后天下午2点"
   - "30分钟后"、"2小时后"、"下周一"
   - "工作时间"、"上午"、"晚上"

3. **语义理解的复杂性**
   - "工作时间每30分钟提醒我喝水" 需要理解：
     - 提醒意图
     - 时间段概念（工作时间 = 09:00-18:00 + 工作日）
     - 周期概念（每30分钟）
     - 提醒内容（喝水）

### 改进方向：让 LLM 更好地工作

**不是减少依赖，而是增强能力：**

1. **提供更好的上下文**
   - 注入当前时间
   - 提供时间转换示例
   - 明确格式要求

2. **增强后端容错**
   - 支持多种时间格式解析（作为兜底）
   - 但主要依靠 Prompt 引导 LLM 输出正确格式

3. **扩展功能支持**
   - 新增时间段提醒参数
   - 让 LLM 能够表达更复杂的提醒需求

## 关键技术点

### 1. 动态 Prompt 注入

```python
# 在 PrepareWorkflow 中动态生成 instructions
time_str = session_state.get("conversation", {}).get("conversation_info", {}).get("time_str", "")
dynamic_instructions = get_reminder_detect_instructions(time_str)

# 临时更新 Agent 的 instructions
original_instructions = reminder_detect_agent.instructions
reminder_detect_agent.instructions = dynamic_instructions

# 执行后恢复
reminder_detect_agent.instructions = original_instructions
```

### 2. 时间段判断逻辑

```python
# 检查是否在时间段内
if time_period.get("enabled"):
    if not is_within_time_period(now, start_time, end_time, active_days):
        # 不在时间段内，重新计算下次触发时间
        next_time = calculate_next_period_trigger(...)
        reminder_dao.reschedule_reminder(reminder_id, next_time)
        continue  # 跳过本次触发
```

### 3. 下次触发时间计算

```python
def calculate_next_period_trigger(current_time, interval_minutes, start_time, end_time, active_days):
    # 1. 如果当前在时间段内，返回 current + interval
    if in_period:
        next_trigger = current + interval
        if next_trigger <= period_end:
            return next_trigger
    
    # 2. 如果当前在时间段外，返回下一个有效时间段的开始时间
    for day_offset in range(8):
        check_date = current_date + day_offset
        if check_date.weekday in active_days:
            return period_start_of_check_date
    
    return None
```

## 测试验证

### 单元测试

```bash
# 测试时间段提醒功能
python tests/test_time_period_reminder.py
```

### 集成测试场景

1. **场景1：工作日提醒**
   - 用户："工作时间每30分钟提醒我喝水"
   - 预期：创建时间段提醒，周一到周五 09:00-18:00，每30分钟

2. **场景2：自定义时间段**
   - 用户："从早上9点到下午5点，每小时提醒我休息"
   - 预期：创建时间段提醒，每天 09:00-17:00，每60分钟

3. **场景3：时间推理**
   - 当前时间：15:30
   - 用户："下午3点提醒我"
   - 预期：LLM 推理出已过下午3点，设置为明天15:00

4. **场景4：跨消息整合**
   - 用户："提醒我"
   - 用户："开会，明天上午10点"
   - 预期：整合为"明天上午10点提醒我开会"

## 性能影响

### LLM 调用次数

- **无变化**：仍然是每次提醒意图检测调用一次 ReminderDetectAgent
- **优化点**：动态 Prompt 生成在内存中完成，无额外开销

### 数据库查询

- **新增字段**：time_period, period_state（不影响现有查询）
- **查询逻辑**：find_pending_reminders 无变化
- **触发逻辑**：增加时间段判断（O(1) 时间复杂度）

### 触发效率

- **时间段内**：正常触发，无额外开销
- **时间段外**：跳过触发，重新计算（避免无效触发）

## 向后兼容性

### 数据兼容

- **现有提醒**：time_period 字段为空或 enabled=False，按原逻辑处理
- **新提醒**：可选择是否启用时间段功能

### API 兼容

- **reminder_tool**：新增参数为可选参数，不影响现有调用
- **触发逻辑**：先检查 time_period.enabled，未启用则按原逻辑

## 未来扩展

### 可能的增强

1. **更灵活的时间段**
   - 支持多个时间段（如上午9-12点，下午2-5点）
   - 支持节假日排除

2. **智能调整**
   - 根据用户行为自动调整提醒频率
   - 学习用户的活跃时间段

3. **提醒优先级**
   - 重要提醒在时间段外也触发
   - 普通提醒严格遵守时间段

4. **统计分析**
   - 记录每天的触发次数
   - 分析用户的提醒使用习惯

## 总结

本次改进通过以下方式提升了提醒系统的能力：

1. **增强 LLM 的时间推理能力**：通过动态注入当前时间和详细的转换规则
2. **支持时间段提醒**：满足"工作时间每30分钟提醒"的复杂需求
3. **保持系统简洁**：只使用一种标准时间格式，避免复杂性
4. **向后兼容**：不影响现有提醒功能

**核心理念：** 不是减少对 LLM 的依赖，而是让 LLM 更好地工作.通过提供更好的上下文和更清晰的指令，让 LLM 能够准确理解用户意图并输出标准格式.
