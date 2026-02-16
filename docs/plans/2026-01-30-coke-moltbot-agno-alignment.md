# Coke 向 Moltbot 对齐：基于 Agno 能力的实现路线图

> 日期：2026-01-30
> 目标：利用 Agno 框架能力，实现 Moltbot 的功能特性

> **DEPRECATED (2026-02-16):** LangBot integration has been removed. This document
> is kept for historical reference only. Future platform integrations will use
> alternative approaches.

---

## 一、三方能力对比

### 1.1 Memory 系统

| 功能 | Moltbot | Agno 提供 | Coke 现状 | 对齐方案 |
|------|---------|----------|----------|---------|
| 长期记忆 | ✅ MEMORY.md 文件驱动 | ✅ User Memory / Learned Knowledge | ⚠️ MongoDB 自实现 | 迁移到 Agno Memory |
| 日志记忆 | ✅ 日期目录存储 | ✅ Session Context | ⚠️ 自实现 | 迁移到 Agno Session |
| 用户档案 | ✅ 结构化存储 | ✅ User Profile | ⚠️ MongoDB users 集合 | 迁移到 Agno Profile |
| 实体记忆 | ✅ 人物/项目追踪 | ✅ Entity Memory | ❌ 未实现 | 新增 |
| 决策日志 | ✅ 审计追踪 | ✅ Decision Log | ❌ 未实现 | 新增 |

### 1.2 知识检索 (RAG)

| 功能 | Moltbot | Agno 提供 | Coke 现状 | 对齐方案 |
|------|---------|----------|----------|---------|
| 向量搜索 | ✅ sqlite-vec | ✅ 25+ 向量库 | ⚠️ DashScope + MongoDB | 迁移到 Agno RAG |
| 关键词搜索 | ✅ FTS5 BM25 | ✅ Hybrid Search | ⚠️ MongoDB text | 迁移到 Agno RAG |
| 混合检索 | ✅ 0.7*vec + 0.3*text | ✅ Hybrid + Reranking | ⚠️ 自实现权重 | 使用 Agno Reranking |
| 嵌入缓存 | ✅ 文本哈希缓存 | ✅ 内置缓存 | ✅ 刚实现 | 评估是否迁移 |
| 多 Embedder | ✅ OpenAI/Gemini/Local | ✅ 29+ 提供商 | ❌ 仅 DashScope | 使用 Agno Embedders |

### 1.3 多模态处理

| 功能 | Moltbot | Agno 提供 | Coke 现状 | 对齐方案 |
|------|---------|----------|----------|---------|
| TTS | ✅ Edge/OpenAI/ElevenLabs | ⚠️ 需自实现 | ✅ MiniMax | 保持 |
| ASR | ✅ OpenAI/Deepgram/Groq | ⚠️ 需自实现 | ✅ 阿里云 NLS | 保持 |
| 图片生成 | ✅ 多提供商 | ✅ DALL-E/Gemini/OpenAI | ✅ LibLib Flux | 可扩展 |
| 图片理解 | ✅ Anthropic/OpenAI | ✅ 多模态模型 | ✅ 已实现 | 保持 |

### 1.4 工具系统

| 功能 | Moltbot | Agno 提供 | Coke 现状 | 对齐方案 |
|------|---------|----------|----------|---------|
| Web 搜索 | ✅ 多提供商 | ✅ DuckDuckGo/Tavily/Brave | ⚠️ Bocha 自实现 | 迁移到 Agno 工具 |
| 浏览器控制 | ✅ Playwright | ✅ Firecrawl/Browserbase | ❌ 未实现 | 使用 Agno 工具 |
| Discord | ✅ 原生支持 | ✅ Discord 工具包 | ❌ 未实现 | 使用 Agno 工具 |
| Slack | ✅ 原生支持 | ✅ Slack 工具包 | ❌ 未实现 | 使用 Agno 工具 |
| WhatsApp | ✅ 原生支持 | ✅ WhatsApp 工具包 | ❌ 未实现 | 使用 Agno 工具 |
| Gmail | ✅ Hook 集成 | ✅ Gmail 工具包 | ❌ 未实现 | 使用 Agno 工具 |

### 1.5 多 Agent 架构

| 功能 | Moltbot | Agno 提供 | Coke 现状 | 对齐方案 |
|------|---------|----------|----------|---------|
| Agent 路由 | ✅ 5 层优先级 | ✅ Teams + Router | ⚠️ 三阶段自实现 | 迁移到 Agno Teams |
| 工作流编排 | ✅ 事件驱动 | ✅ Workflows | ⚠️ 自实现 | 迁移到 Agno Workflows |
| 并行执行 | ✅ 支持 | ✅ Parallel Steps | ❌ 未实现 | 使用 Agno |
| 条件分支 | ✅ 支持 | ✅ Conditional Steps | ⚠️ 代码实现 | 使用 Agno |

### 1.6 消息处理

| 功能 | Moltbot | Agno 提供 | Coke 现状 | 对齐方案 |
|------|---------|----------|----------|---------|
| 消息分块 | ✅ Markdown 安全 | ❌ 无 | ❌ 未实现 | 自实现（如需要） |
| 流式输出 | ✅ 块合并 | ✅ Streaming | ✅ 标签解析 | 保持 |
| 消息队列 | ✅ 智能模式 | ❌ 无 | ⚠️ MongoDB 队列 | 保持/增强 |
| 打断检测 | ✅ 事件驱动 | ❌ 无 | ✅ 阶段间检测 | 保持 |

### 1.7 推理能力

| 功能 | Moltbot | Agno 提供 | Coke 现状 | 对齐方案 |
|------|---------|----------|----------|---------|
| Thinking 控制 | ✅ 8 级别 | ✅ Reasoning 模式 | ❌ 未使用 | 使用 Agno Reasoning |
| Chain-of-thought | ✅ 支持 | ✅ ThinkingTools | ❌ 未使用 | 使用 Agno |
| Extended thinking | ✅ 支持 | ✅ 支持 | ❌ 未使用 | 使用 Agno |

### 1.8 Skill 系统（能力管理）⚠️ 新增

| 功能 | Moltbot | Agno 提供 | Coke 现状 | 对齐方案 |
|------|---------|----------|----------|---------|
| **模块化 Prompt** | ✅ SKILL.md 文件 | ⚠️ Agent.instructions | ❌ Python 硬编码 | 设计模块化方案 |
| **动态能力加载** | ✅ Gating 规则过滤 | ⚠️ 代码控制 | ❌ 静态组装 | 配置驱动 |
| **斜杠命令** | ✅ `/skill-name` | ❌ 无 | ❌ 无 | 按需实现 |
| **能力热重载** | ✅ 文件监听 | ❌ 无 | ❌ 无 | 非必需 |
| **Token 开销统计** | ✅ 公式计算 | ❌ 无 | ❌ 无 | 可借鉴 |
| **能力市场** | ✅ ClawdHub | ❌ 无 | ❌ 无 | 非必需 |

**Moltbot Skill 系统核心价值**：

```
skills/
├── reminder/SKILL.md      # 提醒能力指令
├── web-search/SKILL.md    # 搜索能力指令
├── image-gen/SKILL.md     # 图片生成指令
└── ...
```

1. **模块化**：每个能力是独立的 SKILL.md 文件，而非 Python 代码
2. **动态加载**：根据 `requires.bins/env/config` 按需过滤
3. **斜杠命令**：用户可以 `/reminder` 直接触发特定功能
4. **可扩展**：用户可以添加自己的 skills

**Coke 现状**：

```python
# agent/prompt/agent_instructions_prompt.py - 所有指令硬编码
INSTRUCTIONS_REMINDER_DETECT = "..."
INSTRUCTIONS_CHAT_RESPONSE = "..."
INSTRUCTIONS_ORCHESTRATOR = "..."
```

**对齐方案**：

| 方案 | 描述 | 推荐 |
|------|------|------|
| **A: 配置驱动** | config.json 控制能力开关，代码中动态组装 prompt | ✅ 推荐 |
| **B: Agno Teams** | 使用 Agno Teams + Router 管理能力路由 | ⚠️ 改动大 |
| **C: 文件驱动** | 仿照 Moltbot 实现 SKILL.md 加载 | ❌ 过度设计 |

**推荐实现**：

```python
# conf/config.json
{
  "capabilities": {
    "reminder": { "enabled": true },
    "web_search": { "enabled": true },
    "image_gen": { "enabled": false }
  }
}

# agent/prompt/capability_loader.py
def build_instructions(config: dict) -> str:
    """根据配置动态组装能力指令"""
    parts = [BASE_INSTRUCTIONS]
    if config["capabilities"]["reminder"]["enabled"]:
        parts.append(REMINDER_INSTRUCTIONS)
    if config["capabilities"]["web_search"]["enabled"]:
        parts.append(WEB_SEARCH_INSTRUCTIONS)
    return "\n".join(parts)
```

---

## 二、对齐路线图

### Phase 0: 快速胜利（利用 Agno 现有工具）

| 任务 | 当前 | 目标 | 工作量 |
|------|------|------|--------|
| Web 搜索 | Bocha 自实现 | Agno DuckDuckGo/Tavily | 1 天 |
| Discord 接入 | 无 | Agno Discord 工具包 | 1-2 天 |
| Telegram 接入 | LangBot | Agno Telegram 工具包 | 1-2 天 |

### Phase 1: Memory 系统迁移

| 任务 | 当前 | 目标 | 工作量 |
|------|------|------|--------|
| 用户记忆 | MongoDB users | Agno User Memory | 2-3 天 |
| 用户档案 | MongoDB relations | Agno User Profile | 2 天 |
| 会话上下文 | 自实现 dict | Agno Session Context | 1-2 天 |

### Phase 2: RAG 系统迁移

| 任务 | 当前 | 目标 | 工作量 |
|------|------|------|--------|
| 向量存储 | DashScope + MongoDB | Agno RAG (MongoDB) | 3-4 天 |
| 混合搜索 | 自实现权重 | Agno Hybrid + Reranking | 2-3 天 |
| 多 Embedder | 仅 DashScope | Agno Embedders (回退链) | 1-2 天 |

### Phase 3: Workflow 重构

| 任务 | 当前 | 目标 | 工作量 |
|------|------|------|--------|
| 三阶段工作流 | 自实现 | Agno Workflows | 5-7 天 |
| Agent 路由 | OrchestratorAgent | Agno Teams + Router | 3-4 天 |
| 推理能力 | 无 | Agno Reasoning | 1-2 天 |

### Phase 4: 多平台扩展（利用 Agno 工具包）

| 任务 | 工作量 |
|------|--------|
| Discord 完整集成 | 2-3 天 |
| Slack 集成 | 2-3 天 |
| WhatsApp 集成 | 3-4 天 |
| Gmail 集成 | 2 天 |

---

## 三、优先级建议

### 高优先级（ROI 最高）

1. **Agno 工具包替换** - 直接使用现成工具，减少维护
   - DuckDuckGo/Tavily 替换 Bocha
   - Discord/Telegram 工具包接入

2. **Agno Reasoning** - 开启推理能力，提升回答质量

### 中优先级

3. **Agno Memory** - 统一记忆管理
4. **Agno RAG** - 利用 Reranking 提升检索质量

### 低优先级（大改动）

5. **Agno Workflows** - 需要重构三阶段架构
6. **Agno Teams** - 需要重新设计 Agent 协作模式

---

## 四、关键决策点

### Q1: 是否迁移到 Agno Memory？
- **优点**：6 种记忆类型，Decision Log，Learned Knowledge
- **风险**：需要数据迁移，可能影响现有功能
- **建议**：先在新功能上使用，逐步迁移

### Q2: 是否迁移到 Agno RAG？
- **优点**：Reranking，多 Embedder，内置缓存
- **风险**：需要重写检索逻辑
- **建议**：评估 Agno RAG 与 MongoDB 的兼容性

### Q3: 是否使用 Agno Workflows？
- **优点**：类型安全，Conditional/Loop，更好的可测试性
- **风险**：需要重构三阶段架构
- **建议**：新功能使用 Agno Workflows，旧功能保持

### Q4: 多平台接入策略？
- **方案 A**：使用 Agno 工具包（Discord/Telegram/Slack）
- **方案 B**：使用之前设计的 ChannelAdapter + Gateway
- **建议**：先尝试 Agno 工具包，评估是否满足需求

---

## 五、总结

**核心洞察**：

Coke 目前 "用 Agno 当 OpenAI SDK"，而 Agno 实际上是一个**完整的 Agent 框架**，提供：
- Memory 系统（比 Coke 自实现更完整）
- RAG 系统（比 Coke 自实现更强大）
- 100+ 工具包（包括 Discord/Slack/WhatsApp）
- Teams/Workflows（比 Coke 自实现更规范）

**对齐 Moltbot 的最佳路径**：

1. **不是复刻 Moltbot 的实现**
2. **而是利用 Agno 提供的能力**
3. **Agno 已经实现了 Moltbot 大部分功能**

**下一步行动**：

1. 评估 Agno 工具包是否满足 Discord/Telegram 接入需求
2. 评估 Agno Memory/RAG 是否可替换现有实现
3. 制定渐进式迁移计划
