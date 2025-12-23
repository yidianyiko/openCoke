# 提醒工具时间段参数处理说明

## 参数处理逻辑

### 时间段参数

reminder_tool 支持以下时间段相关参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `period_start` | str | 否 | None | 时间段开始时间，格式 "HH:MM" |
| `period_end` | str | 否 | None | 时间段结束时间，格式 "HH:MM" |
| `period_days` | str | 否 | None | 生效的星期几，格式 "1,2,3,4,5" |

### 处理规则

#### 规则 1：完整时间段参数

**条件：** `period_start` 和 `period_end` 都有值

**行为：** 创建时间段提醒

```python
# 示例
reminder_tool(
    action="create",
    title="喝水",
    trigger_time="2025年12月24日09时00分",
    recurrence_type="interval",
    recurrence_interval=30,
    period_start="09:00",    # ✅ 有值
    period_end="18:00",      # ✅ 有值
    period_days="1,2,3,4,5"  # 可选
)

# 结果：创建时间段提醒
{
    "time_period": {
        "enabled": True,
        "start_time": "09:00",
        "end_time": "18:00",
        "active_days": [1, 2, 3, 4, 5],
        "timezone": "Asia/Shanghai"
    }
}
```

#### 规则 2：不设置时间段参数

**条件：** `period_start` 和 `period_end` 都为 None

**行为：** 创建普通提醒（不包含 time_period 字段）

```python
# 示例
reminder_tool(
    action="create",
    title="开会",
    trigger_time="2025年12月24日09时00分"
    # period_start 和 period_end 都不传
)

# 结果：创建普通提醒
{
    # 没有 time_period 字段
    "title": "开会",
    "next_trigger_time": 1703145600,
    ...
}
```

#### 规则 3：部分时间段参数

**条件：** 只设置了 `period_start` 或 `period_end` 其中一个

**行为：** 忽略时间段参数，创建普通提醒，并记录警告日志

```python
# 示例 1：只设置 period_start
reminder_tool(
    action="create",
    title="测试",
    trigger_time="2025年12月24日09时00分",
    period_start="09:00",    # ✅ 有值
    period_end=None          # ❌ 无值
)

# 示例 2：只设置 period_end
reminder_tool(
    action="create",
    title="测试",
    trigger_time="2025年12月24日09时00分",
    period_start=None,       # ❌ 无值
    period_end="18:00"       # ✅ 有值
)

# 结果：都创建普通提醒（忽略不完整的时间段参数）
# 日志：WARNING - Incomplete time period config: period_start=09:00, period_end=None. Ignoring time period.
```

#### 规则 4：时间段参数但不设置 period_days

**条件：** `period_start` 和 `period_end` 都有值，但 `period_days` 为 None

**行为：** 创建时间段提醒，每天生效

```python
# 示例
reminder_tool(
    action="create",
    title="喝水",
    trigger_time="2025年12月24日09时00分",
    recurrence_type="interval",
    recurrence_interval=30,
    period_start="09:00",
    period_end="18:00"
    # period_days 不传
)

# 结果：创建时间段提醒，每天生效
{
    "time_period": {
        "enabled": True,
        "start_time": "09:00",
        "end_time": "18:00",
        "active_days": None,  # None 表示每天生效
        "timezone": "Asia/Shanghai"
    }
}
```

## 参数组合矩阵

| period_start | period_end | period_days | 结果 | 说明 |
|--------------|------------|-------------|------|------|
| None | None | None | 普通提醒 | 不设置时间段 |
| None | None | "1,2,3" | 普通提醒 | 忽略 period_days |
| "09:00" | None | None | 普通提醒 + 警告 | 参数不完整 |
| "09:00" | None | "1,2,3" | 普通提醒 + 警告 | 参数不完整 |
| None | "18:00" | None | 普通提醒 + 警告 | 参数不完整 |
| None | "18:00" | "1,2,3" | 普通提醒 + 警告 | 参数不完整 |
| "09:00" | "18:00" | None | 时间段提醒（每天） | 完整参数 |
| "09:00" | "18:00" | "1,2,3,4,5" | 时间段提醒（工作日） | 完整参数 |

## LLM 调用建议

### 场景 1：普通提醒

用户说："明天早上9点提醒我开会"

```python
reminder_tool(
    action="create",
    title="开会",
    trigger_time="2025年12月24日09时00分"
    # 不传 period_start, period_end, period_days
)
```

### 场景 2：时间段提醒（工作日）

用户说："工作时间每30分钟提醒我喝水"

```python
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

### 场景 3：时间段提醒（每天）

用户说："从早上9点到下午5点，每小时提醒我休息"

```python
reminder_tool(
    action="create",
    title="休息",
    trigger_time="2025年12月24日09时00分",
    recurrence_type="interval",
    recurrence_interval=60,
    period_start="09:00",
    period_end="17:00"
    # 不传 period_days，表示每天
)
```

## 错误处理

### 不完整的时间段参数

如果 LLM 只传了 `period_start` 或 `period_end` 其中一个：

1. **系统行为：**
   - 忽略时间段参数
   - 创建普通提醒
   - 记录警告日志

2. **日志示例：**
   ```
   WARNING - Incomplete time period config: period_start=09:00, period_end=None. Ignoring time period.
   ```

3. **用户体验：**
   - 提醒仍然会被创建
   - 只是不会有时间段限制
   - 不会报错或失败

### 无效的 period_days 格式

如果 `period_days` 格式错误（如 "abc" 而不是 "1,2,3"）：

1. **系统行为：**
   - 解析失败
   - `active_days` 设为 None（每天生效）
   - 记录警告日志

2. **日志示例：**
   ```
   WARNING - Failed to parse period_days: abc
   ```

3. **用户体验：**
   - 提醒仍然会被创建
   - 时间段每天生效（而不是指定的日期）

## 向后兼容性

### 现有提醒

- 现有提醒没有 `time_period` 字段
- 触发逻辑会检查 `time_period.get("enabled")`
- 如果字段不存在或 `enabled=False`，按普通提醒处理

### 新旧提醒混合

系统可以同时处理：
- 普通提醒（无 time_period 字段）
- 时间段提醒（有 time_period 字段）

触发逻辑会自动识别并正确处理。

## 测试验证

运行测试验证参数处理逻辑：

```bash
python tests/test_reminder_period_params.py -v
```

测试覆盖：
- ✅ 不设置时间段参数（普通提醒）
- ✅ 完整设置时间段参数
- ✅ 只设置 period_start（应该忽略）
- ✅ 只设置 period_end（应该忽略）
- ✅ 设置时间段但不设置 period_days（每天生效）

## 总结

**核心原则：**
1. **完整性优先**：只有 `period_start` 和 `period_end` 都存在时才启用时间段
2. **容错处理**：参数不完整时忽略并创建普通提醒，不影响功能
3. **向后兼容**：不影响现有的普通提醒功能
4. **灵活性**：`period_days` 可选，不传表示每天生效

**最佳实践：**
- LLM 应该同时设置 `period_start` 和 `period_end`，或者都不设置
- 避免只设置其中一个参数
- `period_days` 根据用户意图决定是否设置
