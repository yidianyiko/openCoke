# Coke vs Moltbot 功能对比分析

> 日期：2026-01-30
> 目的：识别差距，制定学习路线图

---

## 一、整体架构对比

| 维度 | Coke Project | Moltbot | 差距分析 |
|------|-------------|---------|---------|
| **语言** | Python 3.12 + Agno 2.x | TypeScript + Node 22 | 语言差异，设计模式可借鉴 |
| **平台数** | 3 (WeChat/Feishu/Telegram) | 15+ | Coke 平台少但够用 |
| **架构模式** | 三阶段 Workflow | Gateway 控制平面 | Coke 更简单直接 |
| **数据库** | MongoDB | SQLite + 文件 | 各有优劣 |
| **消息队列** | MongoDB Collection | WebSocket 实时 | Coke 适合异步场景 |

### 架构图对比

**Coke 架构**：
```
微信/Feishu/Telegram
       ↓
   Connector 层
       ↓
   MongoDB 队列
       ↓
 ┌──────────────────────────────────┐
 │    三阶段 Workflow               │
 │  1. PrepareWorkflow (2-6s)      │
 │     - OrchestratorAgent         │
 │     - context_retrieve_tool     │
 │     - web_search_tool           │
 │  2. StreamingChatWorkflow       │
 │     - ChatResponseAgent         │
 │  3. PostAnalyzeWorkflow         │
 │     - PostAnalyzeAgent          │
 └──────────────────────────────────┘
       ↓
   MongoDB 存储
```

**Moltbot 架构**：
```
15+ 平台
       ↓
 ┌──────────────────────────────────┐
 │      Gateway WebSocket           │
 │  - 多 Agent 路由                 │
 │  - 多客户端支持                  │
 │  - 实时事件广播                  │
 └──────────────────────────────────┘
       ↓
   Agent Runtime (Pi)
       ↓
   SQLite + 文件系统
```

**评估**：Coke 的三阶段架构更清晰，适合当前规模；Moltbot 的 Gateway 适合多平台高并发场景。

---

## 二、记忆系统对比

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 | 优先级 |
|--------|----------|-------------|------|-------|
| **向量检索** | ✅ DashScope + MongoDB | ✅ 多提供商 + sqlite-vec | 功能相当 | - |
| **关键词检索** | ✅ MongoDB text search | ✅ FTS5 BM25 | 功能相当 | - |
| **混合检索** | ✅ 权重融合 | ✅ `0.7*vec + 0.3*text` | **Coke 可优化权重** | 中 |
| **文件驱动记忆** | ❌ 无 | ✅ MEMORY.md + 日志 | 可选功能 | 低 |
| **Session 记忆索引** | ❌ 无 | ✅ JSONL 解析 | 可选功能 | 低 |
| **多嵌入提供商** | ❌ 仅 DashScope | ✅ OpenAI/Gemini/Local 回退 | 可扩展 | 低 |
| **批处理优化** | ❌ 无 | ✅ Batch API | 可优化成本 | 中 |
| **嵌入缓存** | ❌ 无 | ✅ 文本哈希缓存 | **建议添加** | 高 |

### 详细对比：混合检索算法

**Coke 当前实现** (`context_retrieve_tool.py`):
```python
# 向量检索
vec_results = embedding_search(query, metadata_type, top_k=20)
# 关键词检索
text_results = keyword_search(keywords, metadata_type, top_k=20)
# 合并 - 简单权重融合
merged = _merge_results(vec_results, text_results, weights)
```

**Moltbot 实现** (`manager-search.ts`):
```typescript
// 1. 向量检索 (top 200 * 4)
const vecResults = await vectorSearch(query, 800);
// 2. BM25 关键词检索 (top 800)
const textResults = await fts5Search(query, 800);
// 3. 混合合并
for (const r of results) {
  r.finalScore = 0.7 * r.vectorScore + 0.3 * r.textScore;
}
// 4. 过滤 + 排序
return results.filter(r => r.score >= 0.35).slice(0, 6);
```

**建议改进**：
1. 增加 `minScore` 阈值过滤低质量结果
2. 调整候选数量（vectorSearch 扩大候选池）
3. 添加嵌入缓存减少重复计算

---

## 三、多模态处理对比

### 3.1 TTS 语音合成

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 | 优先级 |
|--------|----------|-------------|------|-------|
| **提供商** | MiniMax speech-02-hd | Edge/OpenAI/ElevenLabs | Coke 单一 | 中 |
| **情感支持** | ✅ 高兴/悲伤/愤怒等 | ✅ 通过 voice settings | 功能相当 | - |
| **指令控制** | ❌ 无 | ✅ `[[tts:provider=xxx]]` | **建议添加** | 高 |
| **自适应模式** | ❌ 无 | ✅ always/inbound/tagged | **建议添加** | 高 |
| **提供商回退** | ❌ 无 | ✅ 自动降级 | 可选 | 低 |

**Coke 当前 TTS 流程**：
```python
# agent/tool/voice.py
def text_to_voice(text, voice_id, emotion=None):
    # 固定使用 MiniMax
    result = minimax_api.speech(text, voice_id, emotion)
    # 转换格式：PCM → SILK
    silk_data = convert_pcm_to_silk(result)
    # 上传 OSS
    url = upload_to_oss(silk_data)
    return url
```

**建议改进**：
```python
# 添加 TTS 指令解析
def parse_tts_instruction(text):
    """解析 [[tts:emotion=高兴]] 标签"""
    pattern = r'\[\[tts:([^\]]+)\]\]'
    match = re.search(pattern, text)
    if match:
        params = parse_params(match.group(1))
        return params, text.replace(match.group(0), '')
    return {}, text

# 添加自适应模式
class TTSMode(Enum):
    OFF = "off"
    ALWAYS = "always"
    INBOUND = "inbound"  # 用户发语音时才回语音
    TAGGED = "tagged"    # 有 [[tts]] 标签时
```

### 3.2 ASR 语音识别

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 |
|--------|----------|-------------|------|
| **提供商** | 阿里云 NLS | OpenAI/Deepgram/Groq/Google | Coke 单一但稳定 |
| **格式支持** | SILK | mp3/wav/m4a/flac/opus | Coke 针对微信优化 |
| **多提供商回退** | ❌ | ✅ | 可选功能 |

**评估**：Coke 的阿里云 NLS 对微信语音（SILK 格式）支持良好，暂无需改动。

### 3.3 图片处理

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 |
|--------|----------|-------------|------|
| **图片识别** | ✅ (待确认实现) | ✅ Anthropic/OpenAI | 功能相当 |
| **图片生成** | ✅ LibLib Flux | ✅ 多提供商 | 功能相当 |
| **EXIF 处理** | ❌ 无 | ✅ 自动修正方向 | 可选 |
| **压缩优化** | ❌ 无 | ✅ 多级压缩 | 可选 |

---

## 四、消息处理对比

### 4.1 消息分块

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 | 优先级 |
|--------|----------|-------------|------|-------|
| **长消息分块** | ❌ 无明确实现 | ✅ 三种模式 | **建议添加** | 高 |
| **Markdown 保护** | ❌ 无 | ✅ 代码块边界检测 | **建议添加** | 高 |
| **分块配置** | ❌ 无 | ✅ 按渠道/账户配置 | 建议添加 | 中 |

**Moltbot 分块实现**：
```typescript
// 三种模式
type ChunkMode = "length" | "paragraph" | "newline";

// Markdown 安全分块
function chunkMarkdownText(text: string, limit: number): string[] {
  // 1. 识别代码块边界 (```)
  // 2. 在安全位置断裂
  // 3. 自动补全栅栏标记
}
```

**建议 Coke 添加**：
```python
# agent/util/chunk_util.py
def chunk_message(text: str, limit: int = 2000, mode: str = "length") -> list[str]:
    """
    分块消息，支持 Markdown 安全

    Args:
        text: 原始文本
        limit: 单块最大字符数
        mode: length | paragraph | newline
    """
    if mode == "paragraph":
        return chunk_by_paragraph(text, limit)
    elif mode == "newline":
        return chunk_by_newline(text, limit)
    else:
        return chunk_by_length_markdown_safe(text, limit)
```

### 4.2 流式传输

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 |
|--------|----------|-------------|------|
| **流式回复** | ✅ 标签解析 | ✅ 块合并 | 功能相当 |
| **分段发送** | ✅ `[TEXT]...[/TEXT]` | ✅ 按 minChars 缓冲 | 实现不同 |
| **防抖机制** | ❌ 无 | ✅ 150ms delta 防抖 | 可选 |

**评估**：Coke 的标签解析方式更灵活，适合多模态输出；Moltbot 的块合并适合纯文本。

### 4.3 消息打断

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 |
|--------|----------|-------------|------|
| **打断检测** | ✅ 每阶段检测 | ✅ 事件驱动 | 功能相当 |
| **回滚机制** | ✅ rollback_count | ✅ 取消请求 | 功能相当 |

**评估**：Coke 的实现已经比较完善。

---

## 五、群组处理对比

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 | 优先级 |
|--------|----------|-------------|------|-------|
| **白名单群** | ✅ whitelist_groups | ✅ 多层配置 | 功能相当 | - |
| **@提及检测** | ✅ 基础实现 | ✅ 多级门控 | **可增强** | 中 |
| **回复模式** | ✅ all/mention_only | ✅ 更多模式 | 功能相当 | - |
| **命令门控** | ❌ 无 | ✅ 授权检查 | 可选 | 低 |
| **工具策略** | ❌ 无 | ✅ 群组级工具限制 | 可选 | 低 |

**Coke 当前实现** (`ecloud_adapter.py`):
```python
def should_respond_to_group_message(data, config):
    group_id = data.get('conversationId')
    is_mentioned = check_mention(data)

    # 白名单群
    if group_id in config['whitelist_groups']:
        mode = config['reply_mode']['whitelist']  # "all"
        return mode == "all" or is_mentioned

    # 其他群
    mode = config['reply_mode']['others']  # "mention_only"
    return mode == "all" or is_mentioned
```

**建议增强**：
```python
# 多级门控
def resolve_group_access(data, config):
    """
    三级检查：
    1. 群组可访问性 (白名单/黑名单)
    2. 提及门控 (requireMention + wasMentioned)
    3. 命令门控 (可选：特定命令需要授权)
    """
    # 1. 群组级检查
    group_policy = get_group_policy(data['conversationId'], config)
    if group_policy == "disabled":
        return False

    # 2. 提及门控
    require_mention = group_policy != "all"
    was_mentioned = check_mention(data)
    implicit_mention = check_implicit_mention(data)  # 回复消息等

    if require_mention and not (was_mentioned or implicit_mention):
        return False

    return True
```

---

## 六、安全策略对比

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 | 优先级 |
|--------|----------|-------------|------|-------|
| **DM 配对** | ❌ 无 | ✅ 配对码机制 | 可选（微信无此需求）| 低 |
| **Allowlist** | ✅ 简单实现 | ✅ 三层 allowlist | 可增强 | 低 |
| **安全审计** | ❌ 无 | ✅ CLI 审计命令 | 可选 | 低 |
| **分布式锁** | ✅ MongoDB 锁 | ✅ 文件锁 | 功能相当 | - |
| **消息验证** | ✅ 签名验证 | ✅ Token/Device | 功能相当 | - |

**评估**：微信场景下用户已通过平台验证，DM 配对机制非必需。Coke 当前安全策略基本够用。

---

## 七、工具/插件系统对比

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 | 优先级 |
|--------|----------|-------------|------|-------|
| **工具注册** | ✅ Agno @tool 装饰器 | ✅ registerTool API | 功能相当 | - |
| **生命周期 Hook** | ❌ 无 | ✅ 14 个事件 | **建议添加核心 Hook** | 中 |
| **插件系统** | ❌ 无 | ✅ 完整插件架构 | 可选（当前规模不需要）| 低 |
| **定时任务** | ✅ 后台 handler | ✅ Cron 表达式 | **可增强** | 中 |

### Coke 当前工具实现

```python
# agent/agno_agent/tools/reminder_tools.py
from agno.tools import tool

@tool
def create_reminder(
    trigger_time: str,
    content: str,
    user_id: str
) -> str:
    """创建提醒"""
    # 实现...
```

### 建议添加：核心生命周期 Hook

```python
# agent/hooks.py
class HookManager:
    """核心生命周期 Hook 管理"""

    HOOKS = [
        "before_agent_start",   # Agent 启动前
        "agent_end",            # Agent 执行完成
        "message_received",     # 接收消息
        "message_sending",      # 发送消息前
        "message_sent",         # 消息已发送
        "before_tool_call",     # 工具调用前
        "after_tool_call",      # 工具调用后
    ]

    def __init__(self):
        self._handlers = {hook: [] for hook in self.HOOKS}

    def register(self, hook: str, handler: Callable, priority: int = 0):
        """注册 Hook 处理器"""
        self._handlers[hook].append((priority, handler))
        self._handlers[hook].sort(key=lambda x: -x[0])  # 高优先级先执行

    async def emit(self, hook: str, context: dict) -> dict:
        """触发 Hook"""
        for _, handler in self._handlers[hook]:
            result = await handler(context)
            if result and result.get('cancel'):
                return result
        return context
```

---

## 八、定时任务对比

| 功能点 | Coke 实现 | Moltbot 实现 | 差距 | 优先级 |
|--------|----------|-------------|------|-------|
| **提醒触发** | ✅ 后台轮询 | ✅ Cron 调度 | 功能相当 | - |
| **主动消息** | ✅ future 机制 | ✅ agentTurn payload | 功能相当 | - |
| **调度方式** | ✅ 时间戳比较 | ✅ at/every/cron 三种 | **可增强** | 中 |
| **隔离会话** | ❌ 无 | ✅ sessionTarget | 可选 | 低 |

**Coke 当前实现** (`agent_background_handler.py`):
```python
async def check_and_trigger_reminders():
    """每分钟检查一次待触发的提醒"""
    now = datetime.now()
    reminders = await ReminderDAO.find_pending_before(now)
    for reminder in reminders:
        await trigger_reminder(reminder)
```

**建议增强**：
```python
# 支持多种调度方式
class ScheduleType(Enum):
    AT = "at"           # 一次性，固定时间
    EVERY = "every"     # 周期性，间隔 ms
    CRON = "cron"       # CRON 表达式

class Schedule:
    type: ScheduleType
    at_timestamp: Optional[int]      # for AT
    every_ms: Optional[int]          # for EVERY
    cron_expr: Optional[str]         # for CRON
    timezone: str = "Asia/Shanghai"
```

---

## 九、综合评估与学习路线图

### 9.1 Coke 的优势

1. **架构清晰**：三阶段 Workflow 易于理解和维护
2. **Agno 集成**：原生支持结构化输出和工具调用
3. **微信优化**：针对微信生态深度适配（SILK 音频、群聊处理）
4. **提醒系统**：功能完善的 GTD 风格任务管理
5. **混合检索**：已实现向量 + 关键词融合

### 9.2 建议学习的功能（按优先级）

#### P0 - 高优先级（建议尽快实现）

| 功能 | 预估工作量 | 价值 |
|------|-----------|------|
| **TTS 指令系统** | 2-3 天 | 用户可控，体验提升 |
| **消息分块** | 2-3 天 | 长消息处理，稳定性 |
| **嵌入缓存** | 1-2 天 | 性能优化，成本降低 |

#### P1 - 中优先级（版本迭代时实现）

| 功能 | 预估工作量 | 价值 |
|------|-----------|------|
| **混合检索优化** | 2 天 | 检索质量提升 |
| **群组门控增强** | 2 天 | 更精细的控制 |
| **生命周期 Hook** | 3 天 | 扩展性提升 |
| **定时任务增强** | 2 天 | 更灵活的调度 |

#### P2 - 低优先级（长期规划）

| 功能 | 价值 |
|------|------|
| 多 TTS 提供商 | 可选，当前 MiniMax 够用 |
| 插件系统 | 当前规模不需要 |
| 安全审计 | 微信场景非必需 |
| 文件驱动记忆 | 可选功能 |

### 9.3 学习路线图

```
Phase 1 (1-2 周)
├─ TTS 指令系统 [[tts:emotion=xxx]]
├─ 消息分块 (Markdown 安全)
└─ 嵌入缓存机制

Phase 2 (2-3 周)
├─ 混合检索优化 (权重调整 + minScore)
├─ 群组门控增强 (多级检查)
└─ 生命周期 Hook (7 个核心事件)

Phase 3 (长期)
├─ 定时任务增强 (CRON 表达式)
├─ 多提供商回退 (TTS/ASR)
└─ 其他可选功能
```

---

## 十、具体实现建议

### 10.1 TTS 指令系统

```python
# agent/util/tts_instruction.py
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class TTSInstruction:
    emotion: Optional[str] = None
    speed: float = 1.0
    volume: float = 1.0

def parse_tts_instruction(text: str) -> tuple[TTSInstruction, str]:
    """
    解析 TTS 指令标签

    示例:
        [[tts:emotion=高兴 speed=1.2]]你好
        → TTSInstruction(emotion='高兴', speed=1.2), '你好'
    """
    pattern = r'\[\[tts:([^\]]*)\]\]'
    match = re.search(pattern, text)

    if not match:
        return TTSInstruction(), text

    params = {}
    for param in match.group(1).split():
        if '=' in param:
            key, value = param.split('=', 1)
            params[key] = value

    clean_text = text.replace(match.group(0), '').strip()

    return TTSInstruction(
        emotion=params.get('emotion'),
        speed=float(params.get('speed', 1.0)),
        volume=float(params.get('volume', 1.0))
    ), clean_text
```

### 10.2 消息分块

```python
# agent/util/chunk_util.py
import re
from typing import List

def chunk_message_markdown_safe(text: str, limit: int = 2000) -> List[str]:
    """
    Markdown 安全的消息分块

    特点:
    - 不在代码块中间断裂
    - 自动补全未闭合的代码块
    - 在段落或句子边界断裂
    """
    chunks = []
    current_chunk = ""
    in_code_block = False
    code_fence = ""

    lines = text.split('\n')

    for line in lines:
        # 检测代码块边界
        fence_match = re.match(r'^(`{3,}|~{3,})', line)
        if fence_match:
            if not in_code_block:
                in_code_block = True
                code_fence = fence_match.group(1)
            elif line.startswith(code_fence):
                in_code_block = False
                code_fence = ""

        # 尝试添加当前行
        potential = current_chunk + '\n' + line if current_chunk else line

        if len(potential) > limit and current_chunk:
            # 需要分块
            if in_code_block:
                # 在代码块中，补全栅栏
                chunks.append(current_chunk + '\n' + code_fence)
                current_chunk = code_fence + '\n' + line
            else:
                chunks.append(current_chunk)
                current_chunk = line
        else:
            current_chunk = potential

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
```

### 10.3 嵌入缓存

```python
# agent/util/embedding_cache.py
import hashlib
from typing import Optional, List
from dao.mongodb import get_collection

class EmbeddingCache:
    """嵌入向量缓存，避免重复计算"""

    def __init__(self, collection_name: str = "embedding_cache"):
        self.collection = get_collection(collection_name)

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    async def get(self, text: str, model: str) -> Optional[List[float]]:
        """获取缓存的嵌入"""
        text_hash = self._hash_text(text)
        doc = await self.collection.find_one({
            "text_hash": text_hash,
            "model": model
        })
        return doc["embedding"] if doc else None

    async def set(self, text: str, model: str, embedding: List[float]):
        """缓存嵌入"""
        text_hash = self._hash_text(text)
        await self.collection.update_one(
            {"text_hash": text_hash, "model": model},
            {"$set": {
                "embedding": embedding,
                "updated_at": datetime.now()
            }},
            upsert=True
        )

    async def get_or_compute(
        self,
        text: str,
        model: str,
        compute_fn
    ) -> List[float]:
        """获取缓存或计算新嵌入"""
        cached = await self.get(text, model)
        if cached:
            return cached

        embedding = await compute_fn(text)
        await self.set(text, model, embedding)
        return embedding
```

---

---

## 十一、战略方向：多平台支持演进

> **目标**：向 Moltbot 的多平台能力靠齐

### 11.1 当前状态

```
已支持平台：
├─ WeChat (ecloud) - 主要平台，深度适配
├─ Feishu (LangBot) - 基础支持
├─ Telegram (LangBot) - 基础支持
└─ Terminal - 测试用

当前架构：
├─ BaseConnector - 轮询式 input/output handler
├─ Adapter 模式 - 消息格式转换
└─ Platform 字段 - 标识来源平台
```

### 11.2 Moltbot 多平台架构参考

```
Moltbot 支持的平台 (15+)：
├─ 核心渠道：WhatsApp, Telegram, Discord, Slack, Signal, iMessage, Google Chat
├─ 扩展渠道：MS Teams, Matrix, BlueBubbles, Zalo, Nostr, Mattermost...
└─ 本地接口：macOS App, iOS Node, Android Node, WebChat

关键架构组件：
├─ Gateway 控制平面 - WebSocket 双向通信
├─ 统一渠道适配器接口 - 10+ 个标准适配器方法
├─ 插件式渠道注册 - 运行时加载/卸载
├─ 多 Agent 路由 - 5 层优先级匹配
└─ 会话隔离机制 - per-peer / per-channel-peer
```

### 11.3 演进路径规划（待细化）

| 阶段 | 目标 | 关键工作 |
|------|------|---------|
| **Phase 0** | 功能增强 | TTS 指令、消息分块、嵌入缓存（当前优先） |
| **Phase 1** | 渠道抽象 | 定义统一 ChannelAdapter 接口 |
| **Phase 2** | 路由增强 | 多 Agent 路由、会话密钥规范化 |
| **Phase 3** | 实时通信 | 可选：WebSocket Gateway 或保持队列模式 |
| **Phase 4** | 平台扩展 | Discord、Slack、WhatsApp 等 |

### 11.4 待决策问题

1. **架构选择**：保持队列轮询 vs 引入 Gateway 控制平面？
2. **渠道优先级**：先扩展哪些平台？
3. **多租户需求**：是否需要支持不同用户使用不同平台？
4. **Agent 路由**：是否需要多 Agent 支持？

### 11.5 参考文件索引

**Moltbot 多平台相关**：
- `refer/moltbot/src/channels/` - 渠道抽象层
- `refer/moltbot/src/routing/` - 消息路由
- `refer/moltbot/src/gateway/` - Gateway 控制平面
- `refer/moltbot/extensions/` - 扩展渠道插件

**Coke 当前实现**：
- `connector/base_connector.py` - 基础连接器
- `connector/ecloud/` - WeChat 适配
- `connector/langbot/` - LangBot 适配（Feishu/Telegram）

---

## 总结

Coke 项目已经是一个功能完善的 AI 虚拟人解决方案，与 Moltbot 相比各有特色：

- **Coke 优势**：架构清晰、微信深度优化、Agno 原生集成
- **Moltbot 优势**：多平台支持、插件系统、丰富的安全机制

**近期重点**（Phase 0）- 学习 Moltbot 的功能设计：
1. **TTS 指令系统** - 提升用户体验
2. **消息分块** - 提升稳定性
3. **嵌入缓存** - 优化性能和成本

**中期方向**（Phase 1-4）- 多平台架构演进：
- 向 Moltbot 的多平台能力靠齐
- 具体路径待进一步规划

这些功能可以在不改变核心架构的情况下增量引入。
