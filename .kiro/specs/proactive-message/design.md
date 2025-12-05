# Design Document: Proactive Message Feature

## Overview

主动消息功能（Proactive Message）允许 AI 角色在用户没有主动发起对话的情况下，根据之前的对话规划，主动向用户发送消息。该功能增强了角色的主动性和互动性，使对话体验更加自然。

### 核心流程

```
对话结束 → 规划未来消息 → 定时触发 → 生成主动消息 → 发送消息 → 更新状态
```

### 关键组件

| 组件 | 职责 | 对应需求 |
|------|------|----------|
| FutureMessageResponse Schema | 定义主动消息响应结构 | FR-036 |
| FutureMessageQueryRewriteAgent | 基于规划行动进行问题重写 | FR-036 |
| FutureMessageContextRetrieveAgent | 检索与规划行动相关的上下文 | FR-036 |
| FutureMessageChatAgent | 生成主动消息内容 | FR-038 |
| FutureMessageWorkflow | 编排主动消息生成流程 | FR-036, FR-038 |
| ProactiveMessageTriggerService | 定时触发主动消息 | FR-037 |

## Architecture

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    定时触发服务                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ProactiveMessageTriggerService                          │   │
│  │  - 每 1.5 小时检查一次                                    │   │
│  │  - 查询 future.timestamp 已到达的会话                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FutureMessageWorkflow                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Step 1: QueryRewrite                                    │   │
│  │  - 基于 future.action 生成检索查询词                      │   │
│  │                                                          │   │
│  │  Step 2: ContextRetrieve                                 │   │
│  │  - 检索角色设定、用户资料、知识库                          │   │
│  │                                                          │   │
│  │  Step 3: ChatResponse                                    │   │
│  │  - 生成主动消息内容                                       │   │
│  │  - 处理关系变化                                           │   │
│  │  - 规划下一次主动消息                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    消息发送                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  写入 outputmessages 队列 → Connector 层发送              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 数据流

```
session_state (包含 future.action)
        ↓
FutureMessageQueryRewriteAgent
        ↓ query_rewrite 结果
FutureMessageContextRetrieveAgent
        ↓ context_retrieve 结果
FutureMessageChatAgent
        ↓ FutureMessageResponse
处理关系变化 + 规划下一次主动消息
        ↓
MultiModalResponses → outputmessages
```

## Components and Interfaces

### 1. FutureMessageQueryRewriteAgent

**职责**: 基于规划行动进行问题重写，生成检索查询词

**接口**:
```python
# 输入
message: str  # 渲染后的 user prompt
session_state: Dict[str, Any]  # 包含 future.action

# 输出
QueryRewriteResponse:
    InnerMonologue: str
    CharacterSettingQueryQuestion: str
    CharacterSettingQueryKeywords: str
    UserProfileQueryQuestion: str
    UserProfileQueryKeywords: str
    CharacterKnowledgeQueryQuestion: str
    CharacterKnowledgeQueryKeywords: str
```

### 2. FutureMessageContextRetrieveAgent

**职责**: 调用 context_retrieve_tool 检索与规划行动相关的上下文

**接口**:
```python
# 输入
message: str  # 检索请求
session_state: Dict[str, Any]

# 输出
context_retrieve 结果写入 session_state
```

### 3. FutureMessageChatAgent

**职责**: 基于角色人设和规划行动生成主动消息内容

**接口**:
```python
# 输入
message: str  # 渲染后的 user prompt
session_state: Dict[str, Any]

# 输出
FutureMessageResponse:
    InnerMonologue: str
    MultiModalResponses: List[MultiModalResponse]
    ChatCatelogue: str
    RelationChange: RelationChangeModel
    FutureResponse: FutureResponseModel
```

### 4. FutureMessageWorkflow

**职责**: 编排主动消息生成的完整流程

**接口**:
```python
class FutureMessageWorkflow:
    def run(self, session_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行主动消息生成流程
        
        Returns:
            {
                "content": FutureMessageResponse,
                "session_state": 更新后的 session_state
            }
        """
```

### 5. ProactiveMessageTriggerService

**职责**: 定时检查并触发主动消息

**接口**:
```python
class ProactiveMessageTriggerService:
    def check_and_trigger(self) -> None:
        """检查并触发到期的主动消息"""
    
    def _get_due_conversations(self) -> List[Dict]:
        """查询 future.timestamp 已到达的会话"""
    
    def _trigger_proactive_message(self, conversation: Dict) -> None:
        """触发单个会话的主动消息"""
```

## Data Models

### FutureMessageResponse Schema

```python
class FutureMessageResponse(BaseModel):
    """主动消息响应模型"""
    
    InnerMonologue: str = Field(
        default="",
        description="角色的内心独白"
    )
    
    MultiModalResponses: List[MultiModalResponse] = Field(
        default_factory=list,
        description="角色的回复，可能包含多种类型（text/voice/photo）"
    )
    
    ChatCatelogue: str = Field(
        default="否",
        description="是否涉及角色所熟悉的知识"
    )
    
    RelationChange: RelationChangeModel = Field(
        default_factory=RelationChangeModel,
        description="关系变化"
    )
    
    FutureResponse: FutureResponseModel = Field(
        default_factory=FutureResponseModel,
        description="下一次主动消息的规划"
    )
```

### MultiModalResponse Schema

```python
class MultiModalResponse(BaseModel):
    """多模态响应模型"""
    
    type: Literal["text", "voice", "photo"] = Field(
        description="消息类型"
    )
    
    content: str = Field(
        default="",
        description="消息内容"
    )
    
    emotion: Optional[str] = Field(
        default=None,
        description="情感（用于语音）"
    )
```

### FutureResponseModel Schema

```python
class FutureResponseModel(BaseModel):
    """未来消息规划模型"""
    
    FutureResponseTime: str = Field(
        default="",
        description="下一次主动消息的触发时间"
    )
    
    FutureResponseAction: str = Field(
        default="无",
        description="下一次主动消息的规划行动"
    )
```

### session_state 中的 future 结构

```python
session_state["conversation"]["conversation_info"]["future"] = {
    "timestamp": Optional[int],  # 触发时间戳
    "action": Optional[str],     # 规划行动
    "proactive_times": int       # 连续主动消息次数
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Schema 结构完整性

*For any* FutureMessageResponse 对象，该对象应包含所有必需字段（InnerMonologue、MultiModalResponses、RelationChange、FutureResponse），且 FutureResponse 应包含 FutureResponseTime 和 FutureResponseAction 子字段，MultiModalResponse 的 type 字段只接受 "text"、"voice"、"photo" 三种值。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: Workflow 执行顺序

*For any* FutureMessageWorkflow 执行，应按 QueryRewrite → ContextRetrieve → ChatResponse 的顺序执行，且每个步骤的输出应正确传递到下一步骤的 session_state 中。

**Validates: Requirements 3.1, 3.3**

### Property 3: Workflow 返回结构

*For any* FutureMessageWorkflow 执行完成后，返回值应包含 "content" 和 "session_state" 两个键，且 session_state 中应包含 "MultiModalResponses" 字段。

**Validates: Requirements 3.2, 3.4**

### Property 4: 关系值边界约束

*For any* 关系变化处理，更新后的 closeness 和 trustness 值应在 [0, 100] 范围内，即使输入的变化值导致结果超出范围。

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 5: 主动消息计数递增

*For any* 主动消息发送成功后，proactive_times 应增加 1。

**Validates: Requirements 5.1**

### Property 6: 概率命中时的状态设置

*For any* 概率命中的情况（随机数 < 0.15^(n+1)），future.timestamp 应被设置为解析后的时间戳，future.action 应被设置为 FutureResponseAction 的值。

**Validates: Requirements 5.3, 5.4**

### Property 7: 概率未命中时的状态清除

*For any* 概率未命中的情况（随机数 >= 0.15^(n+1)），future.timestamp 和 future.action 应被设置为 None。

**Validates: Requirements 5.5**

### Property 8: Prompt 模板渲染

*For any* Prompt 模板渲染，渲染后的内容应包含 CONTEXTPROMPT_规划行动 的内容，且当 session_state 缺少字段时不应抛出异常。

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 9: 主动消息输出有效性

*For any* 主动消息生成成功后，MultiModalResponses 列表应非空，且每个元素的 type 字段应为有效值。

**Validates: Requirements 8.2**

## Error Handling

### 1. Prompt 渲染错误

当 session_state 缺少 Prompt 模板所需字段时：
- 记录 WARNING 级别日志
- 使用默认 Prompt 或空字符串替代
- 不中断流程执行

```python
try:
    rendered_prompt = template.format(**session_state)
except KeyError as e:
    logger.warning(f"Prompt 渲染缺少字段: {e}")
    rendered_prompt = default_prompt
```

### 2. Agent 执行错误

当 Agent 执行失败时：
- 依赖 Agno 内置重试机制
- 最终失败时记录 ERROR 级别日志
- 返回空结果，不影响其他流程

### 3. 时间解析错误

当 FutureResponseTime 无法解析时：
- 记录 WARNING 级别日志
- 设置 future.timestamp 为 None
- 不设置下一次主动消息

### 4. 关系值越界

当关系变化导致值越界时：
- 自动限制在 [0, 100] 范围内
- 不记录日志（正常业务逻辑）

## Testing Strategy

### 单元测试

1. **Schema 验证测试**
   - 测试 FutureMessageResponse 的字段完整性
   - 测试 MultiModalResponse 的类型约束
   - 测试 FutureResponseModel 的默认值

2. **关系变化处理测试**
   - 测试正常范围内的变化
   - 测试边界值（0 和 100）
   - 测试越界值的限制

3. **概率控制测试**
   - Mock random.random() 测试概率命中
   - Mock random.random() 测试概率未命中
   - 测试 proactive_times 递增

4. **Prompt 渲染测试**
   - 测试完整 session_state 的渲染
   - 测试缺少字段时的降级处理

### 属性测试（Property-Based Testing）

使用 **Hypothesis** 库进行属性测试：

1. **Property 1: Schema 结构完整性**
   - 生成随机 FutureMessageResponse 对象
   - 验证所有必需字段存在
   - 验证 type 字段值有效

2. **Property 4: 关系值边界约束**
   - 生成随机 closeness/trustness 初始值和变化值
   - 验证结果在 [0, 100] 范围内

3. **Property 5: 主动消息计数递增**
   - 生成随机初始 proactive_times
   - 验证执行后增加 1

4. **Property 6 & 7: 概率控制状态设置**
   - Mock random.random() 返回固定值
   - 验证状态设置/清除正确

### 集成测试

1. **Workflow 端到端测试**
   - 构造完整 session_state
   - 执行 FutureMessageWorkflow
   - 验证返回结构和状态更新

2. **触发服务测试**
   - Mock DAO 层返回到期会话
   - 验证 Workflow 被正确调用
   - 验证消息写入 outputmessages

