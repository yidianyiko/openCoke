# Design Document: Agno Migration

## Overview

本设计文档描述将现有自研 Agent 框架迁移至 Agno 框架的技术方案。迁移采用分层策略：
- **Framework 层**：由 Agno 框架完全替代
- **Agent 层**：重构为 Agno Agent，使用 Pydantic Schema 定义输出格式
- **Runner 层**：适配修改，调用 Agno Workflow 并控制消息打断
- **Connector/DAO 层**：保持不变

详细设计参见：[迁移计划文档](../../../doc/agno-demo/agno-migration-plan.md)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Connector 层 (保留不变)                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ ecloud_input│    │   Adapter   │    │ecloud_output│         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Runner 层 (适配修改)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  context_prepare() → 构建 Agno session_state            │   │
│  │  main_handler() → 调用 Workflow，处理消息打断            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agno Workflow 层 (新建)                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  PrepareWorkflow: QueryRewrite + ReminderDetect +       │   │
│  │                   ContextRetrieve                        │   │
│  │  ChatWorkflow: ChatResponseAgent                         │   │
│  │  PostAnalyzeWorkflow: PostAnalyzeAgent                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agno Framework (替换自研)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ agno.agent  │  │ agno.models │  │ agno.tools  │             │
│  │ Agent 基类  │  │ DeepSeek    │  │ Tool 装饰器 │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Pydantic Schemas

```
qiaoyun/agno_agent/schemas/
├── query_rewrite_schema.py    # QueryRewriteResponse
├── chat_response_schema.py    # ChatResponse, MultiModalResponse, RelationChangeModel
└── post_analyze_schema.py     # PostAnalyzeResponse
```

**QueryRewriteResponse**:
- InnerMonologue: str - 内心独白
- CharacterSettingQueryQuestion: str - 角色设定检索问题
- CharacterSettingQueryKeywords: str - 角色设定检索关键词
- UserProfileQueryQuestion: str - 用户资料检索问题
- UserProfileQueryKeywords: str - 用户资料检索关键词
- CharacterKnowledgeQueryQuestion: str - 角色知识检索问题
- CharacterKnowledgeQueryKeywords: str - 角色知识检索关键词

**ChatResponse**:
- InnerMonologue: str - 内心独白
- MultiModalResponses: List[MultiModalResponse] - 多模态回复列表
- ChatCatelogue: str - 对话分类
- RelationChange: RelationChangeModel - 关系变化
- FutureResponse: FutureResponseModel - 未来消息规划

**PostAnalyzeResponse**:
- CharacterPublicSettings: str - 角色公开设定更新
- CharacterPrivateSettings: str - 角色私有设定更新
- UserSettings: str - 用户资料更新
- UserRealName: str - 用户真名
- RelationDescription: str - 关系描述更新

### 2. Tools

```
qiaoyun/agno_agent/tools/
├── context_retrieve_tool.py   # 向量检索工具
└── reminder_tools.py          # 提醒管理工具
```

**context_retrieve_tool**:
- 输入：character_setting_query, user_profile_query, character_knowledge_query, character_id, user_id
- 输出：dict 包含 character_global, character_private, user, character_knowledge

**reminder_tool**:
- 输入：action (create/update/delete/list), user_id, reminder_id, title, trigger_time, recurrence_type
- 输出：dict 包含 ok, reminder_id/reminders/error

### 3. Agents

```
qiaoyun/agno_agent/agents.py   # 模块级预创建所有 Agent
```

| Agent | Model | Response Model | Tools |
|-------|-------|----------------|-------|
| query_rewrite_agent | DeepSeek | QueryRewriteResponse | - |
| reminder_detect_agent | DeepSeek | - | reminder_tool |
| context_retrieve_agent | DeepSeek | - | context_retrieve_tool |
| chat_response_agent | DeepSeek | ChatResponse | - |
| post_analyze_agent | DeepSeek | PostAnalyzeResponse | - |

### 4. Workflows

```
qiaoyun/agno_agent/workflows/
├── prepare_workflow.py        # 准备阶段
├── chat_workflow.py           # 回复生成
└── post_analyze_workflow.py   # 后处理
```

**执行流程**:
```
Runner 层:
  1. context_prepare() → session_state
  2. PrepareWorkflow.run() → 更新 session_state
  3. 检测新消息 → 如有则 rollback
  4. ChatWorkflow.run() → 生成回复
  5. 发送消息，每条后检测新消息
  6. PostAnalyzeWorkflow.run() → 后处理（可被跳过）
```

### 5. Runner 层接口

**context_prepare(user, character, conversation, relation) -> dict**:
- 将 MongoDB 数据转换为 session_state
- ObjectId 转字符串
- 设置所有 Prompt 模板所需字段的默认值

**main_handler()**:
- 调用三个 Workflow
- 在 Phase 1 后和每条消息发送后检测新消息
- 处理 rollback 逻辑

## Data Models

### session_state 结构

```python
session_state = {
    "user": {
        "_id": str,  # ObjectId 转字符串
        "name": str,
        "platforms": {"wechat": {"nickname": str}}
    },
    "character": {
        "_id": str,
        "name": str,
        "platforms": {"wechat": {"nickname": str}},
        "user_info": {"description": str, "status": {...}}
    },
    "conversation": {
        "_id": str,
        "conversation_info": {
            "time_str": str,
            "chat_history_str": str,
            "input_messages_str": str,
            "chat_history": list,
            "future": {"timestamp": int, "action": str}
        }
    },
    "relation": {
        "_id": str,
        "relationship": {"closeness": int, "trustness": int, "dislike": int},
        "user_info": {"realname": str, "description": str},
        "character_info": {"longterm_purpose": str, "attitude": str}
    },
    # Workflow 执行过程中添加的字段
    "query_rewrite": {...},      # QueryRewriteAgent 输出
    "context_retrieve": {...},   # ContextRetrieveAgent 输出
    "MultiModalResponses": [...] # ChatResponseAgent 输出
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Agent 输出格式一致性
*For any* 有效的 session_state 输入，Agent 执行完成后返回的数据 SHALL 符合对应的 Pydantic Schema 定义，可通过 Schema 验证无错误
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: context_retrieve_tool 返回结构完整性
*For any* 有效的查询参数，context_retrieve_tool 返回的 dict SHALL 包含 character_global, character_private, user, character_knowledge 字段
**Validates: Requirements 3.1**

### Property 3: reminder_tool CRUD 一致性
*For any* 创建的提醒，执行 create 后立即执行 list SHALL 能找到该提醒；执行 delete 后立即执行 list SHALL 找不到该提醒
**Validates: Requirements 3.2**

### Property 4: 时间解析正确性
*For any* 相对时间字符串（如"30分钟后"、"明天"），reminder_tool 解析后的时间戳 SHALL 大于当前时间戳
**Validates: Requirements 3.3**

### Property 5: 动态 instructions 渲染完整性
*For any* 包含 Prompt 模板所需字段的 session_state，动态 instructions 函数渲染后 SHALL 不包含未替换的模板变量（如 {xxx}）
**Validates: Requirements 4.5**

### Property 6: PrepareWorkflow 状态累积
*For any* 有效的初始 session_state，PrepareWorkflow 执行后返回的 session_state SHALL 包含 query_rewrite 和 context_retrieve 字段
**Validates: Requirements 5.1**

### Property 7: Workflow 状态传递
*For any* Workflow 执行过程中对 session_state 的修改，后续步骤 SHALL 能访问到修改后的值
**Validates: Requirements 5.4**

### Property 8: ObjectId 序列化
*For any* 包含 MongoDB ObjectId 的原始数据，context_prepare 转换后的 session_state SHALL 可以成功进行 JSON 序列化
**Validates: Requirements 6.1**

### Property 9: 默认值完整性
*For any* 最小化的输入数据（只包含必需字段），context_prepare 输出的 session_state SHALL 包含所有 Prompt 模板所需的字段路径
**Validates: Requirements 6.2**

### Property 10: 消息合并正确性
*For any* rollback 场景下的多条待处理消息，合并后的上下文 SHALL 包含所有消息的内容
**Validates: Requirements 7.2**

### Property 11: 已发送消息记录
*For any* rollback 发生时已发送的消息，这些消息 SHALL 被记录到对话历史中
**Validates: Requirements 7.4**

## Error Handling

| 错误场景 | 处理方式 |
|---------|---------|
| LLM 调用失败 | Agno 内置重试机制，最终失败后抛出异常 |
| Tool 执行失败 | 返回 {"ok": False, "error": "错误信息"} |
| Prompt 渲染缺少字段 | 记录警告日志，使用原始模板 |
| Workflow 执行异常 | Runner 层捕获异常，记录错误日志，设置 is_failed 标志 |
| 新消息打断 | 设置 is_rollback 标志，跳过后续步骤 |

## Testing Strategy

### 单元测试

| 测试对象 | 测试内容 |
|---------|---------|
| Pydantic Schema | 验证字段定义、类型约束、默认值 |
| context_retrieve_tool | 验证返回结构、字段完整性 |
| reminder_tool | 验证 CRUD 操作、时间解析、周期类型 |
| context_prepare | 验证 ObjectId 转换、默认值设置 |
| 动态 instructions | 验证模板渲染、缺少字段处理 |

### Property-Based Testing

使用 **hypothesis** 库进行属性测试：

| Property | 测试策略 |
|----------|---------|
| Property 1 | 生成随机 session_state，验证 Agent 输出符合 Schema |
| Property 3 | 生成随机提醒数据，验证 create-list-delete-list 一致性 |
| Property 4 | 生成各种相对时间字符串，验证解析结果 |
| Property 8 | 生成包含 ObjectId 的嵌套 dict，验证 JSON 序列化 |
| Property 9 | 生成最小化输入，验证输出包含所有必需字段 |

### 集成测试

| 测试场景 | 验证内容 |
|---------|---------|
| 完整对话流程 | PrepareWorkflow → ChatWorkflow → PostAnalyzeWorkflow |
| 消息打断流程 | 模拟新消息到达，验证 rollback 行为 |
| 提醒创建流程 | 端到端验证提醒识别和创建 |
