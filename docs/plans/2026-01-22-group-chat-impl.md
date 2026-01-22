# 群聊消息接收与回复 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 E云管家群聊消息的接收、处理和回复功能

**Architecture:** 扩展现有 ecloud connector，添加群消息类型支持（80001-80014），通过配置控制回复策略（白名单群全回复，其他群仅@回复），复用现有消息处理流程

**Tech Stack:** Python 3.12, Flask, MongoDB, pytest

---

## Task 1: 添加群聊配置项

**Files:**
- Modify: `conf/config.json`

**Step 1: 添加 group_chat 配置块**

在 `ecloud` 配置块中添加群聊配置：

```json
{
  "ecloud": {
    "Authorization": "...",
    "wId": { "qiaoyun": "..." },
    "group_chat": {
      "enabled": false,
      "context_message_count": 10,
      "whitelist_groups": [],
      "reply_mode": {
        "whitelist": "all",
        "others": "mention_only"
      }
    }
  }
}
```

**Step 2: Commit**

```bash
git add conf/config.json
git commit -m "feat(ecloud): add group_chat configuration structure"
```

---

## Task 2: 创建 ecloud adapter 单元测试

**Files:**
- Create: `tests/unit/connector/test_ecloud_adapter.py`

**Step 1: 写测试文件**

```python
import pytest


class TestIsGroupMessage:
    """Test group message detection."""

    def test_group_text_message(self):
        """80001 should be detected as group message."""
        from connector.ecloud.ecloud_adapter import is_group_message

        data = {"messageType": "80001"}
        assert is_group_message(data) is True

    def test_group_image_message(self):
        """80002 should be detected as group message."""
        from connector.ecloud.ecloud_adapter import is_group_message

        data = {"messageType": "80002"}
        assert is_group_message(data) is True

    def test_private_text_message(self):
        """60001 should not be detected as group message."""
        from connector.ecloud.ecloud_adapter import is_group_message

        data = {"messageType": "60001"}
        assert is_group_message(data) is False

    def test_private_image_message(self):
        """60002 should not be detected as group message."""
        from connector.ecloud.ecloud_adapter import is_group_message

        data = {"messageType": "60002"}
        assert is_group_message(data) is False


class TestEcloudMessageToStdGroup:
    """Test group message conversion to standard format."""

    def test_group_text_message_sets_chatroom_name(self):
        """Group text message should have chatroom_name set."""
        from connector.ecloud.ecloud_adapter import ecloud_message_to_std

        message = {
            "messageType": "80001",
            "data": {
                "fromUser": "wxid_sender",
                "fromGroup": "12345678@chatroom",
                "toUser": "wxid_bot",
                "content": "Hello group",
                "timestamp": 1640845960,
            },
        }

        result = ecloud_message_to_std(message)

        assert result["chatroom_name"] == "12345678@chatroom"
        assert result["message"] == "Hello group"
        assert result["message_type"] == "text"
        assert result["platform"] == "wechat"

    def test_private_text_message_chatroom_name_is_none(self):
        """Private text message should have chatroom_name as None."""
        from connector.ecloud.ecloud_adapter import ecloud_message_to_std

        message = {
            "messageType": "60001",
            "data": {
                "fromUser": "wxid_sender",
                "toUser": "wxid_bot",
                "content": "Hello private",
                "timestamp": 1640845960,
            },
        }

        result = ecloud_message_to_std(message)

        assert result["chatroom_name"] is None
        assert result["message"] == "Hello private"

    def test_group_message_extracts_sender_wxid(self):
        """Group message should extract sender wxid to metadata."""
        from connector.ecloud.ecloud_adapter import ecloud_message_to_std

        message = {
            "messageType": "80001",
            "data": {
                "fromUser": "wxid_sender123",
                "fromGroup": "12345678@chatroom",
                "toUser": "wxid_bot",
                "content": "Test message",
                "timestamp": 1640845960,
            },
        }

        result = ecloud_message_to_std(message)

        assert result["metadata"]["original_sender_wxid"] == "wxid_sender123"
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/unit/connector/test_ecloud_adapter.py -v`
Expected: FAIL (is_group_message not defined, or chatroom_name always None)

**Step 3: Commit 测试文件**

```bash
git add tests/unit/connector/test_ecloud_adapter.py
git commit -m "test(ecloud): add unit tests for group message adapter"
```

---

## Task 3: 实现 is_group_message 函数

**Files:**
- Modify: `connector/ecloud/ecloud_adapter.py`

**Step 1: 在文件顶部添加 is_group_message 函数**

在 import 语句之后、第一个现有函数之前添加：

```python
def is_group_message(data: dict) -> bool:
    """判断是否为群消息

    群消息类型以 '8' 开头：80001, 80002, 80004, 80014
    私聊消息类型以 '6' 开头：60001, 60002, 60004, 60014
    """
    return data.get("messageType", "").startswith("8")
```

**Step 2: 运行测试验证 is_group_message**

Run: `pytest tests/unit/connector/test_ecloud_adapter.py::TestIsGroupMessage -v`
Expected: PASS

**Step 3: Commit**

```bash
git add connector/ecloud/ecloud_adapter.py
git commit -m "feat(ecloud): add is_group_message detection function"
```

---

## Task 4: 修改 ecloud_message_to_std 支持群消息

**Files:**
- Modify: `connector/ecloud/ecloud_adapter.py`

**Step 1: 重构 ecloud_message_to_std 函数**

替换现有的 `ecloud_message_to_std` 函数：

```python
def ecloud_message_to_std(message):
    """将 E云消息转换为标准格式

    支持私聊消息类型：60001(文本), 60002(图片), 60004(语音), 60014(引用)
    支持群聊消息类型：80001(文本), 80002(图片), 80004(语音), 80014(引用)
    """
    msg_type = message["messageType"]

    # 判断是否群消息，提取群ID
    is_group = is_group_message(message)
    group_id = message["data"].get("fromGroup") if is_group else None

    # 映射到对应的处理函数（私聊和群聊使用相同的处理逻辑）
    type_mapping = {
        "60001": ecloud_message_to_std_text_single,
        "80001": ecloud_message_to_std_text_single,
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
        std_msg["chatroom_name"] = group_id
        # 群消息时记录发送者wxid，用于回复时@
        if is_group:
            std_msg["metadata"]["original_sender_wxid"] = message["data"].get("fromUser")
        return std_msg
    return None
```

**Step 2: 运行全部 adapter 测试**

Run: `pytest tests/unit/connector/test_ecloud_adapter.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add connector/ecloud/ecloud_adapter.py
git commit -m "feat(ecloud): support group message conversion in adapter"
```

---

## Task 5: 创建群聊回复判断逻辑测试

**Files:**
- Modify: `tests/unit/connector/test_ecloud_adapter.py`

**Step 1: 添加测试类**

在测试文件末尾添加：

```python
class TestShouldRespondToGroupMessage:
    """Test group message response decision logic."""

    def test_disabled_group_chat_returns_false(self):
        """When group_chat.enabled is False, should not respond."""
        from connector.ecloud.ecloud_adapter import should_respond_to_group_message

        config = {
            "enabled": False,
            "whitelist_groups": ["12345@chatroom"],
            "reply_mode": {"whitelist": "all", "others": "mention_only"},
        }
        data = {
            "messageType": "80001",
            "data": {"fromGroup": "12345@chatroom", "content": "Hello"},
        }

        result = should_respond_to_group_message(data, config, "wxid_bot", "机器人")
        assert result is False

    def test_whitelist_group_all_mode_returns_true(self):
        """Whitelist group with 'all' mode should respond to any message."""
        from connector.ecloud.ecloud_adapter import should_respond_to_group_message

        config = {
            "enabled": True,
            "whitelist_groups": ["12345@chatroom"],
            "reply_mode": {"whitelist": "all", "others": "mention_only"},
        }
        data = {
            "messageType": "80001",
            "data": {"fromGroup": "12345@chatroom", "content": "Hello"},
        }

        result = should_respond_to_group_message(data, config, "wxid_bot", "机器人")
        assert result is True

    def test_non_whitelist_group_without_mention_returns_false(self):
        """Non-whitelist group without mention should not respond."""
        from connector.ecloud.ecloud_adapter import should_respond_to_group_message

        config = {
            "enabled": True,
            "whitelist_groups": ["other_group@chatroom"],
            "reply_mode": {"whitelist": "all", "others": "mention_only"},
        }
        data = {
            "messageType": "80001",
            "data": {"fromGroup": "12345@chatroom", "content": "Hello"},
        }

        result = should_respond_to_group_message(data, config, "wxid_bot", "机器人")
        assert result is False

    def test_non_whitelist_group_with_mention_returns_true(self):
        """Non-whitelist group with @mention should respond."""
        from connector.ecloud.ecloud_adapter import should_respond_to_group_message

        config = {
            "enabled": True,
            "whitelist_groups": [],
            "reply_mode": {"whitelist": "all", "others": "mention_only"},
        }
        data = {
            "messageType": "80001",
            "data": {"fromGroup": "12345@chatroom", "content": "@机器人 你好"},
        }

        result = should_respond_to_group_message(data, config, "wxid_bot", "机器人")
        assert result is True


class TestIsMentionBot:
    """Test @mention detection logic."""

    def test_mention_by_nickname(self):
        """Should detect mention by nickname."""
        from connector.ecloud.ecloud_adapter import is_mention_bot

        content = "@洛云 你好啊"
        result = is_mention_bot(content, "wxid_bot", "洛云")
        assert result is True

    def test_no_mention(self):
        """Should return False when no mention."""
        from connector.ecloud.ecloud_adapter import is_mention_bot

        content = "大家好"
        result = is_mention_bot(content, "wxid_bot", "洛云")
        assert result is False

    def test_mention_other_user(self):
        """Should return False when mentioning other user."""
        from connector.ecloud.ecloud_adapter import is_mention_bot

        content = "@张三 你好"
        result = is_mention_bot(content, "wxid_bot", "洛云")
        assert result is False
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/unit/connector/test_ecloud_adapter.py::TestShouldRespondToGroupMessage -v`
Expected: FAIL (should_respond_to_group_message not defined)

**Step 3: Commit**

```bash
git add tests/unit/connector/test_ecloud_adapter.py
git commit -m "test(ecloud): add tests for group message response logic"
```

---

## Task 6: 实现群聊回复判断函数

**Files:**
- Modify: `connector/ecloud/ecloud_adapter.py`

**Step 1: 添加 is_mention_bot 函数**

在 `is_group_message` 函数之后添加：

```python
def is_mention_bot(content: str, bot_wxid: str, bot_nickname: str) -> bool:
    """检测消息是否@了机器人

    E云@消息格式: @昵称 消息内容

    Args:
        content: 消息内容
        bot_wxid: 机器人的微信ID
        bot_nickname: 机器人的昵称

    Returns:
        bool: 是否@了机器人
    """
    if not content:
        return False
    # 检查是否包含 @昵称 格式
    mention_pattern = f"@{bot_nickname}"
    return mention_pattern in content
```

**Step 2: 添加 should_respond_to_group_message 函数**

在 `is_mention_bot` 函数之后添加：

```python
def should_respond_to_group_message(
    data: dict, config: dict, bot_wxid: str, bot_nickname: str
) -> bool:
    """判断是否应该响应群消息

    Args:
        data: E云消息数据
        config: group_chat 配置
        bot_wxid: 机器人的微信ID
        bot_nickname: 机器人的昵称

    Returns:
        bool: 是否应该响应
    """
    if not config.get("enabled", False):
        return False

    group_id = data["data"].get("fromGroup")
    if not group_id:
        return False

    whitelist = config.get("whitelist_groups", [])
    reply_mode = config.get("reply_mode", {})

    if group_id in whitelist:
        # 白名单群：根据配置决定
        return reply_mode.get("whitelist") == "all"
    else:
        # 其他群：只响应@
        if reply_mode.get("others") == "mention_only":
            content = data["data"].get("content", "")
            return is_mention_bot(content, bot_wxid, bot_nickname)
        return False
```

**Step 3: 运行测试验证**

Run: `pytest tests/unit/connector/test_ecloud_adapter.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add connector/ecloud/ecloud_adapter.py
git commit -m "feat(ecloud): add group message response decision logic"
```

---

## Task 7: 修改 ecloud_input.py 支持群消息类型

**Files:**
- Modify: `connector/ecloud/ecloud_input.py`

**Step 1: 添加 import 和配置**

在文件顶部的 import 区域添加：

```python
from conf.config import CONF
from connector.ecloud.ecloud_adapter import (
    ecloud_message_to_std,
    is_group_message,
    should_respond_to_group_message,
)
```

**Step 2: 扩展 supported_message_types**

修改 `supported_message_types` 列表：

```python
supported_message_types = [
    # 私聊消息
    "60001",  # 私聊文本
    "60014",  # 私聊引用
    "60004",  # 私聊语音
    "60002",  # 私聊图片
    # 群聊消息
    "80001",  # 群聊文本
    "80014",  # 群聊引用
    "80004",  # 群聊语音
    "80002",  # 群聊图片
]
```

**Step 3: Commit**

```bash
git add connector/ecloud/ecloud_input.py
git commit -m "feat(ecloud): add group message types to supported list"
```

---

## Task 8: 修改 handle_message 处理群消息

**Files:**
- Modify: `connector/ecloud/ecloud_input.py`

**Step 1: 修改 handle_message 函数**

在 `handle_message` 函数中，在 `# 验证character或者user是否存在` 之后，修改逻辑以支持群消息：

```python
@app.route("/message", methods=["POST"])
def handle_message():
    """Handle incoming message requests and forward them based on wcId"""
    if not request.is_json:
        logger.warning("Request is not JSON")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    data = request.get_json()
    logger.info(data)

    wcId = data.get("wcId")
    if not wcId:
        logger.warning("No wcId in request")
        return jsonify({"status": "error", "message": "No wcId provided"}), 400

    # 转发逻辑保持不变
    if wcId in whitelist:
        forward_url = whitelist[wcId]
        try:
            logger.info(f"Forwarding request for wcId {wcId} to {forward_url}")
            response = requests.post(
                forward_url, json=data, headers={"Content-Type": "application/json"}
            )
            return jsonify({
                "status": "success",
                "message": f"Request forwarded to {forward_url}",
                "forward_status": response.status_code,
                "forward_response": (
                    response.json()
                    if response.headers.get("content-type") == "application/json"
                    else response.text
                ),
            })
        except requests.RequestException as e:
            logger.error(f"Error forwarding request: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"Error forwarding request: {str(e)}",
            }), 500

    logger.info("message incoming, handling...")

    # 支持的类型
    if data["messageType"] not in supported_message_types:
        logger.info("not supported message type.")
        return jsonify({"status": "success", "message": "not supported message type."}), 200

    # 用户白名单检查
    if len(user_whitelist) != 0:
        if data["data"]["fromUser"] not in user_whitelist:
            logger.info("user not in white list, ignore this message")
            return jsonify({
                "status": "success",
                "message": "user not in white list, ignore this message",
            }), 200

    # 验证character是否存在
    characters = user_dao.find_characters(
        {"platforms.wechat.id": data["data"]["toUser"]}
    )
    if len(characters) == 0:
        return jsonify({"status": "success", "message": "character not exist, skip..."}), 200

    cid = str(characters[0]["_id"])
    character = characters[0]

    # 群消息特殊处理
    if is_group_message(data):
        group_config = CONF.get("ecloud", {}).get("group_chat", {})
        bot_wxid = data["data"]["toUser"]
        bot_nickname = character.get("name", "")

        if not should_respond_to_group_message(data, group_config, bot_wxid, bot_nickname):
            logger.info("group message filtered by reply policy")
            return jsonify({
                "status": "success",
                "message": "group message filtered by reply policy",
            }), 200

    # 查找或创建用户
    users = user_dao.find_users({"platforms.wechat.id": data["data"]["fromUser"]})
    if len(users) == 0:
        logger.info("user not exist, create a new one")
        target_user_alias = characters[0]["name"]
        resp_json = Ecloud_API.getContact(data["data"]["fromUser"], target_user_alias)
        logger.info(resp_json)
        user_wechat_info = resp_json["data"][0]

        uid = user_dao.create_user({
            "is_character": False,
            "name": user_wechat_info["userName"],
            "platforms": {
                "wechat": {
                    "id": data["data"]["fromUser"],
                    "account": user_wechat_info["userName"],
                    "nickname": user_wechat_info["nickName"],
                },
            },
            "status": "normal",
            "user_info": {},
            "user_wechat_info": user_wechat_info,
        })
    else:
        uid = str(users[0]["_id"])

    # 标准化数据
    std = ecloud_message_to_std(data)
    std["from_user"] = uid
    std["to_user"] = cid

    # 插入到数据库
    mongo.insert_one("inputmessages", std)

    return jsonify({"status": "success", "message": "message handing..."}), 200
```

**Step 2: Commit**

```bash
git add connector/ecloud/ecloud_input.py
git commit -m "feat(ecloud): handle group messages in input handler"
```

---

## Task 9: 添加 @用户功能到发送

**Files:**
- Modify: `connector/ecloud/ecloud_output.py`

**Step 1: 修改发送逻辑支持 @用户**

在 `output_handler` 函数中，修改群聊发送部分：

```python
# 实际发送
ecloud = std_to_ecloud_message(message)
ecloud["wId"] = wid

if message["chatroom_name"] is None:
    ecloud["wcId"] = user["platforms"]["wechat"]["account"]
else:
    ecloud["wcId"] = message["chatroom_name"]
    # 群聊回复时，添加 @原发送者
    original_sender_wxid = message.get("metadata", {}).get("original_sender_wxid")
    if original_sender_wxid:
        ecloud["at"] = original_sender_wxid
```

**Step 2: Commit**

```bash
git add connector/ecloud/ecloud_output.py
git commit -m "feat(ecloud): add @mention support in group reply"
```

---

## Task 10: 运行完整测试并验证

**Step 1: 运行单元测试**

Run: `pytest tests/unit/connector/test_ecloud_adapter.py -v`
Expected: PASS

**Step 2: 运行快速测试套件**

Run: `pytest -m "not integration" --tb=short`
Expected: PASS

**Step 3: 代码格式化**

Run: `black connector/ecloud/ tests/unit/connector/test_ecloud_adapter.py && isort connector/ecloud/ tests/unit/connector/test_ecloud_adapter.py`

**Step 4: Commit 格式化**

```bash
git add -A
git commit -m "style: format ecloud connector code"
```

---

## Task 11: 更新文档

**Files:**
- Modify: `doc/architecture/detailed_architecture_analysis.md` (如需要)

**Step 1: 在 CLAUDE.md 中记录群聊功能**

如有需要，在 CLAUDE.md 中添加群聊相关说明。

**Step 2: Final commit**

```bash
git add -A
git commit -m "docs: update documentation for group chat feature"
```

---

## 实现顺序总结

```
Task 1:  配置文件添加 group_chat 配置
Task 2:  创建 adapter 单元测试（TDD）
Task 3:  实现 is_group_message 函数
Task 4:  修改 ecloud_message_to_std 支持群消息
Task 5:  添加回复判断逻辑测试
Task 6:  实现 should_respond_to_group_message
Task 7:  修改 ecloud_input.py 支持群消息类型
Task 8:  修改 handle_message 处理群消息
Task 9:  添加 @用户功能到发送
Task 10: 运行完整测试验证
Task 11: 更新文档
```

## 注意事项

1. **@检测**: 当前实现基于昵称匹配，实际 E云可能有特殊格式，需实测调整
2. **群成员信息**: 首次遇到的群成员会通过 `getContact` 创建，可能需要缓存优化
3. **消息去重**: E云可能重复投递消息，后续可用 `newMsgId` 去重
