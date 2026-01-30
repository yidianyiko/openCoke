# Moltbot 调研报告：可借鉴功能点分析

> 调研日期：2026-01-30
> 目标仓库：refer/moltbot
> 调研目的：为 Coke Project 寻找可借鉴的功能设计和架构模式

---

## 项目对比概览

| 维度 | Coke Project | Moltbot |
|------|-------------|---------|
| **语言** | Python 3.12+ / Agno 2.x | TypeScript / Node.js 22+ |
| **平台** | WeChat (E云管家) | 15+ 平台 (WhatsApp/Telegram/Discord/Slack/Signal/iMessage...) |
| **存储** | MongoDB | SQLite + 文件系统 |
| **架构** | 三阶段工作流 (Prepare→Chat→PostAnalyze) | Gateway WebSocket 控制平面 |
| **LLM** | DeepSeek | 多模型支持 (Anthropic/OpenAI/Gemini/...) |

---

## 一、架构设计（高优先级）

### 1.1 Gateway WebSocket 控制平面

**核心概念**：
- 单一 Gateway 进程管理所有连接和消息流
- WebSocket 双向通信作为控制平面
- 支持多客户端（移动端、桌面、Web、CLI）

**协议设计**：
```
Frame Types:
├─ Request  → 客户端请求 (chat.send, agent, config.get)
├─ Response → 服务器响应 (result/error)
├─ Event    → 事件推送 (agent, chat, presence)
└─ EventAck → 确认事件
```

**可借鉴点**：
- Request ID 追踪机制，便于关联请求和响应
- 事件广播 + `dropIfSlow` 优化慢客户端
- 配置热重载，无需重启服务

### 1.2 多 Agent 路由系统

**路由优先级**（降序）：
1. Peer 绑定（精确 DM/群组）
2. Guild/Team 绑定（工作区级）
3. Account 绑定（账户级）
4. Channel 绑定（渠道级）
5. 默认 Agent

**会话密钥格式**：
```
agent:{agentId}:{channel}:{peerKind}:{peerId}
```

**可借鉴点**：
- 结构化会话密钥，支持多粒度隔离
- 分层绑定解析器，调试友好（matchedBy 标记）
- 身份链接（Identity Links）支持跨渠道用户统一

---

## 二、Memory/记忆系统（高优先级）

### 2.1 核心架构

**分层存储**：
```
~/workspace/
├─ MEMORY.md          # 长期记忆（手动维护）
└─ memory/
   └─ YYYY-MM-DD.md   # 日志记忆（日常笔记）
```

**混合检索**：
- 向量搜索（sqlite-vec / cosine similarity）
- BM25 关键词搜索（FTS5）
- 加权合并：`score = 0.7*vec + 0.3*text`

### 2.2 关键设计

| 特性 | 实现 |
|-----|------|
| **文件驱动** | Markdown 是 Source of Truth，SQLite 仅索引 |
| **增量更新** | 文件哈希跟踪变化，避免全量重建 |
| **多嵌入提供商** | auto → local → OpenAI → Gemini 回退 |
| **批处理优化** | OpenAI/Gemini Batch API 降低成本 50% |
| **Session 记忆** | 可选从 JSONL 会话日志提取 |

### 2.3 可借鉴点

```python
# Coke 可参考的记忆架构
class MemoryManager:
    def search(self, query: str) -> List[MemoryResult]:
        # 1. 向量搜索 (DashScope embeddings)
        vec_results = self.vector_search(query, top_k=200)
        # 2. 关键词搜索 (MongoDB text index)
        text_results = self.keyword_search(query, top_k=200)
        # 3. 混合合并
        return self.merge_results(vec_results, text_results)
```

---

## 三、多模态处理（高优先级）

### 3.1 图片处理

**双后端策略**：Sharp (Node) / sips (macOS)
- EXIF 方向自动修正
- PNG 多压缩等级优化
- HEIC → JPEG 自动转换

### 3.2 音频处理（ASR）

**多提供商支持**：
| 提供商 | 模型 | 特点 |
|-------|------|------|
| OpenAI | gpt-4o-mini-transcribe | FormData 上传 |
| Deepgram | nova-3 | 二进制流上传 |
| Groq | whisper | 高速低成本 |
| Google | Speech-to-Text | 长音频支持 |

### 3.3 TTS 语音合成

**三大提供商**：
1. **Edge TTS**（免费默认）
2. **OpenAI TTS**（tts-1 / tts-1-hd）
3. **ElevenLabs**（多语言高质量）

**指令系统**：
```markdown
[[tts:provider=openai voice=nova]]
Your response text here.
```

**自适应模式**：
- `off` / `always` / `inbound`（用户发音频时） / `tagged`

### 3.4 可借鉴点

- TTS 指令标签化（[[tts:...]]）增强用户控制
- 提供商回退机制，不中断整体流程
- 媒体文件 TTL 自动清理（2分钟）

---

## 四、工具/Skills/插件系统

### 4.1 插件 API 接口

```typescript
api.registerTool(tool, opts)       // 工具注册
api.registerHook(events, handler)  // 生命周期 Hook
api.registerChannel(registration)  // 渠道注册
api.registerCommand(command)       // 自定义命令
api.registerService(service)       // 后台服务
```

### 4.2 14 个生命周期 Hook

```
before_agent_start → agent_end
before_compaction → after_compaction
message_received → message_sending → message_sent
before_tool_call → after_tool_call
session_start → session_end
gateway_start → gateway_stop
```

### 4.3 Cron 定时任务

**三种调度模式**：
- `at`：一次性（固定时间戳）
- `every`：周期性（间隔 ms）
- `cron`：CRON 表达式 + 时区

**隔离会话**：
- 独立 context 运行
- 结果可回发主会话（摘要/全文）

### 4.4 浏览器控制

**快照模式**：
- ARIA 快照（结构化辅助树）
- AI 快照（自然语言友好描述）

### 4.5 可借鉴点

- Hook 优先级排序机制
- 工具沙箱标志（sandboxed context）
- 可选工具白名单（optional + allowlist）

---

## 五、消息路由与群组处理

### 5.1 群组消息判定流程

```
入站消息
  ↓
[群组可访问性检查]
  ↓
[提及门控 Mention Gating]
  ├─ requireMention?
  ├─ wasMentioned?
  └─ → 跳过或继续
  ↓
[命令门控 Command Gating]
  ├─ hasControlCommand?
  ├─ commandAuthorized?
  └─ → 阻挡或继续
  ↓
处理消息
```

### 5.2 消息分块

**三种模式**：
1. **Length**（默认）：按长度，词边界断裂
2. **Paragraph**：按 `\n\n` 分隔
3. **Newline**：按行分割

**Markdown 安全**：
- 识别代码块边界
- 自动补全栅栏标记

### 5.3 流式传输合并

```
minChars: 800    # 缓冲启动
maxChars: 1200   # 强制发送
idleMs: 1000     # 超时发送
```

### 5.4 可借鉴点

- 嵌套门控（mention → command → tool）
- Markdown 安全分块保护代码
- 块合并减少网络往返

---

## 六、安全与 DM 策略

### 6.1 DM 配对流程

**配对码**：8 字符，大写字母 + 数字，排除易混淆字符

**流程**：
1. 未知 sender DM → 生成配对码
2. 发送配对消息给 sender
3. Owner 执行 `moltbot pairing approve <channel> <code>`
4. Sender 自动加入 allowlist

### 6.2 四种 DM Policy

| 模式 | 行为 |
|------|------|
| `pairing`（默认） | 需配对批准 |
| `allowlist` | 只允许列表中的人 |
| `open` | 任何人可 DM（需 "*" 配置） |
| `disabled` | 禁用 DM |

### 6.3 三层 Allowlist

```
Layer 1: DM Allowlist（谁可以私信）
Layer 2: Group Allowlist（谁可以在群里触发）
Layer 3: Elevated Tool Allowlist（谁可以运行危险命令）
```

### 6.4 安全审计框架

```bash
moltbot security audit --deep   # 发现问题
moltbot security audit --fix    # 自动修复
```

**检查项示例**：
- 群组允许但无 allowlist → critical
- allowlist 包含 "*" → critical
- 配置文件权限过宽 → warn

### 6.5 可借鉴点

- Pairing 作为安全默认（而非 open）
- 原子文件操作（临时文件 + rename + 锁）
- 分层防护（网络 → 渠道 → 会话 → 工具）

---

## 七、综合建议：Coke 项目可借鉴清单

### 高优先级（建议尽快采纳）

| 功能 | 当前状态 | 借鉴方案 |
|------|---------|---------|
| **混合记忆检索** | 仅向量搜索 | 向量 + BM25 加权合并 |
| **TTS 指令系统** | 基础 MiniMax TTS | 添加 [[tts:...]] 标签控制 |
| **消息分块** | 未实现 | Markdown 安全分块 + 代码块保护 |
| **群组 @mention 检测** | 基础实现 | 多级门控（mention → command） |

### 中优先级（版本迭代时考虑）

| 功能 | 借鉴方案 |
|------|---------|
| **工具 Hook 系统** | 14 个生命周期事件 + 优先级 |
| **定时任务** | Cron 表达式 + 隔离会话 |
| **DM 配对机制** | 配对码 + 自动 allowlist |
| **安全审计** | CLI 命令检测配置问题 |

### 低优先级（长期规划）

| 功能 | 借鉴方案 |
|------|---------|
| **多渠道支持** | 统一渠道适配器接口 |
| **浏览器控制** | Playwright + 快照模式 |
| **Gateway 架构** | WebSocket 控制平面 |
| **插件系统** | 工厂模式 + 沙箱隔离 |

---

## 八、关键文件索引

### 架构相关
- `src/gateway/server.impl.ts` - Gateway 服务实现
- `src/routing/resolve-route.ts` - 路由解析
- `src/routing/session-key.ts` - 会话密钥生成

### 记忆系统
- `src/memory/manager.ts` - 记忆管理器（73KB）
- `src/memory/manager-search.ts` - 混合搜索
- `extensions/memory-lancedb/` - LanceDB 扩展

### 多模态
- `src/media/` - 媒体处理管道
- `src/tts/tts.ts` - TTS 实现
- `src/media-understanding/` - 媒体理解

### 插件系统
- `src/plugins/loader.ts` - 插件加载
- `src/plugins/types.ts` - 接口定义
- `src/cron/service.ts` - Cron 服务

### 消息处理
- `src/auto-reply/chunk.ts` - 消息分块
- `src/channels/plugins/group-mentions.ts` - 群组门控
- `src/channels/mention-gating.ts` - 提及检测

### 安全
- `src/pairing/pairing-store.ts` - 配对存储
- `src/security/audit.ts` - 安全审计
- `src/web/inbound/access-control.ts` - 访问控制

---

## 九、总结

Moltbot 是一个成熟的多平台 AI 助手框架，其设计体现了以下核心理念：

1. **安全默认**：Pairing 而非 Open，分层防护
2. **灵活扩展**：插件系统 + Hook 生命周期
3. **性能优化**：批处理、缓存、流式合并
4. **用户体验**：指令标签、Markdown 保护、智能分块

对于 Coke 项目而言，最具价值的借鉴点是：
- **混合记忆检索**（向量 + 关键词）
- **TTS 指令系统**（用户可控）
- **消息分块**（长文本处理）
- **群组门控**（精细化控制）

这些功能可以在不改变现有架构的情况下逐步引入，提升整体用户体验。
