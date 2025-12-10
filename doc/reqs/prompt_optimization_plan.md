# 提示词优化计划

基于 Poke 提示词分析，本文档说明新增提示词的使用方式和集成计划。

## 新增文件

`agent/prompt/personality_prompt.py` - 人格与行为规范提示词

## 提示词与 Agent 对应关系

| 提示词 | ChatResponseAgent | FutureMessageChatAgent | OrchestratorAgent | PostAnalyzeAgent |
|--------|:-----------------:|:----------------------:|:-----------------:|:----------------:|
| MESSAGE_SOURCE_HANDLING | ✅ | ✅ | ✅ | ❌ |
| PERSONALITY_WARMTH | ✅ | ✅ | ❌ | ❌ |
| PERSONALITY_WIT | ✅ | ✅ | ❌ | ❌ |
| PERSONALITY_CONCISENESS | ✅ | ✅ | ❌ | ❌ |
| PERSONALITY_ADAPTIVENESS | ✅ | ✅ | ❌ | ❌ |
| TRANSPARENCY_RULES | ✅ | ✅ | ❌ | ❌ |
| CONTEXT_HIERARCHY | ✅ | ✅ | ❌ | ❌ |
| BAD_TRIGGER_HANDLING | ❌ | ✅ | ❌ | ❌ |

## 集成方式

### 方式一：在 Workflow 的 userp_template 中添加

在 `ChatWorkflow` 和 `FutureMessageWorkflow` 的 userp_template 中引入组合提示词：

```python
from agent.prompt.personality_prompt import CHAT_AGENT_PERSONALITY

userp_template = (
    TASKPROMPT_微信对话 +
    CHAT_AGENT_PERSONALITY +  # 新增
    CONTEXTPROMPT_时间 +
    # ... 其他模板
)
```

### 方式二：在 Agent 的 instructions 中添加

修改 `agent/agno_agent/agents/__init__.py` 中的 Agent 定义：

```python
from agent.prompt.personality_prompt import CHAT_AGENT_PERSONALITY

chat_response_agent = Agent(
    id="chat-response-agent",
    name="ChatResponseAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=SYSTEMPROMPT_小说越狱 + CHAT_AGENT_PERSONALITY,  # 新增
    output_schema=ChatResponse,
    markdown=False,
)
```

### 推荐方式

推荐使用**方式一**，原因：
1. 人格规范与具体任务上下文相关，放在 user prompt 中更合适
2. system prompt 保持简洁，专注于角色扮演的基础设定
3. 便于根据不同场景动态调整

## 已完成的修改

1. ✅ 创建 `agent/prompt/personality_prompt.py`
2. ✅ 更新 `agent/prompt/chat_noticeprompt.py` 中的 `NOTICE_常规注意事项_空输入处理`

## 已完成的集成

1. ✅ 在 `ChatWorkflow.userp_template` 中添加 `CHAT_AGENT_PERSONALITY`
2. ✅ 在 `FutureMessageWorkflow.chat_userp_template` 中添加 `FUTURE_MESSAGE_AGENT_PERSONALITY`
3. ⏳ 在 `OrchestratorAgent` 的 instructions 中添加 `MESSAGE_SOURCE_HANDLING`（可选，暂不实施）

## 测试建议

集成后建议测试以下场景：
1. 用户发送简单问候（如"hi"），验证回复不是 AI 客服风格
2. 用户发送带 emoji 的消息，验证回复的 emoji 使用规则
3. 提醒触发场景，验证过时提醒是否被静默取消
4. 错误场景，验证不会暴露技术细节
