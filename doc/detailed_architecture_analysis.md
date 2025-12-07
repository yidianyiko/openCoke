# Coke Project 详细架构分析文档

> 本文档基于 Agno 框架重构后的代码库进行深入分析
> 
> 文档版本：v2.0  
> 日期：2025-12-07

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

---

## 1. 项目概述

### 1.1 项目定位

Coke Project 是一个**微信Bot虚拟人解决方案**，实现了具有记忆、情感、多模态交互能力的AI虚拟角色。

### 1.2 核心特性

- **Agno 框架驱动**：采用 Agno 2.x 作为核心 Agent 框架，支持 Workflow 编排
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
│                 Agno Workflow 编排层                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  PrepareWorkflow (Phase 1):                          │   │
│  │    QueryRewrite → ReminderDetect → ContextRetrieve   │   │
│  │                                                       │   │
│  │  ChatWorkflow (Phase 2):                              │   │
│  │    ChatResponseAgent → MultiModalResponses            │   │
│  │                                                       │   │
│  │  PostAnalyzeWorkflow (Phase 3):                       │   │
│  │    PostAnalyzeAgent → 更新关系和记忆                   │   │
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

#### 2.2.1 消息队列模式

- **输入队列**：`inputmessages` 集合，状态流转：`pending → handling → handled/failed/hold`
- **输出队列**：`outputmessages` 集合，状态流转：`pending → handled/failed`
- **轮询机制**：独立的 input/output handler 持续轮询数据库

#### 2.2.2 Agno Workflow 分段执行模式

- 将对话处理拆分为三个 Phase，由 Runner 层控制分段执行
- 在 Phase 间插入消息打断检测点
- 支持 session_state 在 Workflow 间传递

#### 2.2.3 Tool 封装模式

- 将复杂业务逻辑（向量检索、提醒管理）封装为 Agno Tool
- Agent 通过调用 Tool 完成具体功能
- Tool 负责数据访问，Workflow 保持纯净

#### 2.2.4 分布式锁模式

- 基于 MongoDB 实现的分布式锁
- 会话级锁定，防止同一会话的并发处理
- 支持锁超时和自动释放

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

### 4.1 Agno Agent 定义

所有 Agent 在模块级别预创建（`agent/agno_agent/agents/__init__.py`）：

```python
from agno.agent import Agent
from agno.models.deepseek import DeepSeek

query_rewrite_agent = Agent(
    id="query-rewrite-agent",
    name="QueryRewriteAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=get_query_rewrite_instructions,
    output_schema=QueryRewriteResponse,
)

chat_response_agent = Agent(
    id="chat-response-agent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=SYSTEMPROMPT,
    output_schema=ChatResponse,
)
```

### 4.2 Pydantic Schema 定义

```python
# schemas/chat_response_schema.py
class ChatResponse(BaseModel):
    InnerMonologue: str                    # 角色内心独白
    MultiModalResponses: List[dict]        # 多模态回复
    RelationChange: RelationChangeModel    # 关系变化
    FutureResponse: FutureResponseModel    # 未来消息规划
```

### 4.3 Runner 层

Runner 层（`agent/runner/agent_handler.py`）负责 Workflow 调度：

```python
async def main_handler():
    context = context_prepare(user, character, conversation)
    
    # Phase 1: 准备阶段
    prepare_response = prepare_workflow.run(input_message, context)
    
    # 检测点 1
    if is_new_message_coming_in(...):
        is_rollback = True
    
    if not is_rollback:
        # Phase 2: 生成回复
        chat_response = chat_workflow.run(input_message, context)
        
        # 发送消息 + 检测点 2
        for response in multimodal_responses:
            send_message(...)
            if is_new_message_coming_in(...):
                break
        
        # Phase 3: 后处理
        post_analyze_workflow.run(session_state=context)
```

---

## 5. Agno Workflow 详解

### 5.1 PrepareWorkflow

执行：QueryRewrite → ReminderDetect → ContextRetrieve

```python
class PrepareWorkflow:
    def run(self, input_message: str, session_state: dict) -> dict:
        # Step 1: 问题重写
        session_state["query_rewrite"] = query_rewrite_agent.run(...).content
        
        # Step 2: 提醒检测
        reminder_detect_agent.run(...)
        
        # Step 3: 上下文检索
        session_state["context_retrieve"] = context_retrieve_agent.run(...).content
        
        return {"session_state": session_state}
```

### 5.2 ChatWorkflow

生成多模态回复：

```python
class ChatWorkflow:
    userp_template = TASKPROMPT + CONTEXTPROMPT_*  # 模板组合
    
    def run(self, input_message: str, session_state: dict) -> dict:
        rendered_userp = self._render_template(self.userp_template, session_state)
        response = chat_response_agent.run(input=rendered_userp, session_state=session_state)
        return {"content": response.content, "session_state": session_state}
```

### 5.3 PostAnalyzeWorkflow

后处理分析，更新关系和记忆。

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

### 7.2 消息状态机

```
inputmessages:  pending → handling → handled/failed/hold
outputmessages: pending → handled/failed
```

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

---

## 9. 部署与运维

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

本文档依据 Agno 框架重构后的代码库编制。
