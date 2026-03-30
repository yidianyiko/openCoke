import pytest

from api.config import AccountNotFoundError, ChannelNotFoundError, GatewayConfig


def test_gateway_config_resolves_account_and_channel():
    app_config = {
        "gateway": {
            "enabled": True,
            "openclaw_url": "https://gateway.example.com",
            "openclaw_token": "token-123",
            "shared_secret": "secret-123",
            "group_chat": {
                "enabled": True,
                "context_message_count": 20,
                "whitelist_groups": [],
                "reply_mode": {"whitelist": "all", "others": "mention_only"},
            },
            "account_mapping": {
                "acct-1": {
                    "character": "coke",
                    "channels": {
                        "wechat": {
                            "character_platform_id": "coke-wechat",
                        }
                    },
                }
            },
        }
    }

    config = GatewayConfig.from_app_config(app_config)
    resolved = config.resolve_account("acct-1", "wechat")

    assert resolved.character == "coke"
    assert resolved.character_platform_id == "coke-wechat"
    assert resolved.account_id == "acct-1"
    assert resolved.channel == "wechat"


def test_gateway_config_raises_for_unknown_account():
    config = GatewayConfig.from_app_config(
        {
            "gateway": {
                "enabled": True,
                "openclaw_url": "https://gateway.example.com",
                "openclaw_token": "token-123",
                "shared_secret": "secret-123",
                "group_chat": {
                    "enabled": True,
                    "context_message_count": 20,
                    "whitelist_groups": [],
                    "reply_mode": {"whitelist": "all", "others": "mention_only"},
                },
                "account_mapping": {},
            }
        }
    )

    with pytest.raises(AccountNotFoundError):
        config.resolve_account("missing-account", "wechat")


def test_gateway_config_raises_for_unknown_channel():
    config = GatewayConfig.from_app_config(
        {
            "gateway": {
                "enabled": True,
                "openclaw_url": "https://gateway.example.com",
                "openclaw_token": "token-123",
                "shared_secret": "secret-123",
                "group_chat": {
                    "enabled": True,
                    "context_message_count": 20,
                    "whitelist_groups": [],
                    "reply_mode": {"whitelist": "all", "others": "mention_only"},
                },
                "account_mapping": {
                    "acct-1": {
                        "character": "coke",
                        "channels": {
                            "wechat": {
                                "character_platform_id": "coke-wechat",
                            }
                        },
                    }
                },
            }
        }
    )

    with pytest.raises(ChannelNotFoundError):
        config.resolve_account("acct-1", "telegram")


def test_gateway_config_parses_string_booleans_and_validates_mapping():
    config = GatewayConfig.from_app_config(
        {
            "gateway": {
                "enabled": "false",
                "openclaw_url": "https://gateway.example.com",
                "openclaw_token": "token-123",
                "shared_secret": "secret-123",
                "group_chat": {
                    "enabled": "yes",
                    "context_message_count": 20,
                    "whitelist_groups": [],
                    "reply_mode": {"whitelist": "all", "others": "mention_only"},
                },
                "account_mapping": {
                    "acct-1": {
                        "character": "coke",
                        "channels": {
                            "wechat": {
                                "character_platform_id": "coke-wechat",
                            }
                        },
                    }
                },
            }
        }
    )

    assert config.enabled is False
    assert config.group_chat["enabled"] is True


def test_gateway_config_rejects_malformed_account_mapping():
    with pytest.raises(ValueError):
        GatewayConfig.from_app_config(
            {
                "gateway": {
                    "enabled": True,
                    "openclaw_url": "https://gateway.example.com",
                    "openclaw_token": "token-123",
                    "shared_secret": "secret-123",
                    "group_chat": {
                        "enabled": True,
                        "context_message_count": 20,
                        "whitelist_groups": [],
                        "reply_mode": {"whitelist": "all", "others": "mention_only"},
                    },
                    "account_mapping": {
                        "acct-1": {
                            "character": "coke",
                            "channels": {
                                "wechat": {}
                            },
                        }
                    },
                }
            }
        )
