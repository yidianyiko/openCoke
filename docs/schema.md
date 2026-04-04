# MongoDB Schema Reference

本文档只保留当前系统常用集合的简明说明。字段会随功能演进扩展，这里列的是主干字段而不是完整 schema。

## users

```json
{
  "_id": "ObjectId",
  "is_character": true,
  "name": "qiaoyun",
  "platforms": {
    "wechat": {
      "id": "platform-user-id",
      "account": "wechat-account",
      "nickname": "昵称"
    }
  },
  "status": "normal",
  "user_info": {}
}
```

## conversations

```json
{
  "_id": "ObjectId",
  "platform": "wechat",
  "chatroom_name": null,
  "talkers": [],
  "conversation_info": {
    "chat_history": [],
    "chat_history_str": "",
    "input_messages": [],
    "input_messages_str": "",
    "photo_history": [],
    "future": {}
  }
}
```

## reminders

```json
{
  "_id": "ObjectId",
  "user_id": "ObjectId",
  "conversation_id": "ObjectId",
  "title": "买牛奶",
  "status": "active",
  "next_trigger_time": 1738289400,
  "list_id": "default",
  "created_at": "datetime"
}
```

说明：

- `list_id="inbox"` 通常表示没有具体触发时间的待办
- `next_trigger_time=null` 表示尚未安排具体触发时间

## inputmessages

```json
{
  "_id": "ObjectId",
  "input_timestamp": 1738289400,
  "handled_timestamp": null,
  "status": "pending",
  "from_user": "ObjectId",
  "to_user": "ObjectId",
  "platform": "wechat",
  "chatroom_name": null,
  "message_type": "text",
  "message": "你好",
  "metadata": {}
}
```

常见状态：

- `pending`
- `handled`
- `failed`
- `hold`

附加控制字段可能包括 `retry_count`、`rollback_count`、`hold_started_at`、`last_error`。

## outputmessages

```json
{
  "_id": "ObjectId",
  "expect_output_timestamp": 1738289400,
  "handled_timestamp": null,
  "status": "pending",
  "from_user": "ObjectId",
  "to_user": "ObjectId",
  "platform": "wechat",
  "chatroom_name": null,
  "message_type": "text",
  "message": "收到",
  "metadata": {}
}
```

常见状态：

- `pending`
- `handled`
- `failed`

## embeddings

```json
{
  "_id": "ObjectId",
  "key": "角色设定-作息",
  "key_embedding": [],
  "value": "晚上容易熬夜",
  "value_embedding": [],
  "metadata": {
    "type": "character_global",
    "uid": "ObjectId",
    "cid": "ObjectId",
    "url": "",
    "from_user": "ObjectId",
    "to_user": "ObjectId",
    "timestamp": 1738289400,
    "message_type": "text"
  }
}
```

## locks

```json
{
  "_id": "ObjectId",
  "resource_type": "conversation",
  "resource_id": "conversation:...",
  "holder": "worker-1",
  "expires_at": "datetime"
}
```

## orders

```json
{
  "_id": "ObjectId",
  "order_no": "ORDER-001",
  "expire_time": "datetime",
  "bound_user_id": null,
  "bound_at": null,
  "created_at": "datetime",
  "metadata": {}
}
```

## usage_records

```json
{
  "_id": "ObjectId",
  "timestamp": "datetime",
  "user_id": "ObjectId",
  "agent_name": "OrchestratorAgent",
  "input_tokens": 100,
  "output_tokens": 200,
  "total_tokens": 300,
  "duration": 1.2
}
```
