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
