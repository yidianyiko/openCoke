# 提醒系统多任务支持方案

## 最终方案：统一的 batch 操作

### 设计思路

**核心原则**：`tool_call_limit=1`，通过 `batch` 操作一次调用处理任意数量、任意类型的操作组合.

### 支持的场景

| 场景 | 操作 | 示例 |
|------|------|------|
| 单个创建 | create | "明天9点提醒我开会" |
| 多个创建 | batch | "设置三个提醒：8点起床、12点吃饭、6点下班" |
| 单个删除 | delete | "删除开会提醒" |
| 单个更新 | update | "把开会改到下午3点" |
| 混合操作 | batch | "删除提醒1，把提醒2改到明天，再加一个新提醒" |

### 实现

#### 1. batch 操作

```python
@tool(description="""...
## 批量操作 (action="batch")
- operations: JSON字符串，包含操作列表
  格式: '[{"action":"delete","reminder_id":"xxx"},{"action":"create","title":"喝水","trigger_time":"..."}]'
""")
def reminder_tool(
    action: str,
    ...
    operations: Optional[str] = None
) -> dict:
```

#### 2. _batch_operations 函数

- 解析 JSON 字符串
- 限制最大操作数（MAX_BATCH_SIZE=20）
- 按顺序执行每个操作（create/update/delete）
- 收集所有结果
- 返回详细的批量结果

### 使用示例

**用户输入**："把开会提醒删掉，把喝水提醒改到下午5点，再帮我加一个运动提醒"

**Agent 调用**：
```json
{
  "action": "batch",
  "operations": "[{\"action\":\"delete\",\"reminder_id\":\"xxx\"},{\"action\":\"update\",\"reminder_id\":\"yyy\",\"trigger_time\":\"2025年12月24日17时00分\"},{\"action\":\"create\",\"title\":\"运动\",\"trigger_time\":\"2025年12月24日19时00分\"}]"
}
```

**返回结果**：
```json
{
  "ok": true,
  "results": [...],
  "summary": {
    "total": 3,
    "success": 3,
    "created": 1,
    "updated": 1,
    "deleted": 1,
    "failed": 0
  },
  "message": "批量操作完成：创建1个提醒，更新1个提醒，删除1个提醒"
}
```

### 优势

| 特性 | 说明 |
|------|------|
| 防止循环 | tool_call_limit=1，彻底杜绝 |
| 支持任意组合 | create + update + delete 任意组合 |
| 支持任意数量 | 最多 20 个操作 |
| 详细反馈 | 返回每个操作的状态 |
| 原子性 | 每个操作独立执行，部分失败不影响其他 |

### 操作规则

```
单个操作：
- create: 创建单个提醒
- update: 更新单个提醒
- delete: 删除单个提醒
- list: 查询提醒列表

批量操作：
- batch: 执行多个操作的任意组合

限制：
- 只能调用一次工具
- batch 操作内部可包含任意数量的 create/update/delete
```

## 相关文件

- `agent/agno_agent/tools/reminder_tools.py` - batch 操作和 _batch_operations 函数
- `agent/agno_agent/agents/__init__.py` - tool_call_limit=1
- `agent/prompt/agent_instructions_prompt.py` - Instructions
