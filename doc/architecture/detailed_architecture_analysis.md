# Coke Project 详细架构分析文档

> 本文档基于 Agno 框架重构后的代码库进行深入分析
> 
> 文档版本：v2.7  
> 日期：2025-12-11  
> 更新：消息处理机制优化 - 安全锁释放、乐观锁更新、重试机制、hold 状态恢复

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构设计](#2-整体架构设计)
3. [目录结构详解](#3-目录结构详解)
4. [核心模块分析](#4-核心模块分析)
5. [Agno Workflow 详解](#5-agno-workflow-详解)
6. [数据流与消息流](#6-数据流与消息流)
7. [数据库设计](#7-数据库设计)
8. [关键技术实现](#8-关键技术实现)
9. [部署与运维](#9-部署与运维)
10. [Agent 提示词清单](#10-agent-提示词清单)
11. [部署与运维](#11-部署与运维)

---

## 1. 项目概述

### 1.1 项目定位

Coke Project 是一个**微信Bot虚拟人解决方案**，实现了具有记忆、情感、多模态交互能力的AI虚拟角色.

### 1.2 核心特性

- **Agno 框架驱动**：采用 Agno 2.x 作为核心 Agent 框架，支持 Workflow 编排
- **全链路异步化**：基于 asyncio 的真正并发处理，多用户消息并行处理
- **通信与算法解耦**：支持延迟回复、主动回复、一回多、多回一
- **全类型多模态能力**：文本、图片、语音
- **多库多路召回记忆体**：向量检索 + 关键词检索的混合召回
- **消息打断机制**：在 Workflow 阶段间检测新消息，避免对话上下文割裂
- **微信Bot对接层框架**：支持 ecloud、terminal 等多种接入方式

### 1.3 技术栈

| 类别 | 技术选型 | 版本 |
|------|----------|------|
| Agent 框架 | Agno | >= 2.0.0 |
| LLM 模型 | DeepSeek | - |
| Web 框架 | Flask | 3.1.0 |
| 数据库 | MongoDB + pymongo | 4.12.0 |
| 语音识别 | 阿里云 NLS | 1.1.0 |
| 语音合成 | MiniMax | - |
| Embedding | DashScope | 1.23.2 |
| 对象存储 | 阿里云 OSS | - |
| OpenAI SDK | openai | 1.75.2 |

---

## 2. 整体架构设计

### 2.1 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                      外部平台层                               │
│              (微信、E云管家等)                                │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    Connector 连接器层                         │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │ ecloud       │  │ terminal     │                        │
│  │ (E云管家)     │  │ (终端测试)    │                        │
│  └──────────────┘  └──────────────┘                        │
│         Input/Output Handler + Message Adapter              │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                   Entity & DAO 数据层                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  MongoDB Collections:                                │   │
│  │  • inputmessages  • outputmessages                   │   │
│  │  • users          • conversations                    │   │
│  │  • relations      • embeddings                       │   │
│  │  • reminders      • locks                            │   │
│  └──────────────────────────────────────────────────────┘   │
│  DAO层: UserDAO, ConversationDAO, ReminderDAO, LockManager  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                   Runner 业务处理层                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Main Handler │  │ Background   │  │ Hardcode     │      │
│  │ (主消息处理)  │  │ Handler      │  │ Handler      │      │
│  │              │  │ (后台任务)    │  │ (管理指令)    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         Context Preparation + Workflow Orchestration        │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                 Agno Workflow 编排层 (V2)                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  PrepareWorkflow (Phase 1):                          │   │
│  │    OrchestratorAgent → context_retrieve_tool         │   │
│  │                     → ReminderDetectAgent (按需)     │   │
│  │                                                       │   │
│  │  StreamingChatWorkflow (Phase 2):                     │   │
│  │    ChatResponseAgent → MultiModalResponses (流式)     │   │
│  │    (V2: 不再输出 RelationChange/FutureResponse)       │   │
│  │                                                       │   │
│  │  PostAnalyzeWorkflow (Phase 3):                       │   │
│  │    PostAnalyzeAgent → 更新关系和记忆                   │   │
│  │    (V2: 新增 RelationChange/FutureResponse 处理)      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    Agno Agent/Tool 层                        │
│  ┌──────────────┐  ┌──────────────────────────────────┐     │
│  │ Agents       │  │ Tools:                           │     │
│  │ (DeepSeek)   │  │ • context_retrieve_tool          │     │
│  │              │  │ • reminder_tools                 │     │
│  │              │  │ • voice_tools  • image_tools     │     │
│  └──────────────┘  └──────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心设计模式

#### 2.2.1 消息队列模式 (V2.7 优化)

- **输入队列**：`inputmessages` 集合，状态流转：`pending → handled/failed/hold`（V2.7 去掉 handling）
- **输出队列**：`outputmessages` 集合，状态流转：`pending → handled/failed`
- **轮询机制**：独立的 input/output handler 持续轮询数据库
- **V2.7 新增**：乐观锁更新 `update_message_status_safe()`，防止并发更新冲突

#### 2.2.2 Agno Workflow 分段执行模式

- 将对话处理拆分为三个 Phase，由 Runner 层控制分段执行
- 在 Phase 间插入消息打断检测点
- 支持 session_state 在 Workflow 间传递

#### 2.2.3 Tool 封装模式

- 将复杂业务逻辑（向量检索、提醒管理）封装为 Agno Tool
- Agent 通过调用 Tool 完成具体功能
- Tool 负责数据访问，Workflow 保持纯净

#### 2.2.4 分布式锁模式 (V2.7 增强)

- 基于 MongoDB 实现的分布式锁
- 会话级锁定，防止同一会话的并发处理
- 支持锁超时和自动释放
- 支持同步和异步两种获取方式
- **V2.7 新增**：安全锁释放 `release_lock_safe()`，只释放属于自己且未过期的锁
- **V2.7 新增**：锁续期机制，在 Phase 2 前和每发送一条消息后续期

#### 2.2.5 异步并发模式

- 基于 asyncio 的协程并发，多 Worker 真正并行处理
- Workflow 层全面异步化，使用 `agent.arun()` 调用 LLM
- 锁管理器提供 `acquire_lock_async()` 异步方法
- 流式输出使用 `async for` 异步迭代

### 2.3 Agent 架构 V2 (编排式设计)

基于 Poke 编排式多智能体架构，采用 OrchestratorAgent 作为智能调度核心.

#### 2.3.1 OrchestratorAgent 核心职责

OrchestratorAgent 是整个系统的"调度大脑"，负责：

| 职责 | 说明 |
|------|------|
| 语义理解 | 理解用户意图，生成检索参数 |
| 意图识别 | 识别是否包含提醒、查询等特殊意图 |
| 调度决策 | 决定需要调用哪些 Tool/Agent |

**注意**：Orchestrator 只做"决策"，不做"执行".复杂任务（如提醒）交给专门的 Agent 处理.

#### 2.3.2 架构特点

| 特点 | 说明 |
|------|------|
| 智能调度 | 根据用户意图按需调用 Agent/Tool |
| 直接调用 Tool | context_retrieve_tool 直接函数调用，无需 Agent 包装 |
| 按需提醒检测 | ReminderDetectAgent 仅在检测到提醒意图时调用 |
| 流式回复 | ChatResponseAgent 支持流式输出多模态内容 |

---

## 3. 目录结构详解

### 3.1 根目录结构

```
coke/
├── agent/                              # 核心业务层 (Agno 实现)
├── alibabacloud-nls-python-sdk-dev/    # 阿里云语音识别 SDK
├── conf/                               # 配置文件
├── connector/                          # 连接器层
├── dao/                                # 数据访问层
├── doc/                                # 文档
├── entity/                             # 实体定义
├── framework/tool/                     # 底层工具封装
├── scripts/                            # 脚本工具
├── tests/                              # 测试用例
├── util/                               # 通用工具
└── requirements.txt                    # 项目依赖
```

### 3.2 agent/ - 核心业务层

```
agent/
├── agno_agent/                         # Agno Agent/Workflow/Tool 实现
│   ├── __init__.py
│   ├── agents/                         # Agent 定义 (预创建在 __init__.py)
│   │   └── future_message_agents.py    # 主动消息 Agent
│   ├── workflows/                      # Workflow 编排
│   │   ├── prepare_workflow.py         # 准备阶段
│   │   ├── chat_workflow.py            # 回复生成
│   │   ├── post_analyze_workflow.py    # 后处理分析
│   │   └── future_message_workflow.py  # 主动消息流程
│   ├── tools/                          # Tool 定义
│   │   ├── context_retrieve_tool.py    # 向量检索
│   │   ├── reminder_tools.py           # 提醒管理
│   │   ├── voice_tools.py              # 语音处理
│   │   ├── image_tools.py              # 图片处理
│   │   └── album_tools.py              # 相册管理
│   ├── schemas/                        # Pydantic 响应模型
│   │   ├── query_rewrite_schema.py
│   │   ├── chat_response_schema.py
│   │   ├── post_analyze_schema.py
│   │   └── future_message_schema.py
│   └── services/                       # 业务服务
│       └── proactive_message_trigger_service.py
│
├── runner/                             # Runner 层
│   ├── agent_handler.py                # 主消息处理器
│   ├── agent_background_handler.py     # 后台任务处理器
│   ├── agent_hardcode_handler.py       # 硬编码指令处理
│   ├── agent_runner.py                 # 并发调度入口
│   └── context.py                      # 上下文准备
│
├── prompt/                             # Prompt 模板
│   ├── system_prompt.py                # 系统 Prompt
│   ├── chat_contextprompt.py           # 上下文 Prompt
│   ├── chat_taskprompt.py              # 任务 Prompt
│   └── image_prompt.py                 # 图片 Prompt
│
├── role/                               # 角色配置
├── tool/                               # 业务工具 (voice.py, image.py)
└── util/                               # 业务工具类
```

### 3.3 connector/ - 连接器层

```
connector/
├── base_connector.py                   # 连接器基类
├── ecloud/                             # E云管家连接器
│   ├── ecloud_adapter.py               # 消息格式适配器
│   ├── ecloud_api.py                   # E云 API 封装
│   ├── ecloud_input.py                 # 入站处理 (Flask)
│   └── ecloud_output.py                # 出站处理 (轮询)
└── terminal/                           # 终端测试连接器
```

### 3.4 dao/ - 数据访问层

```
dao/
├── mongo.py                            # MongoDB 基础操作和向量检索
├── lock.py                             # 分布式锁管理
├── user_dao.py                         # 用户数据访问
├── conversation_dao.py                 # 会话数据访问
└── reminder_dao.py                     # 提醒数据访问
```

---

## 4. 核心模块分析

### 4.1 Agno Agent 定义 (V2.7 更新)

所有 Agent 在模块级别预创建（`agent/agno_agent/agents/__init__.py`），V2.7 新增 Model 层重试配置：

```python
from agno.agent import Agent
from agno.models.deepseek import DeepSeek

# V2.7 新增：创建带重试配置的 Model
def create_deepseek_model(model_id: str = "deepseek-chat"):
    """创建带重试配置的 DeepSeek Model"""
    return DeepSeek(
        id=model_id,
        max_retries=2,  # 2次重试，解决 API 限流问题
    )

query_rewrite_agent = Agent(
    id="query-rewrite-agent",
    name="QueryRewriteAgent",
    model=create_deepseek_model(),  # V2.7: 使用带重试的 Model
    instructions=get_query_rewrite_instructions,
    output_schema=QueryRewriteResponse,
)

chat_response_agent = Agent(
    id="chat-response-agent",
    model=create_deepseek_model(),  # V2.7: 使用带重试的 Model
    instructions=SYSTEMPROMPT,
    output_schema=ChatResponse,
)
```

### 4.2 Pydantic Schema 定义

```python
# schemas/chat_response_schema.py (V2 精简版)
class ChatResponse(BaseModel):
    InnerMonologue: str                    # 角色内心独白
    MultiModalResponses: List[dict]        # 多模态回复
    ChatCatelogue: str                     # 分类标签
    # 已移除: RelationChange -> PostAnalyzeResponse
    # 已移除: FutureResponse -> PostAnalyzeResponse

# schemas/post_analyze_schema.py (V2 扩展版)
class PostAnalyzeResponse(BaseModel):
    RelationChange: RelationChangeModel    # 关系变化 (从 ChatResponse 移入)
    FutureResponse: FutureResponseModel    # 未来消息规划 (从 ChatResponse 移入)
    CharacterPublicSettings: str           # 角色公开设定
    CharacterPrivateSettings: str          # 角色私有设定
    UserSettings: str                      # 用户设定
    # ... 其他记忆更新字段
```

### 4.3 Runner 层

Runner 层（`agent/runner/agent_handler.py`）负责 Workflow 调度，采用全异步设计：

```python
async def _handler():
    context = context_prepare(user, character, conversation)
    
    # Phase 1: 准备阶段 (异步)
    prepare_response = await prepare_workflow.run(input_message, context)
    
    # 检测点 1
    if is_new_message_coming_in(...):
        is_rollback = True
    
    if not is_rollback:
        # Phase 2: 生成回复 (异步流式)
        async for event in streaming_chat_workflow.run_stream(input_message, context):
            if event["type"] == "message":
                send_message(event["data"])
                if is_new_message_coming_in(...):
                    break
        
        # Phase 3: 后处理 (异步)
        await post_analyze_workflow.run(session_state=context)
```

---

## 5. Agno Workflow 详解

### 5.1 PrepareWorkflow (V2 架构 - 异步)

新架构下的 PrepareWorkflow 采用 OrchestratorAgent 智能调度，全面异步化：

```python
class PrepareWorkflow:
    """
    准备阶段 Workflow (V2 - 异步)
    
    执行流程：
    1. OrchestratorAgent - 语义理解 + 调度决策 (1次 LLM)
    2. 根据决策执行 Tool/Agent:
       - context_retrieve_tool: 直接函数调用 (0次 LLM)
       - ReminderDetectAgent: 按需调用 (0-1次 LLM)
    """
    
    async def run(self, input_message: str, session_state: dict) -> dict:
        # Step 1: Orchestrator 决策 (异步 LLM 调用)
        orchestrator_response = await orchestrator_agent.arun(
            input=self._render_prompt(input_message, session_state),
            session_state=session_state
        )
        
        decisions = orchestrator_response.content
        session_state["orchestrator"] = decisions.model_dump()
        logger.info("OrchestratorAgent 执行完成")
        
        # Step 2: 上下文检索 (直接调用 Tool，0次 LLM)
        if decisions.need_context_retrieve:
            params = decisions.context_retrieve_params
            context_result = context_retrieve_tool(
                character_setting_query=params.character_setting_query,
                # ... 其他参数
            )
            session_state["context_retrieve"] = context_result
            logger.info("context_retrieve_tool 执行完成")
        
        # Step 3: 提醒检测 (按需调用 Agent，异步 LLM 调用)
        if decisions.need_reminder_detect:
            set_reminder_session_state(session_state)
            await reminder_detect_agent.arun(
                input=input_message,
                session_state=session_state
            )
            logger.info("ReminderDetectAgent 执行完成")
        
        return {"session_state": session_state}
```

### 5.2 StreamingChatWorkflow (异步流式)

生成多模态回复，支持异步流式输出：

```python
class StreamingChatWorkflow:
    userp_template = TASKPROMPT + CONTEXTPROMPT_*  # 模板组合
    
    async def run_stream(self, input_message: str, session_state: dict):
        """异步流式生成回复"""
        rendered_userp = self._render_template(self.userp_template, session_state)
        
        # 异步流式调用 Agent (Agno v2 arun with stream=True)
        async for chunk in self.agent.arun(
            input=rendered_userp,
            session_state=session_state,
            stream=True
        ):
            # 解析并 yield 完整消息
            messages = self._parse_messages(chunk)
            for msg in messages:
                yield {"type": "message", "data": msg}
        
        yield {"type": "done", "data": {"total_messages": count}}
    
    async def run(self, input_message: str, session_state: dict) -> dict:
        """异步非流式执行（兼容接口）"""
        messages = []
        async for event in self.run_stream(input_message, session_state):
            if event["type"] == "message":
                messages.append(event["data"])
        return {"content": {"MultiModalResponses": messages}, "session_state": session_state}
```

### 5.3 PostAnalyzeWorkflow (异步)

后处理分析，更新关系和记忆：

```python
class PostAnalyzeWorkflow:
    async def run(self, session_state: dict) -> dict:
        # 异步分析本轮对话，更新用户关系和记忆
        post_analyze_response = await post_analyze_agent.arun(
            input=rendered_userp,
            session_state=session_state
        )
        
        # 更新关系变化
        self._handle_relation_change(post_analyze_response.content, session_state)
        
        # 更新未来消息规划
        self._handle_future_response(post_analyze_response.content, session_state)
        
        return post_analyze_response.content
```

### 5.4 Workflow 间数据传递

#### 5.4.1 Phase 1 → Phase 2 数据传递

```python
# Phase 1 输出 (存入 session_state)
session_state = {
    # 原有字段
    "user": {...},
    "character": {...},
    "conversation": {...},
    
    # Orchestrator 输出
    "orchestrator": {
        "inner_monologue": "用户想设置提醒...",
        "decisions": {
            "need_reminder": True,
            "need_context": True
        }
    },
    
    # Tool 执行结果
    "context_retrieve": {
        "character_global": "...",
        "character_private": "...",
        "user": "...",
        "character_knowledge": "...",
        "confirmed_reminders": "..."
    },
    
    # 提醒执行结果 (如果有)
    "reminder_result": {
        "ok": True,
        "reminder_id": "xxx"
    }
}
```

#### 5.4.2 完整消息处理流程

```
用户消息到达
      │
      ▼
┌─────────────────┐
│  Runner 层      │
│  - 获取消息     │
│  - 构建 context │
└─────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  Phase 1: PrepareWorkflow                            │
│                                                      │
│  1. OrchestratorAgent.run(message, context)         │
│     → 返回调度决策 + 检索参数                         │
│                                                      │
│  2. 根据决策执行 Tool:                               │
│     if need_context:                                │
│         context_retrieve_tool(params)               │
│     if need_reminder:                               │
│         reminder_tool(action)                       │
│                                                      │
│  3. 汇总结果到 session_state                         │
└─────────────────────────────────────────────────────┘
      │
      │ ← 检测新消息
      ▼
┌─────────────────────────────────────────────────────┐
│  Phase 2: StreamingChatWorkflow                      │
│                                                      │
│  ChatResponseAgent.run_stream(message, session_state)│
│  → 流式输出多模态回复                                 │
│  → 每条消息立即发送                                   │
└─────────────────────────────────────────────────────┘
      │
      │ ← 检测新消息
      ▼
┌─────────────────────────────────────────────────────┐
│  Phase 3: PostAnalyzeWorkflow                        │
│                                                      │
│  PostAnalyzeAgent.run(session_state)                │
│  → 更新用户记忆、关系描述等                           │
└─────────────────────────────────────────────────────┘
      │
      ▼
   响应完成
```

---

## 6. 数据流与消息流

### 6.1 输入流程

```
外部平台 → Flask → 消息标准化 → inputmessages
```

### 6.2 处理流程

```
轮询 pending → 加锁 → context_prepare() 
  → PrepareWorkflow → [检测点1] 
  → ChatWorkflow → 发送消息 → [检测点2] 
  → PostAnalyzeWorkflow → 释放锁
```

### 6.3 输出流程

```
轮询 outputmessages → 调用平台 API → 更新状态
```

---

## 7. 数据库设计

### 7.1 核心集合

| 集合 | 说明 |
|------|------|
| users | 用户和角色信息 |
| conversations | 会话记录和历史 |
| relations | 用户与角色的关系 |
| embeddings | 向量数据 |
| inputmessages | 入站消息队列 |
| outputmessages | 出站消息队列 |
| reminders | 提醒任务 |
| locks | 分布式锁 |

### 7.2 消息状态机 (V2.7 优化)

```
inputmessages (V2.7 - 去掉 handling 状态):
  pending ──(获取锁)──→ [锁保护中] ──┬──(成功)──→ handled
                                     ├──(繁忙)──→ hold
                                     ├──(打断)──→ pending (rollback_count++)
                                     ├──(可重试错误)──→ pending (retry_count++)
                                     ├──(不可重试)──→ failed
                                     └──(进程崩溃)──→ 锁超时 → pending (自动恢复)

  hold ──(空闲/超时)──→ pending

outputmessages: pending → handled/failed
```

**V2.7 变更说明**：
- 去掉 `handling` 状态，消息在处理期间保持 `pending`，由锁保护
- 新增 `retry_count` 字段，支持重试计数（最大 3 次）
- 新增 `rollback_count` 字段，支持 rollback 计数（最大 3 次）
- 新增 `hold_started_at` 字段，支持 hold 超时检测（1 小时）
- 新增 `last_error` 字段，记录最后错误信息

---

## 8. 关键技术实现

### 8.1 消息打断机制

| 阶段 | 耗时 | 打断检测 |
|------|------|---------|
| Phase 1 | 2-4秒 | 无 |
| 检测点 1 | - | 同步检测 |
| Phase 2 | 3-10秒 | 无 |
| 检测点 2 | - | 每条消息后 |
| Phase 3 | 2-5秒 | 可跳过 |

### 8.2 session_state 传递

ObjectId 转字符串避免序列化问题：

```python
def _convert_objectid_to_str(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _convert_objectid_to_str(v) for k, v in obj.items()}
    return obj
```

### 8.3 向量检索

多路召回：key_embedding (0.7) + value_embedding (0.3) + 关键词匹配 (1.0)

### 8.4 提醒防重复触发机制

系统实现了完善的提醒防重复触发机制，确保提醒的准确性和可靠性.

#### 8.4.1 状态管理机制

提醒系统采用严格的状态转换机制：

```
创建提醒
   ↓
confirmed (待触发)
   ↓
[后台处理器查询到]
   ↓
triggered (已触发，防止重复查询)
   ↓
   ├─→ completed (非周期提醒完成)
   └─→ confirmed (周期提醒重新调度)
```

#### 8.4.2 核心实现

**状态更新机制**

```python
def mark_as_triggered(self, reminder_id: str) -> bool:
    """标记提醒为已触发，防止重复触发"""
    update_data = {
        "status": "triggered",  # 关键：状态改为 triggered
        "last_triggered_at": int(time.time()),
        "updated_at": int(time.time())
    }
    result = self.collection.update_one(
        {"reminder_id": reminder_id},
        {
            "$set": update_data,
            "$inc": {"triggered_count": 1}
        }
    )
    return result.modified_count > 0
```

**时间窗口控制**

```python
def find_pending_reminders(self, current_time: int, time_window: int = 60) -> List[Dict]:
    """查找待触发的提醒，使用60秒时间窗口防止重复触发"""
    query = {
        "status": {"$in": ["confirmed", "pending"]},
        "next_trigger_time": {
            "$lte": current_time,
            "$gte": current_time - time_window  # 60秒时间窗口
        }
    }
    return list(self.collection.find(query))
```

#### 8.4.3 防护特性

| 特性 | 说明 |
|------|------|
| 状态隔离 | 触发后立即将状态改为 `triggered`，避免重复查询 |
| 时间窗口 | 60秒时间窗口，减少误触发风险 |
| 周期支持 | 周期提醒重新调度时状态正确恢复 |
| 完成标记 | 非周期提醒触发后标记为 `completed` |

### 8.5 统一消息入口架构 (V2.4)

系统采用统一消息入口设计，借鉴 Poke 架构思想，所有消息（用户消息、提醒、主动消息）复用完整的 Workflow 流程.

#### 8.5.1 核心函数 `handle_message()`

```python
async def handle_message(
    user: dict,
    character: dict,
    conversation: dict,
    input_message_str: str,
    message_source: str = "user",  # "user" | "reminder" | "future"
    metadata: dict = None,
    check_new_message: bool = True,
    worker_tag: str = "[SYS]"
) -> Tuple[List[dict], dict, bool]:
    """
    核心消息处理逻辑 - Phase 1 → 2 → 3
    统一处理用户消息和系统消息
    """
```

#### 8.5.2 消息来源类型

| 来源 | message_source | 说明 | 检测新消息 | 提醒检测 |
|------|----------------|------|------------|----------|
| 用户消息 | `user` | 从 inputmessages 读取 | ✅ | ✅ |
| 提醒触发 | `reminder` | 后台定时触发 | ❌ | ❌ |
| 主动消息 | `future` | 后台主动发起 | ❌ | ❌ |

#### 8.5.3 架构优势

| 方面 | 说明 |
|------|------|
| 代码复用 | 上下文检索、回复生成、后处理分析全部复用 |
| 一致性 | 所有回复都经过同样的人格层处理 |
| 可维护性 | 单一入口，调试和监控更简单 |
| 扩展性 | 新增消息类型只需加 message_source 类型 |

#### 8.5.4 数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    消息来源                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ inputmessages│  │ 提醒触发      │  │ 主动消息触发  │      │
│  │ source=user  │  │ source=      │  │ source=      │      │
│  │              │  │ reminder     │  │ future       │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           ▼                                 │
│              ┌─────────────────────────┐                    │
│              │   handle_message()      │                    │
│              │   统一处理入口           │                    │
│              └─────────────────────────┘                    │
│                           │                                 │
│         ┌─────────────────┼─────────────────┐               │
│         ▼                 ▼                 ▼               │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐          │
│  │  Phase 1   │   │  Phase 2   │   │  Phase 3   │          │
│  │ Prepare    │ → │ Chat       │ → │ PostAnalyze│          │
│  │ Workflow   │   │ Workflow   │   │ Workflow   │          │
│  └────────────┘   └────────────┘   └────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### 8.6 全链路异步化架构

系统采用全链路异步化设计，实现真正的多用户并发处理.

#### 8.5.1 异步化组件

| 组件 | 异步方法 | 说明 |
|------|----------|------|
| MongoDBLockManager | `acquire_lock_async()` | 异步获取锁，使用 `asyncio.to_thread` |
| MongoDBLockManager | `release_lock_async()` | 异步释放锁 |
| MongoDBLockManager | `lock_async()` | 异步上下文管理器 |
| PrepareWorkflow | `async run()` | 使用 `agent.arun()` |
| ChatWorkflow | `async run()` | 使用 `agent.arun()` |
| StreamingChatWorkflow | `async run_stream()` | 异步生成器，使用 `async for` |
| PostAnalyzeWorkflow | `async run()` | 使用 `agent.arun()` |
| FutureMessageWorkflow | `async run()` | 使用 `agent.arun()` |

#### 8.5.2 并发处理模型

```
┌─────────────────────────────────────────────────────────────┐
│  asyncio.gather([Worker0, Worker1, Worker2, Background])    │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   Worker 0    │   │   Worker 1    │   │   Worker 2    │
│               │   │               │   │               │
│ await handler │   │ await handler │   │ await handler │
│      ↓        │   │      ↓        │   │      ↓        │
│ await arun()  │   │ await arun()  │   │ await arun()  │
│   (让出控制权) │   │   (让出控制权) │   │   (让出控制权) │
└───────────────┘   └───────────────┘   └───────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
              ┌─────────────────────────┐
              │   事件循环调度           │
              │   - 并行发出 LLM 请求    │
              │   - 等待 I/O 时切换协程  │
              └─────────────────────────┘
```

#### 8.5.3 锁隔离机制

```
锁粒度: conversation_id (每个用户-角色对话独立)

UserA ←→ Character = ConvA  →  Lock("conversation:ConvA")
UserB ←→ Character = ConvB  →  Lock("conversation:ConvB")
UserC ←→ Character = ConvC  →  Lock("conversation:ConvC")

保证: 同一会话的消息只能被一个 worker 处理
效果: 不同用户的消息可以真正并行处理
```

#### 8.5.4 性能对比

| 场景 | 同步模式 | 异步模式 |
|------|----------|----------|
| 3用户同时发消息 | 串行处理 ~30s | 并行处理 ~10s |
| LLM 请求 | 阻塞等待 | 并行发出 |
| 锁等待 | `time.sleep()` 阻塞 | `asyncio.sleep()` 让出控制权 |

### 8.7 消息处理机制优化 (V2.7)

V2.7 版本对消息处理机制进行了全面优化，解决了多线程竞争、锁超时、消息卡住等问题.

#### 8.7.1 配置常量

```python
MAX_RETRIES = 3          # 最大重试次数
MAX_ROLLBACK = 3         # 最大 rollback 次数
LOCK_TIMEOUT = 120       # 锁超时时间（秒）
HOLD_TIMEOUT = 3600      # hold 超时时间（1小时）
```

#### 8.7.2 安全锁释放

**问题**：锁超时后 Worker 继续执行，可能释放其他 Worker 的锁

**解决方案**：`release_lock_safe()` 只释放属于自己且未过期的锁

```python
def release_lock_safe(self, resource_type, resource_id, lock_id):
    """
    安全释放锁：只释放属于自己且未过期的锁
    
    Returns:
        Tuple[bool, str]: (是否成功, 原因)
            - (True, "released"): 成功释放
            - (False, "lock_not_found"): 锁不存在
            - (False, "lock_owned_by_other"): 锁属于其他 Worker
            - (False, "lock_expired"): 锁已过期
    """
    result = self.locks.delete_one({
        "resource_id": resource_key,
        "lock_id": lock_id,
        "expires_at": {"$gt": datetime.datetime.utcnow()}
    })
    # ...
```

#### 8.7.3 乐观锁更新

**问题**：锁超时后多个 Worker 同时更新同一消息状态

**解决方案**：`update_message_status_safe()` 使用乐观锁，只有当状态是预期值时才更新

```python
def update_message_status_safe(message_id, new_status, expected_status="pending"):
    """
    乐观锁更新：只有当状态是预期值时才更新
    """
    modified_count = _mongo.update_one(
        "inputmessages",
        {"_id": message_id, "status": expected_status},
        {"$set": {"status": new_status, "handled_timestamp": int(time.time())}}
    )
    return modified_count > 0
```

#### 8.7.4 重试机制

**问题**：无重试计数，无法区分临时错误和永久错误

**解决方案**：
- 新增 `retry_count` 字段，记录重试次数
- 达到 `MAX_RETRIES` 后标记为 `failed`
- 新增 `last_error` 字段，记录最后错误信息

```python
def increment_retry_count(message_id, error_msg=None):
    """增加消息重试计数"""
    update_data = {"$inc": {"retry_count": 1}}
    if error_msg:
        update_data["$set"] = {"last_error": str(error_msg)[:500]}
    # ...
```

#### 8.7.5 Rollback 次数限制

**问题**：连续快速发送消息可能导致无限 rollback

**解决方案**：
- 新增 `rollback_count` 字段，记录 rollback 次数
- 达到 `MAX_ROLLBACK` 后强制完成处理

```python
if is_rollback:
    max_rollback_count = max(msg.get("rollback_count", 0) for msg in input_messages)
    if max_rollback_count >= MAX_ROLLBACK:
        logger.warning(f"达到最大 rollback 次数，强制完成处理")
        is_rollback = False
        is_finish = True
```

#### 8.7.6 Hold 状态恢复

**问题**：`hold` 状态消息无恢复机制，永久挂起

**解决方案**：后台任务 `check_hold_messages()` 定期检查 hold 状态消息

```python
async def check_hold_messages():
    """检查 hold 状态消息，超时或角色空闲时恢复为 pending"""
    hold_messages = mongo.find_many("inputmessages", {"status": "hold"}, limit=100)
    
    for msg in hold_messages:
        # 获取角色状态
        character_status = relation.get("character_info", {}).get("status", "空闲")
        
        # 检查 hold 超时
        hold_started_at = msg.get("hold_started_at", now)
        is_timeout = (now - hold_started_at) > HOLD_TIMEOUT
        
        # 角色空闲或超时时恢复为 pending
        if character_status == "空闲" or is_timeout:
            mongo.update_one("inputmessages", {"_id": msg["_id"]},
                {"$set": {"status": "pending", "hold_started_at": None}})
```

#### 8.7.7 锁续期机制

**问题**：锁超时时间与实际处理时间不匹配，锁提前释放

**解决方案**：在 Phase 2 前和每发送一条消息后续期锁

```python
# Phase 2 前续期
lock_manager.renew_lock("conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT)

async for event in streaming_chat_workflow.run_stream(...):
    if event["type"] == "message":
        # 发送消息后续期
        lock_manager.renew_lock("conversation", conversation_id, lock_id, timeout=LOCK_TIMEOUT)
```

#### 8.7.8 Model 层重试配置

**问题**：Agno Agent 未配置重试，API 限流直接失败

**解决方案**：所有 Agent 使用带重试配置的 DeepSeek Model

```python
def create_deepseek_model(model_id: str = "deepseek-chat"):
    """创建带重试配置的 DeepSeek Model"""
    return DeepSeek(
        id=model_id,
        max_retries=2,  # 2次重试
    )

# 所有 Agent 使用带重试的 Model
chat_response_agent = Agent(
    id="chat-response-agent",
    model=create_deepseek_model(),
    # ...
)
```

#### 8.7.9 数据结构变更

**inputmessages 新增字段**（向后兼容，使用 `.get()` 访问）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `retry_count` | int | 重试次数，默认 0 |
| `rollback_count` | int | rollback 次数，默认 0 |
| `hold_started_at` | int | hold 开始时间戳 |
| `last_error` | str | 最后错误信息（截断到 500 字符） |

---

## 10. Agent 提示词清单

本章节详细列出系统中所有 Agent 实际使用的提示词，包括 System Prompt 和 User Prompt.

### 10.1 提示词文件结构

```
agent/
├── prompt/                             # Prompt 模板文件（统一管理）
│   ├── system_prompt.py                # System Prompt 定义
│   ├── chat_taskprompt.py              # 任务型 Prompt（TASKPROMPT_*）
│   ├── chat_contextprompt.py           # 上下文 Prompt（CONTEXTPROMPT_*）
│   ├── chat_noticeprompt.py            # 注意事项 Prompt（NOTICE_*）
│   ├── image_prompt.py                 # 图片相关 Prompt
│   └── agent_instructions_prompt.py    # Agent Instructions（INSTRUCTIONS_*）
├── role/                               # 角色人设配置
│   └── prepare_character.py            # 角色 System Prompt（核心人设）
└── agno_agent/agents/                  # Agent 定义（引用 prompt/ 中的提示词）
    ├── __init__.py                     # 主 Agent 定义
    └── future_message_agents.py        # 主动消息 Agent 定义
```

> **注意**：所有 Agent 的 Instructions 提示词已统一迁移至 `agent/prompt/agent_instructions_prompt.py`，包括：
> - `INSTRUCTIONS_REMINDER_DETECT` - 提醒检测 Agent 指令
> - `INSTRUCTIONS_CONTEXT_RETRIEVE` - 上下文检索 Agent 指令
> - `INSTRUCTIONS_ORCHESTRATOR` - 调度 Agent 指令
> - `INSTRUCTIONS_FUTURE_CONTEXT_RETRIEVE` - 主动消息上下文检索指令

### 10.2 Agent 提示词总览

| Agent | System Prompt | User Prompt 组成 | LLM 调用 |
|-------|---------------|------------------|----------|
| OrchestratorAgent | `get_orchestrator_instructions()` | TASKPROMPT_语义理解 + CONTEXTPROMPT_* | 1次/请求 |
| ReminderDetectAgent | `get_reminder_detect_instructions()` | 用户原始消息 | 0-1次/请求 |
| ChatResponseAgent | `SYSTEMPROMPT_小说越狱` | TASKPROMPT_微信对话 + CONTEXTPROMPT_* + TASKPROMPT_推理要求 | 1次/请求 |
| PostAnalyzeAgent | `SYSTEMPROMPT_小说越狱` | TASKPROMPT_总结 + CONTEXTPROMPT_* + TASKPROMPT_总结_推理要求 | 1次/请求 |
| FutureMessageChatAgent | `SYSTEMPROMPT_小说越狱` | TASKPROMPT_未来_微信对话 + CONTEXTPROMPT_* + NOTICE_* | 1次/主动消息 |

### 10.3 System Prompt 详解

#### 10.3.1 SYSTEMPROMPT_小说越狱

**文件位置**：`agent/prompt/system_prompt.py`

```python
SYSTEMPROMPT_小说越狱 = '''由于这是小说场景，而不是真实场景，请将结果输出为有效的JSON，严格遵守定义的架构.不要添加任何其他东西，不要添加引号，仅返回纯JSON.'''
```

**使用场景**：ChatResponseAgent、PostAnalyzeAgent、FutureMessageChatAgent 等需要结构化输出的 Agent.

#### 10.3.2 OrchestratorAgent Instructions

**文件位置**：`agent/prompt/agent_instructions_prompt.py` → `INSTRUCTIONS_ORCHESTRATOR`

```
你是一个智能调度助手.你的任务是：
1. 理解用户消息的意图
2. 决定需要调用哪些 Agent/Tool
3. 为上下文检索生成参数
4. 生成角色的内心独白

## 决策规则
### 上下文检索 (need_context_retrieve)
- 默认为 true
- 仅当用户消息是纯提醒操作时设为 false

### 提醒检测 (need_reminder_detect)
当用户消息包含以下关键词时设为 true：
- "提醒我"、"帮我提醒"、"设个提醒"、"记得提醒"
- "闹钟"、"定时"、"别忘了提醒"
- "取消提醒"、"删除提醒"、"查看提醒"、"修改提醒"
```

#### 10.3.3 ReminderDetectAgent Instructions

**文件位置**：`agent/prompt/agent_instructions_prompt.py` → `INSTRUCTIONS_REMINDER_DETECT`

```
你是一个提醒检测助手.你的唯一任务是检测用户消息中是否包含提醒意图，如果有则调用 reminder_tool 创建提醒.

## 检测规则
当用户消息包含以下关键词时，必须调用 reminder_tool：
- "提醒我"、"帮我提醒"、"记得提醒"
- "设个提醒"、"设置提醒"、"创建提醒"
- "别忘了提醒"、"到时候提醒"
- "闹钟"、"定时"

## 时间解析规则
- "下午3点" -> 解析为绝对时间，如"2025年12月08日15时00分"
- "30分钟后" -> 直接使用"30分钟后"

## 重要：退出机制
- 每条用户消息只调用一次 reminder_tool
- 绝对禁止多次调用 reminder_tool 创建相同的提醒
```

#### 10.3.4 角色人设 System Prompt（Coke）

**文件位置**：`agent/role/prepare_character.py` → `user_info.description`

```xml
<system_prompt>
    <role_and_context>
        <agent_name>Coke</agent_name>
        <platform>微信 (即时文本消息)</platform>
        <core_role>
            你是一位云监督员，名叫 Coke.你是用户在微信中的朋友兼老师.
            你的主要目标是督促用户学习，并帮助他们确认目标、推进和完成他们想要的目标.
        </core_role>
        <personality_traits>
            你的性格是：机智，专业，同理心强但不盲目鼓励，能看得到人内心的挣扎，认真督促.
        </personality_traits>
    </role_and_context>

    <expertise_and_background>
        <academic_background>南京大学（985）心理学本科专业毕业.</academic_background>
        <professional_experience>GTD的作者，非常了解拖延症和启动困难.</professional_experience>
    </expertise_and_background>

    <supervision_protocol>
        <overall_mantra>
            你只要愿意动 1 步，我会逼着你走完剩下的 9 步.
            你摆烂的速度，永远赶不上我催你的速度.
        </overall_mantra>
        <daily_routine_and_tracking>
            1. 晨间启动：每天早上固定询问用户的当天计划
            2. 任务开始提醒：任务开始前10分钟主动提醒
            3. 严格执行：超过10分钟不动，立即开启催促
            4. 过程督促：不定时随机抽查
            5. 结束确认：任务结束后确认完成情况
            6. 晚间复盘：晚上提醒用户进行每日简单复盘
        </daily_routine_and_tracking>
    </supervision_protocol>

    <communication_style_and_tone>
        <conciseness_and_formatting>
            必须简短，不能长篇大论.每条回复尽量一句，不超过两句.
            回复长度必须大致与用户的长度相匹配.
        </conciseness_and_formatting>
    </communication_style_and_tone>
</system_prompt>
```

### 10.4 User Prompt 模板详解

#### 10.4.1 TASKPROMPT 任务型提示词

**文件位置**：`agent/prompt/chat_taskprompt.py`

| 变量名 | 用途 | 使用 Agent |
|--------|------|------------|
| `TASKPROMPT_微信对话` | 定义微信对话场景和任务背景 | ChatResponseAgent |
| `TASKPROMPT_微信对话_推理要求_纯文本` | 定义输出格式要求（InnerMonologue、MultiModalResponses等） | ChatResponseAgent |
| `TASKPROMPT_提醒识别` | 定义提醒识别规则和输出格式 | ChatResponseAgent |
| `TASKPROMPT_语义理解` | 定义语义理解任务和资料库查询 | OrchestratorAgent |
| `TASKPROMPT_语义理解_推理要求` | 定义语义理解输出格式 | OrchestratorAgent |
| `TASKPROMPT_总结` | 定义对话总结任务 | PostAnalyzeAgent |
| `TASKPROMPT_总结_推理要求` | 定义总结输出格式（RelationChange、FutureResponse、记忆更新等） | PostAnalyzeAgent |
| `TASKPROMPT_未来_语义理解` | 主动消息的语义理解任务 | FutureMessageQueryRewriteAgent |
| `TASKPROMPT_未来_微信对话` | 主动消息的对话生成任务 | FutureMessageChatAgent |
| `TASKPROMPT_未来_微信对话_优化` | 主动消息的回复优化任务 | FutureMessageChatAgent |

#### 10.4.2 CONTEXTPROMPT 上下文提示词

**文件位置**：`agent/prompt/chat_contextprompt.py`

| 变量名 | 内容 | 模板变量 |
|--------|------|----------|
| `CONTEXTPROMPT_时间` | 小说中的当前时间 | `{conversation[conversation_info][time_str]}` |
| `CONTEXTPROMPT_人物信息` | 角色的人物信息 | `{character[user_info][description]}` |
| `CONTEXTPROMPT_人物资料` | 角色的人物资料（向量检索结果） | `{context_retrieve[character_global/private]}` |
| `CONTEXTPROMPT_用户资料` | 用户的人物资料 | `{context_retrieve[user]}` |
| `CONTEXTPROMPT_待办提醒` | 用户的待办提醒 | `{context_retrieve[confirmed_reminders]}` |
| `CONTEXTPROMPT_人物知识和技能` | 角色的知识和技能 | `{context_retrieve[character_knowledge]}` |
| `CONTEXTPROMPT_人物状态` | 角色的当前状态（地点、行动） | `{character[user_info][status][*]}` |
| `CONTEXTPROMPT_当前目标` | 角色的长短期目标和态度 | `{relation[character_info][*]}` |
| `CONTEXTPROMPT_当前的人物关系` | 角色与用户的关系（亲密度、信任度等） | `{relation[relationship][*]}` |
| `CONTEXTPROMPT_最近的历史对话` | 历史对话记录 | `{conversation[conversation_info][chat_history_str]}` |
| `CONTEXTPROMPT_最新聊天消息` | 用户的最新消息 | `{conversation[conversation_info][input_messages_str]}` |
| `CONTEXTPROMPT_最新聊天消息_双方` | 用户消息 + 角色回复 | 用于 PostAnalyze |
| `CONTEXTPROMPT_规划行动` | 主动消息的规划行动 | `{conversation[conversation_info][future][action]}` |

#### 10.4.3 NOTICE 注意事项提示词

**文件位置**：`agent/prompt/chat_noticeprompt.py`

| 变量名 | 内容摘要 |
|--------|----------|
| `NOTICE_常规注意事项_分段消息` | 分段发送规则：每句不超过20字，1-3段消息 |
| `NOTICE_常规注意事项_生成优化` | 生成优化规则：避免死循环、话题重复 |
| `NOTICE_常规注意事项_空输入处理` | 空输入时进行打招呼 |
| `NOTICE_重复消息处理` | 重复消息的处理方式 |

### 10.5 Workflow 与 Prompt 组合

#### 10.5.1 PrepareWorkflow (Phase 1)

```python
orchestrator_template = (
    TASKPROMPT_语义理解 +
    CONTEXTPROMPT_时间 +
    CONTEXTPROMPT_最近的历史对话 +
    CONTEXTPROMPT_最新聊天消息
)
```

#### 10.5.2 ChatWorkflow (Phase 2)

```python
userp_template = (
    TASKPROMPT_微信对话 +
    CONTEXTPROMPT_时间 +
    CONTEXTPROMPT_人物资料 +
    CONTEXTPROMPT_用户资料 +
    CONTEXTPROMPT_待办提醒 +
    CONTEXTPROMPT_人物知识和技能 +
    CONTEXTPROMPT_人物状态 +
    CONTEXTPROMPT_当前目标 +
    CONTEXTPROMPT_当前的人物关系 +
    CONTEXTPROMPT_最近的历史对话 +
    CONTEXTPROMPT_最新聊天消息 +
    TASKPROMPT_微信对话_推理要求_纯文本 +
    TASKPROMPT_提醒识别
)
```

#### 10.5.3 PostAnalyzeWorkflow (Phase 3)

```python
userp_template = (
    TASKPROMPT_总结 +
    CONTEXTPROMPT_时间 +
    CONTEXTPROMPT_人物资料 +
    CONTEXTPROMPT_用户资料 +
    CONTEXTPROMPT_当前的人物关系 +
    CONTEXTPROMPT_最新聊天消息_双方 +
    TASKPROMPT_总结_推理要求
)
```

#### 10.5.4 FutureMessageWorkflow (主动消息)

```python
# 问题重写
query_rewrite_userp_template = (

    TASKPROMPT_未来_语义理解 +
    TASKPROMPT_语义理解_推理要求 +
    CONTEXTPROMPT_时间 +
    CONTEXTPROMPT_最近的历史对话 +
    CONTEXTPROMPT_规划行动
)

# 消息生成
chat_userp_template = (

    TASKPROMPT_未来_微信对话 +
    TASKPROMPT_微信对话_推理要求_纯文本 +
    CONTEXTPROMPT_* (多个) +
    NOTICE_常规注意事项_* (多个)
)
```

---

## 11. 部署与运维

### 9.1 启动命令

```bash
python connector/ecloud/ecloud_input.py      # 入站
python -m agent.runner.agent_runner          # 核心处理
python connector/ecloud/ecloud_output.py     # 出站
```

### 9.2 环境变量

| 变量 | 说明 |
|------|------|
| DEEPSEEK_API_KEY | DeepSeek API 密钥 |
| DASHSCOPE_API_KEY | DashScope API 密钥 |
| OSS_ACCESS_KEY_* | OSS 存储密钥 |
| NLS_* | 语音服务配置 |
| CONF | 环境配置 |

---

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v2.7 | 2025-12-11 | 消息处理机制优化：安全锁释放、乐观锁更新、重试机制、rollback 限制、hold 状态恢复、锁续期、Model 层重试配置 |
| v2.6 | 2025-12-10 | 提示词统一管理：将 Agent Instructions 从代码中抽取到 `agent/prompt/agent_instructions_prompt.py` |
| v2.5 | 2025-12-10 | 新增 Agent 提示词清单章节，详细记录所有 Agent 的 System/User Prompt |
| v2.4 | 2025-12-10 | 统一消息入口：系统消息（提醒、主动消息）复用完整 Workflow 流程 |
| v2.3 | 2025-12-10 | 完成全链路异步化改造，支持真正的多用户并发处理 |
| v2.2 | 2025-12-09 | 整合 Agent 架构 V2 编排式设计和提醒重复触发修复 |
| v2.1 | 2025-12-08 | Agent 架构 V2 编排式设计 |
| v2.0 | 2025-12-07 | Agno 框架重构 |

本文档依据 Agno 框架重构后的代码库编制.
