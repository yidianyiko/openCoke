# Agent Prompt 规范

本文档定义了 Agno Agent 的标准化配置模式，所有 Agent 应遵循此规范以保持一致性。

## 设计原则

基于 Agno 框架最佳实践，Agent 配置采用 **三层分离** 模式：

| 层 | 配置位置 | 职责 | 示例 |
|---|---------|------|------|
| **角色身份** | `DESCRIPTION_XXX` | 你是谁 | "你是一个智能调度助手..." |
| **决策逻辑** | `INSTRUCTIONS_XXX` | 怎么做决策 | "当满足条件X时，设为 true" |
| **格式约束** | Schema `Field(description=...)` | 输出什么格式 | "格式：'xxx-xxx'层级，示例：..." |

## 文件结构

```
agent/
├── prompt/
│   └── agent_instructions_prompt.py    # 所有 DESCRIPTION_XXX 和 INSTRUCTIONS_XXX
├── agno_agent/
│   ├── schemas/
│   │   └── xxx_schema.py               # Pydantic Schema，含 Field description
│   └── agents/
│       └── __init__.py                 # Agent 实例化，引用 prompt 常量
```

## 命名规范

### 常量命名

```python
# agent_instructions_prompt.py

# 角色身份
DESCRIPTION_ORCHESTRATOR = "..."
DESCRIPTION_CHAT_RESPONSE = "..."

# 决策逻辑
INSTRUCTIONS_ORCHESTRATOR = "..."
INSTRUCTIONS_CHAT_RESPONSE = "..."
```

### Schema 字段命名

- **使用 `snake_case`**（Agno 框架推荐）
- 示例：`inner_monologue`, `need_context_retrieve`, `context_retrieve_params`

## DESCRIPTION 编写规范

角色身份描述，简洁说明 Agent 的核心职责。

```python
DESCRIPTION_ORCHESTRATOR = "你是一个智能调度助手，负责理解用户意图并做出调度决策。"
```

**要求**：
- 一句话概括
- 说明"你是谁"和"做什么"
- 不包含具体规则

## INSTRUCTIONS 编写规范

决策逻辑，说明如何做出决策。

```python
INSTRUCTIONS_ORCHESTRATOR = """理解用户消息意图，做出调度决策。

## 决策规则

### need_context_retrieve
- 默认 true
- 设为 false：纯提醒操作（取消/查看/删除提醒）

### need_reminder_detect
设为 true（满足任一）：
1. 包含提醒关键词：提醒我、闹钟、定时、别忘了
2. 表达提醒意图（即使无关键词）：明天叫我起床
3. 上下文延续：正在补充提醒信息

设为 false：
1. 普通聊天，不涉及提醒
2. 叙述事实：我今天取消了会议（不是请求）

### context_retrieve_params
根据用户消息内容生成检索参数，参考 Schema 中的格式说明。

### inner_monologue
推测用户意图，简述调度决策理由。"""
```

**要求**：
- 只包含决策规则，不重复格式说明
- 使用 Markdown 结构化
- 按字段名分节
- 提供正例和反例

## Schema Field Description 编写规范

格式约束，在 Pydantic Field 的 description 中定义。

```python
class OrchestratorResponse(BaseModel):
    inner_monologue: str = Field(
        default="",
        description=(
            "角色的内心独白，推测用户意图的思考过程。"
            "长度：20-50字。"
            "示例：'用户想设置一个明天早上的提醒，需要调用提醒检测'"
        ),
    )
    
    character_setting_query: str = Field(
        default="",
        description=(
            "角色设定检索语句。"
            "格式：使用'xxx-xxx'层级格式。"
            "示例：'日常习惯-作息'、'性格特点-社交'"
        ),
    )
```

**要求**：
- 包含三部分：**功能说明 + 格式要求 + 示例**
- 使用括号拼接多行字符串
- 示例要具体、可直接使用

## Agent 实例化规范

```python
# agents/__init__.py

from agent.prompt.agent_instructions_prompt import (
    DESCRIPTION_ORCHESTRATOR,
    INSTRUCTIONS_ORCHESTRATOR,
)
from agent.agno_agent.schemas.orchestrator_schema import OrchestratorResponse

orchestrator_agent = Agent(
    id="orchestrator-agent",
    name="OrchestratorAgent",
    model=create_deepseek_model(),
    description=DESCRIPTION_ORCHESTRATOR,      # 从 prompt 导入
    instructions=get_orchestrator_instructions(),
    output_schema=OrchestratorResponse,
    use_json_mode=True,
    markdown=False,
)
```

**要求**：
- 所有文本常量从 `agent_instructions_prompt.py` 导入
- 不允许在 `__init__.py` 中硬编码 magic string
- Agent 注释说明设计原则

## 标准化 Agent 示例

以 OrchestratorAgent 为参考实现：

### 1. prompt/agent_instructions_prompt.py

```python
# ========== OrchestratorAgent ==========
# 设计原则：
# - DESCRIPTION: 角色身份（你是谁）
# - INSTRUCTIONS: 决策逻辑（怎么做决策）
# - Schema Field.description: 格式约束（输出什么格式）

DESCRIPTION_ORCHESTRATOR = "你是一个智能调度助手，负责理解用户意图并做出调度决策。"

INSTRUCTIONS_ORCHESTRATOR = """理解用户消息意图，做出调度决策。
...
"""
```

### 2. schemas/orchestrator_schema.py

```python
"""
OrchestratorResponse Schema

设计原则：
- Schema Field.description 负责格式约束（字段类型、格式要求、示例）
- Instructions 负责决策逻辑（什么时候设 true/false）
"""

class OrchestratorResponse(BaseModel):
    inner_monologue: str = Field(
        default="",
        description=(
            "角色的内心独白，推测用户意图的思考过程。"
            "长度：20-50字。"
            "示例：'用户想设置一个明天早上的提醒，需要调用提醒检测'"
        ),
    )
    # ... 其他字段
```

### 3. agents/__init__.py

```python
# OrchestratorAgent - V2 架构核心，语义理解 + 调度决策
# 设计原则（参考 Agno 框架标准）：
# - description: 角色身份（你是谁）
# - instructions: 决策逻辑（怎么做决策）
# - output_schema: 格式约束（输出什么格式）
orchestrator_agent = Agent(
    id="orchestrator-agent",
    name="OrchestratorAgent",
    model=create_deepseek_model(),
    description=DESCRIPTION_ORCHESTRATOR,
    instructions=get_orchestrator_instructions(),
    output_schema=OrchestratorResponse,
    use_json_mode=True,
    markdown=False,
)
```

## 检查清单

新增或修改 Agent 时，确认以下项目：

- [ ] `DESCRIPTION_XXX` 在 `agent_instructions_prompt.py` 中定义
- [ ] `INSTRUCTIONS_XXX` 在 `agent_instructions_prompt.py` 中定义
- [ ] Schema 字段使用 `snake_case` 命名
- [ ] Schema Field description 包含：功能说明 + 格式要求 + 示例
- [ ] Agent 实例化使用导入的常量，无 magic string
- [ ] 代码注释说明设计原则

## 参考

- [Agno Framework Documentation](https://docs.agno.com)
- 参考实现：`OrchestratorAgent`
