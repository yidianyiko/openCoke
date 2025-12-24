# Chat History Semantic Retrieval Implementation Plan

> **Version**: v1.0  
> **Date**: 2025-12-19  
> **Status**: Ready for Implementation  
> **Estimated Effort**: 3 days

---

## Problem Statement

The current system uses a sliding window of **20 recent messages** for chat history context. When users ask about past conversations (e.g., "remember what we talked about last week?"), the agent often cannot recall because older messages are discarded.

---

## Solution Overview

Enhance the context construction with **semantic retrieval** for chat history:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Enhanced Flow                                 │
├─────────────────────────────────────────────────────────────────┤
│  CONTEXTPROMPT_历史最近二十条对话                                │
│  → Recent 20 messages (sliding window, unchanged)               │
├─────────────────────────────────────────────────────────────────┤
│  CONTEXTPROMPT_历史最相关的十条对话                              │
│  → Semantically retrieved 10 messages (NEW)                     │
└─────────────────────────────────────────────────────────────────┘
```

**Key Benefits**:
- **Recency**: Recent 20 messages maintain conversation flow
- **Relevance**: Semantic 10 messages recall related history from any time
- **Cost**: Only embedding API cost (~$0.0001/message), zero extra LLM calls

---

## Implementation Tasks

### Phase 1: Storage - Save Chat Messages as Embeddings

#### Task 1.1: Add `store_chat_message()` function

**File**: `util/embedding_util.py`

```python
def store_chat_message(
    message: str,
    from_user: str,
    to_user: str,
    character_id: str,
    user_id: str,
    timestamp: int,
    message_type: str = "text"
) -> str:
    """
    Store a chat message as embedding for future retrieval.
    
    Args:
        message: Message content
        from_user: Sender user ID
        to_user: Receiver user ID
        character_id: Character ID
        user_id: User ID (human)
        timestamp: Message timestamp
        message_type: text/voice/image
    
    Returns:
        Inserted document ID, or None if failed
    """
    if not message or len(message.strip()) < 2:
        return None  # Skip empty or very short messages
    
    mongo = MongoDBBase()
    
    # Generate embedding for message content
    message_embedding = embedding_by_aliyun(message)
    if message_embedding is None:
        logger.warning(f"Failed to generate embedding for message: {message[:50]}...")
        return None
    
    # Create metadata
    metadata = {
        "type": "chat_history",
        "cid": character_id,
        "uid": user_id,
        "from_user": from_user,
        "to_user": to_user,
        "timestamp": timestamp,
        "message_type": message_type
    }
    
    # Store (key = message content, value = same for chat)
    doc_id = mongo.insert_vector(
        collection_name="embeddings",
        key=message,
        key_embedding=message_embedding,
        value=message,
        value_embedding=message_embedding,
        metadata=metadata
    )
    
    logger.debug(f"Stored chat message embedding: {doc_id}")
    return doc_id
```

#### Task 1.2: Integrate storage in `agent_handler.py`

**File**: `agent/runner/agent_handler.py`

Add a helper function and call it after successful conversation handling:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Thread pool for background embedding storage
_embedding_executor = ThreadPoolExecutor(max_workers=2)

def _store_messages_for_retrieval_sync(context: dict, resp_messages: list):
    """
    Store messages as embeddings for future retrieval (sync, runs in background thread).
    """
    from util.embedding_util import store_chat_message
    
    character_id = str(context.get("character", {}).get("_id", ""))
    user_id = str(context.get("user", {}).get("_id", ""))
    
    try:
        # Store user's input messages
        input_messages = context.get("conversation", {}).get("conversation_info", {}).get("input_messages", [])
        for msg in input_messages:
            message_content = msg.get("message", "")
            if message_content:
                store_chat_message(
                    message=message_content,
                    from_user=msg.get("from_user", ""),
                    to_user=msg.get("to_user", ""),
                    character_id=character_id,
                    user_id=user_id,
                    timestamp=msg.get("input_timestamp", 0),
                    message_type=msg.get("message_type", "text")
                )
        
        # Store character's responses
        for msg in resp_messages:
            message_content = msg.get("message", "")
            if message_content:
                store_chat_message(
                    message=message_content,
                    from_user=character_id,
                    to_user=user_id,
                    character_id=character_id,
                    user_id=user_id,
                    timestamp=msg.get("expect_output_timestamp", 0),
                    message_type=msg.get("message_type", "text")
                )
        
        logger.debug(f"Stored {len(input_messages) + len(resp_messages)} messages for semantic retrieval")
    except Exception as e:
        logger.warning(f"Failed to store messages for retrieval: {e}")

def store_messages_background(context: dict, resp_messages: list):
    """Submit message storage to background thread pool."""
    _embedding_executor.submit(_store_messages_for_retrieval_sync, context, resp_messages)
```

**Integration point**: After `conversation_dao.update_conversation_info()` succeeds, call:

```python
# Store messages for semantic retrieval (background, non-blocking)
store_messages_background(context, resp_messages)
```

---

### Phase 2: Retrieval - Extend context_retrieve_tool

#### Task 2.1: Extend `ContextRetrieveParams` Schema

**File**: `agent/agno_agent/schemas/orchestrator_schema.py`

```python
class ContextRetrieveParams(BaseModel):
    """上下文检索参数"""
    
    # ... existing fields ...
    
    # NEW: Chat history retrieval
    chat_history_query: str = Field(
        default="",
        description="历史对话检索语句，用于找回与当前话题相关的过往对话"
    )
    
    chat_history_keywords: str = Field(
        default="",
        description="历史对话关键词，逗号分隔"
    )
```

#### Task 2.2: Extend `context_retrieve_tool`

**File**: `agent/agno_agent/tools/context_retrieve_tool.py`

Add new parameters and retrieval logic:

```python
def context_retrieve_tool(
    character_setting_query: str = "",
    character_setting_keywords: str = "",
    user_profile_query: str = "",
    user_profile_keywords: str = "",
    character_knowledge_query: str = "",
    character_knowledge_keywords: str = "",
    chat_history_query: str = "",        # NEW
    chat_history_keywords: str = "",     # NEW
    character_id: str = "",
    user_id: str = ""
) -> dict:
    """
    向量检索工具，检索角色设定、用户资料、角色知识、相关历史对话
    """
    mongo = MongoDBBase()
    
    return_resp = {
        "character_global": "",
        "character_private": "",
        "user": "",
        "character_knowledge": "",
        "confirmed_reminders": "",
        "relevant_history": ""   # NEW
    }
    
    try:
        # ... existing retrieval code for character_global, character_private, user, character_knowledge ...
        
        # NEW: Chat history retrieval
        if chat_history_query or chat_history_keywords:
            return_resp["relevant_history"] = _search_embeddings(
                mongo=mongo,
                query_question=chat_history_query,
                query_keywords=chat_history_keywords,
                metadata_type="chat_history",
                character_id=character_id,
                user_id=user_id,
                top_k=15,        # Search more candidates
                result_limit=10  # Return top 10 relevant messages
            )
            logger.info(f"Retrieved {len(return_resp['relevant_history'])} relevant history messages")
        
        # ... existing reminder retrieval ...
        
    except Exception as e:
        logger.error(f"Error in context_retrieve_tool: {e}")
        raise
    
    return return_resp
```

#### Task 2.3: Update `prepare_workflow.py`

**File**: `agent/agno_agent/workflows/prepare_workflow.py`

Pass new parameters to `context_retrieve_tool`:

```python
context_result = context_retrieve_tool(
    character_setting_query=params.get("character_setting_query", ""),
    character_setting_keywords=params.get("character_setting_keywords", ""),
    user_profile_query=params.get("user_profile_query", ""),
    user_profile_keywords=params.get("user_profile_keywords", ""),
    character_knowledge_query=params.get("character_knowledge_query", ""),
    character_knowledge_keywords=params.get("character_knowledge_keywords", ""),
    chat_history_query=params.get("chat_history_query", ""),           # NEW
    chat_history_keywords=params.get("chat_history_keywords", ""),     # NEW
    character_id=character_id,
    user_id=user_id
)
```

---

### Phase 3: Context Integration

#### Task 3.1: Add/Update Context Templates

**File**: `agent/prompt/chat_contextprompt.py`

```python
# Rename existing template for clarity
CONTEXTPROMPT_历史最近二十条对话 = '''### 历史对话（最近二十条）
{conversation[conversation_info][chat_history_str]}'''

# Keep old name as alias for backward compatibility
CONTEXTPROMPT_最近的历史对话 = CONTEXTPROMPT_历史最近二十条对话

# NEW: Semantically retrieved history
CONTEXTPROMPT_历史最相关的十条对话 = '''### 相关历史对话（语义检索）
以下是与当前话题语义相关的过往对话：
{context_retrieve[relevant_history]}'''
```

#### Task 3.2: Update Template Composition

**File**: `agent/agno_agent/workflows/chat_workflow_streaming.py`

```python
from agent.prompt.chat_contextprompt import (
    # ... existing imports ...
    CONTEXTPROMPT_历史最近二十条对话,
    CONTEXTPROMPT_历史最相关的十条对话,  # NEW
)

# Update userp_template_base
userp_template_base = (
    TASKPROMPT_微信对话 +
    CONTEXTPROMPT_时间 +
    CONTEXTPROMPT_人物信息 +
    CONTEXTPROMPT_人物资料 +
    CONTEXTPROMPT_用户资料 +
    CONTEXTPROMPT_待办提醒 +
    CONTEXTPROMPT_人物知识和技能 +
    CONTEXTPROMPT_人物状态 +
    CONTEXTPROMPT_当前目标 +
    CONTEXTPROMPT_当前的人物关系 +
    CONTEXTPROMPT_历史最相关的十条对话 +    # NEW: Semantic history (10)
    CONTEXTPROMPT_历史最近二十条对话         # RENAMED: Recent history (20)
)
```

#### Task 3.3: Set Default Value in `context.py`

**File**: `agent/runner/context.py`

```python
# In context_prepare(), update context_retrieve defaults:
context.setdefault("context_retrieve", {
    "character_global": "",
    "character_private": "",
    "user": "",
    "character_knowledge": "",
    "confirmed_reminders": "",
    "relevant_history": ""   # NEW
})
```

---

### Phase 4: OrchestratorAgent Prompt Update

#### Task 4.1: Update Orchestrator Instructions

**File**: `agent/prompt/chat_taskprompt.py` (or wherever TASKPROMPT_语义理解 is defined)

Add guidance for generating `chat_history_query`:

```python
# Add to TASKPROMPT_语义理解:

"""
## 历史对话检索
当用户消息涉及以下情况时，生成 chat_history_query 和 chat_history_keywords：
- 用户提到过去的对话或事件（如"我之前跟你说过的..."、"上次我们聊的..."）
- 用户询问之前讨论的内容（如"你还记得我说的那件事吗？"）
- 用户回顾或延续之前的话题

示例：
- 用户说"我之前跟你说过的那件事" → chat_history_query="用户提到的事件", chat_history_keywords="之前,说过,事件"
- 用户说"上次我们聊的电影" → chat_history_query="电影讨论", chat_history_keywords="电影,上次,推荐"
- 用户说"你还记得我养的猫吗" → chat_history_query="用户的宠物猫", chat_history_keywords="猫,宠物,养"

如果用户消息不涉及历史对话，chat_history_query 和 chat_history_keywords 留空.
"""
```

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `util/embedding_util.py` | Add function | `store_chat_message()` |
| `agent/runner/agent_handler.py` | Add function + integration | `store_messages_background()` |
| `agent/agno_agent/schemas/orchestrator_schema.py` | Add fields | `chat_history_query`, `chat_history_keywords` |
| `agent/agno_agent/tools/context_retrieve_tool.py` | Extend | Add `relevant_history` retrieval |
| `agent/agno_agent/workflows/prepare_workflow.py` | Update | Pass new params to tool |
| `agent/prompt/chat_contextprompt.py` | Add template | `CONTEXTPROMPT_历史最相关的十条对话` |
| `agent/agno_agent/workflows/chat_workflow_streaming.py` | Update | Include new template |
| `agent/runner/context.py` | Update | Add `relevant_history` default |
| `agent/prompt/chat_taskprompt.py` | Update | Add orchestrator guidance |

---

## Execution Order

```
Phase 1: Storage
├── Task 1.1: Add store_chat_message() in embedding_util.py
└── Task 1.2: Add store_messages_background() in agent_handler.py

Phase 2: Retrieval
├── Task 2.1: Extend ContextRetrieveParams schema
├── Task 2.2: Extend context_retrieve_tool
└── Task 2.3: Update prepare_workflow.py

Phase 3: Context Integration
├── Task 3.1: Add/update context templates
├── Task 3.2: Update workflow template composition
└── Task 3.3: Set default value in context.py

Phase 4: Prompt Update
└── Task 4.1: Update orchestrator instructions

Phase 5: Testing
├── Test message storage (verify embeddings in MongoDB)
├── Test retrieval (verify relevant history returned)
└── Test end-to-end (verify agent recalls past conversations)
```

---

## Testing Checklist

- [ ] New messages are stored in `embeddings` collection with `metadata.type = "chat_history"`
- [ ] `context_retrieve_tool` returns `relevant_history` when query provided
- [ ] Context template renders correctly with relevant history
- [ ] Agent can recall past conversations when user asks
- [ ] Background storage does not block main conversation flow
- [ ] Empty/short messages are not stored (to avoid noise)

---

## Cost Analysis

| Item | Cost |
|------|------|
| Aliyun Embedding API | ~$0.0001 per message |
| MongoDB storage | Negligible (existing infra) |
| Extra LLM calls | 0 |

For 1000 conversations/month × 5 messages avg = **$0.50/month**

---

## Rollback Plan

If issues arise:
1. Remove `CONTEXTPROMPT_历史最相关的十条对话` from template composition
2. Set `chat_history_query` and `chat_history_keywords` to always empty in prepare_workflow
3. Storage can continue (no harm); retrieval is simply disabled

---

## Future Enhancements

1. **Deduplication**: Exclude messages that already appear in recent 20 from semantic results
2. **Time-aware retrieval**: Add timestamp filtering (e.g., "last week" → filter by date range)
3. **Cleanup job**: Periodically clean old embeddings (e.g., >6 months) to manage storage
