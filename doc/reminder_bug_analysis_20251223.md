# 提醒系统 Bug 分析报告

**日期**: 2025-12-23  
**问题**: ReminderDetectAgent 陷入无限循环并自动删除刚创建的提醒

## 问题现象

### 时间线（14:24:54 - 14:27:55）

1. **14:24:54** - 用户发送消息："过一会提醒我站起来"
2. **14:25:09** - 创建提醒成功（14:55）
3. **14:25:12** - 自动查询提醒列表（发现 2 个提醒）
4. **14:25:16** - 自动删除"喝水"提醒
5. **14:25:19** - 再次查询列表（剩 1 个）
6. **14:25:23** - 自动删除"站起来"提醒（刚创建的！）
7. **14:25:26 - 14:27:55** - 持续发送 API 请求约 30 次，无工具调用日志
8. **14:27:55** - 第一次请求超时，系统重新处理
9. **14:28:16** - 第二次请求正常完成

### 用户体验影响

- 用户等待 3 分钟才收到回复
- 回复说"14:43提醒你站起来"，但实际上第一次创建的提醒（14:55）已被删除
- 造成用户困惑和不信任

## 根本原因

### 原因 1：tool_call_limit 设置过高

```python
# agent/agno_agent/agents/__init__.py (修复前)
reminder_detect_agent = Agent(
    ...
    tool_call_limit=5,  # ❌ 允许连续调用 5 次工具
    ...
)
```

**问题**：
- Agent 可以在一次执行中连续调用 5 次 `reminder_tool`
- 导致：创建 → 查询 → 删除 → 查询 → 删除 的连锁反应
- LLM 误以为需要"清理"或"验证"提醒

### 原因 2：没有操作组合限制

工具层面没有限制操作组合，允许任意顺序调用 create/list/delete。

## 解决方案

### 修复 1：在工具层面限制操作组合

```python
# agent/agno_agent/tools/reminder_tools.py (新增)
def _check_operation_allowed(action: str) -> tuple[bool, str]:
    """
    检查操作是否允许，防止 create→list→delete 循环
    
    规则：
    - create 可以多次调用（支持多任务）
    - create 之后不能调用 list 或 delete
    - list 只能调用一次
    - delete 只能调用一次
    """
```

**效果**：
- 支持多任务：用户说"9点开会，3点喝水"可以创建 2 个提醒
- 防止循环：create 之后调用 list/delete 会被拒绝
- 在代码层面强制执行，不依赖 LLM 遵守规则

### 修复 2：调整 tool_call_limit

```python
# agent/agno_agent/agents/__init__.py (修复后)
reminder_detect_agent = Agent(
    ...
    tool_call_limit=3,  # ✅ 支持多任务，但工具层面会阻止循环
    ...
)
```

### 修复 3：更新 Instructions

```
## 重要：操作规则（系统强制执行）
- 创建操作（create）可以多次调用，支持一条消息创建多个提醒
- 查询操作（list）只能调用一次
- 删除操作（delete）只能调用一次
- **禁止在创建提醒后调用 list 或 delete**（系统会自动拒绝并返回错误）

## 多任务处理
当用户在一条消息中要求创建多个提醒时，依次调用多次 create
```

## 预期效果

### 场景 1：单个提醒
- 输入："过一会提醒我站起来"
- 行为：调用一次 create → 结束
- 响应时间：< 5 秒

### 场景 2：多个提醒
- 输入："明天9点提醒我开会，下午3点提醒我喝水"
- 行为：调用两次 create → 结束
- 响应时间：< 10 秒

### 场景 3：循环尝试（被阻止）
- 输入："过一会提醒我站起来"
- Agent 尝试：create → list
- 系统响应：list 被拒绝，返回错误"不能在创建提醒后查询列表"
- 结果：只有 create 成功，循环被阻止

## 相关文件

- `agent/agno_agent/agents/__init__.py` - Agent 定义
- `agent/prompt/agent_instructions_prompt.py` - Instructions
- `agent/agno_agent/tools/reminder_tools.py` - 提醒工具（新增操作组合检查）
- `agent/agno_agent/workflows/prepare_workflow.py` - PrepareWorkflow

## 总结

这是一个典型的 **Agent 行为失控** 问题，通过两层防护解决：

1. **工具层面**：`_check_operation_allowed()` 强制限制操作组合
2. **Instructions 层面**：明确告知 LLM 规则

这种"双保险"设计确保即使 LLM 不遵守规则，系统也能在代码层面阻止危险行为。
