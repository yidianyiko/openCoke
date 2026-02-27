# -*- coding: utf-8 -*-
"""
Unit tests for Gateway Config
"""

import pytest

from connector.gateway.config import GatewayConfig


class TestGatewayConfig:
    """Test GatewayConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GatewayConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8765
        assert config.heartbeat_interval == 30.0
        assert config.reconnect_delay == 5.0
        assert config.max_retries == 3
        assert config.enabled is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = GatewayConfig(
            host="127.0.0.1",
            port=9000,
            heartbeat_interval=60.0,
            reconnect_delay=10.0,
            max_retries=5,
            enabled=False,
        )
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.heartbeat_interval == 60.0
        assert config.reconnect_delay == 10.0
        assert config.max_retries == 5
        assert config.enabled is False

    def test_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "host": "192.168.1.1",
            "port": 8080,
            "heartbeat_interval": 45.0,
            "reconnect_delay": 3.0,
            "max_retries": 2,
            "enabled": False,
        }
        config = GatewayConfig.from_dict(config_dict)

        assert config.host == "192.168.1.1"
        assert config.port == 8080
        assert config.heartbeat_interval == 45.0
        assert config.reconnect_delay == 3.0
        assert config.max_retries == 2
        assert config.enabled is False

    def test_from_dict_partial(self):
        """Test creating config from partial dictionary."""
        config_dict = {"port": 9999, "enabled": False}
        config = GatewayConfig.from_dict(config_dict)

        # Partial values should use defaults
        assert config.host == "0.0.0.0"
        assert config.port == 9999
        assert config.heartbeat_interval == 30.0
        assert config.enabled is False

    def test_from_dict_empty(self):
        """Test creating config from empty dictionary."""
        config = GatewayConfig.from_dict({})
        # Should use all defaults
        assert config.host == "0.0.0.0"
        assert config.port == 8765
        assert config.heartbeat_interval == 30.0
        assert config.reconnect_delay == 5.0
        assert config.max_retries == 3
        assert config.enabled is True

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = GatewayConfig(host="10.0.0.1", port=7000, heartbeat_interval=90.0)
        config_dict = config.to_dict()

        assert config_dict["host"] == "10.0.0.1"
        assert config_dict["port"] == 7000
        assert config_dict["heartbeat_interval"] == 90.0
        assert config_dict["reconnect_delay"] == 5.0
        assert config_dict["max_retries"] == 3
        assert config_dict["enabled"] is True

    def test_roundtrip_dict(self):
        """Test roundtrip conversion from dict to config and back."""
        original_dict = {
            "host": "172.16.0.1",
            "port": 7777,
            "heartbeat_interval": 120.0,
            "reconnect_delay": 15.0,
            "max_retries": 10,
            "enabled": True,
        }
        config = GatewayConfig.from_dict(original_dict)
        result_dict = config.to_dict()

        assert result_dict == original_dict
