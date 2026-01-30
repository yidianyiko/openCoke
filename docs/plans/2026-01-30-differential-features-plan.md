# 差异化功能实现规划

> 日期：2026-01-30
> 目标：实现三个差异化功能

---

## 一、功能概览

| 功能 | 实现方式 | 工作量 |
|------|---------|--------|
| **链接理解** | 新增 URL 检测 + Agno Website Reader | 1-2 天 |
| **Usage 追踪** | 启用 Agno Metrics | 0.5 天 |
| **上下文压缩** | 使用 Agno compress_tool_results + num_history_messages | 1 天 |

---

## 二、功能一：链接理解

### 2.1 目标

用户发送包含 URL 的消息时，自动提取链接内容并摘要，作为上下文传给 Agent。

**示例**：
```
用户: 帮我看看这个 https://example.com/article
```

**处理流程**：
```
1. 检测消息中的 URL
2. 使用 Agno Website Reader 提取内容
3. 摘要内容（可选，如果过长）
4. 将摘要作为上下文传给 ChatResponseAgent
```

### 2.2 实现方案

**方案 A：PrepareWorkflow 中处理**

```python
# agent/agno_agent/workflows/prepare_workflow.py

import re
from agno.tools.website import WebsiteReader  # 或 Firecrawl

URL_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'

async def extract_urls_content(message: str) -> list[dict]:
    """
    从消息中提取 URL 并获取内容

    Returns:
        List of {"url": str, "title": str, "summary": str}
    """
    urls = re.findall(URL_PATTERN, message)
    if not urls:
        return []

    results = []
    reader = WebsiteReader()

    for url in urls[:3]:  # 限制最多处理 3 个 URL
        try:
            content = await reader.read(url)
            # 如果内容过长，截断或摘要
            summary = content[:2000] if len(content) > 2000 else content
            results.append({
                "url": url,
                "summary": summary
            })
        except Exception as e:
            logger.warning(f"Failed to fetch URL {url}: {e}")

    return results
```

**集成到 PrepareWorkflow**：

```python
# 在 PrepareWorkflow._run_async() 中

# 1. URL 检测和提取
url_contents = await extract_urls_content(user_message)
if url_contents:
    session_state["url_context"] = url_contents

# 2. 在 context prompt 中包含 URL 内容
if "url_context" in session_state:
    url_context_str = "\n".join([
        f"[链接: {u['url']}]\n{u['summary']}"
        for u in session_state["url_context"]
    ])
    # 添加到 context
```

### 2.3 配置

```json
// conf/config.json
{
  "features": {
    "link_understanding": {
      "enabled": true,
      "max_urls": 3,
      "max_content_length": 2000,
      "reader": "website"  // "website" | "firecrawl" | "trafilatura"
    }
  }
}
```

### 2.4 任务清单

- [ ] 添加 URL 检测正则
- [ ] 集成 Agno WebsiteReader（或 Firecrawl）
- [ ] 在 PrepareWorkflow 中添加 URL 处理
- [ ] 添加 url_context 到 prompt 模板
- [ ] 添加配置开关
- [ ] 测试

---

## 三、功能二：Usage 追踪

### 3.1 目标

追踪每次 Agent 调用的 token 用量，用于成本监控和优化。

### 3.2 Agno Metrics 能力

Agno 的 `RunOutput.metrics` 已提供：

```python
@dataclass
class Metrics:
    input_tokens: int       # 输入 token
    output_tokens: int      # 输出 token
    total_tokens: int       # 总 token
    audio_input_tokens: int
    audio_output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    time_to_first_token: Optional[float]
    duration: Optional[float]  # 执行时间
    provider_metrics: Optional[dict]
```

### 3.3 实现方案

**方案：记录并聚合 metrics**

```python
# agent/agno_agent/utils/usage_tracker.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from agno.models.metrics import Metrics

@dataclass
class UsageRecord:
    """单次调用的用量记录"""
    timestamp: datetime
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration: Optional[float] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None

class UsageTracker:
    """用量追踪器"""

    def __init__(self):
        self._records: list[UsageRecord] = []

    def record(
        self,
        agent_name: str,
        metrics: Metrics,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        """记录一次调用的用量"""
        record = UsageRecord(
            timestamp=datetime.now(),
            agent_name=agent_name,
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            total_tokens=metrics.total_tokens,
            duration=metrics.duration,
            user_id=user_id,
            session_id=session_id
        )
        self._records.append(record)

        # 可选：持久化到 MongoDB
        self._persist(record)

    def _persist(self, record: UsageRecord):
        """持久化到 MongoDB"""
        from dao.mongo import MongoDBBase
        mongo = MongoDBBase()
        mongo.insert_one("usage_records", {
            "timestamp": record.timestamp,
            "agent_name": record.agent_name,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "total_tokens": record.total_tokens,
            "duration": record.duration,
            "user_id": record.user_id,
            "session_id": record.session_id
        })

    def get_daily_summary(self, date: datetime = None) -> dict:
        """获取日用量汇总"""
        # 从 MongoDB 聚合
        pass

# 全局实例
usage_tracker = UsageTracker()
```

**集成到 Workflow**：

```python
# agent/agno_agent/workflows/chat_workflow_streaming.py

from agent.agno_agent.utils.usage_tracker import usage_tracker

async def _run_async(self, session_state, ...):
    # ... existing code ...

    response = await self.agent.arun(...)

    # 记录用量
    if response.metrics:
        usage_tracker.record(
            agent_name="ChatResponseAgent",
            metrics=response.metrics,
            user_id=session_state.get("user_id"),
            session_id=session_state.get("session_id")
        )
```

### 3.4 MongoDB Collection Schema

```json
// usage_records collection
{
  "_id": ObjectId,
  "timestamp": ISODate,
  "agent_name": "ChatResponseAgent",
  "input_tokens": 1500,
  "output_tokens": 500,
  "total_tokens": 2000,
  "duration": 1.23,
  "user_id": "user_123",
  "session_id": "session_456"
}
```

### 3.5 任务清单

- [ ] 创建 UsageTracker 类
- [ ] 创建 usage_records MongoDB collection
- [ ] 在 ChatResponseAgent 集成用量记录
- [ ] 在 OrchestratorAgent 集成用量记录
- [ ] 在 PostAnalyzeAgent 集成用量记录
- [ ] 添加日用量汇总查询

---

## 四、功能三：上下文压缩

### 4.1 目标

使用 Agno 内置的上下文管理能力，替换当前的简单截断。

### 4.2 Agno 相关参数

```python
Agent(
    # 历史消息数量限制
    num_history_messages=10,      # 保留最近 10 条消息

    # 工具结果压缩
    compress_tool_results=True,   # 压缩工具调用结果

    # 历史工具调用限制
    max_tool_calls_from_history=5,  # 历史中最多保留 5 个工具调用

    # 会话摘要（自动压缩长会话）
    enable_session_summaries=True,
)
```

### 4.3 实现方案

**方案：配置 Agno Agent 参数**

```python
# agent/agno_agent/workflows/chat_workflow_streaming.py

self.agent = Agent(
    id="chat-response-agent-streaming",
    name="ChatResponseAgentStreaming",
    model=DeepSeek(id="deepseek-chat", max_tokens=4096),
    instructions=INSTRUCTIONS_CHAT_RESPONSE,

    # 新增：上下文压缩配置
    num_history_messages=15,        # 保留最近 15 条消息
    compress_tool_results=True,     # 压缩工具结果
    max_tool_calls_from_history=5,  # 历史工具调用限制

    # 可选：会话摘要
    # enable_session_summaries=True,

    use_json_mode=True,
    markdown=False,
)
```

### 4.4 配置化

```json
// conf/config.json
{
  "agent": {
    "context_compression": {
      "num_history_messages": 15,
      "compress_tool_results": true,
      "max_tool_calls_from_history": 5,
      "enable_session_summaries": false
    }
  }
}
```

### 4.5 任务清单

- [ ] 更新 ChatResponseAgent 配置
- [ ] 更新 OrchestratorAgent 配置
- [ ] 添加配置到 config.json
- [ ] 测试压缩效果
- [ ] 对比 token 用量（before/after）

---

## 五、实施顺序

### Day 1: Usage 追踪（最简单）
1. 创建 UsageTracker
2. 集成到各 Agent
3. 验证 metrics 数据

### Day 2: 上下文压缩
1. 更新 Agent 配置
2. 测试压缩效果
3. 调整参数

### Day 3-4: 链接理解
1. 添加 URL 检测
2. 集成 WebsiteReader
3. 更新 PrepareWorkflow
4. 测试端到端

---

## 六、验收标准

### 链接理解
- [ ] 消息中的 URL 能被自动检测
- [ ] URL 内容能被提取（文本）
- [ ] Agent 能基于链接内容回答问题

### Usage 追踪
- [ ] 每次 Agent 调用记录 token 用量
- [ ] 可查询日用量汇总
- [ ] MongoDB 中有 usage_records 数据

### 上下文压缩
- [ ] 长会话不再超出上下文限制
- [ ] 工具结果被压缩
- [ ] Token 用量减少（对比测试）

---

## 七、参考资源

- Agno Token Counting: https://docs.agno.com/basics/context-compression/token-counting
- Agno Website Reader: https://docs.agno.com/tools/website
- Agno Metrics: `agno.models.metrics.Metrics`
