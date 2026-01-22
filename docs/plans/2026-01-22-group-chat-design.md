# 群聊消息接收与回复功能设计

## 1. 设计决策

| 决策项 | 选择 |
|--------|------|
| 回复触发机制 | 可配置：白名单群全回复，其他群只响应@ |
| 上下文管理 | 仅保留最近 N 条群消息（不区分用户） |
| 回复风格 | 与私聊保持一致 |

## 2. 当前实现分析

### 2.1 现有架构

```
ecloud_input.py  → 接收 webhook，过滤消息类型，创建 inputmessage
ecloud_adapter.py → 消息格式转换 (ecloud ↔ 标准格式)
ecloud_output.py → 轮询 outputmessages，发送消息
ecloud_api.py    → E云 API 封装
```

### 2.2 当前限制

- `supported_message_types` 只包含私聊类型: `60001, 60002, 60004, 60014`
- `ecloud_adapter.py` 中 `chatroom_name` 始终设为 `None`
- 不解析 `fromGroup` 字段

### 2.3 E云群消息格式 (参考文档)

```json
{
    "wcId": "wxid_xxx",
    "messageType": "80001",  // 群聊文本
    "data": {
        "fromUser": "wxid_sender",
        "fromGroup": "19931632641@chatroom",  // 群ID
        "toUser": "wxid_bot",
        "content": "消息内容",
        "timestamp": 1640845960
    }
}
```

群消息类型：
- `80001`: 群文本
- `80002`: 群图片
- `80004`: 群语音
- `80014`: 群引用消息

## 3. 数据结构变更

### 3.1 变更总览

| 存储位置 | 变更类型 | 说明 |
|----------|----------|------|
| `conf/config.json` | **新增** | 添加 `group_chat` 配置块 |
| `inputmessages` 集合 | **复用** | `chatroom_name` 字段从 `None` 变为群ID |
| `inputmessages.metadata` | **扩展** | 新增 `sender_nickname`, `original_sender_wxid` |
| `outputmessages` 集合 | **无变化** | 已有 `chatroom_name` 字段支持 |
| `users` 集合 | **无变化** | 群成员复用现有用户结构 |
| `conversations` 集合 | **无变化** | 已有群聊支持 |

### 3.2 inputmessages 集合结构

**现有字段** (无需修改 schema):
```python
{
    "_id": ObjectId,
    "input_timestamp": int,           # 输入时间戳
    "handled_timestamp": int | None,  # 处理完成时间戳
    "status": str,                    # pending | handled | canceled | failed
    "platform": str,                  # "wechat"
    "chatroom_name": str | None,      # 私聊=None, 群聊=群ID (如 "xxx@chatroom")
    "from_user": str,                 # 发送者 MongoDB user ID
    "to_user": str,                   # 接收者 MongoDB character ID
    "message_type": str,              # text | image | voice | reference
    "message": str,                   # 消息内容
    "metadata": dict                  # 扩展元数据
}
```

**metadata 扩展** (群聊消息新增):
```python
"metadata": {
    # 现有字段
    "file_path": str,        # 语音/图片文件路径
    "url": str,              # 图片URL
    "reference": dict,       # 引用消息信息

    # 群聊新增字段
    "sender_nickname": str,       # 群消息发送者昵称 (用于上下文显示)
    "original_sender_wxid": str,  # 发送者微信ID (用于回复时@)
    "is_mention": bool,           # 是否@了机器人
}
```

### 3.3 outputmessages 集合结构

**无需修改**，现有结构已支持群聊:
```python
{
    "_id": ObjectId,
    "platform": str,
    "chatroom_name": str | None,  # 群聊时填群ID，私聊为None
    "from_user": str,             # character ID
    "to_user": str,               # user ID
    "message_type": str,
    "message": str,
    "metadata": {
        "at": str | None,         # 可选：@的用户wxid (群聊回复时使用)
    }
}
```

### 3.4 数据流示意

```
E云群消息 (fromGroup: "xxx@chatroom")
    ↓
ecloud_adapter.py: chatroom_name = fromGroup
    ↓
inputmessages: { chatroom_name: "xxx@chatroom", metadata: { sender_nickname, ... } }
    ↓
agent 处理
    ↓
outputmessages: { chatroom_name: "xxx@chatroom", metadata: { at: "wxid_xxx" } }
    ↓
ecloud_output.py: wcId = chatroom_name, at = metadata.at
```

## 4. 配置设计

### 4.1 新增配置项 (conf/config.json)

```json
{
  "ecloud": {
    "Authorization": "...",
    "wId": { "qiaoyun": "xxx" },
    "group_chat": {
      "enabled": true,
      "context_message_count": 10,
      "whitelist_groups": ["19931632641@chatroom"],
      "reply_mode": {
        "whitelist": "all",
        "others": "mention_only"
      }
    }
  }
}
```

### 4.2 配置说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用群聊功能 |
| `context_message_count` | int | 群聊上下文保留消息数量 |
| `whitelist_groups` | list | 白名单群ID列表 |
| `reply_mode.whitelist` | str | 白名单群回复模式: `all` |
| `reply_mode.others` | str | 其他群回复模式: `mention_only` |

## 5. 实现计划

### Phase 1: 消息接收 (ecloud_input.py)

#### Task 1.1: 添加群消息类型支持

**文件**: `connector/ecloud/ecloud_input.py`

**修改**:
```python
supported_message_types = [
    # 私聊
    "60001", "60014", "60004", "60002",
    # 群聊 (新增)
    "80001", "80002", "80004", "80014",
]
```

#### Task 1.2: 群聊配置加载与判断逻辑

**文件**: `connector/ecloud/ecloud_input.py`

**新增函数**:
```python
def is_group_message(data: dict) -> bool:
    """判断是否为群消息"""
    return data.get("messageType", "").startswith("8")

def should_respond_to_group_message(data: dict, character_wxid: str) -> bool:
    """判断是否应该响应群消息"""
    group_config = CONF.get("ecloud", {}).get("group_chat", {})

    if not group_config.get("enabled", False):
        return False

    group_id = data["data"].get("fromGroup")
    whitelist = group_config.get("whitelist_groups", [])
    reply_mode = group_config.get("reply_mode", {})

    if group_id in whitelist:
        # 白名单群：全部回复
        return reply_mode.get("whitelist") == "all"
    else:
        # 其他群：只响应@
        if reply_mode.get("others") == "mention_only":
            return is_mention_bot(data, character_wxid)
        return False

def is_mention_bot(data: dict, character_wxid: str) -> bool:
    """检测消息是否@了机器人"""
    content = data["data"].get("content", "")
    # E云@消息格式: @昵称 消息内容
    # 也可能包含在 XML 中
    # 需要结合实际测试完善
    return character_wxid in content or "@" in content
```

#### Task 1.3: 群成员用户创建

**文件**: `connector/ecloud/ecloud_input.py`

群消息的 `fromUser` 是发送者的 wxid，需要：
1. 检查用户是否存在
2. 不存在则通过 `getContact` 或 `getChatRoomMemberInfo` 获取信息并创建

### Phase 2: 消息适配 (ecloud_adapter.py)

#### Task 2.1: 群消息格式转换

**文件**: `connector/ecloud/ecloud_adapter.py`

**修改 `ecloud_message_to_std` 函数**:
```python
def ecloud_message_to_std(message):
    msg_type = message["messageType"]

    # 判断是否群消息
    is_group = msg_type.startswith("8")
    group_id = message["data"].get("fromGroup") if is_group else None

    # 映射到对应的处理函数
    type_mapping = {
        "60001": ecloud_message_to_std_text_single,
        "80001": ecloud_message_to_std_text_single,  # 群文本复用
        "60002": ecloud_message_to_std_image_single,
        "80002": ecloud_message_to_std_image_single,
        "60004": ecloud_message_to_std_voice_single,
        "80004": ecloud_message_to_std_voice_single,
        "60014": ecloud_message_to_std_reference_single,
        "80014": ecloud_message_to_std_reference_single,
    }

    handler = type_mapping.get(msg_type)
    if handler:
        std_msg = handler(message)
        std_msg["chatroom_name"] = group_id  # 关键：设置群ID
        return std_msg
    return None
```

#### Task 2.2: 群消息中提取发送者昵称

群消息中可能需要显示发送者昵称用于上下文，在 metadata 中添加：
```python
std_msg["metadata"]["sender_nickname"] = "xxx"  # 从群成员信息获取
```

### Phase 3: 触发与上下文

#### Task 3.1: 群聊上下文查询

**文件**: `dao/conversation_dao.py` (已有基础支持)

确认现有方法：
- `get_group_conversation(platform, chatroom_name)`
- `create_group_conversation(platform, chatroom_name, initial_talkers)`

**新增/修改**: 获取最近 N 条群消息
```python
def get_recent_group_messages(self, chatroom_name: str, limit: int = 10) -> list:
    """获取群聊最近N条消息"""
    return list(self.mongo.find(
        "inputmessages",
        {"chatroom_name": chatroom_name, "status": "handled"},
        sort=[("input_timestamp", -1)],
        limit=limit
    ))
```

#### Task 3.2: 上下文注入到 workflow

**文件**: `agent/runner/agent_handler.py` 或相关 workflow

在处理群消息时，将最近 N 条消息作为上下文注入 prompt。

### Phase 4: 消息发送

#### Task 4.1: 群聊发送逻辑

**文件**: `connector/ecloud/ecloud_output.py`

现有代码已支持：
```python
if message["chatroom_name"] is None:
    ecloud["wcId"] = user["platforms"]["wechat"]["account"]
else:
    ecloud["wcId"] = message["chatroom_name"]  # 已正确使用群ID
```

无需大改，但需验证群消息发送是否正常工作。

#### Task 4.2: @用户功能 (可选)

**文件**: `connector/ecloud/ecloud_api.py`

**新增方法**:
```python
@staticmethod
def sendTextWithMention(data):
    """发送带@的文本消息
    data: {
        "wId": "xxx",
        "wcId": "groupId@chatroom",
        "content": "@昵称 消息内容",
        "at": "wxid_user"  # 被@的用户wxid
    }
    """
    resp = requests.post(
        url=host + "/sendText",
        json=data,
        headers={"Authorization": auth, "Content-Type": "application/json"},
    )
    return json.loads(resp.content.decode("utf-8"))
```

**修改 ecloud_output.py**:
在群聊回复时，可选@原消息发送者：
```python
if message["chatroom_name"] is not None:
    # 群聊回复，@原发送者
    original_sender_wxid = message.get("metadata", {}).get("original_sender_wxid")
    if original_sender_wxid:
        ecloud["at"] = original_sender_wxid
```

## 6. 测试计划

### 5.1 单元测试

- [ ] `test_is_group_message`: 正确识别群消息类型
- [ ] `test_should_respond_to_group_message`: 白名单/非白名单/@ 判断
- [ ] `test_ecloud_message_to_std_group`: 群消息正确转换

### 5.2 集成测试

- [ ] 白名单群收到消息 → 自动回复
- [ ] 非白名单群收到普通消息 → 不回复
- [ ] 非白名单群被@消息 → 回复
- [ ] 群聊回复正确发送到群

## 7. 实现顺序

```
Phase 1: 消息接收
├── Task 1.1: 添加群消息类型 (ecloud_input.py)
├── Task 1.2: 群聊判断逻辑 (ecloud_input.py)
└── Task 1.3: 群成员用户创建 (ecloud_input.py)

Phase 2: 消息适配
├── Task 2.1: 群消息格式转换 (ecloud_adapter.py)
└── Task 2.2: 提取发送者信息 (ecloud_adapter.py)

Phase 3: 上下文管理
├── Task 3.1: 群聊上下文查询 (conversation_dao.py)
└── Task 3.2: 上下文注入 workflow (agent_handler.py)

Phase 4: 消息发送
├── Task 4.1: 验证群聊发送 (ecloud_output.py)
└── Task 4.2: @用户功能 (ecloud_api.py, ecloud_output.py)
```

## 8. 风险与注意事项

1. **@检测准确性**: E云@消息格式需实际测试验证
2. **群成员信息获取**: `getChatRoomMemberInfo` 一次只能查一个成员，可能需要缓存
3. **消息去重**: 参考文档提到消息可能重复投递，需用 `newMsgId` 去重
4. **性能**: 白名单群全回复可能导致高负载，需监控
