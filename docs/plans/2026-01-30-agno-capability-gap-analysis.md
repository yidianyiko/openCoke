# Agno 能力差距分析

> 日期：2026-01-30
> 发现：Coke 仅使用了 Agno 框架约 5% 的能力

---

## 一、核心发现

**Coke 实际使用的 Agno 能力**：

```python
from agno.agent import Agent           # 基础 Agent 类
from agno.models.deepseek import DeepSeek  # DeepSeek 模型
from agno.tools import tool            # @tool 装饰器
```

仅此三项。

---

## 二、Agno 完整能力（未被 Coke 利用）

### 2.1 Memory 系统（6 种类型）

| 类型 | 描述 | Coke 现状 |
|------|------|----------|
| **User Memory** | 非结构化用户观察 | 自己用 MongoDB 实现 |
| **User Profile** | 结构化用户信息 | 自己用 MongoDB 实现 |
| **Entity Memory** | 公司、项目、人物信息 | 未实现 |
| **Session Context** | 目标、计划、进度 | 部分实现 |
| **Decision Log** | 决策日志（审计和学习） | 未实现 |
| **Learned Knowledge** | 跨用户学习 | 未实现 |

**存储后端支持**：MongoDB, PostgreSQL, Redis, SQLite 等

### 2.2 Knowledge & RAG

| 能力 | Agno 提供 | Coke 现状 |
|------|----------|----------|
| **搜索类型** | Vector + Keyword + Hybrid + Agentic RAG + Reranking | 仅 Vector + Keyword |
| **Embedders** | 29+ 提供商 (OpenAI, Cohere, HuggingFace, Gemini, Mistral...) | 仅 DashScope |
| **向量数据库** | 25+ (Pinecone, Qdrant, Weaviate, MongoDB, LanceDB...) | 仅 MongoDB |
| **Chunking 策略** | Semantic, Fixed-size, Recursive, Markdown, Code, CSV | 未使用 |
| **文档读取** | PDF, CSV, JSON, Markdown, Web, YouTube, Arxiv | 未使用 |

### 2.3 Tools & 工具包

**Agno 提供 100+ 工具集成**：

| 类别 | 工具 |
|------|------|
| **搜索** | DuckDuckGo, Tavily, Brave Search, Exa, Perplexity |
| **数据库** | PostgreSQL, Neo4j, DuckDB, pandas, BigQuery |
| **API** | GitHub, Slack, Gmail, **Discord**, **WhatsApp**, Notion, Linear, Jira |
| **Web** | Firecrawl, Browserbase, Spider, Trafilatura |
| **媒体** | DALL-E, Image generation (Gemini, OpenAI), Video tools |

**Coke 现状**：仅用 @tool 装饰器自己实现了 7 个业务工具

### 2.4 Teams（多 Agent 协作）

| 能力 | 描述 | Coke 现状 |
|------|------|----------|
| **委托模式** | Leader 委托任务给专业成员 | 未使用 |
| **直接响应** | 路由请求到专业 Agent | 未使用（自己实现三阶段） |
| **知识共享** | 跨 Agent 共享知识库 | 未使用 |
| **执行模式** | Sequential / Parallel | 未使用（自己实现） |

### 2.5 Workflows

| 能力 | 描述 | Coke 现状 |
|------|------|----------|
| **Step 类型** | Sequential, Parallel, Conditional, Loop, Router | 自己实现三阶段 |
| **数据流** | Pydantic 类型安全 | 自己用 dict |
| **执行模式** | Streaming / Batch | 自己实现 |
| **Session** | 有状态多轮工作流 | 自己实现 |

### 2.6 Reasoning

| 能力 | 描述 | Coke 现状 |
|------|------|----------|
| **推理模型** | OpenAI o1/o4, DeepSeek R1, Claude, Gemini | 未使用 |
| **Chain-of-thought** | 结构化思考工具 | 未使用 |
| **Extended thinking** | 非推理模型的深度思考 | 未使用 |

---

## 三、重复造轮子清单

| Coke 自实现 | Agno 已提供 | 迁移难度 |
|------------|------------|---------|
| MongoDB 记忆存储 | Memory 系统 | 中 |
| DashScope 向量搜索 | Agentic RAG | 中 |
| 三阶段工作流 | Workflows | 高 |
| Web Search Tool | DuckDuckGo/Tavily 工具包 | 低 |
| 手动 Prompt 模板 | 内置 Prompt 管理 | 中 |

---

## 四、潜在迁移收益

### 4.1 使用 Agno Memory 系统

**收益**：
- 6 种记忆类型，比当前更丰富
- 内置存储后端支持（已支持 MongoDB）
- Decision Log 可用于审计
- Learned Knowledge 可实现跨用户学习

### 4.2 使用 Agno RAG

**收益**：
- 混合搜索 + Reranking 开箱即用
- 29+ Embedder 提供商可选
- 多种 Chunking 策略
- 文档读取器（PDF、Web 等）

### 4.3 使用 Agno Workflows

**收益**：
- 类型安全的数据流
- 内置 Conditional/Loop 支持
- Streaming 和 Batch 模式
- 更好的可测试性

### 4.4 使用 Agno 工具包

**收益**：
- Discord、WhatsApp 等平台工具已有
- 减少自己实现的工作量
- 社区维护，持续更新

---

## 五、建议行动（待规划）

### 短期（低风险）
1. 使用 Agno 内置搜索工具替换 Web Search Tool
2. 探索 Agno Memory 系统与现有 MongoDB 的兼容性

### 中期（需评估）
1. 评估 Agno RAG 是否能替换当前向量搜索实现
2. 评估 Agno Workflows 是否适合替换三阶段工作流

### 长期（架构调整）
1. 全面迁移到 Agno 原生能力
2. 利用 Agno Discord/WhatsApp 工具包简化多平台接入

---

## 六、参考资源

- Agno 官方文档：https://docs.agno.com
- Agno GitHub：https://github.com/agno-agi/agno
- Agno 工具包列表：https://docs.agno.com/tools

---

## 七、结论

**Coke 目前处于 "用 Agno 当作 OpenAI SDK 封装" 的状态**，未利用其核心优势：
- Memory 系统
- Agentic RAG
- Teams & Workflows
- 100+ 工具包

这是一个重要的技术债务发现，后续可根据优先级逐步迁移。
